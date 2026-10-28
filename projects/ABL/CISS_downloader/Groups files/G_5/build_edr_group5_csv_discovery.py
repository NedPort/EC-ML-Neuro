"""
Discover Group 5 CSV candidates: non-time-series crash/event measurements.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Optional supporting handoff
---------------------------
data/processed/edr/group4_final_v1/timeseries_companion_metadata.csv

Source
------
Original CSV exports referenced by report_index.csv.

Output
------
data/processed/edr/group5_csv_discovery_v1/

    group5_candidate_fields.csv
    group5_review_fields.csv
    group5_report_coverage.csv
    group5_label_summary.csv
    group5_family_summary.csv
    group5_section_summary.csv
    errors.csv
    metadata.json

Purpose
-------
Discover scalar / summary crash-event measurements that belong to Group 5.

Examples include:
- maximum/final Delta-V or recorded velocity-change summaries
- longitudinal/lateral/resultant velocity-change summaries
- time of maximum Delta-V / maximum recorded velocity change
- peak acceleration
- peak/max roll angle
- peak/max angular rate
- crash pulse / Delta-V duration or length
- clipping time / accelerometer-range-exceeded timing
- recorded side / crash direction / PDOF-like scalar fields

Important boundaries
--------------------
Group 4:
    repeated time-series rows remain excluded.

Group 3:
    deployment command timing, restraint/occupant/deployment/status fields,
    DTCs, warning lamps, etc. are not Group 5.

Group 6:
    module configuration, technical identifiers, investigation fields, etc.
    are not Group 5 unless a field is independently a crash measurement.

This is a DISCOVERY stage only:
- no semantic normalization
- no unit conversion
- no event-identity inference
- no source modification
- no final structured extraction

The original CSV remains authoritative. Group 4 companion metadata is used
only as optional supporting evidence.
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
# General helpers
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

    # Allow numeric source values with common unit suffixes.
    text = re.sub(
        r"\s*(?:"
        r"mph|km/h|kph|m/s|m/s\^2|g|"
        r"ms|msec|milliseconds?|"
        r"sec|seconds?|"
        r"deg|degrees?|deg/s|rad/s|"
        r"%|percent"
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
        "n/a",
        "na",
        "sna",
        "not available",
        "data not available",
        "unknown",
        "invalid",
    }:
        return True

    # Some direction/side scalar measurements are textual.
    if re.fullmatch(
        r"(?:"
        r"left|right|front|rear|"
        r"frontal|side|rollover|"
        r"longitudinal|lateral|"
        r"positive|negative"
        r")",
        text,
        re.I,
    ):
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

        # On Windows this is usually already a valid path. This fallback
        # also helps if the project was moved but the basename is unchanged.
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
                    # Prefer cdr_exports.
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
# Section-heading detection
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

    # Common CDR headings are often uppercase, title-like, or end in DATA.
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
            r"data|status|summary|"
            r"information|configuration|"
            r"event|retrieval|deployment|"
            r"non[- ]deployment|"
            r"crash|rollover|"
            r"delta[- ]?v|velocity change|"
            r"system"
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
# Group 5 family rules
# ============================================================

FAMILY_RULES = [
    (
        "delta_v_summary",
        [
            r"\bmaximum\b.*\bdelta[- ]?v\b",
            r"\bmax(?:imum)?\b.*\bvelocity change\b",
            r"\bmaximum\b.*\brecorded vehicle velocity change\b",
            r"\bmaximum\b.*\brecorded velocity change\b",
            r"\bfinal\b.*\bdelta[- ]?v\b",
            r"\bfinal\b.*\bvelocity change\b",
            r"\bresultant\b.*\bdelta[- ]?v\b",
            r"\bresultant\b.*\bvelocity change\b",
            r"\blongitudinal\b.*\bvelocity change\b",
            r"\blateral\b.*\bvelocity change\b",
            r"\blongitudinal\b.*\bdelta[- ]?v\b",
            r"\blateral\b.*\bdelta[- ]?v\b",
        ],
    ),
    (
        "delta_v_timing",
        [
            r"\btime\b.*\bmaximum\b.*\bdelta[- ]?v\b",
            r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
            r"\balgorithm enable\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime from algorithm enable\b.*\bmaximum\b",
            r"\btime\b.*\bmax(?:imum)?\b.*\brecorded velocity change\b",
            r"\btime\b.*\bmax(?:imum)?\b.*\brecorded vehicle velocity change\b",
        ],
    ),
    (
        "acceleration_summary",
        [
            r"\b(?:maximum|max|peak)\b.*\bacceleration\b",
            r"\bacceleration\b.*\b(?:maximum|max|peak)\b",
            r"\bpeak\b.*\bg\b",
        ],
    ),
    (
        "roll_summary",
        [
            r"\b(?:maximum|max|peak)\b.*\broll angle\b",
            r"\broll angle\b.*\b(?:maximum|max|peak)\b",
            r"\brollangle peak\b",
        ],
    ),
    (
        "angular_rate_summary",
        [
            r"\b(?:maximum|max|peak)\b.*\b(?:angular rate|yaw rate|roll rate)\b",
            r"\b(?:angular rate|yaw rate|roll rate)\b.*\b(?:maximum|max|peak)\b",
        ],
    ),
    (
        "duration_length",
        [
            r"\blength of\b.*\bdelta[- ]?v\b",
            r"\bduration\b.*\bdelta[- ]?v\b",
            r"\bduration\b.*\bcrash pulse\b",
            r"\bcrash pulse\b.*\bduration\b",
            r"\bdelta[- ]?v\b.*\bduration\b",
        ],
    ),
    (
        "range_clipping_timing",
        [
            r"\bclipping time\b",
            r"\baccelerometer range exceeded\b",
            r"\btime\b.*\baccelerometer\b.*\brange exceeded\b",
        ],
    ),
    (
        "direction_summary",
        [
            r"\bpdof\b",
            r"\bprincipal direction of force\b",
            r"\bcrash direction\b",
            r"\brecorded direction\b",
            r"\brecorded side\b",
            r"\bprincipal direction\b",
        ],
    ),
    (
        "trigger_relative_timing",
        [
            r"\btime from time zero to trg\b",
            r"\btime zero\b.*\btrg\b",
            r"\btime\b.*\btrigger\b",
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
# Strong Group 3 / Group 2 / Group 6 exclusions
# ============================================================

GROUP3_PATTERNS = [
    r"\bair ?bag\b",
    r"\bpretensioner\b",
    r"\bdeployment command\b",
    r"\bdeployment criteria\b",
    r"\b1st stage\b",
    r"\b2nd stage\b",
    r"\bbelt switch\b",
    r"\bseat belt\b",
    r"\boccupant\b",
    r"\bpassenger classification\b",
    r"\bsuppression\b",
    r"\bwarning lamp\b",
    r"\bsir\b",
    r"\bdtc\b",
    r"\bdiagnostic trouble\b",
    r"\bseat position\b",
    r"\brestraint\b",
]

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
]

GROUP6_PATTERNS = [
    r"\bignition cycles?\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bmodule\b",
    r"\bconfiguration\b",
    r"\bconfigured for\b",
    r"\bdownload\b",
    r"\binvestigation\b",
    r"\bvin\b",
    r"\bvehicle identification number\b",
]

GROUP1_PATTERNS = [
    r"\bfilename\b",
    r"\bimaged with\b",
    r"\breported with\b",
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
    r"\buser entered vin\b",
    r"\bdevice type\b",
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


# ============================================================
# Time-series exclusion
# ============================================================

TIMESERIES_AXIS_PATTERNS = [
    r"^\s*time\s*(?:\([^)]*\))?\s*$",
    r"^\s*times\s*(?:\([^)]*\))?\s*$",
    r"^\s*seconds?\s+before\b",
    r"^\s*seconds?\s+after\b",
    r"^\s*sample\s+count\b",
    r"^\s*buffer address\b",
]


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
# Group 4 companion handoff support
# ============================================================

def load_companion_label_support(path: Path):
    """
    Build a normalized-label support set from Group 4 companion metadata.
    This is supporting evidence only.
    """

    support = Counter()

    if not path.exists():
        return support

    rows = read_csv_dict(path)

    for row in rows:
        raw_json = row.get(
            "source_rows_json",
            "",
        )

        if raw_json:
            try:
                source_rows = json.loads(
                    raw_json
                )
            except (
                json.JSONDecodeError,
                TypeError,
            ):
                source_rows = []

            if isinstance(
                source_rows,
                list,
            ):
                for source_row in source_rows:
                    if not isinstance(
                        source_row,
                        list,
                    ):
                        continue

                    _, label = (
                        first_populated_with_index(
                            source_row
                        )
                    )

                    key = norm_key(label)

                    if key:
                        support[key] += 1

        for field in (
            "source_heading_hint",
            "source_heading",
        ):
            key = norm_key(
                row.get(
                    field,
                    ""
                )
            )

            if key:
                support[key] += 1

    return support


# ============================================================
# Candidate scoring
# ============================================================

def score_field(
    label,
    value,
    section_heading,
    companion_support,
):
    label_text = norm(label)
    section_text = norm(
        section_heading
    )

    combined = (
        label_text
        + " | "
        + section_text
    )

    family = classify_family(
        label_text
    )

    score = 0
    evidence = []
    exclusions = []

    # --------------------------------------------------------
    # Strong positive family evidence
    # --------------------------------------------------------

    if family:
        if family in {
            "delta_v_summary",
            "delta_v_timing",
            "acceleration_summary",
            "roll_summary",
            "angular_rate_summary",
            "direction_summary",
        }:
            score += 6
        else:
            score += 5

        evidence.append(
            f"family:{family}"
        )

    # Generic crash-measurement cues.
    if re.search(
        r"\b(?:"
        r"maximum|max|peak|final|"
        r"resultant|velocity change|"
        r"delta[- ]?v|acceleration|"
        r"roll angle|angular rate|"
        r"yaw rate|roll rate|"
        r"clipping|recorded side|pdof"
        r")\b",
        label_text,
        re.I,
    ):
        score += 1
        evidence.append(
            "crash_measurement_terms"
        )

    # Scalar-like value.
    if looks_value_like(
        value
    ):
        score += 1
        evidence.append(
            "scalar_value_like"
        )

    # Event/crash context can modestly support a candidate.
    if re.search(
        r"\b(?:"
        r"crash|event|deployment|"
        r"non[- ]deployment|"
        r"delta[- ]?v|velocity change"
        r")\b",
        section_text,
        re.I,
    ):
        score += 1
        evidence.append(
            "event_or_crash_section_context"
        )

    # Optional Group 4 handoff support.
    support_count = companion_support.get(
        norm_key(
            label_text
        ),
        0,
    )

    if support_count:
        score += 2
        evidence.append(
            "group4_companion_handoff_support"
        )

    # --------------------------------------------------------
    # Strong exclusions
    # --------------------------------------------------------

    if looks_like_timeseries_axis(
        label_text
    ):
        exclusions.append(
            "group4_timeseries_axis"
        )

    if matches_any(
        label_text,
        GROUP3_PATTERNS,
    ):
        # Do not exclude a true Delta-V summary merely because a broad
        # section happens to say Deployment. Exclusion is label-based.
        exclusions.append(
            "group3_deployment_status"
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

    # Explicit deployment timing is Group 3, even though it contains "time".
    if re.search(
        r"\btime\b.*\bdeployment\b",
        label_text,
        re.I,
    ) and not re.search(
        r"\bmaximum\b.*\bvelocity change\b",
        label_text,
        re.I,
    ):
        if (
            "group3_deployment_status"
            not in exclusions
        ):
            exclusions.append(
                "group3_deployment_status"
            )

    # Event-to-event timing is structural/contextual rather than a crash
    # dynamic measurement for this extraction grouping.
    if re.search(
        r"\btime between\b.*\bevents?\b",
        label_text,
        re.I,
    ):
        exclusions.append(
            "group2_event_relationship_timing"
        )

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    if exclusions:
        decision = "excluded_overlap"

    elif score >= 6:
        decision = "candidate"

    elif score >= 3:
        decision = "review"

    else:
        decision = "not_group5"

    return {
        "family":
            family
            or "other_crash_measurement",

        "score":
            score,

        "decision":
            decision,

        "evidence":
            evidence,

        "exclusions":
            exclusions,

        "group4_companion_support_count":
            support_count,
    }


# ============================================================
# Parse scalar-like observations
# ============================================================

def parse_scalar_observation(
    row,
):
    """
    Return (label, value, value_column_index) for a likely field-value row.

    Discovery is intentionally conservative:
    - at least two populated cells
    - first populated cell must be textual
    - later rows of obvious numeric time-series are rejected elsewhere
    """

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

    # For ordinary scalar rows, the next populated cell is usually the value.
    # If there are only a few cells, use the last populated cell because some
    # layouts include a separate unit/middle column.
    if len(nonblank) <= 4:
        value_index, value = (
            nonblank[-1]
        )
    else:
        # Very wide rows are more likely tables/time-series than scalars.
        return None

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
        "--group4-companion",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_final_v1/"
            "timeseries_companion_metadata.csv"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_discovery_v1"
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

    companion_support = (
        load_companion_label_support(
            args.group4_companion
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

    for report_number, index_row in enumerate(
        report_index,
        1,
    ):

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

        # Select reports that appear to have an available CSV.
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

            # Very common time-series/data-table headers should not enter
            # scalar discovery even if they are only two cells wide.
            if looks_like_timeseries_axis(
                label
            ):
                continue

            result = score_field(
                label=label,
                value=value,
                section_heading=current_section,
                companion_support=companion_support,
            )

            if result[
                "decision"
            ] == "not_group5":
                continue

            event_hint = extract_event_hint(
                current_section,
                label,
            )

            candidate_id = (
                "g5csv_"
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

                "group5_candidate_id":
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

                "group4_companion_support_count":
                    result[
                        "group4_companion_support_count"
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
                "group5_candidates_found"
            )

        elif report_reviews:
            status = (
                "review_only"
            )

        else:
            status = (
                "no_group5_candidates"
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
                "Discovered Group 5 CSV "
                f"{csv_processed}/"
                f"{csv_selected} reports...",
                flush=True,
            )

    # ========================================================
    # Summaries
    # ========================================================

    label_summary = []

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
    # Output
    # ========================================================

    candidate_columns = [
        *BASE,
        "group5_candidate_id",
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
        "group4_companion_support_count",
        "semantic_normalization_status",
        "unit_conversion_status",
        "event_link_status",
    ]

    write_csv(
        out
        / "group5_candidate_fields.csv",
        candidates,
        candidate_columns,
    )

    write_csv(
        out
        / "group5_review_fields.csv",
        reviews,
        candidate_columns,
    )

    # Keep excluded overlap evidence because it will help us refine Group 3/6
    # routing later, but it is not part of the Group 5 candidate population.
    write_csv(
        out
        / "group5_excluded_overlap_fields.csv",
        excluded_overlap,
        candidate_columns,
    )

    write_csv(
        out
        / "group5_report_coverage.csv",
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
        / "group5_label_summary.csv",
        label_summary,
        [
            "normalized_label",
            "candidate_count",
            "raw_label_examples_json",
        ],
    )

    write_csv(
        out
        / "group5_family_summary.csv",
        family_summary,
        [
            "candidate_family",
            "candidate_count",
        ],
    )

    write_csv(
        out
        / "group5_section_summary.csv",
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
            "Group 5 - Non-time-series crash and event measurements",

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

        "reports_with_group5_candidates":
            len(
                reports_with_candidates
            ),

        "reports_with_review_only_or_review_fields":
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

        "group4_companion_handoff_available":
            args.group4_companion.exists(),

        "group4_companion_support_label_count":
            len(
                companion_support
            ),

        "source_errors":
            len(
                errors
            ),

        "scope":
            (
                "CSV-first discovery for Group 5 scalar/non-time-series "
                "crash and event measurements. Original CSV exports are "
                "authoritative. Group 4 companion metadata is used only "
                "as optional supporting evidence. Candidate families "
                "include Delta-V/velocity-change summaries, timing of "
                "maximum velocity change, peak acceleration, roll and "
                "angular summaries, duration/length fields, clipping or "
                "accelerometer-range timing, recorded side/direction, "
                "and similar scalar crash-dynamics measurements. "
                "Repeated temporal structures remain Group 4. "
                "Deployment/restraint/status fields are excluded toward "
                "Group 3; record-structure fields toward Group 2; "
                "technical/investigation fields toward Group 6. "
                "No semantic normalization, unit conversion, event "
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
        "GROUP 5 CSV DISCOVERY COMPLETE."
    )


if __name__ == "__main__":
    main()
