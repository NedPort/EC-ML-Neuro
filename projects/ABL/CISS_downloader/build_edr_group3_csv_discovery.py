"""
Discover Group 3 CSV candidates: event conditions, deployment, restraint,
occupant, warning/status, and related event-state information.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Optional supporting handoffs
----------------------------
data/processed/edr/group5_csv_resolved_v1/excluded_non_group5_fields.csv
data/processed/edr/group2_final_v1/

Authoritative source
--------------------
Original CSV exports referenced by report_index.csv.

Output
------
data/processed/edr/group3_csv_discovery_v1/

    group3_candidate_fields.csv
    group3_review_fields.csv
    group3_excluded_overlap_fields.csv
    group3_report_coverage.csv
    group3_label_summary.csv
    group3_family_summary.csv
    group3_section_summary.csv
    errors.csv
    metadata.json

Purpose
-------
Discover non-time-series event-condition/status fields that belong to Group 3.

Examples include:
- airbag / pretensioner deployment status
- deployment command timing
- event severity/status
- restraint and belt status
- occupant / passenger classification status
- warning-lamp state
- high-voltage-disable status
- power-loss/event-condition state
- algorithm active/start/reset state
- related event-time status fields

Important boundaries
--------------------
Group 2:
    record/event structure, event counts, recording completeness,
    lock/retrieval status, multiple-event bookkeeping.

Group 4:
    repeated time-series measurements and temporal tables.

Group 5:
    scalar crash-dynamics measurements such as maximum/final Delta-V,
    time of maximum Delta-V, peak acceleration, roll-angle summaries,
    clipping/range timing, and similar physical crash measurements.

Group 6:
    technical/module/configuration/investigation information such as
    serial/part numbers, supplier IDs, production dates, ignition cycles
    at investigation, software versions, odometer/mileage, etc.

This is a DISCOVERY stage only:
- no semantic normalization
- no unit conversion
- no fuzzy event identity inference
- no source modification
- no final structured extraction
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


# ============================================================
# I/O
# ============================================================

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
        reader = csv.reader(f)

        for index, row in enumerate(reader):
            rows.append(
                (
                    index,
                    [clean_cell(cell) for cell in row],
                )
            )

    return rows


def write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".part"
    )

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

def clean_cell(value):
    text = str(
        value
        if value is not None
        else ""
    )

    text = text.replace(
        "\r",
        " ",
    ).replace(
        "\n",
        " ",
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        clean_cell(value),
    )


def norm_key(value):
    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            norm(value).casefold(),
        )
    )


def identifier(*parts):
    text = "|".join(
        norm(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode(
            "utf-8"
        )
    ).hexdigest()[:24]


def populated(row):
    return [
        value
        for value in row
        if norm(value)
    ]


def first_populated_with_index(row):
    for index, value in enumerate(row):
        value = norm(value)

        if value:
            return index, value

    return None, ""


def looks_numeric(value):
    text = norm(value)

    if not text:
        return False

    text = text.replace(
        ",",
        "",
    )

    text = re.sub(
        r"\s*(?:"
        r"mph|km/h|kph|m/s|m/s\^2|g|"
        r"ms|msec|milliseconds?|"
        r"sec|seconds?|"
        r"deg|degrees?|deg/s|rad/s|"
        r"%|percent|cycles?"
        r")\s*$",
        "",
        text,
        flags=re.I,
    )

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def looks_value_like(value):
    text = norm(value)

    if not text:
        return False

    if looks_numeric(text):
        return True

    if text.casefold() in {
        "yes",
        "no",
        "on",
        "off",
        "active",
        "inactive",
        "enabled",
        "disabled",
        "buckled",
        "unbuckled",
        "forward",
        "rearward",
        "present",
        "not present",
        "deployed",
        "not deployed",
        "deployment",
        "non-deployment",
        "pretensioner only",
        "n/a",
        "na",
        "sna",
        "unknown",
        "invalid",
        "data invalid",
        "data valid",
    }:
        return True

    return False


# ============================================================
# Source path resolution
# ============================================================

def resolve_csv_path(
    index_row: dict,
    source_root: Path,
):
    raw = norm(
        index_row.get(
            "csv_path",
            ""
        )
    )

    if raw:
        direct = Path(raw)

        if direct.exists():
            return direct

        basename = PureWindowsPath(
            raw
        ).name

        case_id = norm(
            index_row.get(
                "case_id",
                ""
            )
        )

        if case_id and basename:
            case_root = (
                source_root
                / case_id
            )

            if case_root.exists():
                matches = list(
                    case_root.rglob(
                        basename
                    )
                )

                if len(matches) == 1:
                    return matches[0]

                if len(matches) > 1:
                    preferred = [
                        path
                        for path in matches
                        if "cdr_exports"
                        in str(path).casefold()
                    ]

                    if len(preferred) == 1:
                        return preferred[0]

                    return matches[0]

    basename = norm(
        index_row.get(
            "export_basename",
            ""
        )
    )

    case_id = norm(
        index_row.get(
            "case_id",
            ""
        )
    )

    if basename and case_id:
        case_root = (
            source_root
            / case_id
        )

        if case_root.exists():
            matches = list(
                case_root.rglob(
                    basename + ".CSV"
                )
            )

            if not matches:
                matches = list(
                    case_root.rglob(
                        basename + ".csv"
                    )
                )

            if matches:
                return matches[0]

    return None


# ============================================================
# Section detection
# ============================================================

def is_heading_row(row):
    values = populated(row)

    if len(values) != 1:
        return False

    text = values[0]

    if not text:
        return False

    if looks_numeric(text):
        return False

    if len(text) > 220:
        return False

    alpha = [
        char
        for char in text
        if char.isalpha()
    ]

    if alpha:
        uppercase_ratio = (
            sum(
                1
                for char in alpha
                if char.isupper()
            )
            / len(alpha)
        )
    else:
        uppercase_ratio = 0.0

    heading_terms = bool(
        re.search(
            r"\b(?:"
            r"status|deployment|"
            r"non[- ]deployment|"
            r"system|event|restraint|"
            r"occupant|passenger|driver|"
            r"airbag|air bag|pretensioner|"
            r"warning|configuration|"
            r"multiple event|crash"
            r")\b",
            text,
            re.I,
        )
    )

    return (
        uppercase_ratio >= 0.70
        or heading_terms
    )


# ============================================================
# Event hint extraction
# ============================================================

EVENT_PATTERNS = [
    r"\bevent record\s*#?\s*\d+\b",
    r"\bevent\s*#\s*\d+\b",
    r"\bdeployment event\s*#?\s*\d*\b",
    r"\bnon[- ]deployment event\b",
    r"\bmost recent event\b",
    r"\b\d+(?:st|nd|rd|th)\s+prior event\b",
    r"\btrg\s*\d+\b",
]


def extract_event_hint(*texts):
    combined = " | ".join(
        norm(text)
        for text in texts
        if norm(text)
    )

    hints = []

    for pattern in EVENT_PATTERNS:
        for match in re.findall(
            pattern,
            combined,
            flags=re.I,
        ):
            cleaned = norm(match)

            if cleaned.casefold() not in {
                item.casefold()
                for item in hints
            }:
                hints.append(
                    cleaned
                )

    return " | ".join(hints)


# ============================================================
# Group 3 families
# ============================================================

FAMILY_RULES = [
    (
        "deployment_timing",
        [
            r"\btime\b.*\bdeployment command\b",
            r"\btime from algorithm enable\b.*\bdeployment\b",
            r"\bdeployment command criteria met\b.*\b(?:msec|ms|time)\b",
            r"\b1st stage time\b",
            r"\b2nd stage time\b",
            r"\bstage time from algorithm enable\b",
            r"\btime to deploy\b",
        ],
    ),
    (
        "deployment_status",
        [
            r"\bair ?bag\b.*\b(?:deployed|deployment|commanded|status)\b",
            r"\bdeployment\b.*\b(?:status|level|commanded|occurred)\b",
            r"\bfrontal deployment\b",
            r"\bside deployment\b",
            r"\bknee deployment\b",
            r"\bcurtain deployment\b",
            r"\brollover deployment\b",
            r"\bdeployment level\b",
        ],
    ),
    (
        "pretensioner_status",
        [
            r"\bpretensioner\b",
        ],
    ),
    (
        "restraint_status",
        [
            r"\bbelt switch\b",
            r"\bsafety belt\b",
            r"\bseat belt\b",
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
            r"\bseat occupancy\b",
            r"\boccupancy\b",
            r"\bpassenger seat position\b",
            r"\bseat position switch\b",
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
        "warning_lamp_status",
        [
            r"\bwarning lamp\b",
            r"\bsir warning lamp\b",
            r"\bair ?bag warning\b",
            r"\bmalfunction indicator\b",
        ],
    ),
    (
        "power_event_condition",
        [
            r"\bpower loss\b.*\bevent\b",
            r"\bpower supply status\b",
            r"\bvehicle power mode status\b",
            r"\brun/crank\b",
            r"\bremote start status\b",
        ],
    ),
    (
        "high_voltage_status",
        [
            r"\bhigh voltage disable\b",
            r"\bhigh voltage\b.*\bnotification\b",
        ],
    ),
    (
        "algorithm_status",
        [
            r"\balgorithm active\b",
            r"\balgorithm status\b",
            r"\btime from time zero to algorithm start\b",
            r"\btime from time zero to algorithm reset\b",
            r"\balgorithm enable status\b",
        ],
    ),
    (
        "sensor_validity_status",
        [
            r"\bdata validity\b",
            r"\belectronic data validity\b",
            r"\bvalidity check status\b",
            r"\bdata valid\b",
            r"\bdata invalid\b",
        ],
    ),
    (
        "other_event_condition",
        [
            r"\brsca disable\b",
            r"\bonstar\b.*\b(?:sent|deployment|status)\b",
            r"\bevent condition\b",
        ],
    ),
]


def classify_family(label):
    text = norm(label)

    for family, patterns in FAMILY_RULES:
        if any(
            re.search(
                pattern,
                text,
                re.I,
            )
            for pattern in patterns
        ):
            return family

    return ""


# ============================================================
# Strong exclusions
# ============================================================

GROUP2_PATTERNS = [
    r"\bevent recording complete\b",
    r"\bcrash record locked\b",
    r"\brecording complete\b",
    r"\bmultiple events?\b",
    r"\bevent counter\b",
    r"\brecord status\b",
    r"\bretrieval status\b",
    r"\bassociated events?\b",
    r"\bevents? not recorded\b",
    r"\btime between\b.*\bevents?\b",
    r"\bprevious crash type\b",
    r"\bevent record type\b",
    r"\btrg count\b",
    r"\btrip count\b",
]

GROUP5_PATTERNS = [
    r"\bmaximum\b.*\bdelta[- ]?v\b",
    r"\bmax(?:imum)?\b.*\bvelocity change\b",
    r"\bmaximum\b.*\brecorded vehicle velocity change\b",
    r"\bmaximum\b.*\brecorded velocity change\b",
    r"\btime\b.*\bmaximum\b.*\bdelta[- ]?v\b",
    r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
    r"\bmaximum acceleration\b",
    r"\btime\b.*\bmaximum acceleration\b",
    r"\broll angle peak\b",
    r"\bmaximum\b.*\broll angle\b",
    r"\btime from time zero to trg\b",
    r"\blength of delta[- ]?v\b",
    r"\bclipping time\b",
    r"\baccelerometer range exceeded\b",
    r"\bsensor design range exceeded\b",
    r"\brecorded side\b",
    r"\bpdof\b",
]

GROUP6_PATTERNS = [
    r"\bignition cycles? at investigation\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bsupplier id\b",
    r"\bproduction date\b",
    r"\bmodule\b.*\b(?:id|identifier|number|version)\b",
    r"\bconfiguration\b",
    r"\bconfigured for\b",
    r"\bodometer\b",
    r"\bvehicle mileage\b",
    r"\boperating time\b",
    r"\bdownload\b",
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
    r"\buser entered vin\b",
    r"\bdevice type\b",
]

TIMESERIES_AXIS_PATTERNS = [
    r"^\s*time\s*(?:\([^)]*\))?\s*$",
    r"^\s*times\s*(?:\([^)]*\))?\s*$",
    r"^\s*seconds?\s+before\b",
    r"^\s*seconds?\s+after\b",
    r"^\s*sample\s+count\b",
    r"^\s*buffer address\b",
]


def matches_any(
    text,
    patterns,
):
    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in patterns
    )


def looks_like_timeseries_axis(label):
    text = norm(label)

    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in TIMESERIES_AXIS_PATTERNS
    )


# ============================================================
# Optional Group 5 handoff support
# ============================================================

def load_group5_handoff(path: Path):
    """
    Extract labels that Group 5 explicitly routed to Group 3.

    The handoff is support only; original CSV source remains authoritative.
    """

    support = Counter()

    if not path.exists():
        return support

    for row in read_csv_dict(path):
        label = norm(
            row.get(
                "field_label_raw",
                "",
            )
        )

        if not label:
            continue

        destination = norm(
            row.get(
                "resolution_destination",
                "",
            )
        ).casefold()

        audit_family = norm(
            row.get(
                "audited_family",
                "",
            )
        ).casefold()

        audit_reason = norm(
            row.get(
                "audit_reason",
                "",
            )
        ).casefold()

        if (
            "group3"
            in destination
            or "group3"
            in audit_family
            or any(
                term in audit_reason
                for term in [
                    "deployment",
                    "restraint",
                    "event_status",
                    "event_condition",
                    "algorithm_state",
                ]
            )
        ):
            support[
                norm_key(
                    label
                )
            ] += 1

    return support


# ============================================================
# Scalar field parsing
# ============================================================

def parse_scalar_observation(row):
    nonblank = [
        (
            index,
            norm(value),
        )
        for index, value in enumerate(
            row
        )
        if norm(value)
    ]

    if len(nonblank) < 2:
        return None

    label_index, label = (
        nonblank[0]
    )

    if looks_numeric(
        label
    ):
        return None

    if len(nonblank) > 4:
        return None

    value_index, value = (
        nonblank[-1]
    )

    if value_index == label_index:
        return None

    return {
        "label_index":
            label_index,

        "label":
            label,

        "value_index":
            value_index,

        "value":
            value,

        "populated_cell_count":
            len(nonblank),
    }


# ============================================================
# Candidate scoring
# ============================================================

def score_field(
    label,
    value,
    section_heading,
    handoff_support,
):
    label_text = norm(
        label
    )

    section_text = norm(
        section_heading
    )

    family = classify_family(
        label_text
    )

    score = 0
    evidence = []
    exclusions = []

    if family:
        score += 6
        evidence.append(
            f"family:{family}"
        )

    if looks_value_like(
        value
    ):
        score += 1
        evidence.append(
            "status_or_scalar_value_like"
        )

    if re.search(
        r"\b(?:"
        r"status|deployment|pretensioner|"
        r"belt|restraint|occupant|"
        r"warning|severity|power|"
        r"high voltage|algorithm|validity"
        r")\b",
        label_text,
        re.I,
    ):
        score += 1
        evidence.append(
            "group3_terms"
        )

    if re.search(
        r"\b(?:"
        r"system status|deployment|"
        r"non[- ]deployment|restraint|"
        r"occupant|event status"
        r")\b",
        section_text,
        re.I,
    ):
        score += 1
        evidence.append(
            "group3_section_context"
        )

    support_count = handoff_support.get(
        norm_key(
            label_text
        ),
        0,
    )

    if support_count:
        score += 3
        evidence.append(
            "group5_to_group3_handoff_support"
        )

    # Explicit exclusions
    if looks_like_timeseries_axis(
        label_text
    ):
        exclusions.append(
            "group4_timeseries_axis"
        )

    if matches_any(
        label_text,
        GROUP2_PATTERNS,
    ):
        exclusions.append(
            "group2_record_structure"
        )

    if matches_any(
        label_text,
        GROUP5_PATTERNS,
    ):
        exclusions.append(
            "group5_crash_measurement"
        )

    if matches_any(
        label_text,
        GROUP6_PATTERNS,
    ):
        exclusions.append(
            "group6_technical_or_investigation"
        )

    if matches_any(
        label_text,
        GROUP1_PATTERNS,
    ):
        exclusions.append(
            "group1_report_metadata"
        )

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
            family
            or "other_event_condition",

        "score":
            score,

        "decision":
            decision,

        "evidence":
            evidence,

        "exclusions":
            exclusions,

        "handoff_support_count":
            support_count,
    }


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--report-index",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group1_v4/report_index.csv"
        ),
    )

    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(
            "data/temp"
        ),
    )

    parser.add_argument(
        "--group5-handoff",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_resolved_v1/"
            "excluded_non_group5_fields.csv"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group3_csv_discovery_v1"
        ),
    )

    args = parser.parse_args()

    if not args.report_index.exists():
        raise FileNotFoundError(
            args.report_index
        )

    report_index = read_csv_dict(
        args.report_index
    )

    handoff_support = (
        load_group5_handoff(
            args.group5_handoff
        )
    )

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates = []
    reviews = []
    excluded_overlap = []
    coverage = []
    errors = []

    label_counter = Counter()
    family_counter = Counter()
    section_counter = Counter()
    decision_counter = Counter()

    csv_selected = 0
    csv_processed = 0

    reports_with_candidates = set()
    reports_with_reviews = set()

    for index_row in report_index:

        csv_status = norm(
            index_row.get(
                "csv_status",
                ""
            )
        ).casefold()

        csv_path_text = norm(
            index_row.get(
                "csv_path",
                ""
            )
        )

        if (
            not csv_path_text
            or csv_status
            in {
                "",
                "not_available",
                "missing",
                "none",
            }
        ):
            continue

        csv_selected += 1

        csv_path = resolve_csv_path(
            index_row,
            args.source_root,
        )

        if (
            csv_path is None
            or not csv_path.exists()
        ):
            errors.append({
                **{
                    key:
                        index_row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "error_type":
                    "csv_source_not_found",

                "csv_path":
                    csv_path_text,

                "error":
                    "Could not resolve CSV source path.",
            })

            coverage.append({
                **{
                    key:
                        index_row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "csv_path":
                    csv_path_text,

                "processing_status":
                    "source_not_found",

                "candidate_count":
                    0,

                "review_count":
                    0,

                "excluded_overlap_count":
                    0,
            })

            continue

        try:
            rows = read_raw_csv(
                csv_path
            )

        except Exception as exc:
            errors.append({
                **{
                    key:
                        index_row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "error_type":
                    type(exc).__name__,

                "csv_path":
                    str(csv_path),

                "error":
                    str(exc),
            })

            coverage.append({
                **{
                    key:
                        index_row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "csv_path":
                    str(csv_path),

                "processing_status":
                    "source_error",

                "candidate_count":
                    0,

                "review_count":
                    0,

                "excluded_overlap_count":
                    0,
            })

            continue

        csv_processed += 1

        current_section = ""

        report_candidates = 0
        report_reviews = 0
        report_excluded = 0

        for row_index, row in rows:

            if is_heading_row(
                row
            ):
                current_section = (
                    populated(row)[0]
                )
                continue

            parsed = parse_scalar_observation(
                row
            )

            if parsed is None:
                continue

            label = parsed[
                "label"
            ]

            value = parsed[
                "value"
            ]

            result = score_field(
                label=label,
                value=value,
                section_heading=current_section,
                handoff_support=handoff_support,
            )

            if result[
                "decision"
            ] == "not_group3":
                continue

            event_hint = extract_event_hint(
                current_section,
                label,
            )

            candidate_id = (
                "g3csv_"
                + identifier(
                    index_row.get(
                        "report_id",
                        ""
                    ),
                    row_index,
                    label,
                    value,
                )
            )

            observation = {
                **{
                    key:
                        index_row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "group3_candidate_id":
                    candidate_id,

                "source_format":
                    "csv",

                "source_path":
                    str(csv_path),

                "source_record_index":
                    row_index,

                "source_section_heading":
                    current_section,

                "event_hint":
                    event_hint,

                "field_label_raw":
                    label,

                "field_value_raw":
                    value,

                "value_column_index":
                    parsed[
                        "value_index"
                    ],

                "populated_cell_count":
                    parsed[
                        "populated_cell_count"
                    ],

                "source_row_json":
                    json.dumps(
                        row,
                        ensure_ascii=False,
                    ),

                "candidate_family":
                    result[
                        "family"
                    ],

                "candidate_score":
                    result[
                        "score"
                    ],

                "discovery_decision":
                    result[
                        "decision"
                    ],

                "evidence_json":
                    json.dumps(
                        result[
                            "evidence"
                        ],
                        ensure_ascii=False,
                    ),

                "overlap_exclusions_json":
                    json.dumps(
                        result[
                            "exclusions"
                        ],
                        ensure_ascii=False,
                    ),

                "group5_handoff_support_count":
                    result[
                        "handoff_support_count"
                    ],

                "semantic_normalization_status":
                    "not_normalized",

                "unit_conversion_status":
                    "not_converted",

                "event_link_status":
                    (
                        "source_hint_only"
                        if event_hint
                        else "not_linked"
                    ),
            }

            decision_counter[
                result[
                    "decision"
                ]
            ] += 1

            if result[
                "decision"
            ] == "candidate":

                candidates.append(
                    observation
                )

                report_candidates += 1

                reports_with_candidates.add(
                    index_row.get(
                        "report_id",
                        ""
                    )
                )

                label_counter[
                    norm_key(label)
                ] += 1

                family_counter[
                    result[
                        "family"
                    ]
                ] += 1

                section_counter[
                    norm(
                        current_section
                    )
                    or "<no_section_heading>"
                ] += 1

            elif result[
                "decision"
            ] == "review":

                reviews.append(
                    observation
                )

                report_reviews += 1

                reports_with_reviews.add(
                    index_row.get(
                        "report_id",
                        ""
                    )
                )

            elif result[
                "decision"
            ] == "excluded_overlap":

                excluded_overlap.append(
                    observation
                )

                report_excluded += 1

        if report_candidates:
            status = (
                "group3_candidates_found"
            )

        elif report_reviews:
            status = (
                "review_only"
            )

        else:
            status = (
                "no_group3_candidates"
            )

        coverage.append({
            **{
                key:
                    index_row.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "csv_path":
                str(csv_path),

            "processing_status":
                status,

            "candidate_count":
                report_candidates,

            "review_count":
                report_reviews,

            "excluded_overlap_count":
                report_excluded,
        })

        if (
            csv_processed % 100 == 0
            or csv_processed
            == csv_selected
        ):
            print(
                "Discovered Group 3 CSV "
                f"{csv_processed}/"
                f"{csv_selected} reports...",
                flush=True,
            )

    # ========================================================
    # Summaries
    # ========================================================

    raw_label_examples = defaultdict(
        Counter
    )

    for row in candidates:
        key = norm_key(
            row[
                "field_label_raw"
            ]
        )

        raw_label_examples[
            key
        ][
            row[
                "field_label_raw"
            ]
        ] += 1

    label_summary = []

    for key, count in (
        label_counter.most_common()
    ):
        examples = [
            label
            for label, _
            in raw_label_examples[
                key
            ].most_common(
                5
            )
        ]

        label_summary.append({
            "normalized_label":
                key,

            "candidate_count":
                count,

            "raw_label_examples_json":
                json.dumps(
                    examples,
                    ensure_ascii=False,
                ),
        })

    family_summary = [
        {
            "candidate_family":
                family,

            "candidate_count":
                count,
        }
        for family, count
        in family_counter.most_common()
    ]

    section_summary = [
        {
            "source_section_heading":
                section,

            "candidate_count":
                count,
        }
        for section, count
        in section_counter.most_common()
    ]

    # ========================================================
    # Write
    # ========================================================

    candidate_columns = [
        *BASE,
        "group3_candidate_id",
        "source_format",
        "source_path",
        "source_record_index",
        "source_section_heading",
        "event_hint",
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
        "group5_handoff_support_count",
        "semantic_normalization_status",
        "unit_conversion_status",
        "event_link_status",
    ]

    write_csv(
        out
        / "group3_candidate_fields.csv",
        candidates,
        candidate_columns,
    )

    write_csv(
        out
        / "group3_review_fields.csv",
        reviews,
        candidate_columns,
    )

    write_csv(
        out
        / "group3_excluded_overlap_fields.csv",
        excluded_overlap,
        candidate_columns,
    )

    write_csv(
        out
        / "group3_report_coverage.csv",
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
        out
        / "group3_label_summary.csv",
        label_summary,
        [
            "normalized_label",
            "candidate_count",
            "raw_label_examples_json",
        ],
    )

    write_csv(
        out
        / "group3_family_summary.csv",
        family_summary,
        [
            "candidate_family",
            "candidate_count",
        ],
    )

    write_csv(
        out
        / "group3_section_summary.csv",
        section_summary,
        [
            "source_section_heading",
            "candidate_count",
        ],
    )

    write_csv(
        out
        / "errors.csv",
        errors,
        [
            *BASE,
            "error_type",
            "csv_path",
            "error",
        ],
    )

    coverage_counts = Counter(
        row[
            "processing_status"
        ]
        for row in coverage
    )

    # ========================================================
    # Metadata
    # ========================================================

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 3 - Event conditions, deployment, and status information",

        "stage":
            "CSV discovery",

        "reports_in_index":
            len(
                report_index
            ),

        "csv_reports_selected":
            csv_selected,

        "csv_reports_processed":
            csv_processed,

        "reports_with_group3_candidates":
            len(
                reports_with_candidates
            ),

        "reports_with_review_fields":
            len(
                reports_with_reviews
            ),

        "candidate_field_count":
            len(
                candidates
            ),

        "review_field_count":
            len(
                reviews
            ),

        "excluded_overlap_field_count":
            len(
                excluded_overlap
            ),

        "candidate_family_counts":
            dict(
                family_counter
            ),

        "decision_counts":
            dict(
                decision_counter
            ),

        "coverage_status_counts":
            dict(
                coverage_counts
            ),

        "unique_candidate_labels":
            len(
                label_counter
            ),

        "group5_handoff_available":
            args.group5_handoff.exists(),

        "group5_handoff_support_label_count":
            len(
                handoff_support
            ),

        "source_errors":
            len(
                errors
            ),

        "scope":
            (
                "CSV-first discovery for Group 3 event conditions, "
                "deployment, restraint, occupant, warning/status, power, "
                "high-voltage, algorithm, validity, and similar event-state "
                "information. Original CSV exports remain authoritative. "
                "Prior Group 5 routing evidence is used only as optional "
                "support. Group 2 record structure, Group 4 time-series, "
                "Group 5 scalar crash-dynamics measurements, and Group 6 "
                "technical/investigation metadata are explicitly excluded. "
                "No semantic normalization, unit conversion, fuzzy event "
                "identity inference, PDF processing, or final extraction "
                "is performed."
            ),
    }

    tmp = (
        out
        / "metadata.json.part"
    )

    tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        out
        / "metadata.json"
    )

    print()
    print(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        f"Outputs: {out}"
    )

    print()
    print(
        "GROUP 3 CSV DISCOVERY COMPLETE."
    )


if __name__ == "__main__":
    main()
