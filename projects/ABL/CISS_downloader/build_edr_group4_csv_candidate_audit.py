"""
Audit and clean Group 4 CSV time-series discovery candidates.

This stage operates on the discovery outputs only. It does NOT reread
the original CSV reports.

It combines:
    timeseries_candidate_sections.csv
    review_sections.csv

and classifies sections into:

1. accepted time-series sections
2. companion metadata for time-series sections
3. excluded known non-time-series structures
4. residual review sections

Two structural orientations are recognized:

A. samples_by_rows
   Time | Signal A | Signal B
   -5   | ...
   -4   | ...

B. samples_by_columns
   Time       | -5 | -4 | -3
   Speed      | ...
   Brake      | ...

No signal semantics, units, event identities, or values are normalized.
"""

from __future__ import annotations

import argparse
import csv
import json
import re

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


csv.field_size_limit(10_000_000)


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
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
):
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
        )
        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


# ============================================================
# Helpers
# ============================================================
def is_crash_pulse_scalar_companion(
    heading,
    rows,
):
    """
    Identify crash-pulse sections that contain scalar metadata
    describing a time-series record but do not contain sampled
    measurements themselves.
    """

    if "CRASH PULSE" not in heading.upper():
        return False

    useful_rows = [
        populated(row)
        for row in rows
        if populated(row)
    ]

    if not useful_rows:
        return False

    max_width = max(
        len(row)
        for row in useful_rows
    )

    # Scalar field/value structures only.
    if max_width > 2:
        return False

    text = " ".join(
        " ".join(row)
        for row in useful_rows
    )

    metadata_patterns = [
        r"Recording Status.*Time Series",
        r"Time from TRG to Next Sample",
        r"Maximum Delta-V",
        r"Time,\s*Maximum Delta-V",
        r"Clipping Time",
        r"Length of Delta-V",
        r"RollAngle Peak",
        r"Roll Angle at the Time of TRG",
    ]

    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in metadata_patterns
    )
def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )


def load_rows(value):
    try:
        parsed = json.loads(value)

        if isinstance(parsed, list):
            return parsed

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        pass

    return []


def populated(row):
    return [
        norm(value)
        for value in row
        if norm(value)
    ]


def clean_numeric_token(value):
    """
    Normalize formatting only for structural detection.

    Examples:
        "- 5.0" -> "-5.0"
        "+ 2"   -> "+2"

    Original source values are never changed in outputs.
    """

    text = norm(value)

    text = re.sub(
        r"^([+-])\s+",
        r"\1",
        text,
    )

    text = text.replace(
        ",",
        "",
    )

    return text


def is_numeric(value):
    text = clean_numeric_token(
        value
    )

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def is_time_value(value):
    """
    Allow simple annotation after a numeric time value.

    Examples:
        0 (TRG)
        -5.0
        100
    """

    text = norm(value)

    text = re.sub(
        r"\([^)]*\)\s*$",
        "",
        text,
    )

    return is_numeric(
        text
    )


# ============================================================
# Structural evidence
# ============================================================

def count_sample_rows(rows):
    """
    Samples-by-rows orientation.

    Count rows with:
    - at least two populated cells
    - numeric first populated cell
    """

    count = 0

    for row in rows:

        values = populated(
            row
        )

        if len(values) < 2:
            continue

        if is_numeric(
            values[0]
        ):
            count += 1

    return count


def detect_transposed_time_axis(rows):
    """
    Detect samples-by-columns orientation.

    Supports both explicit time coordinates and ordered sample counts.

    Examples:

        Time (sec)      -5  -4  -3  -2
        Vehicle Speed   ...

    or

        Pre-Crash Sample Count from TRG
                        -5 count  -4 count ... 0 (TRG)
        Vehicle Speed   ...
    """

    for row_index, row in enumerate(rows[:8]):

        if not row:
            continue

        first = norm(
            row[0]
            if row
            else ""
        )

        # ----------------------------------------------------
        # Explicit time axis
        # ----------------------------------------------------

        explicit_time_header = bool(
            re.search(
                r"\b(?:"
                r"time|"
                r"seconds?|"
                r"sec|"
                r"msec|"
                r"ms"
                r")\b",
                first,
                re.I,
            )
        )

        # ----------------------------------------------------
        # Relative sample-count axis
        # ----------------------------------------------------

        sample_count_header = bool(
            re.search(
                r"\bsample\s+count\b",
                first,
                re.I,
            )
            and re.search(
                r"\bTRG\b",
                first,
                re.I,
            )
        )

        if not (
            explicit_time_header
            or sample_count_header
        ):
            continue

        sample_values = [
            value
            for value in row[1:]
            if norm(value)
        ]

        valid_count = 0

        for value in sample_values:

            text = norm(value)

            # Remove trigger annotation.
            text = re.sub(
                r"\([^)]*\)\s*$",
                "",
                text,
            )

            # Remove "count" suffix.
            text = re.sub(
                r"\s*count\s*$",
                "",
                text,
                flags=re.I,
            )

            if is_numeric(text):
                valid_count += 1

        if valid_count >= 2:

            axis_type = (
                "sample_count_relative_to_trigger"
                if sample_count_header
                else "explicit_time"
            )

            return (
                True,
                row_index,
                valid_count,
                axis_type,
            )

    return (
        False,
        "",
        0,
        "",
    )

def detect_buffer_axis(rows):
    """
    PCM-style ordered buffer table.
    """

    text = " ".join(
        " ".join(
            populated(row)
        )
        for row
        in rows[:6]
    )

    return bool(
        re.search(
            r"\bbuffer\s+address\b",
            text,
            re.I,
        )
    )


# ============================================================
# Known exclusions / companion metadata
# ============================================================

def classify_known_non_timeseries(
    heading,
):
    h = (
        heading
        .upper()
        .replace(
            "_",
            "-",
        )
    )

    if (
        "EVENT RECORD SUMMARY"
        in h
    ):
        return (
            "excluded_group2_summary",
            "Event record summary is a Group 2 record/retrieval structure, not a time series.",
        )

    if re.search(
        r"\bDTCS?\s+PRESENT\b",
        h,
    ):
        return (
            "excluded_dtc_structure",
            "DTC/PID structure is not a temporal measurement sequence.",
        )

    if (
        "DEPLOYMENT COMMAND DATA"
        in h
        or re.match(
            r"^DEPLOYMENT DATA\b",
            h,
        )
    ):
        return (
            "excluded_deployment_scalar",
            "Deployment timing/status fields are scalar event information rather than repeated samples.",
        )

    if (
        "SYSTEM STATUS"
        in h
        or "SYSTEM CONFIGURATION"
        in h
    ):
        return (
            "excluded_status_configuration",
            "System status/configuration table is scalar/contextual information.",
        )

    if (
        "1 SAMPLE"
        in h
        or re.search(
            r"\bPRE-CRASH DATA -1 SEC\b",
            h,
        )
    ):
        return (
            "excluded_single_snapshot",
            "Single pre-crash snapshot is not treated as a repeated time series.",
        )

    return (
        "",
        "",
    )


def is_companion_metadata(
    heading,
):
    h = heading.upper()

    # Common CDR pattern:
    # table 1 contains metadata/status,
    # table 2 contains actual sampled pulse data.
    if (
        "CRASH PULSE"
        in h
        and "TABLE 1 OF 2"
        in h
    ):
        return True

    return False


# ============================================================
# Family/component routing
# ============================================================

def structural_family(
    heading,
):
    h = (
        heading
        .upper()
        .replace(
            "_",
            "-",
        )
    )

    # Order matters.

    if "PCM EDR DATA" in h:
        return "pcm_edr"

    if re.search(
        r"\bPRE-CRASH\b",
        h,
    ):
        return "pre_crash"

    if re.search(
        r"\bPOST-CRASH\b",
        h,
    ):
        return "post_crash"

    if "CRASH PULSE" in h:
        return "crash_pulse"

    if re.search(
        r"\bDELTA[- ]?V\b",
        h,
    ) or re.search(
        r"\bVELOCITY CHANGE\b",
        h,
    ):
        return "delta_v"

    if "ROLL ANGLE" in h:
        return "roll_angle"

    if re.search(
        r"\bROLL RATE\b",
        h,
    ) or re.search(
        r"\bANGULAR RATE\b",
        h,
    ):
        return "angular_rate"

    if "ACCELERATION" in h:
        return "acceleration"

    if (
        "PERIPHERAL SENSOR"
        in h
        or "PRESSURE SENSOR"
        in h
        or "SATELLITE SENSOR"
        in h
        or "LOW-G Z"
        in h
    ):
        return "sensor_timeseries"

    if "ROLLOVER SENSOR DATA" in h:
        return "rollover_sensor"

    if re.search(
        r"\bVEHICLE\s+LONGITUDINAL\s+VELOCITY\b",
        h,
    ):
        return "velocity"

    return "other_timeseries"


def component(
    heading,
):
    h = heading.upper()

    has_longitudinal = (
        "LONGITUDINAL"
        in h
    )

    has_lateral = (
        "LATERAL"
        in h
    )

    if (
        has_longitudinal
        and has_lateral
    ):
        return "longitudinal_lateral"

    if has_longitudinal:
        return "longitudinal"

    if has_lateral:
        return "lateral"

    if (
        "NORMAL"
        in h
        or "VERTICAL"
        in h
        or "LOW-G Z"
        in h
    ):
        return "normal_vertical"

    if (
        "ROLL"
        in h
        or "ANGULAR"
        in h
    ):
        return "roll_angular"

    if re.search(
        r"\bSENSOR X\b",
        h,
    ):
        return "x"

    if re.search(
        r"\bSENSOR Y\b",
        h,
    ):
        return "y"

    return "unspecified"


# ============================================================
# Main classification
# ============================================================

def audit_row(
    row,
    discovery_origin,
):
    heading = norm(
        row.get(
            "source_heading",
            "",
        )
    )

    rows = load_rows(
        row.get(
            "source_rows_json",
            "",
        )
    )

    sample_row_count = (
        count_sample_rows(
            rows
        )
    )

    (
        transposed,
        transposed_time_row,
        transposed_sample_count,
        transposed_axis_type,
    ) = detect_transposed_time_axis(
        rows
    )

    buffer_axis = (
        detect_buffer_axis(
            rows
        )
    )

    exclusion_status, exclusion_reason = (
        classify_known_non_timeseries(
            heading
        )
    )

    family = structural_family(
        heading
    )

    axis_component = component(
        heading
    )

    orientation = ""

    if buffer_axis:
        orientation = (
            "buffer_order_table"
        )

    elif sample_row_count >= 2:
        orientation = (
            "samples_by_rows"
        )

    elif transposed:
        orientation = (
            "samples_by_columns"
        )

    # --------------------------------------------------------
    # Known exclusions have priority.
    # --------------------------------------------------------

    if exclusion_status:

        final_status = (
            exclusion_status
        )

        decision = (
            "exclude_from_group4"
        )

        reason = (
            exclusion_reason
        )

    # --------------------------------------------------------
    # Companion metadata is retained separately.
    # --------------------------------------------------------

    elif is_companion_metadata(
        heading
    ):

        final_status = (
            "timeseries_companion_metadata"
        )

        decision = (
            "preserve_as_companion_metadata"
        )

        reason = (
            "Crash-pulse Table 1 of 2 appears to contain "
            "metadata/status associated with the sampled table."
        )
    elif is_crash_pulse_scalar_companion(
        heading,
        rows,
    ):

        final_status = (
            "timeseries_companion_metadata"
        )

        decision = (
            "preserve_as_companion_metadata"
        )

        reason = (
            "Crash-pulse section contains scalar metadata "
            "describing the associated sampled time-series record, "
            "but does not itself contain repeated measurements."
        )
    # --------------------------------------------------------
    # PCM accepted through structural buffer evidence.
    # --------------------------------------------------------

    elif (
        family
        == "pcm_edr"
        and buffer_axis
    ):

        final_status = (
            "accepted_timeseries"
        )

        decision = (
            "accept"
        )

        reason = (
            "PCM EDR table contains an ordered buffer/time structure."
        )

    # --------------------------------------------------------
    # Ordinary samples-down-rows tables.
    # --------------------------------------------------------

    elif sample_row_count >= 2:

        final_status = (
            "accepted_timeseries"
        )

        decision = (
            "accept"
        )

        reason = (
            "At least two repeated numeric-axis sample rows were detected."
        )

    # --------------------------------------------------------
    # Transposed time-series tables.
    # --------------------------------------------------------

    elif transposed:

        final_status = (
            "accepted_timeseries"
        )

        decision = (
            "accept"
        )

        reason = (
            "A time-axis row with multiple sample coordinates "
            "was detected across columns."
        )

    # --------------------------------------------------------
    # Everything else remains visible for review.
    # --------------------------------------------------------

    else:

        final_status = (
            "requires_structural_review"
        )

        decision = (
            "review"
        )

        reason = (
            "Heading suggests possible temporal content, but repeated "
            "sample structure was not demonstrated conservatively."
        )

    return {
        **row,

        "discovery_origin":
            discovery_origin,

        "audit_decision":
            decision,
            
        "transposed_axis_type":
            transposed_axis_type,

        "audit_status":
            final_status,

        "audit_reason":
            reason,

        "audited_family":
            family,

        "audited_component":
            axis_component,

        "table_orientation":
            orientation,

        "sample_row_count":
            sample_row_count,

        "transposed_time_axis":
            transposed,

        "transposed_time_row_index":
            transposed_time_row,

        "transposed_sample_count":
            transposed_sample_count,

        "audited_buffer_axis":
            buffer_axis,
    }


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--discovery-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_discovery_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_audit_v1"
        ),
    )

    args = parser.parse_args()

    discovery = (
        args.discovery_directory
    )

    candidate_path = (
        discovery
        / "timeseries_candidate_sections.csv"
    )

    review_path = (
        discovery
        / "review_sections.csv"
    )

    if not candidate_path.exists():
        raise FileNotFoundError(
            candidate_path
        )

    if not review_path.exists():
        raise FileNotFoundError(
            review_path
        )

    candidates = read_csv(
        candidate_path
    )

    reviews = read_csv(
        review_path
    )

    audited = []

    for row in candidates:
        audited.append(
            audit_row(
                row,
                "discovery_candidate",
            )
        )

    for row in reviews:
        audited.append(
            audit_row(
                row,
                "near_threshold_review",
            )
        )

    accepted = [
        row
        for row in audited
        if row[
            "audit_decision"
        ]
        == "accept"
    ]

    companion = [
        row
        for row in audited
        if row[
            "audit_decision"
        ]
        == "preserve_as_companion_metadata"
    ]

    excluded = [
        row
        for row in audited
        if row[
            "audit_decision"
        ]
        == "exclude_from_group4"
    ]

    remaining_review = [
        row
        for row in audited
        if row[
            "audit_decision"
        ]
        == "review"
    ]

    # ========================================================
    # Family summary
    # ========================================================

    family_groups = defaultdict(
        list
    )

    for row in accepted:
        family_groups[
            (
                row[
                    "audited_family"
                ],
                row[
                    "audited_component"
                ],
                row[
                    "table_orientation"
                ],
            )
        ].append(
            row
        )

    family_summary = []

    for (
        family,
        component_name,
        orientation,
    ), rows in sorted(
        family_groups.items()
    ):

        headings = Counter(
            row[
                "source_heading"
            ]
            for row in rows
        )

        report_ids = {
            row[
                "report_id"
            ]
            for row in rows
        }

        family_summary.append({
            "audited_family":
                family,

            "audited_component":
                component_name,

            "table_orientation":
                orientation,

            "section_count":
                len(rows),

            "report_count":
                len(
                    report_ids
                ),

            "unique_heading_count":
                len(
                    headings
                ),

            "top_headings_json":
                json.dumps(
                    headings.most_common(
                        30
                    ),
                    ensure_ascii=False,
                ),
        })

    # ========================================================
    # Summary metadata
    # ========================================================

    decision_counts = Counter(
        row[
            "audit_decision"
        ]
        for row in audited
    )

    status_counts = Counter(
        row[
            "audit_status"
        ]
        for row in audited
    )

    family_counts = Counter(
        row[
            "audited_family"
        ]
        for row in accepted
    )

    component_counts = Counter(
        row[
            "audited_component"
        ]
        for row in accepted
    )

    orientation_counts = Counter(
        row[
            "table_orientation"
        ]
        for row in accepted
    )

    origin_counts = Counter(
        row[
            "discovery_origin"
        ]
        for row in accepted
    )

    # ========================================================
    # Output
    # ========================================================

    out = (
        args.output_directory
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_columns = list(
        audited[0].keys()
    )

    write_csv(
        out
        / "all_section_audit.csv",
        audited,
        audit_columns,
    )

    write_csv(
        out
        / "accepted_timeseries_sections.csv",
        accepted,
        audit_columns,
    )

    write_csv(
        out
        / "timeseries_companion_metadata_sections.csv",
        companion,
        audit_columns,
    )

    write_csv(
        out
        / "excluded_non_timeseries_sections.csv",
        excluded,
        audit_columns,
    )

    write_csv(
        out
        / "remaining_review_sections.csv",
        remaining_review,
        audit_columns,
    )

    write_csv(
        out
        / "accepted_family_summary.csv",
        family_summary,
        [
            "audited_family",
            "audited_component",
            "table_orientation",
            "section_count",
            "report_count",
            "unique_heading_count",
            "top_headings_json",
        ],
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "CSV candidate audit",

        "input_discovery_candidates":
            len(
                candidates
            ),

        "input_near_threshold_reviews":
            len(
                reviews
            ),

        "total_sections_audited":
            len(
                audited
            ),

        "accepted_timeseries_sections":
            len(
                accepted
            ),

        "companion_metadata_sections":
            len(
                companion
            ),

        "excluded_non_timeseries_sections":
            len(
                excluded
            ),

        "remaining_review_sections":
            len(
                remaining_review
            ),

        "decision_counts":
            dict(
                decision_counts
            ),

        "status_counts":
            dict(
                status_counts
            ),

        "accepted_family_counts":
            dict(
                family_counts
            ),

        "accepted_component_counts":
            dict(
                component_counts
            ),

        "accepted_orientation_counts":
            dict(
                orientation_counts
            ),

        "accepted_origin_counts":
            dict(
                origin_counts
            ),

        "scope":
            (
                "Conservative audit of Group 4 CSV discovery outputs. "
                "Known non-time-series structures are explicitly "
                "excluded; crash-pulse companion metadata is preserved "
                "separately; repeated numeric-axis tables and transposed "
                "time-axis tables are accepted as time-series candidates. "
                "No signal normalization, unit conversion, event identity "
                "inference, or final sample extraction is performed."
            ),
    }

    metadata_tmp = (
        out
        / "metadata.json.part"
    )

    metadata_tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    metadata_tmp.replace(
        out
        / "metadata.json"
    )

    print(
        json.dumps(
            metadata,
            indent=2,
        )
    )

    print(
        f"Outputs: {out}"
    )


if __name__ == "__main__":
    main()