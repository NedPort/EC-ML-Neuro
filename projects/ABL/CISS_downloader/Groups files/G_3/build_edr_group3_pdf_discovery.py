"""
Discover Group 3 fields from PDF-only EDR reports.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Authoritative source
--------------------
Original PDF reports for reports without an available CSV export.

Output
------
data/processed/edr/group3_pdf_discovery_v1/

    group3_pdf_candidates.csv
    group3_pdf_review.csv
    group3_pdf_excluded_overlap.csv
    group3_pdf_report_coverage.csv
    group3_pdf_label_summary.csv
    group3_pdf_family_summary.csv
    errors.csv
    metadata.json

Purpose
-------
Discover Group 3 event-condition, deployment, restraint, occupant,
warning/status, power, high-voltage, algorithm, validity, and similar
event-state fields from PDF-only reports.

Important boundaries
--------------------
Group 2:
    record/event structure, recording completeness, counters, locking,
    retrieval status, multiple-event bookkeeping.

Group 4:
    repeated time-series measurements.

Group 5:
    scalar crash/event measurements such as maximum/final Delta-V,
    time of maximum Delta-V, peak acceleration, roll summaries,
    clipping/range timing, etc.

Group 6:
    technical/module/configuration/investigation metadata such as
    software versions, supplier IDs, production dates, part/serial
    numbers, ignition cycles at investigation, odometer, etc.

No OCR is performed.
No semantic normalization, unit conversion, fuzzy event linking,
or source mutation is performed.
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


# ============================================================
# I/O
# ============================================================

def read_csv(path: Path):
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")

    with tmp.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


# ============================================================
# Helpers
# ============================================================

def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").replace("\x00", " ").strip(),
    )


def norm_key(value):
    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            norm(value).casefold(),
        )
    )


def stable_id(*parts):
    text = "|".join(norm(part) for part in parts)
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:24]


def matches_any(text, patterns):
    return any(
        re.search(pattern, norm(text), re.I)
        for pattern in patterns
    )


def looks_numeric(value):
    text = norm(value).replace(",", "")

    return bool(
        re.fullmatch(
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?"
            r"(?:\s*(?:ms|msec|sec|s|V|volts?|cycles?|%|mph|km/h|kph))?",
            text,
            flags=re.I,
        )
    )


def looks_status_value(value):
    text = norm(value).casefold()

    return text in {
        "yes",
        "no",
        "on",
        "off",
        "active",
        "inactive",
        "enabled",
        "disabled",
        "deployed",
        "not deployed",
        "deployment",
        "non-deployment",
        "buckled",
        "unbuckled",
        "present",
        "not present",
        "forward",
        "rearward",
        "valid",
        "invalid",
        "data valid",
        "data invalid",
        "sna",
        "n/a",
        "na",
        "unknown",
    }


# ============================================================
# PDF path resolution
# ============================================================

def resolve_pdf_path(index_row: dict, source_root: Path):
    raw = norm(index_row.get("pdf_path", ""))

    if raw:
        direct = Path(raw)

        if direct.exists():
            return direct

        basename = PureWindowsPath(raw).name
        case_id = norm(index_row.get("case_id", ""))

        if case_id and basename:
            case_root = source_root / case_id

            if case_root.exists():
                matches = list(case_root.rglob(basename))

                if matches:
                    preferred = [
                        p for p in matches
                        if "pdf" in p.suffix.casefold()
                    ]

                    return preferred[0] if preferred else matches[0]

    basename = norm(index_row.get("export_basename", ""))
    case_id = norm(index_row.get("case_id", ""))

    if basename and case_id:
        case_root = source_root / case_id

        if case_root.exists():
            matches = list(case_root.rglob(basename + ".PDF"))

            if not matches:
                matches = list(case_root.rglob(basename + ".pdf"))

            if matches:
                return matches[0]

    return None


# ============================================================
# Candidate parsing
# ============================================================

SEPARATOR_PATTERNS = [
    r"^(?P<label>.+?)\s*[:=]\s*(?P<value>.+?)$",
    r"^(?P<label>.+?)\s{2,}(?P<value>\S.+?)$",
]

UNIT_OR_VALUE_RE = re.compile(
    r"""
    (?:
        [-+]?\d+(?:\.\d+)?
        (?:\s*(?:ms|msec|sec|s|V|volts?|cycles?|%|mph|km/h|kph))?
        |
        Yes|No|ON|OFF|Active|Inactive|Enabled|Disabled|
        Deployed|Not\ Deployed|Deployment|Non-Deployment|
        Buckled|Unbuckled|Present|Not\ Present|
        Forward|Rearward|Valid|Invalid|SNA|N/A|NA|Unknown
    )
    """,
    re.I | re.X,
)


def split_pdf_line(line):
    text = norm(line)

    if not text:
        return None

    for pattern in SEPARATOR_PATTERNS:
        match = re.match(pattern, text, flags=re.I)

        if match:
            label = norm(match.group("label"))
            value = norm(match.group("value"))

            if label and value and len(label) <= 260:
                return label, value, "separator"

    # Conservative fallback:
    # split at final recognizable scalar/status token only.
    matches = list(UNIT_OR_VALUE_RE.finditer(text))

    if not matches:
        return None

    final = matches[-1]

    if final.end() != len(text):
        return None

    label = norm(text[:final.start()])
    value = norm(final.group(0))

    if not label or not value:
        return None

    if len(label) > 260:
        return None

    return label, value, "terminal_value"


# ============================================================
# Event hints / section context
# ============================================================

EVENT_PATTERNS = [
    r"\bevent record\s*#?\s*\d+\b",
    r"\bevent\s*#\s*\d+\b",
    r"\bdeployment event\s*#?\s*\d*\b",
    r"\bnon[- ]deployment event\b",
    r"\bmost recent event\b",
    r"\b\d+(?:st|nd|rd|th)\s+prior event\b",
]


def extract_event_hint(*texts):
    combined = " | ".join(
        norm(x)
        for x in texts
        if norm(x)
    )

    hints = []

    for pattern in EVENT_PATTERNS:
        for match in re.findall(pattern, combined, flags=re.I):
            cleaned = norm(match)

            if cleaned.casefold() not in {
                x.casefold()
                for x in hints
            }:
                hints.append(cleaned)

    return " | ".join(hints)


def looks_heading(line):
    text = norm(line)

    if not text:
        return False

    if len(text) > 180:
        return False

    if ":" in text or "=" in text:
        return False

    if looks_numeric(text):
        return False

    alpha = [c for c in text if c.isalpha()]

    if not alpha:
        return False

    upper_ratio = sum(c.isupper() for c in alpha) / len(alpha)

    return (
        upper_ratio >= 0.70
        or bool(
            re.search(
                r"\b(?:"
                r"system status|deployment|non[- ]deployment|"
                r"restraint|occupant|air ?bag|pretensioner|"
                r"warning|event data|crash event"
                r")\b",
                text,
                re.I,
            )
        )
    )


# ============================================================
# Group 3 classification
# ============================================================

FAMILY_RULES = [
    (
        "pretensioner_timing",
        [
            r"\bpretensioner\b.*\b(?:time|fire|deployment)\b",
            r"\bbelt tensioner\b.*\btime\b",
        ],
    ),
    (
        "restraint_deployment_timing",
        [
            r"\b(?:"
            r"load limiter|head[- ]?rest|knee bolster|"
            r"inflatable seatbelt|adaptive steering column|"
            r"battery disconnect|rollover protection system"
            r")\b.*\b(?:time|deploy|deployment|fire)\b",
        ],
    ),
    (
        "deployment_timing",
        [
            r"\bdeployment\b.*\b(?:time|criteria met)\b",
            r"\btime\b.*\bdeployment\b",
            r"\b1st stage time\b",
            r"\b2nd stage time\b",
        ],
    ),
    (
        "pretensioner_status",
        [
            r"\bpretensioner\b",
            r"\bbelt tensioner\b",
        ],
    ),
    (
        "deployment_status",
        [
            r"\bair ?bag\b.*\b(?:deployed|deployment|status|commanded)\b",
            r"\bdeployment\b.*\b(?:status|level|commanded|occurred)\b",
            r"\bside seat airbags? deployment\b",
            r"\bfrontal deployment\b",
            r"\brollover deployment\b",
        ],
    ),
    (
        "restraint_status",
        [
            r"\bseat belt\b",
            r"\bsafety belt\b",
            r"\bbelt switch\b",
            r"\brestraint\b",
            r"\bbuckled\b",
            r"\bunbuckled\b",
        ],
    ),
    (
        "occupant_status",
        [
            r"\boccupant\b",
            r"\bpassenger classification\b",
            r"\bpassenger presence\b",
            r"\boccupancy\b",
            r"\bseat track\b",
            r"\bseat position\b",
        ],
    ),
    (
        "warning_lamp_status",
        [
            r"\bwarning lamp\b",
            r"\bwarning light\b",
            r"\bmalfunction indicator\b",
        ],
    ),
    (
        "event_severity_status",
        [
            r"\bevent severity\b",
            r"\bseverity status\b",
            r"\bcrash severity\b",
        ],
    ),
    (
        "high_voltage_status",
        [
            r"\bhigh[- ]?voltage\b",
            r"\bhigh voltage disable\b",
        ],
    ),
    (
        "power_event_condition",
        [
            r"\bpower loss\b",
            r"\bpower supply status\b",
            r"\bvehicle power mode\b",
            r"\bbattery voltage\b.*\balgorithm wake[- ]?up\b",
            r"\benergy reserve voltage\b.*\balgorithm wake[- ]?up\b",
        ],
    ),
    (
        "algorithm_timing",
        [
            r"\btime\b.*\balgorithm\b.*\b(?:wake[- ]?up|reset|start|decision)\b",
            r"\bfuel cutoff algorithm decision time\b",
        ],
    ),
    (
        "algorithm_status",
        [
            r"\balgorithm active\b",
            r"\balgorithm status\b",
            r"\balgorithm enable\b",
        ],
    ),
    (
        "deployment_sensor_status",
        [
            r"\b(?:discriminating deployment|safing deployment)\b",
            r"\bfreeze signal factor\b.*\bdeployment\b",
        ],
    ),
    (
        "sensor_fault_status",
        [
            r"\bsensor\b.*\bfault\b",
        ],
    ),
    (
        "other_event_condition",
        [
            r"\bevent condition\b",
            r"\brsca disable\b",
            r"\bonstar\b.*\bstatus\b",
        ],
    ),
]


GROUP2_PATTERNS = [
    r"\bevent recording complete\b",
    r"\brecording status\b",
    r"\bcrash record locked\b",
    r"\brecord complete\b",
    r"\bevent counter\b",
    r"\bdeployment command counter\b",
    r"\bretrieval status\b",
    r"\bmultiple events?\b",
    r"\btime between\b.*\bevents?\b",
]

GROUP5_PATTERNS = [
    r"\bmaximum\b.*\bdelta[- ]?v\b",
    r"\bmax(?:imum)?\b.*\bvelocity change\b",
    r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
    r"\bmaximum acceleration\b",
    r"\btime\b.*\bmaximum acceleration\b",
    r"\broll angle peak\b",
    r"\blength of delta[- ]?v\b",
    r"\bclipping time\b",
    r"\baccelerometer range exceeded\b",
    r"\bsensor design range exceeded\b",
    r"\bpdof\b",
]

GROUP6_PATTERNS = [
    r"\bignition cycles? at investigation\b",
    r"\bpower[- ]on cycle at reading\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bsupplier id\b",
    r"\bproduction date\b",
    r"\bmodule\b.*\b(?:id|identifier|number|version)\b",
    r"\bodometer\b",
    r"\bvehicle mileage\b",
    r"\boperating time\b",
    r"\binvestigation\b",
    r"\bvin\b",
]

GROUP1_PATTERNS = [
    r"\bfilename\b",
    r"\bsaved on\b",
    r"\bimaged with\b",
    r"\breported with\b",
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
]


def classify_family(label):
    text = norm(label)

    for family, patterns in FAMILY_RULES:
        if any(
            re.search(pattern, text, re.I)
            for pattern in patterns
        ):
            return family

    return ""


def score_field(label, value, section):
    family = classify_family(label)
    score = 0
    evidence = []
    exclusions = []

    if family:
        score += 6
        evidence.append(f"family:{family}")

    if looks_status_value(value):
        score += 1
        evidence.append("status_value")

    elif looks_numeric(value):
        score += 1
        evidence.append("scalar_value")

    if re.search(
        r"\b(?:"
        r"deployment|pretensioner|belt|restraint|"
        r"occupant|warning|severity|power|"
        r"high[- ]?voltage|algorithm|fault|status"
        r")\b",
        norm(label),
        re.I,
    ):
        score += 1
        evidence.append("group3_terms")

    if re.search(
        r"\b(?:"
        r"system status|deployment|non[- ]deployment|"
        r"restraint|occupant|event status"
        r")\b",
        norm(section),
        re.I,
    ):
        score += 1
        evidence.append("group3_section_context")

    if matches_any(label, GROUP2_PATTERNS):
        exclusions.append("group2_record_structure")

    if matches_any(label, GROUP5_PATTERNS):
        exclusions.append("group5_crash_measurement")

    if matches_any(label, GROUP6_PATTERNS):
        exclusions.append("group6_technical_or_investigation")

    if matches_any(label, GROUP1_PATTERNS):
        exclusions.append("group1_report_metadata")

    if exclusions:
        decision = "excluded_overlap"
    elif score >= 6:
        decision = "candidate"
    elif score >= 3:
        decision = "review"
    else:
        decision = "not_group3"

    return {
        "family":
            family or "other_event_condition",
        "score":
            score,
        "decision":
            decision,
        "evidence":
            evidence,
        "exclusions":
            exclusions,
    }


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--report-index",
        type=Path,
        default=Path(
            "data/processed/edr/group1_v4/report_index.csv"
        ),
    )

    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("data/temp"),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_pdf_discovery_v1"
        ),
    )

    args = parser.parse_args()

    if not args.report_index.exists():
        raise FileNotFoundError(args.report_index)

    report_index = read_csv(args.report_index)
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)

    candidates = []
    review = []
    excluded = []
    coverage = []
    errors = []

    family_counts = Counter()
    label_counts = Counter()

    selected = 0
    processed = 0

    reports_with_candidates = set()
    reports_with_review = set()

    for row in report_index:
        csv_path = norm(row.get("csv_path", ""))
        pdf_path_text = norm(row.get("pdf_path", ""))

        # PDF-only population
        if csv_path:
            continue

        if not pdf_path_text:
            continue

        selected += 1

        pdf_path = resolve_pdf_path(
            row,
            args.source_root,
        )

        if pdf_path is None or not pdf_path.exists():
            errors.append({
                **{
                    key: row.get(key, "")
                    for key in BASE
                },
                "error_type": "pdf_source_not_found",
                "pdf_path": pdf_path_text,
                "error": "Could not resolve PDF source path.",
            })

            coverage.append({
                **{
                    key: row.get(key, "")
                    for key in BASE
                },
                "pdf_path": pdf_path_text,
                "processing_status": "source_not_found",
                "candidate_count": 0,
                "review_count": 0,
                "excluded_overlap_count": 0,
            })

            continue

        report_candidate_count = 0
        report_review_count = 0
        report_excluded_count = 0

        try:
            with pdfplumber.open(pdf_path) as pdf:
                current_section = ""

                for page_index, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""

                    lines = [
                        norm(line)
                        for line in text.splitlines()
                        if norm(line)
                    ]

                    for line_index, line in enumerate(lines, start=1):
                        if looks_heading(line):
                            current_section = line
                            continue

                        parsed = split_pdf_line(line)

                        if parsed is None:
                            continue

                        label, value, split_method = parsed

                        result = score_field(
                            label,
                            value,
                            current_section,
                        )

                        if result["decision"] == "not_group3":
                            continue

                        event_hint = extract_event_hint(
                            current_section,
                            label,
                            line,
                        )

                        candidate_id = (
                            "g3pdf_"
                            + stable_id(
                                row.get("report_id", ""),
                                page_index,
                                line_index,
                                label,
                                value,
                            )
                        )

                        observation = {
                            **{
                                key: row.get(key, "")
                                for key in BASE
                            },
                            "group3_candidate_id": candidate_id,
                            "source_format": "pdf",
                            "source_path": str(pdf_path),
                            "pdf_page": page_index,
                            "pdf_line_number": line_index,
                            "source_section_heading": current_section,
                            "event_hint": event_hint,
                            "source_line_raw": line,
                            "field_label_raw": label,
                            "field_value_raw": value,
                            "split_method": split_method,
                            "candidate_family": result["family"],
                            "candidate_score": result["score"],
                            "discovery_decision": result["decision"],
                            "evidence_json": json.dumps(
                                result["evidence"],
                                ensure_ascii=False,
                            ),
                            "overlap_exclusions_json": json.dumps(
                                result["exclusions"],
                                ensure_ascii=False,
                            ),
                            "semantic_normalization_status": "not_normalized",
                            "unit_conversion_status": "not_converted",
                            "event_link_status":
                                "source_hint_only"
                                if event_hint
                                else "not_linked",
                        }

                        if result["decision"] == "candidate":
                            candidates.append(observation)
                            report_candidate_count += 1
                            reports_with_candidates.add(
                                row.get("report_id", "")
                            )
                            family_counts[result["family"]] += 1
                            label_counts[norm_key(label)] += 1

                        elif result["decision"] == "review":
                            review.append(observation)
                            report_review_count += 1
                            reports_with_review.add(
                                row.get("report_id", "")
                            )

                        elif result["decision"] == "excluded_overlap":
                            excluded.append(observation)
                            report_excluded_count += 1

            processed += 1

            if report_candidate_count:
                status = "group3_candidates_found"
            elif report_review_count:
                status = "review_only"
            else:
                status = "no_group3_candidates"

            coverage.append({
                **{
                    key: row.get(key, "")
                    for key in BASE
                },
                "pdf_path": str(pdf_path),
                "processing_status": status,
                "candidate_count": report_candidate_count,
                "review_count": report_review_count,
                "excluded_overlap_count": report_excluded_count,
            })

        except Exception as exc:
            errors.append({
                **{
                    key: row.get(key, "")
                    for key in BASE
                },
                "error_type": type(exc).__name__,
                "pdf_path": str(pdf_path),
                "error": str(exc),
            })

            coverage.append({
                **{
                    key: row.get(key, "")
                    for key in BASE
                },
                "pdf_path": str(pdf_path),
                "processing_status": "source_error",
                "candidate_count": 0,
                "review_count": 0,
                "excluded_overlap_count": 0,
            })

        if processed % 25 == 0 or processed == selected:
            print(
                f"Discovered Group 3 PDF {processed}/{selected} reports...",
                flush=True,
            )

    # ========================================================
    # Summaries
    # ========================================================

    label_examples = defaultdict(Counter)

    for row in candidates:
        label_examples[
            norm_key(row["field_label_raw"])
        ][
            row["field_label_raw"]
        ] += 1

    label_summary = []

    for key, count in label_counts.most_common():
        examples = [
            label
            for label, _
            in label_examples[key].most_common(5)
        ]

        label_summary.append({
            "normalized_label": key,
            "candidate_count": count,
            "raw_label_examples_json": json.dumps(
                examples,
                ensure_ascii=False,
            ),
        })

    family_summary = [
        {
            "candidate_family": family,
            "candidate_count": count,
        }
        for family, count
        in family_counts.most_common()
    ]

    candidate_columns = [
        *BASE,
        "group3_candidate_id",
        "source_format",
        "source_path",
        "pdf_page",
        "pdf_line_number",
        "source_section_heading",
        "event_hint",
        "source_line_raw",
        "field_label_raw",
        "field_value_raw",
        "split_method",
        "candidate_family",
        "candidate_score",
        "discovery_decision",
        "evidence_json",
        "overlap_exclusions_json",
        "semantic_normalization_status",
        "unit_conversion_status",
        "event_link_status",
    ]

    write_csv(
        out / "group3_pdf_candidates.csv",
        candidates,
        candidate_columns,
    )

    write_csv(
        out / "group3_pdf_review.csv",
        review,
        candidate_columns,
    )

    write_csv(
        out / "group3_pdf_excluded_overlap.csv",
        excluded,
        candidate_columns,
    )

    write_csv(
        out / "group3_pdf_report_coverage.csv",
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

    write_csv(
        out / "group3_pdf_label_summary.csv",
        label_summary,
        [
            "normalized_label",
            "candidate_count",
            "raw_label_examples_json",
        ],
    )

    write_csv(
        out / "group3_pdf_family_summary.csv",
        family_summary,
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
        row["processing_status"]
        for row in coverage
    )

    metadata = {
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 3 - Event conditions, deployment, and status information",

        "stage":
            "PDF-only discovery",

        "reports_in_index":
            len(report_index),

        "pdf_only_reports_selected":
            selected,

        "pdf_only_reports_processed":
            processed,

        "reports_with_group3_candidates":
            len(reports_with_candidates),

        "reports_with_review_fields":
            len(reports_with_review),

        "candidate_field_count":
            len(candidates),

        "review_field_count":
            len(review),

        "excluded_overlap_field_count":
            len(excluded),

        "candidate_family_counts":
            dict(family_counts),

        "unique_candidate_labels":
            len(label_counts),

        "coverage_status_counts":
            dict(coverage_counts),

        "source_errors":
            len(errors),

        "ocr_used":
            False,

        "scope":
            (
                "PDF-only discovery for Group 3 event conditions, deployment, "
                "restraint, occupant, warning/status, power, high-voltage, "
                "algorithm, fault, and related event-state information. "
                "Processing is restricted to reports without a CSV source, "
                "and the original PDF remains authoritative. Group 2 record "
                "structure, Group 4 repeated time-series, Group 5 scalar crash "
                "measurements, and Group 6 technical/investigation metadata "
                "are explicitly excluded. No OCR, semantic normalization, "
                "unit conversion, fuzzy event linking, or source mutation "
                "is performed."
            ),
    }

    tmp = out / "metadata.json.part"
    tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(out / "metadata.json")

    print()
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print()
    print(f"Outputs: {out}")
    print()
    print("GROUP 3 PDF-ONLY DISCOVERY COMPLETE.")


if __name__ == "__main__":
    main()
