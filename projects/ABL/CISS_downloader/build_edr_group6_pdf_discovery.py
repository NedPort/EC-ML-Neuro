"""
Discover Group 6 candidates in PDF-only EDR reports.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Population
----------
Only reports without a CSV source and with an original PDF source.

Output
------
data/processed/edr/group6_pdf_discovery_v1/

    group6_candidate_fields.csv
    group6_review_fields.csv
    group6_excluded_overlap_fields.csv
    group6_report_coverage.csv
    group6_label_summary.csv
    group6_family_summary.csv
    errors.csv
    metadata.json

Rules
-----
- Original PDF is authoritative for PDF-only reports.
- No OCR.
- Preserve page, line number, full source line, raw label/value,
  section context, and provenance.
- Conservative line parsing only.
- No semantic normalization, unit conversion, fuzzy inference,
  or source mutation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

import pdfplumber

csv.field_size_limit(100_000_000)

BASE = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def norm(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "").strip())


def norm_key(v):
    return norm(re.sub(r"[^a-z0-9]+", " ", norm(v).casefold()))


def stable_id(*parts):
    text = "|".join(norm(x) for x in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def resolve_pdf_path(row: dict, source_root: Path):
    raw = norm(row.get("pdf_path", ""))

    if raw:
        p = Path(raw)
        if p.exists():
            return p

        basename = PureWindowsPath(raw).name
        case_id = norm(row.get("case_id", ""))

        if case_id and basename:
            case_root = source_root / case_id
            if case_root.exists():
                matches = list(case_root.rglob(basename))
                if matches:
                    return matches[0]

    basename = norm(row.get("export_basename", ""))
    case_id = norm(row.get("case_id", ""))

    if basename and case_id:
        case_root = source_root / case_id
        if case_root.exists():
            matches = list(case_root.rglob(basename + ".pdf"))
            if not matches:
                matches = list(case_root.rglob(basename + ".PDF"))
            if matches:
                return matches[0]

    return None


def split_label_value(line: str):
    text = norm(line)
    if not text or len(text) > 500:
        return None

    # Prefer colon-delimited scalar lines.
    m = re.match(r"^(.{2,220}?):\s*(.+)$", text)
    if m:
        return norm(m.group(1)), norm(m.group(2))

    # Conservative multi-space split.
    parts = re.split(r"\s{2,}", text, maxsplit=1)
    if len(parts) == 2:
        label, value = norm(parts[0]), norm(parts[1])
        if label and value:
            return label, value

    return None


FAMILY_RULES = [
    ("ignition_cycle_readout", [
        r"\bignition cycles?\b.*\b(?:investigation|readout|reading|download)\b",
        r"\bpower[- ]on cycles?\b.*\b(?:reading|readout|download)\b",
        r"\bcycles? at investigation\b",
        r"\bcycles? at reading\b",
    ]),
    ("part_serial_identifier", [
        r"\bpart number\b",
        r"\bserial number\b",
        r"\bhardware number\b",
    ]),
    ("software_calibration_version", [
        r"\bsoftware\b.*\b(?:version|number|id|strategy)\b",
        r"\bcalibration\b.*\b(?:version|number|id|level|file)\b",
        r"\bfirmware\b",
        r"\bapplication version\b",
        r"\bhardware version\b",
    ]),
    ("module_supplier", [
        r"\b(?:acm|airbag control module|module)\s+supplier\b",
    ]),
    ("vehicle_identifier_technical", [
        r"\bcurrent vin\b",
        r"\bvehicle identification number\b",
    ]),
    ("configuration", [
        r"\bconfigured for\b",
        r"\bconfiguration\b",
    ]),
    ("module_key_definition", [
        r"\bprimary key definition\b",
    ]),
    ("odometer_mileage", [
        r"\bodometer\b",
        r"\bvehicle mileage\b",
        r"\bmileage at\b",
    ]),
    ("operating_time", [
        r"\boperating time\b",
        r"\blifetime operating timer\b",
        r"\bengine operating time\b",
        r"\bmodule operating time\b",
    ]),
    ("readout_voltage", [
        r"\bsupply voltage at time of retrieval\b",
        r"\bvoltage at retrieval\b",
    ]),
    ("readout_tool_status", [
        r"\badapter detected during download\b",
        r"\bdownload tool\b",
        r"\breadout tool\b",
    ]),
    ("module_identifier", [
        r"\b(?:module|acm|sdm|pcm|ecm)\b.*\b(?:id|identifier)\b",
        r"\bsupplier id\b",
        r"\bmanufacturer id\b",
    ]),
    ("production_manufacture_date", [
        r"\bproduction date\b",
        r"\bmanufacture date\b",
        r"\bmanufacturing date\b",
        r"\bdate of manufacture\b",
    ]),
]


GROUP3_EXCLUSIONS = [
    r"\bonstar sdm recorded vehicle velocity change data sent\b",
    r"\b(?:acm|system|supply)\b.*\bvoltage at event\b",
    r"\bair ?bag\b.*\b(?:deployment|deployed|status)\b",
    r"\bpretensioner\b",
    r"\boccupant\b",
    r"\bwarning lamp\b",
    r"\bevent severity\b",
]

GROUP2_EXCLUSIONS = [
    r"\bevent recording complete\b",
    r"\brecording status\b",
    r"\bcrash record locked\b",
    r"\bevent counter\b",
    r"\bretrieval status\b",
]

GROUP5_EXCLUSIONS = [
    r"\bdelta[- ]?v\b",
    r"\bmaximum acceleration\b",
    r"\bpdof\b",
    r"\broll angle peak\b",
]

GROUP1_EXCLUSIONS = [
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
    r"\bcase number entered\b",
    r"\buser entered vin\b",
    r"\bsaved on\b",
]


def classify(label: str, section: str):
    text = norm(label)

    for pattern in GROUP1_EXCLUSIONS:
        if re.search(pattern, text, re.I):
            return "excluded_overlap", "", "group1"

    for pattern in GROUP2_EXCLUSIONS:
        if re.search(pattern, text, re.I):
            return "excluded_overlap", "", "group2"

    for pattern in GROUP3_EXCLUSIONS:
        if re.search(pattern, text, re.I):
            return "excluded_overlap", "", "group3"

    for pattern in GROUP5_EXCLUSIONS:
        if re.search(pattern, text, re.I):
            return "excluded_overlap", "", "group5"

    for family, patterns in FAMILY_RULES:
        if any(re.search(p, text, re.I) for p in patterns):
            return "candidate", family, ""

    # Technical/module section can justify review, but not automatic acceptance.
    if re.search(
        r"\b(?:module|technical|configuration|identification|"
        r"investigation|readout|vehicle information|system information)\b",
        section,
        re.I,
    ):
        if re.search(
            r"\b(?:module|part|serial|software|calibration|supplier|"
            r"configuration|vin|odometer|mileage|operating|"
            r"production|manufacture|voltage|adapter|download|readout)\b",
            text,
            re.I,
        ):
            return "review", "other_structured_technical", ""

    return "ignore", "", ""


def looks_section(line: str):
    text = norm(line)
    if not text or len(text) > 180:
        return False
    if ":" in text:
        return False

    alpha = [c for c in text if c.isalpha()]
    upper_ratio = (
        sum(c.isupper() for c in alpha) / len(alpha)
        if alpha else 0.0
    )

    return (
        upper_ratio >= 0.70
        or bool(re.search(
            r"\b(?:module information|vehicle information|"
            r"technical information|configuration|identification|"
            r"investigation|readout information|system information)\b",
            text,
            re.I,
        ))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-index",
        type=Path,
        default=Path("data/processed/edr/group1_v4/report_index.csv"),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("data/temp"),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("data/processed/edr/group6_pdf_discovery_v1"),
    )
    args = parser.parse_args()

    index = read_csv(args.report_index)
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)

    candidates = []
    reviews = []
    excluded = []
    coverage = []
    errors = []

    family_counts = Counter()
    label_counts = Counter()
    raw_examples = defaultdict(Counter)

    selected = 0
    processed = 0

    reports_with_candidates = set()
    reports_with_review = set()

    for row in index:
        has_csv = bool(norm(row.get("csv_path", "")))
        has_pdf = bool(norm(row.get("pdf_path", "")))

        if has_csv or not has_pdf:
            continue

        selected += 1
        pdf_path = resolve_pdf_path(row, args.source_root)

        if pdf_path is None or not pdf_path.exists():
            errors.append({
                **{k: row.get(k, "") for k in BASE},
                "error_type": "pdf_source_not_found",
                "pdf_path": norm(row.get("pdf_path", "")),
                "error": "Could not resolve PDF path.",
            })
            continue

        c_count = 0
        r_count = 0
        e_count = 0

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    section = ""

                    for line_no, line in enumerate(text.splitlines(), start=1):
                        source_line = norm(line)
                        if not source_line:
                            continue

                        if looks_section(source_line):
                            section = source_line
                            continue

                        parsed = split_label_value(source_line)
                        if parsed is None:
                            continue

                        label, value = parsed
                        decision, family, route = classify(label, section)

                        if decision == "ignore":
                            continue

                        candidate_id = (
                            "g6pdf_"
                            + stable_id(
                                row.get("report_id", ""),
                                page_no,
                                line_no,
                                label,
                                value,
                            )
                        )

                        obs = {
                            **{k: row.get(k, "") for k in BASE},
                            "group6_candidate_id": candidate_id,
                            "source_format": "pdf",
                            "source_path": str(pdf_path),
                            "pdf_page": page_no,
                            "pdf_line_number": line_no,
                            "source_section_heading": section,
                            "source_line_raw": source_line,
                            "field_label_raw": label,
                            "field_value_raw": value,
                            "candidate_family": family,
                            "discovery_decision": decision,
                            "overlap_route": route,
                            "semantic_normalization_status": "not_normalized",
                            "unit_conversion_status": "not_converted",
                        }

                        if decision == "candidate":
                            candidates.append(obs)
                            c_count += 1
                            reports_with_candidates.add(row.get("report_id", ""))
                            family_counts[family] += 1
                            key = norm_key(label)
                            label_counts[key] += 1
                            raw_examples[key][label] += 1

                        elif decision == "review":
                            reviews.append(obs)
                            r_count += 1
                            reports_with_review.add(row.get("report_id", ""))

                        elif decision == "excluded_overlap":
                            excluded.append(obs)
                            e_count += 1

            processed += 1

        except Exception as exc:
            errors.append({
                **{k: row.get(k, "") for k in BASE},
                "error_type": type(exc).__name__,
                "pdf_path": str(pdf_path),
                "error": str(exc),
            })
            continue

        coverage.append({
            **{k: row.get(k, "") for k in BASE},
            "pdf_path": str(pdf_path),
            "processing_status": (
                "group6_candidates_found"
                if c_count
                else (
                    "review_only"
                    if r_count
                    else "no_group6_candidates"
                )
            ),
            "candidate_count": c_count,
            "review_count": r_count,
            "excluded_overlap_count": e_count,
        })

        if processed % 25 == 0 or processed == selected:
            print(
                f"Discovered Group 6 PDF {processed}/{selected} reports...",
                flush=True,
            )

    cols = [
        *BASE,
        "group6_candidate_id",
        "source_format",
        "source_path",
        "pdf_page",
        "pdf_line_number",
        "source_section_heading",
        "source_line_raw",
        "field_label_raw",
        "field_value_raw",
        "candidate_family",
        "discovery_decision",
        "overlap_route",
        "semantic_normalization_status",
        "unit_conversion_status",
    ]

    write_csv(out / "group6_candidate_fields.csv", candidates, cols)
    write_csv(out / "group6_review_fields.csv", reviews, cols)
    write_csv(out / "group6_excluded_overlap_fields.csv", excluded, cols)

    write_csv(
        out / "group6_report_coverage.csv",
        coverage,
        [
            *BASE,
            "pdf_path",
            "processing_status",
            "candidate_count",
            "review_count",
            "excluded_overlap_count",
        ],
    )

    label_summary = [
        {
            "normalized_label": key,
            "candidate_count": count,
            "raw_label_examples_json": json.dumps(
                [x for x, _ in raw_examples[key].most_common(5)],
                ensure_ascii=False,
            ),
        }
        for key, count in label_counts.most_common()
    ]

    write_csv(
        out / "group6_label_summary.csv",
        label_summary,
        [
            "normalized_label",
            "candidate_count",
            "raw_label_examples_json",
        ],
    )

    write_csv(
        out / "group6_family_summary.csv",
        [
            {
                "candidate_family": family,
                "candidate_count": count,
            }
            for family, count in family_counts.most_common()
        ],
        [
            "candidate_family",
            "candidate_count",
        ],
    )

    write_csv(
        out / "errors.csv",
        errors,
        [
            *BASE,
            "error_type",
            "pdf_path",
            "error",
        ],
    )

    coverage_counts = Counter(
        x["processing_status"] for x in coverage
    )

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "group": "Group 6 - Other structured technical and investigation information",
        "stage": "PDF-only discovery",
        "reports_in_index": len(index),
        "pdf_only_reports_selected": selected,
        "pdf_only_reports_processed": processed,
        "reports_with_group6_candidates": len(reports_with_candidates),
        "reports_with_review_fields": len(reports_with_review),
        "candidate_field_count": len(candidates),
        "review_field_count": len(reviews),
        "excluded_overlap_field_count": len(excluded),
        "candidate_family_counts": dict(family_counts),
        "unique_candidate_labels": len(label_counts),
        "coverage_status_counts": dict(coverage_counts),
        "source_errors": len(errors),
        "ocr_used": False,
        "scope": (
            "PDF-only discovery for Group 6 technical, module, configuration, "
            "investigation, and readout information. Only reports without CSV "
            "sources are processed. Original PDFs are authoritative. Page, line, "
            "source line, raw label/value, section context, and provenance are "
            "preserved. No OCR, semantic normalization, unit conversion, fuzzy "
            "inference, or source mutation is performed."
        ),
    }

    (out / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print()
    print(f"Outputs: {out}")
    print()
    print("GROUP 6 PDF DISCOVERY COMPLETE.")


if __name__ == "__main__":
    main()
