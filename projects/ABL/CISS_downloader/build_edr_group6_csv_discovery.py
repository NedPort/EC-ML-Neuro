"""
Discover Group 6 CSV candidates: other structured technical,
module/configuration, investigation, and readout information.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Authoritative source
--------------------
Original CSV exports referenced by report_index.csv.

Output
------
data/processed/edr/group6_csv_discovery_v1/

    group6_candidate_fields.csv
    group6_review_fields.csv
    group6_excluded_overlap_fields.csv
    group6_report_coverage.csv
    group6_label_summary.csv
    group6_family_summary.csv
    group6_section_summary.csv
    errors.csv
    metadata.json

Purpose
-------
Discover structured information that does not belong to Groups 1--5,
including technical/module/configuration/investigation/readout metadata.

Typical Group 6 content
-----------------------
- ignition cycles at investigation/readout
- power-on cycles at reading
- module supplier/part/serial identifiers
- software/calibration/version identifiers
- production/manufacture date
- module configuration / configured-for fields
- odometer / vehicle mileage / operating time
- readout/download/investigation context
- module/equipment technical status
- other structured technical fields

Important boundaries
--------------------
Group 1:
    report introduction/documentation metadata.

Group 2:
    recorded-event structure, counters, lock/retrieval/recording status.

Group 3:
    event conditions, deployment, restraint, occupant, warning/status.

Group 4:
    repeated time-series measurements.

Group 5:
    scalar crash/event measurements.

This is DISCOVERY only:
- no semantic normalization
- no unit conversion
- no fuzzy inference
- no source modification
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

csv.field_size_limit(100_000_000)

BASE = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


def read_csv_dict(path: Path):
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def read_raw_csv(path: Path):
    rows = []
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        for index, row in enumerate(csv.reader(f)):
            rows.append((index, [clean_cell(x) for x in row]))
    return rows


def write_csv(path: Path, rows: list[dict], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def clean_cell(value):
    text = str(value if value is not None else "")
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def norm(value):
    return clean_cell(value)


def norm_key(value):
    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            norm(value).casefold(),
        )
    )


def stable_id(*parts):
    text = "|".join(norm(x) for x in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def populated(row):
    return [x for x in row if norm(x)]


def looks_numeric(value):
    text = norm(value).replace(",", "")
    return bool(
        re.fullmatch(
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?"
            r"(?:\s*(?:"
            r"miles?|mi|km|hours?|hrs?|minutes?|min|"
            r"cycles?|V|volts?|%|mph|km/h|kph"
            r"))?",
            text,
            flags=re.I,
        )
    )


def resolve_csv_path(index_row: dict, source_root: Path):
    raw = norm(index_row.get("csv_path", ""))

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
                if len(matches) == 1:
                    return matches[0]
                if matches:
                    preferred = [
                        p for p in matches
                        if "cdr_exports" in str(p).casefold()
                    ]
                    return preferred[0] if preferred else matches[0]

    basename = norm(index_row.get("export_basename", ""))
    case_id = norm(index_row.get("case_id", ""))

    if basename and case_id:
        case_root = source_root / case_id
        if case_root.exists():
            matches = list(case_root.rglob(basename + ".CSV"))
            if not matches:
                matches = list(case_root.rglob(basename + ".csv"))
            if matches:
                return matches[0]

    return None


def is_heading_row(row):
    values = populated(row)

    if len(values) != 1:
        return False

    text = values[0]

    if not text or looks_numeric(text) or len(text) > 220:
        return False

    alpha = [c for c in text if c.isalpha()]
    upper_ratio = (
        sum(c.isupper() for c in alpha) / len(alpha)
        if alpha else 0.0
    )

    technical_terms = bool(
        re.search(
            r"\b(?:"
            r"module|acm|sdm|ecm|pcm|technical|"
            r"vehicle information|system information|"
            r"investigation|readout|configuration|"
            r"identification|identifiers|version|"
            r"diagnostic|manufacturer|production"
            r")\b",
            text,
            re.I,
        )
    )

    return upper_ratio >= 0.70 or technical_terms


def parse_scalar_observation(row):
    nonblank = [
        (i, norm(v))
        for i, v in enumerate(row)
        if norm(v)
    ]

    if len(nonblank) < 2 or len(nonblank) > 5:
        return None

    label_index, label = nonblank[0]
    value_index, value = nonblank[-1]

    if label_index == value_index or looks_numeric(label):
        return None

    return {
        "label_index": label_index,
        "label": label,
        "value_index": value_index,
        "value": value,
        "populated_cell_count": len(nonblank),
    }


FAMILY_RULES = [
    (
        "ignition_cycle_readout",
        [
            r"\bignition cycles?\b.*\b(?:investigation|readout|reading|download)\b",
            r"\bpower[- ]on cycles?\b.*\b(?:reading|readout|download)\b",
            r"\bcycles? at investigation\b",
            r"\bcycles? at reading\b",
        ],
    ),
    (
        "module_identifier",
        [
            r"\b(?:module|acm|sdm|pcm|ecm)\b.*\b(?:id|identifier)\b",
            r"\bsupplier id\b",
            r"\bmanufacturer id\b",
        ],
    ),
    (
        "part_serial_identifier",
        [
            r"\bpart number\b",
            r"\bserial number\b",
            r"\bhardware number\b",
        ],
    ),
    (
        "software_calibration_version",
        [
            r"\bsoftware\b.*\b(?:version|number|id)\b",
            r"\bcalibration\b.*\b(?:version|number|id)\b",
            r"\bfirmware\b.*\b(?:version|number|id)\b",
            r"\bbootloader\b",
        ],
    ),
    (
        "production_manufacture_date",
        [
            r"\bproduction date\b",
            r"\bmanufacture date\b",
            r"\bmanufacturing date\b",
            r"\bdate of manufacture\b",
        ],
    ),
    (
        "configuration",
        [
            r"\bconfigured for\b",
            r"\bconfiguration\b",
            r"\bmodule configuration\b",
            r"\bequipment configuration\b",
            r"\bvehicle configuration\b",
        ],
    ),
    (
        "odometer_mileage",
        [
            r"\bodometer\b",
            r"\bvehicle mileage\b",
            r"\bmileage at\b",
        ],
    ),
    (
        "operating_time",
        [
            r"\boperating time\b",
            r"\blifetime operating timer\b",
            r"\bengine operating time\b",
            r"\bmodule operating time\b",
        ],
    ),
    (
        "readout_investigation_context",
        [
            r"\bdownload date\b",
            r"\bdownload time\b",
            r"\breadout date\b",
            r"\breadout time\b",
            r"\binvestigation date\b",
            r"\binvestigator\b",
            r"\bdownload tool\b",
            r"\breadout tool\b",
        ],
    ),
    (
        "technical_status",
        [
            r"\bmodule status\b",
            r"\bdiagnostic status\b",
            r"\bcommunication status\b",
            r"\bdata retrieval status\b",
        ],
    ),
    (
        "other_structured_technical",
        [
            r"\btechnical\b",
            r"\bmanufacturer\b",
            r"\bmodule\b",
            r"\bacm\b",
            r"\bsdm\b",
            r"\bpcm\b",
            r"\becm\b",
        ],
    ),
]


GROUP1_PATTERNS = [
    r"\bfilename\b",
    r"\bsaved on\b",
    r"\bimaged with\b",
    r"\breported with\b",
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
    r"\buser entered vin\b",
    r"\bcase number entered\b",
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
    r"\bmost recent event\b",
    r"\b\d+(?:st|nd|rd|th)\s+prior event\b",
]

GROUP3_PATTERNS = [
    r"\bair ?bag\b.*\b(?:deployment|deployed|status)\b",
    r"\bpretensioner\b",
    r"\bseat belt\b",
    r"\bsafety belt\b",
    r"\boccupant\b",
    r"\bpassenger classification\b",
    r"\bwarning lamp\b",
    r"\bevent severity\b",
    r"\bhigh[- ]?voltage disable\b",
    r"\balgorithm\b.*\b(?:wake|reset|deployment)\b",
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
    r"\bpdof\b",
]

GROUP4_PATTERNS = [
    r"^\s*time\s*(?:\([^)]*\))?\s*$",
    r"^\s*times\s*(?:\([^)]*\))?\s*$",
    r"^\s*sample\s+count\b",
    r"^\s*buffer address\b",
]


def classify_family(label):
    text = norm(label)

    for family, patterns in FAMILY_RULES:
        if any(re.search(p, text, re.I) for p in patterns):
            return family

    return ""


def matches_any(text, patterns):
    return any(
        re.search(pattern, norm(text), re.I)
        for pattern in patterns
    )


def score_field(label, value, section):
    family = classify_family(label)
    score = 0
    evidence = []
    exclusions = []

    if family:
        score += 6
        evidence.append(f"family:{family}")

    if re.search(
        r"\b(?:"
        r"module|part number|serial number|supplier|"
        r"software|firmware|calibration|production date|"
        r"configuration|odometer|mileage|operating time|"
        r"investigation|readout|download|ignition cycles?|"
        r"power[- ]on cycles?"
        r")\b",
        norm(label),
        re.I,
    ):
        score += 1
        evidence.append("group6_terms")

    if re.search(
        r"\b(?:"
        r"module|technical|vehicle information|"
        r"system information|investigation|readout|"
        r"configuration|identification"
        r")\b",
        norm(section),
        re.I,
    ):
        score += 1
        evidence.append("group6_section_context")

    if looks_numeric(value):
        score += 1
        evidence.append("scalar_value")

    if matches_any(label, GROUP1_PATTERNS):
        exclusions.append("group1_report_metadata")

    if matches_any(label, GROUP2_PATTERNS):
        exclusions.append("group2_record_structure")

    if matches_any(label, GROUP3_PATTERNS):
        exclusions.append("group3_event_condition")

    if matches_any(label, GROUP5_PATTERNS):
        exclusions.append("group5_crash_measurement")

    if matches_any(label, GROUP4_PATTERNS):
        exclusions.append("group4_timeseries_axis")

    if exclusions:
        decision = "excluded_overlap"
    elif score >= 6:
        decision = "candidate"
    elif score >= 3:
        decision = "review"
    else:
        decision = "not_group6"

    return {
        "family":
            family or "other_structured_technical",
        "score":
            score,
        "decision":
            decision,
        "evidence":
            evidence,
        "exclusions":
            exclusions,
    }


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
            "data/processed/edr/group6_csv_discovery_v1"
        ),
    )

    args = parser.parse_args()

    if not args.report_index.exists():
        raise FileNotFoundError(args.report_index)

    report_index = read_csv_dict(args.report_index)
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)

    candidates = []
    reviews = []
    excluded = []
    coverage = []
    errors = []

    family_counts = Counter()
    label_counts = Counter()
    section_counts = Counter()

    selected = 0
    processed = 0

    reports_with_candidates = set()
    reports_with_reviews = set()

    for index_row in report_index:
        csv_path_text = norm(index_row.get("csv_path", ""))

        if not csv_path_text:
            continue

        selected += 1

        csv_path = resolve_csv_path(index_row, args.source_root)

        if csv_path is None or not csv_path.exists():
            errors.append({
                **{
                    k: index_row.get(k, "")
                    for k in BASE
                },
                "error_type": "csv_source_not_found",
                "csv_path": csv_path_text,
                "error": "Could not resolve CSV source path.",
            })
            continue

        try:
            rows = read_raw_csv(csv_path)
        except Exception as exc:
            errors.append({
                **{
                    k: index_row.get(k, "")
                    for k in BASE
                },
                "error_type": type(exc).__name__,
                "csv_path": str(csv_path),
                "error": str(exc),
            })
            continue

        processed += 1

        current_section = ""
        c_count = 0
        r_count = 0
        e_count = 0

        for row_index, row in rows:
            if is_heading_row(row):
                current_section = populated(row)[0]
                continue

            parsed = parse_scalar_observation(row)

            if parsed is None:
                continue

            label = parsed["label"]
            value = parsed["value"]

            result = score_field(
                label,
                value,
                current_section,
            )

            if result["decision"] == "not_group6":
                continue

            candidate_id = (
                "g6csv_"
                + stable_id(
                    index_row.get("report_id", ""),
                    row_index,
                    label,
                    value,
                )
            )

            observation = {
                **{
                    k: index_row.get(k, "")
                    for k in BASE
                },
                "group6_candidate_id": candidate_id,
                "source_format": "csv",
                "source_path": str(csv_path),
                "source_record_index": row_index,
                "source_section_heading": current_section,
                "field_label_raw": label,
                "field_value_raw": value,
                "value_column_index": parsed["value_index"],
                "populated_cell_count": parsed["populated_cell_count"],
                "source_row_json": json.dumps(
                    row,
                    ensure_ascii=False,
                ),
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
            }

            if result["decision"] == "candidate":
                candidates.append(observation)
                c_count += 1
                reports_with_candidates.add(
                    index_row.get("report_id", "")
                )
                family_counts[result["family"]] += 1
                label_counts[norm_key(label)] += 1
                section_counts[
                    norm(current_section)
                    or "<no_section_heading>"
                ] += 1

            elif result["decision"] == "review":
                reviews.append(observation)
                r_count += 1
                reports_with_reviews.add(
                    index_row.get("report_id", "")
                )

            elif result["decision"] == "excluded_overlap":
                excluded.append(observation)
                e_count += 1

        coverage.append({
            **{
                k: index_row.get(k, "")
                for k in BASE
            },
            "csv_path": str(csv_path),
            "processing_status":
                "group6_candidates_found"
                if c_count
                else (
                    "review_only"
                    if r_count
                    else "no_group6_candidates"
                ),
            "candidate_count": c_count,
            "review_count": r_count,
            "excluded_overlap_count": e_count,
        })

        if processed % 100 == 0 or processed == selected:
            print(
                f"Discovered Group 6 CSV {processed}/{selected} reports...",
                flush=True,
            )

    raw_label_examples = defaultdict(Counter)

    for row in candidates:
        raw_label_examples[
            norm_key(row["field_label_raw"])
        ][
            row["field_label_raw"]
        ] += 1

    label_summary = []

    for key, count in label_counts.most_common():
        label_summary.append({
            "normalized_label": key,
            "candidate_count": count,
            "raw_label_examples_json": json.dumps(
                [
                    label
                    for label, _
                    in raw_label_examples[key].most_common(5)
                ],
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

    section_summary = [
        {
            "source_section_heading": section,
            "candidate_count": count,
        }
        for section, count
        in section_counts.most_common()
    ]

    candidate_columns = [
        *BASE,
        "group6_candidate_id",
        "source_format",
        "source_path",
        "source_record_index",
        "source_section_heading",
        "field_label_raw",
        "field_value_raw",
        "value_column_index",
        "populated_cell_count",
        "source_row_json",
        "candidate_family",
        "candidate_score",
        "discovery_decision",
        "evidence_json",
        "overlap_exclusions_json",
        "semantic_normalization_status",
        "unit_conversion_status",
    ]

    write_csv(
        out / "group6_candidate_fields.csv",
        candidates,
        candidate_columns,
    )

    write_csv(
        out / "group6_review_fields.csv",
        reviews,
        candidate_columns,
    )

    write_csv(
        out / "group6_excluded_overlap_fields.csv",
        excluded,
        candidate_columns,
    )

    write_csv(
        out / "group6_report_coverage.csv",
        coverage,
        [
            *BASE,
            "csv_path",
            "processing_status",
            "candidate_count",
            "review_count",
            "excluded_overlap_count",
        ],
    )

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
        family_summary,
        [
            "candidate_family",
            "candidate_count",
        ],
    )

    write_csv(
        out / "group6_section_summary.csv",
        section_summary,
        [
            "source_section_heading",
            "candidate_count",
        ],
    )

    write_csv(
        out / "errors.csv",
        errors,
        [
            *BASE,
            "error_type",
            "csv_path",
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
            "Group 6 - Other structured technical and investigation information",

        "stage":
            "CSV discovery",

        "reports_in_index":
            len(report_index),

        "csv_reports_selected":
            selected,

        "csv_reports_processed":
            processed,

        "reports_with_group6_candidates":
            len(reports_with_candidates),

        "reports_with_review_fields":
            len(reports_with_reviews),

        "candidate_field_count":
            len(candidates),

        "review_field_count":
            len(reviews),

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

        "scope":
            (
                "CSV-first discovery for Group 6 other structured technical, "
                "module/configuration, investigation, and readout information. "
                "Original CSV exports remain authoritative. Group 1 report "
                "metadata, Group 2 record structure, Group 3 event conditions, "
                "Group 4 time-series, and Group 5 scalar crash/event measurements "
                "are explicitly excluded. No semantic normalization, unit "
                "conversion, fuzzy inference, PDF processing, or source mutation "
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
    print("GROUP 6 CSV DISCOVERY COMPLETE.")


if __name__ == "__main__":
    main()
