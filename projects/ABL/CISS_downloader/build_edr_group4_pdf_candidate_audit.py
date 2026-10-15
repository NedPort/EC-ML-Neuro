"""
Audit Group 4 PDF-only time-series candidates.

Inputs
------
data/processed/edr/group4_pdf_discovery_v1/
    pdf_timeseries_candidate_tables.csv
    pdf_review_tables.csv

Outputs
-------
data/processed/edr/group4_pdf_audit_v1/

    accepted_timeseries_tables.csv
    companion_metadata_tables.csv
    excluded_non_timeseries_tables.csv
    remaining_review_tables.csv
    audit_all_tables.csv
    family_summary.csv
    decision_summary.csv
    metadata.json

Purpose
-------
This stage audits PDF discovery results before structured extraction.

It:

1. Re-evaluates all discovery candidates.
2. Re-evaluates all near-threshold review tables.
3. Recognizes:
       - samples-by-rows temporal tables
       - samples-by-columns / transposed tables
       - "Parameter | -5 sec | -4 sec ..." pre-crash tables
       - repeated time/signal blocks
4. Separates:
       - accepted time-series
       - time-series companion metadata
       - explicit non-time-series structures
       - graphical/garbled structures requiring review
       - unresolved review cases
5. Refines structural family classification using the actual table,
   not only the PDF page heading.
6. Preserves continuation hints such as "Table 1 of 4".

This stage does NOT:
- extract final sample/value datasets,
- normalize signals,
- convert units,
- infer event identity,
- merge physical PDF tables,
- or modify the frozen Group 4 CSV package.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


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
        newline="",
    ) as f:
        return list(
            csv.DictReader(f)
        )


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
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


# ============================================================
# General helpers
# ============================================================

def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(
            value
            if value is not None
            else ""
        ).strip(),
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


def load_rows(value):
    try:
        rows = json.loads(
            value
        )

        if isinstance(
            rows,
            list,
        ):
            return rows

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


def row_text(row):
    return " ".join(
        populated(
            row
        )
    )


def table_text(rows):
    return " ".join(
        row_text(
            row
        )
        for row in rows
    )


def first_populated(row):
    for index, value in enumerate(
        row
    ):

        value = norm(
            value
        )

        if value:
            return (
                index,
                value,
            )

    return (
        None,
        "",
    )


# ============================================================
# Numeric / axis helpers
# ============================================================

def strip_axis_annotation(value):
    text = norm(
        value
    )

    # Examples:
    # -5 sec
    # -0.5 seconds
    # 10 ms
    # -5 count
    # 0 (TRG)

    text = re.sub(
        r"\(\s*TRG[^)]*\)\s*$",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s+count\s*$",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s*(?:"
        r"seconds?|"
        r"secs?|"
        r"msec|"
        r"milliseconds?|"
        r"ms"
        r")\s*$",
        "",
        text,
        flags=re.I,
    )

    return norm(
        text
    )


def is_numeric_axis_token(value):
    text = strip_axis_annotation(
        value
    )

    text = text.replace(
        ",",
        "",
    )

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def is_time_header(value):
    text = norm_key(
        value
    )

    return bool(
        re.search(
            r"\b(?:"
            r"time|"
            r"times|"
            r"seconds before|"
            r"seconds after|"
            r"sample count|"
            r"relative time|"
            r"buffer address"
            r")\b",
            text,
            re.I,
        )
    )


def is_parameter_axis_header(value):
    return bool(
        re.search(
            r"\bparameter\b",
            norm(
                value
            ),
            re.I,
        )
    )


# ============================================================
# Structural temporal detection
# ============================================================

def detect_samples_by_rows(rows):
    """
    Identify tables such as:

        Time (ms) | Delta-V
        10        | 0.0
        20        | -0.5
        30        | -1.0

    or:

        Seconds Before AE | Vehicle Speed | ...
        -5                | ...
        -4                | ...
    """

    best = None

    for header_index, row in enumerate(
        rows[:8]
    ):

        axis_col, header_value = (
            first_populated(
                row
            )
        )

        if axis_col is None:
            continue

        if not is_time_header(
            header_value
        ):
            continue

        numeric_rows = []

        for row_index in range(
            header_index + 1,
            len(
                rows
            ),
        ):

            candidate = rows[
                row_index
            ]

            if axis_col >= len(
                candidate
            ):
                continue

            axis_value = norm(
                candidate[
                    axis_col
                ]
            )

            if not is_numeric_axis_token(
                axis_value
            ):
                continue

            if len(
                populated(
                    candidate
                )
            ) < 2:
                continue

            numeric_rows.append(
                row_index
            )

        if len(
            numeric_rows
        ) < 2:
            continue

        candidate = {
            "header_row_index":
                header_index,

            "axis_column_index":
                axis_col,

            "sample_row_count":
                len(
                    numeric_rows
                ),

            "sample_row_indexes":
                numeric_rows,

            "axis_label":
                header_value,
        }

        if (
            best is None
            or candidate[
                "sample_row_count"
            ]
            > best[
                "sample_row_count"
            ]
        ):
            best = candidate

    return best


def detect_samples_by_columns(rows):
    """
    Identify tables such as:

        Time (ms) | 0 | 10 | 20 | 30
        Delta-V   | 0 | -1 | -2 | -3

    and:

        Parameter     | -5 sec | -4 sec | -3 sec
        Vehicle Speed | 50     | 48     | 45
    """

    best = None

    for header_index, row in enumerate(
        rows[:10]
    ):

        values = [
            norm(value)
            for value in row
        ]

        if not values:
            continue

        first_col, first_value = (
            first_populated(
                row
            )
        )

        if first_col is None:
            continue

        valid_header = (
            is_time_header(
                first_value
            )
            or is_parameter_axis_header(
                first_value
            )
        )

        if not valid_header:
            continue

        axis_columns = [
            column_index
            for column_index, value
            in enumerate(values)
            if (
                column_index
                != first_col
                and is_numeric_axis_token(
                    value
                )
            )
        ]

        if len(
            axis_columns
        ) < 2:
            continue

        signal_rows = []

        for row_index in range(
            header_index + 1,
            len(
                rows
            ),
        ):

            signal_row = rows[
                row_index
            ]

            _, label = first_populated(
                signal_row
            )

            if not label:
                continue

            values_on_axis = sum(
                1
                for column_index
                in axis_columns
                if (
                    column_index
                    < len(
                        signal_row
                    )
                    and norm(
                        signal_row[
                            column_index
                        ]
                    )
                )
            )

            if values_on_axis >= 2:
                signal_rows.append(
                    row_index
                )

        if not signal_rows:
            continue

        candidate = {
            "header_row_index":
                header_index,

            "axis_columns":
                axis_columns,

            "sample_count":
                len(
                    axis_columns
                ),

            "signal_row_count":
                len(
                    signal_rows
                ),

            "signal_row_indexes":
                signal_rows,

            "axis_label":
                first_value,
        }

        if (
            best is None
            or candidate[
                "sample_count"
            ]
            > best[
                "sample_count"
            ]
        ):
            best = candidate

    return best


def detect_repeated_transposed_blocks(rows):
    """
    Identify a table containing multiple transposed time/signal blocks.

    Example:

        Time (ms)     0 10 20 ...
        Delta-V       0 -1 -2 ...
        Time (ms)     80 90 ...
        Delta-V       ...
    """

    blocks = []

    for row_index, row in enumerate(
        rows
    ):

        first_col, first_value = (
            first_populated(
                row
            )
        )

        if first_col is None:
            continue

        if not is_time_header(
            first_value
        ):
            continue

        axis_count = sum(
            1
            for column_index, value
            in enumerate(row)
            if (
                column_index
                != first_col
                and is_numeric_axis_token(
                    value
                )
            )
        )

        if axis_count < 2:
            continue

        if (
            row_index + 1
            >= len(
                rows
            )
        ):
            continue

        next_row = rows[
            row_index + 1
        ]

        next_values = populated(
            next_row
        )

        if len(
            next_values
        ) < 3:
            continue

        blocks.append(
            row_index
        )

    return blocks


# ============================================================
# Companion metadata detection
# ============================================================

COMPANION_PATTERNS = [
    r"\brecording status\b.*\btime series data\b",
    r"\btime from trg to next sample\b",
    r"\bmaximum delta[- ]?v\b",
    r"\btime,?\s*maximum delta[- ]?v\b",
    r"\bclipping time\b",
    r"\blength of delta[- ]?v\b",
    r"\brollangle peak\b",
    r"\broll angle at (?:the )?time of trg\b",
    r"\btrg count\b",
    r"\bevent type\b",
    r"\bprevious crash type\b",
    r"\bfreeze signal\b",
    r"\bdiagnostic trouble codes?\b",
    r"\bignition cycle since dtc\b",
    r"\bedr generation\b",
    r"\bcomplete file recorded\b",
]


def companion_score(rows):
    text = table_text(
        rows
    )

    matches = [
        pattern
        for pattern
        in COMPANION_PATTERNS
        if re.search(
            pattern,
            text,
            re.I,
        )
    ]

    return (
        len(
            matches
        ),
        matches,
    )


# ============================================================
# Explicit non-time-series detection
# ============================================================

NON_TIMESERIES_PATTERNS = [
    (
        "event_record_summary",
        r"\bevent record summary\b",
    ),

    (
        "dtc_structure",
        r"\bdtcs?\s+present\b",
    ),

    (
        "system_status",
        r"\bsystem\s+(?:status|configuration)\b",
    ),

    (
        "deployment_scalar",
        r"\bdeployment\s+(?:command\s+)?data\b",
    ),
]


def explicit_non_timeseries_reason(
    rows,
):
    text = table_text(
        rows
    )

    for reason, pattern in (
        NON_TIMESERIES_PATTERNS
    ):

        if re.search(
            pattern,
            text,
            re.I,
        ):
            return reason

    return ""


# ============================================================
# Numbered legends / deployment lists
# ============================================================

def is_numbered_legend(rows):
    """
    Detect structures like:

        1 | Driver Airbag Deployment Time
        2 | Passenger Airbag Deployment Time
        3 | Pretensioner Deployment

    These are index/legend structures, not sampled time-series.
    """

    numeric_first = 0
    temporal_headers = 0

    for row in rows:

        column, value = first_populated(
            row
        )

        if column is None:
            continue

        if is_numeric_axis_token(
            value
        ):
            numeric_first += 1

        if is_time_header(
            value
        ):
            temporal_headers += 1

    return (
        numeric_first >= 3
        and temporal_headers == 0
    )


# ============================================================
# Garbled graphical table detection
# ============================================================

def duplicated_character_ratio(text):
    """
    PDF plot text often appears as:

        DDeellttaa--VV
        LLoonnggiittuuddiinnaall

    Estimate repeated-character corruption.
    """

    letters = [
        char
        for char in text
        if char.isalpha()
    ]

    if len(
        letters
    ) < 8:
        return 0.0

    repeated = 0

    for index in range(
        1,
        len(
            letters
        )
    ):

        if (
            letters[
                index
            ].lower()
            ==
            letters[
                index - 1
            ].lower()
        ):
            repeated += 1

    return (
        repeated
        / max(
            1,
            len(
                letters
            )
            - 1,
        )
    )


def is_garbled_graphical_structure(
    rows,
):
    """
    Identify plot/graph extraction where numeric axes are collapsed
    into single cells instead of a usable source table.
    """

    if len(
        rows
    ) > 8:
        return False

    text = table_text(
        rows
    )

    has_graph_terms = bool(
        re.search(
            r"\b(?:"
            r"delta[- ]?v|"
            r"crash pulse|"
            r"acceleration"
            r")\b",
            text,
            re.I,
        )
    )

    has_time_embedded = bool(
        re.search(
            r"\btime\s*\(?(?:msec|ms|milliseconds?)\)?",
            text,
            re.I,
        )
    )

    long_single_cells = sum(
        1
        for row in rows
        for value in row
        if len(
            norm(
                value
            )
        ) > 60
    )

    repeated_ratio = (
        duplicated_character_ratio(
            text
        )
    )

    return (
        has_graph_terms
        and (
            long_single_cells >= 2
            or repeated_ratio > 0.18
        )
        and has_time_embedded
    )


# ============================================================
# Family refinement
# ============================================================

def temporal_header_text(rows):
    pieces = []

    for row in rows[:5]:

        values = populated(
            row
        )

        if not values:
            continue

        pieces.extend(
            values[:8]
        )

    return " ".join(
        pieces
    )


def refine_family(
    rows,
    heading_hint,
    original_family,
):
    """
    Structural table content has priority over broad PDF page headings.
    """

    header_text = temporal_header_text(
        rows
    )

    table = table_text(
        rows
    )

    combined = (
        header_text
        + " "
        + norm(
            heading_hint
        )
    )

    # --------------------------------------------------------
    # Pre-crash
    # --------------------------------------------------------

    if re.search(
        r"\bseconds?\s+before\s+(?:ae|event)\b",
        header_text,
        re.I,
    ):
        return "pre_crash"

    if re.search(
        r"\bpre[-_ ]?crash\b",
        combined,
        re.I,
    ):
        return "pre_crash"

    if (
        re.search(
            r"\bparameter\b",
            header_text,
            re.I,
        )
        and re.search(
            r"-\s*\d+(?:\.\d+)?\s*sec",
            header_text,
            re.I,
        )
    ):
        return "pre_crash"

    # --------------------------------------------------------
    # Roll angle before generic acceleration
    # --------------------------------------------------------

    if re.search(
        r"\bvehicle\s+roll\s+angle\b|\broll\s+angle\b",
        header_text,
        re.I,
    ):
        return "roll_angle"

    # --------------------------------------------------------
    # Angular / rollover
    # --------------------------------------------------------

    if re.search(
        r"\broll\s+rate\b|\bangular\s+rate\b",
        header_text,
        re.I,
    ):
        return "angular_rate"

    # --------------------------------------------------------
    # Delta-V
    # --------------------------------------------------------

    if re.search(
        r"\b(?:"
        r"delta[- ]?v|"
        r"recorded velocity change|"
        r"velocity change"
        r")\b",
        header_text,
        re.I,
    ):
        return "delta_v"

    # --------------------------------------------------------
    # Acceleration
    # --------------------------------------------------------

    if re.search(
        r"\bacceleration\b",
        header_text,
        re.I,
    ):
        return "acceleration"

    # --------------------------------------------------------
    # Crash pulse
    # --------------------------------------------------------

    if re.search(
        r"\bcrash pulse\b",
        combined,
        re.I,
    ):
        return "crash_pulse"

    return (
        norm(
            original_family
        )
        or "other_timeseries"
    )


def refine_component(
    rows,
    heading_hint,
    original_component,
):
    text = (
        temporal_header_text(
            rows
        )
        + " "
        + norm(
            heading_hint
        )
    )

    has_longitudinal = bool(
        re.search(
            r"\blongitudinal\b",
            text,
            re.I,
        )
    )

    has_lateral = bool(
        re.search(
            r"\blateral\b",
            text,
            re.I,
        )
    )

    if (
        has_longitudinal
        and has_lateral
    ):
        return (
            "longitudinal_lateral"
        )

    if has_longitudinal:
        return "longitudinal"

    if has_lateral:
        return "lateral"

    if re.search(
        r"\b(?:normal|vertical)\b",
        text,
        re.I,
    ):
        return "normal_vertical"

    if re.search(
        r"\b(?:roll|angular)\b",
        text,
        re.I,
    ):
        return "roll_angular"

    return (
        norm(
            original_component
        )
        or "unspecified"
    )


# ============================================================
# Continuation / multi-part hints
# ============================================================

TABLE_PART_PATTERN = re.compile(
    r"\btable\s+(\d+)\s+of\s+(\d+)\b",
    re.I,
)


def extract_table_part(
    heading,
):
    match = TABLE_PART_PATTERN.search(
        norm(
            heading
        )
    )

    if not match:
        return (
            "",
            "",
        )

    return (
        int(
            match.group(
                1
            )
        ),
        int(
            match.group(
                2
            )
        ),
    )


def continuation_heading_key(
    heading,
):
    text = norm(
        heading
    )

    text = TABLE_PART_PATTERN.sub(
        "",
        text,
    )

    text = re.sub(
        r"\s*[-–—]\s*$",
        "",
        text,
    )

    return norm_key(
        text
    )


# ============================================================
# Header signature
# ============================================================

def build_header_signature(
    rows,
    row_structure,
    column_structure,
):
    if row_structure is not None:

        row_index = (
            row_structure[
                "header_row_index"
            ]
        )

        return norm_key(
            " | ".join(
                populated(
                    rows[
                        row_index
                    ]
                )
            )
        )

    if column_structure is not None:

        row_index = (
            column_structure[
                "header_row_index"
            ]
        )

        first_header = norm(
            rows[
                row_index
            ][0]
            if rows[
                row_index
            ]
            else ""
        )

        signal_labels = []

        for signal_row_index in (
            column_structure[
                "signal_row_indexes"
            ]
        ):

            _, label = (
                first_populated(
                    rows[
                        signal_row_index
                    ]
                )
            )

            if label:
                signal_labels.append(
                    label
                )

        return norm_key(
            " | ".join(
                [
                    first_header,
                    *signal_labels,
                ]
            )
        )

    return ""


# ============================================================
# Audit one table
# ============================================================

def audit_table(
    source,
):
    rows = load_rows(
        source.get(
            "source_rows_json",
            ""
        )
    )

    heading = norm(
        source.get(
            "source_heading_hint",
            ""
        )
    )

    # --------------------------------------------------------
    # Structural detection
    # --------------------------------------------------------

    row_structure = (
        detect_samples_by_rows(
            rows
        )
    )

    column_structure = (
        detect_samples_by_columns(
            rows
        )
    )

    repeated_blocks = (
        detect_repeated_transposed_blocks(
            rows
        )
    )

    companion_count, companion_matches = (
        companion_score(
            rows
        )
    )

    non_timeseries_reason = (
        explicit_non_timeseries_reason(
            rows
        )
    )

    numbered_legend = (
        is_numbered_legend(
            rows
        )
    )

    graphical = (
        is_garbled_graphical_structure(
            rows
        )
    )

    family = refine_family(
        rows,
        heading,
        source.get(
            "family_candidate",
            "",
        ),
    )

    component = refine_component(
        rows,
        heading,
        source.get(
            "component_candidate",
            "",
        ),
    )

    # --------------------------------------------------------
    # Orientation
    # --------------------------------------------------------

    if column_structure is not None:

        orientation = (
            "samples_by_columns"
        )

    elif row_structure is not None:

        orientation = (
            "samples_by_rows"
        )

    else:

        orientation = (
            "unknown"
        )

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    structural_timeseries = (
        row_structure is not None
        or column_structure is not None
    )

    if structural_timeseries:

        decision = "accept"

        audit_status = (
            "accepted_structural_timeseries"
        )

        audit_reason = (
            "validated_temporal_axis_structure"
        )

    elif graphical:

        decision = "review"

        audit_status = (
            "review_graphical_timeseries"
        )

        audit_reason = (
            "graphical_or_garbled_pdf_structure"
        )

    elif numbered_legend:

        decision = "exclude"

        audit_status = (
            "excluded_numbered_legend"
        )

        audit_reason = (
            "ordered_labels_not_sampled_time_axis"
        )

    elif non_timeseries_reason:

        decision = "exclude"

        audit_status = (
            "excluded_known_non_timeseries"
        )

        audit_reason = (
            non_timeseries_reason
        )

    elif companion_count >= 2:

        decision = "companion"

        audit_status = (
            "companion_metadata"
        )

        audit_reason = (
            "timeseries_context_without_sample_axis"
        )

    else:

        decision = "review"

        audit_status = (
            "remaining_review"
        )

        audit_reason = (
            "insufficient_structural_evidence"
        )

    # --------------------------------------------------------
    # Continuation hints
    # --------------------------------------------------------

    (
        table_part_index,
        table_part_total,
    ) = extract_table_part(
        heading
    )

    continuation_key = ""

    if table_part_total:

        continuation_key = (
            "g4pdfcont_"
            + identifier(
                source.get(
                    "report_id",
                    "",
                ),
                continuation_heading_key(
                    heading
                ),
                family,
                component,
            )
        )

    header_signature = (
        build_header_signature(
            rows,
            row_structure,
            column_structure,
        )
    )

    # --------------------------------------------------------
    # Counts
    # --------------------------------------------------------

    if row_structure is not None:

        detected_sample_count = (
            row_structure[
                "sample_row_count"
            ]
        )

        detected_signal_count = ""

    elif column_structure is not None:

        detected_sample_count = (
            column_structure[
                "sample_count"
            ]
        )

        detected_signal_count = (
            column_structure[
                "signal_row_count"
            ]
        )

    else:

        detected_sample_count = ""
        detected_signal_count = ""

    return {
        "decision":
            decision,

        "audit_status":
            audit_status,

        "audit_reason":
            audit_reason,

        "audited_family":
            family,

        "audited_component":
            component,

        "audited_orientation":
            orientation,

        "detected_sample_count":
            detected_sample_count,

        "detected_signal_count":
            detected_signal_count,

        "row_axis_detected":
            row_structure
            is not None,

        "column_axis_detected":
            column_structure
            is not None,

        "repeated_transposed_block_count":
            len(
                repeated_blocks
            ),

        "companion_pattern_count":
            companion_count,

        "companion_patterns_json":
            json.dumps(
                companion_matches,
                ensure_ascii=False,
            ),

        "numbered_legend_detected":
            numbered_legend,

        "graphical_structure_detected":
            graphical,

        "non_timeseries_reason":
            non_timeseries_reason,

        "header_signature":
            header_signature,

        "table_part_index":
            table_part_index,

        "table_part_total":
            table_part_total,

        "continuation_candidate_key":
            continuation_key,
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
            "group4_pdf_discovery_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_audit_v1"
        ),
    )

    args = parser.parse_args()

    discovery = (
        args.discovery_directory
    )

    candidate_path = (
        discovery
        / "pdf_timeseries_candidate_tables.csv"
    )

    review_path = (
        discovery
        / "pdf_review_tables.csv"
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

    combined = []

    for row in candidates:

        combined.append({
            **row,

            "discovery_origin":
                "candidate",
        })

    for row in reviews:

        combined.append({
            **row,

            "discovery_origin":
                "near_threshold_review",
        })

    audited = []

    for index, source in enumerate(
        combined,
        1,
    ):

        result = audit_table(
            source
        )

        audited.append({
            **source,
            **result,
        })

        if (
            index % 250 == 0
            or index
            == len(
                combined
            )
        ):

            print(
                "Audited Group 4 PDF "
                f"{index}/{len(combined)} tables...",
                flush=True,
            )

    # ========================================================
    # Split decisions
    # ========================================================

    accepted = [
        row
        for row in audited
        if row[
            "decision"
        ]
        == "accept"
    ]

    companions = [
        row
        for row in audited
        if row[
            "decision"
        ]
        == "companion"
    ]

    excluded = [
        row
        for row in audited
        if row[
            "decision"
        ]
        == "exclude"
    ]

    remaining_review = [
        row
        for row in audited
        if row[
            "decision"
        ]
        == "review"
    ]

    # ========================================================
    # Summaries
    # ========================================================

    decision_counts = Counter(
        row[
            "decision"
        ]
        for row in audited
    )

    status_counts = Counter(
        row[
            "audit_status"
        ]
        for row in audited
    )

    origin_decision_counts = Counter(
        (
            row[
                "discovery_origin"
            ],
            row[
                "decision"
            ],
        )
        for row in audited
    )

    family_counts = Counter(
        row[
            "audited_family"
        ]
        for row in accepted
    )

    orientation_counts = Counter(
        row[
            "audited_orientation"
        ]
        for row in accepted
    )

    reports_with_accepted = {
        row[
            "report_id"
        ]
        for row in accepted
    }

    continuation_tables = [
        row
        for row in accepted
        if row[
            "continuation_candidate_key"
        ]
    ]

    continuation_groups = {
        row[
            "continuation_candidate_key"
        ]
        for row in continuation_tables
    }

    # --------------------------------------------------------
    # Family summary
    # --------------------------------------------------------

    family_grouped = defaultdict(
        list
    )

    for row in accepted:

        family_grouped[
            (
                row[
                    "audited_family"
                ],
                row[
                    "audited_component"
                ],
                row[
                    "audited_orientation"
                ],
            )
        ].append(
            row
        )

    family_summary = []

    for (
        family,
        component,
        orientation,
    ), rows in sorted(
        family_grouped.items()
    ):

        family_summary.append({
            "audited_family":
                family,

            "audited_component":
                component,

            "audited_orientation":
                orientation,

            "table_count":
                len(
                    rows
                ),

            "report_count":
                len(
                    {
                        row[
                            "report_id"
                        ]
                        for row
                        in rows
                    }
                ),

            "origin_candidate_count":
                sum(
                    1
                    for row in rows
                    if row[
                        "discovery_origin"
                    ]
                    == "candidate"
                ),

            "origin_review_recovered_count":
                sum(
                    1
                    for row in rows
                    if row[
                        "discovery_origin"
                    ]
                    == "near_threshold_review"
                ),
        })

    # --------------------------------------------------------
    # Decision summary
    # --------------------------------------------------------

    decision_summary = []

    for (
        origin,
        decision,
    ), count in sorted(
        origin_decision_counts.items()
    ):

        decision_summary.append({
            "discovery_origin":
                origin,

            "audit_decision":
                decision,

            "table_count":
                count,
        })

    # ========================================================
    # Write outputs
    # ========================================================

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_columns = list(
        audited[0].keys()
    ) if audited else []

    write_csv(
        out
        / "audit_all_tables.csv",
        audited,
        audit_columns,
    )

    write_csv(
        out
        / "accepted_timeseries_tables.csv",
        accepted,
        audit_columns,
    )

    write_csv(
        out
        / "companion_metadata_tables.csv",
        companions,
        audit_columns,
    )

    write_csv(
        out
        / "excluded_non_timeseries_tables.csv",
        excluded,
        audit_columns,
    )

    write_csv(
        out
        / "remaining_review_tables.csv",
        remaining_review,
        audit_columns,
    )

    write_csv(
        out
        / "family_summary.csv",
        family_summary,
        [
            "audited_family",
            "audited_component",
            "audited_orientation",
            "table_count",
            "report_count",
            "origin_candidate_count",
            "origin_review_recovered_count",
        ],
    )

    write_csv(
        out
        / "decision_summary.csv",
        decision_summary,
        [
            "discovery_origin",
            "audit_decision",
            "table_count",
        ],
    )

    # ========================================================
    # Validation
    # ========================================================

    accounted = (
        len(
            accepted
        )
        + len(
            companions
        )
        + len(
            excluded
        )
        + len(
            remaining_review
        )
    )

    validation = {

        "input_tables":
            len(
                combined
            ),

        "accounted_tables":
            accounted,

        "all_tables_accounted_for":
            (
                accounted
                == len(
                    combined
                )
            ),

        "duplicate_candidate_ids":
            (
                len(
                    [
                        candidate_id
                        for candidate_id, count
                        in Counter(
                            row[
                                "pdf_candidate_id"
                            ]
                            for row
                            in combined
                        ).items()
                        if count > 1
                    ]
                )
            ),
    }

    if not validation[
        "all_tables_accounted_for"
    ]:

        raise RuntimeError(
            "Audit accounting failure."
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
            "Group 4 - Time-series measurements",

        "stage":
            "PDF candidate audit",

        "input_discovery_candidates":
            len(
                candidates
            ),

        "input_near_threshold_reviews":
            len(
                reviews
            ),

        "total_tables_audited":
            len(
                combined
            ),

        "accepted_timeseries_tables":
            len(
                accepted
            ),

        "companion_metadata_tables":
            len(
                companions
            ),

        "excluded_non_timeseries_tables":
            len(
                excluded
            ),

        "remaining_review_tables":
            len(
                remaining_review
            ),

        "reports_with_accepted_timeseries":
            len(
                reports_with_accepted
            ),

        "decision_counts":
            dict(
                decision_counts
            ),

        "audit_status_counts":
            dict(
                status_counts
            ),

        "accepted_family_counts":
            dict(
                family_counts
            ),

        "accepted_orientation_counts":
            dict(
                orientation_counts
            ),

        "recovered_from_near_threshold_review":
            sum(
                1
                for row in accepted
                if row[
                    "discovery_origin"
                ]
                == "near_threshold_review"
            ),

        "original_candidates_rejected_or_reviewed":
            sum(
                1
                for row in audited
                if (
                    row[
                        "discovery_origin"
                    ]
                    == "candidate"
                    and row[
                        "decision"
                    ]
                    != "accept"
                )
            ),

        "continuation_candidate_table_count":
            len(
                continuation_tables
            ),

        "continuation_candidate_group_count":
            len(
                continuation_groups
            ),

        "validation":
            validation,

        "scope":
            (
                "Audit of all Group 4 PDF discovery candidates and "
                "near-threshold review tables. Temporal structure is "
                "validated using explicit row-wise or column-wise "
                "sample axes. Parameter-by-time pre-crash structures "
                "are recovered. Companion metadata, numbered deployment "
                "legends, known scalar/status structures, and graphical "
                "PDF artifacts are separated. Structural family "
                "classification is refined from actual table contents. "
                "Multi-part table numbering is preserved as continuation "
                "evidence only; physical tables are not merged. No final "
                "time-series extraction, semantic normalization, unit "
                "conversion, event identity inference, or CSV/PDF "
                "integration is performed."
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
        "GROUP 4 PDF CANDIDATE AUDIT COMPLETE."
    )


if __name__ == "__main__":
    main()