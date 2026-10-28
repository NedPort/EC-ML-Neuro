"""
Second-pass diagnostic discovery for Group 6 in PDF-only EDR reports.

Why this exists
---------------
The first PDF-only Group 6 discovery processed all 181 PDF-only reports but
returned zero candidates. Because Group 6 fields are common in CSV-backed
reports, this second pass checks whether PDF text layout prevented the first
line-based "label : value" parser from seeing them.

This script does NOT promote anything directly into Group 6.
It produces evidence for audit.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Output
------
data/processed/edr/group6_pdf_diagnostic_v1/

    keyword_hits.csv
    nearby_line_candidates.csv
    report_summary.csv
    keyword_summary.csv
    errors.csv
    metadata.json

Method
------
- PDF-only reports only
- original PDFs only
- no OCR
- scans every extracted text line for Group 6 keywords
- preserves neighboring lines so split label/value layouts can be inspected
- no semantic normalization
- no unit conversion
- no fuzzy event linking
- no source mutation
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
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
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").strip(),
    )


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


KEYWORD_RULES = [
    ("ignition_cycle_readout", [
        r"\bignition cycles?\b",
        r"\bpower[- ]on cycles?\b",
        r"\bcycles? at investigation\b",
        r"\bcycles? at reading\b",
    ]),
    ("part_serial_identifier", [
        r"\bpart number\b",
        r"\bserial number\b",
        r"\bhardware number\b",
    ]),
    ("software_calibration_version", [
        r"\bsoftware\b",
        r"\bcalibration\b",
        r"\bfirmware\b",
        r"\bapplication version\b",
        r"\bhardware version\b",
        r"\bsoftware strategy\b",
    ]),
    ("module_supplier", [
        r"\bsupplier\b",
    ]),
    ("vehicle_identifier_technical", [
        r"\bcurrent vin\b",
        r"\bvehicle identification number\b",
        r"\bvin\b",
    ]),
    ("configuration", [
        r"\bconfigured for\b",
        r"\bconfiguration\b",
    ]),
    ("module_key_definition", [
        r"\bprimary key definition\b",
        r"\bprimary key\b",
    ]),
    ("odometer_mileage", [
        r"\bodometer\b",
        r"\bvehicle mileage\b",
        r"\bmileage\b",
    ]),
    ("operating_time", [
        r"\boperating time\b",
        r"\blifetime operating timer\b",
        r"\bengine operating time\b",
        r"\bmodule operating time\b",
    ]),
    ("readout_voltage", [
        r"\bvoltage at time of retrieval\b",
        r"\bsupply voltage at time of retrieval\b",
        r"\bvoltage at retrieval\b",
    ]),
    ("readout_tool_status", [
        r"\badapter detected\b",
        r"\bdownload tool\b",
        r"\breadout tool\b",
    ]),
    ("module_identifier", [
        r"\bmodule id\b",
        r"\bmodule identifier\b",
        r"\bacm id\b",
        r"\bsdm id\b",
        r"\bpcm id\b",
        r"\becm id\b",
        r"\bmanufacturer id\b",
    ]),
    ("production_manufacture_date", [
        r"\bproduction date\b",
        r"\bmanufacture date\b",
        r"\bmanufacturing date\b",
        r"\bdate of manufacture\b",
    ]),
]


def match_families(line: str):
    hits = []
    for family, patterns in KEYWORD_RULES:
        if any(re.search(pattern, line, re.I) for pattern in patterns):
            hits.append(family)
    return hits


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
        default=Path("data/processed/edr/group6_pdf_diagnostic_v1"),
    )

    parser.add_argument(
        "--neighbor-radius",
        type=int,
        default=2,
    )

    args = parser.parse_args()

    index = read_csv(args.report_index)
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)

    keyword_hits = []
    nearby_candidates = []
    report_summary = []
    errors = []

    family_counts = Counter()
    reports_with_hits = set()

    selected = 0
    processed = 0

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

        report_hit_count = 0
        report_families = Counter()

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    lines = [norm(x) for x in text.splitlines()]

                    for idx, line in enumerate(lines):
                        if not line:
                            continue

                        families = match_families(line)
                        if not families:
                            continue

                        report_hit_count += 1
                        reports_with_hits.add(row.get("report_id", ""))

                        for family in families:
                            family_counts[family] += 1
                            report_families[family] += 1

                        before = [
                            lines[j]
                            for j in range(
                                max(0, idx - args.neighbor_radius),
                                idx,
                            )
                            if lines[j]
                        ]

                        after = [
                            lines[j]
                            for j in range(
                                idx + 1,
                                min(
                                    len(lines),
                                    idx + 1 + args.neighbor_radius,
                                ),
                            )
                            if lines[j]
                        ]

                        keyword_hits.append({
                            **{k: row.get(k, "") for k in BASE},
                            "source_format": "pdf",
                            "source_path": str(pdf_path),
                            "pdf_page": page_no,
                            "pdf_line_number": idx + 1,
                            "matched_families": ";".join(families),
                            "source_line_raw": line,
                            "previous_lines_json": json.dumps(
                                before,
                                ensure_ascii=False,
                            ),
                            "next_lines_json": json.dumps(
                                after,
                                ensure_ascii=False,
                            ),
                        })

                        # Evidence row for manual/audit reconstruction.
                        nearby_candidates.append({
                            **{k: row.get(k, "") for k in BASE},
                            "source_format": "pdf",
                            "source_path": str(pdf_path),
                            "pdf_page": page_no,
                            "pdf_line_number": idx + 1,
                            "matched_families": ";".join(families),
                            "previous_line_2":
                                before[-2] if len(before) >= 2 else "",
                            "previous_line_1":
                                before[-1] if len(before) >= 1 else "",
                            "matched_line": line,
                            "next_line_1":
                                after[0] if len(after) >= 1 else "",
                            "next_line_2":
                                after[1] if len(after) >= 2 else "",
                        })

            processed += 1

        except Exception as exc:
            errors.append({
                **{k: row.get(k, "") for k in BASE},
                "error_type": type(exc).__name__,
                "pdf_path": str(pdf_path),
                "error": str(exc),
            })
            continue

        report_summary.append({
            **{k: row.get(k, "") for k in BASE},
            "pdf_path": str(pdf_path),
            "keyword_hit_count": report_hit_count,
            "matched_family_counts_json": json.dumps(
                dict(report_families),
                ensure_ascii=False,
            ),
        })

        if processed % 25 == 0 or processed == selected:
            print(
                f"Diagnosed Group 6 PDF {processed}/{selected} reports...",
                flush=True,
            )

    write_csv(
        out / "keyword_hits.csv",
        keyword_hits,
        [
            *BASE,
            "source_format",
            "source_path",
            "pdf_page",
            "pdf_line_number",
            "matched_families",
            "source_line_raw",
            "previous_lines_json",
            "next_lines_json",
        ],
    )

    write_csv(
        out / "nearby_line_candidates.csv",
        nearby_candidates,
        [
            *BASE,
            "source_format",
            "source_path",
            "pdf_page",
            "pdf_line_number",
            "matched_families",
            "previous_line_2",
            "previous_line_1",
            "matched_line",
            "next_line_1",
            "next_line_2",
        ],
    )

    write_csv(
        out / "report_summary.csv",
        report_summary,
        [
            *BASE,
            "pdf_path",
            "keyword_hit_count",
            "matched_family_counts_json",
        ],
    )

    write_csv(
        out / "keyword_summary.csv",
        [
            {
                "family": family,
                "keyword_hit_count": count,
            }
            for family, count in family_counts.most_common()
        ],
        [
            "family",
            "keyword_hit_count",
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

    reports_zero_hits = sum(
        1 for row in report_summary
        if int(row["keyword_hit_count"]) == 0
    )

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "group": "Group 6 - Other structured technical and investigation information",
        "stage": "PDF-only second-pass diagnostic",
        "reports_in_index": len(index),
        "pdf_only_reports_selected": selected,
        "pdf_only_reports_processed": processed,
        "reports_with_group6_keyword_hits": len(reports_with_hits),
        "reports_with_zero_keyword_hits": reports_zero_hits,
        "keyword_hit_count": len(keyword_hits),
        "family_keyword_hit_counts": dict(family_counts),
        "source_errors": len(errors),
        "ocr_used": False,
        "scope": (
            "Second-pass diagnostic scan of all PDF-only reports after the "
            "first structured-line discovery returned zero Group 6 candidates. "
            "Every extracted PDF text line is scanned for Group 6 terminology "
            "and neighboring lines are preserved to diagnose split or collapsed "
            "PDF layout. This stage does not itself accept fields into Group 6. "
            "No OCR, semantic normalization, unit conversion, fuzzy inference, "
            "or source mutation is performed."
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
    print("GROUP 6 PDF DIAGNOSTIC COMPLETE.")


if __name__ == "__main__":
    main()
