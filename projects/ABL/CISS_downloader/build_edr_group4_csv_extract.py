"""
Build structured Group 4 CSV time-series datasets.

Input
-----
data/processed/edr/group4_csv_audit_v1/
    accepted_timeseries_sections.csv
    timeseries_companion_metadata_sections.csv

Output
------
data/processed/edr/group4_csv_structured_v1/
    timeseries_registry.csv
    timeseries_signal_registry.csv
    timeseries_samples_wide.csv
    timeseries_values_long.csv
    timeseries_companion_metadata.csv
    timeseries_audit.csv
    extraction_failures.csv
    validation_report.csv
    metadata.json

Scope
-----
This is a STRUCTURAL extraction stage.

The script:
- extracts accepted CSV time-series sections,
- supports samples-by-rows,
- supports samples-by-columns,
- supports PCM/buffer-order tables,
- trims raw PID/hex payloads beginning at PIDsStart,
- re-detects transposed tables after trimming PID tails,
- uses the section heading as the signal identity for single-signal
  tables whose column header contains only a unit,
- preserves raw source labels,
- preserves raw units,
- preserves raw axis values,
- preserves source provenance,
- preserves missing/N/A/SNA values,
- preserves companion metadata separately.

The script does NOT:
- semantically normalize signal names,
- convert units,
- invent missing time values,
- infer crash-event identities,
- merge signals across manufacturers,
- use PDF data,
- or classify signals into biomechanical meaning.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


csv.field_size_limit(50_000_000)


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


def json_compact(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )


def load_rows(value):
    try:
        result = json.loads(
            value
        )

        if isinstance(
            result,
            list,
        ):
            return result

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        pass

    return []


def populated_positions(row):
    return [
        (
            index,
            norm(value),
        )
        for index, value
        in enumerate(row)
        if norm(value)
    ]


def populated(row):
    return [
        value
        for _, value
        in populated_positions(
            row
        )
    ]


def clean_numeric_token(value):
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


def remove_axis_annotation(value):
    text = norm(value)

    text = re.sub(
        r"\([^)]*\)\s*$",
        "",
        text,
    )

    text = re.sub(
        r"\s+count\s*$",
        "",
        text,
        flags=re.I,
    )

    return norm(text)


def is_numeric(value):
    text = clean_numeric_token(
        value
    )

    if not text:
        return False

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def axis_is_numeric(value):
    return is_numeric(
        remove_axis_annotation(
            value
        )
    )


def numeric_value(value):
    text = remove_axis_annotation(
        value
    )

    text = clean_numeric_token(
        text
    )

    if not is_numeric(text):
        return ""

    try:
        number = float(
            text
        )

        if math.isfinite(
            number
        ):
            return number

    except ValueError:
        pass

    return ""


def is_na_like(value):
    return (
        norm(value).casefold()
        in {
            "",
            "n/a",
            "na",
            "not available",
            "not applicable",
            "sna",
            "unknown",
            "not recorded",
        }
    )


# ============================================================
# Known non-timeseries tail trimming
# ============================================================

def trim_non_timeseries_tail(rows):
    """
    Remove known diagnostic/PID payloads appended after an otherwise
    valid time-series table.

    The original source is unchanged. This only prevents raw PID/hex
    payloads from being interpreted as Group 4 sample rows.

    Current known delimiter:
        PIDsStart
    """

    trimmed = []

    for row in rows:

        values = [
            norm(value)
            for value in row
            if norm(value)
        ]

        if any(
            value.casefold()
            == "pidsstart"
            for value in values
        ):
            break

        trimmed.append(
            row
        )

    return trimmed


# ============================================================
# Header / unit helpers
# ============================================================

UNIT_PATTERNS = [
    r"^\(?\s*km/h\s*\)?$",
    r"^\(?\s*mph\s*\)?$",
    r"^\(?\s*km\/h\s*\)?$",
    r"^\(?\s*mi\/h\s*\)?$",
    r"^\(?\s*rpm\s*\)?$",
    r"^\(?\s*%\s*\)?$",
    r"^\(?\s*g\s*\)?$",
    r"^\(?\s*m/s(?:\^?2|²)?\s*\)?$",
    r"^\(?\s*ft/s(?:\^?2|²)?\s*\)?$",
    r"^\(?\s*deg(?:ree)?s?\s*\)?$",
    r"^\(?\s*degrees?/s\s*\)?$",
    r"^\(?\s*deg/sec\s*\)?$",
    r"^\(?\s*rad/s\s*\)?$",
    r"^\(?\s*sec(?:onds?)?\s*\)?$",
    r"^\(?\s*s\s*\)?$",
    r"^\(?\s*ms(?:ec)?\s*\)?$",
    r"^\(?\s*msec\s*\)?$",
    r"^\(?\s*n/?a\s*\)?$",
]


def looks_like_unit(value):
    text = norm(value)

    if not text:
        return False

    return any(
        re.fullmatch(
            pattern,
            text,
            re.I,
        )
        for pattern
        in UNIT_PATTERNS
    )


def join_header_fragments(values):
    cleaned = []

    for value in values:

        text = norm(value)

        if not text:
            continue

        if text in cleaned:
            continue

        cleaned.append(
            text
        )

    return " | ".join(
        cleaned
    )


def derive_label_and_unit(
    fragments,
    fallback_label,
):
    """
    Conservatively separate label-like header fragments and unit-like
    fragments.

    Original fragments are preserved separately.
    """

    fragments = [
        norm(value)
        for value in fragments
        if norm(value)
    ]

    unit = ""
    non_unit = []

    for fragment in fragments:

        if looks_like_unit(
            fragment
        ):
            unit = fragment

        else:
            non_unit.append(
                fragment
            )

    if non_unit:
        label = non_unit[-1]
    else:
        label = fallback_label

    return (
        label,
        unit,
        fragments,
    )


# ============================================================
# Axis helpers
# ============================================================

def classify_axis_label(
    label,
    orientation,
):
    text = norm_key(
        label
    )

    if re.search(
        r"\bbuffer address\b",
        text,
    ):
        return "buffer_address"

    if re.search(
        r"\bsample count\b",
        text,
    ):
        return "sample_count_relative_to_trigger"

    if re.search(
        r"\bseconds before\b",
        text,
    ):
        return "seconds_before_event"

    if re.search(
        r"\bseconds after\b",
        text,
    ):
        return "seconds_after_event"

    if re.search(
        r"\brelative time\b",
        text,
    ):
        return "relative_time"

    if re.search(
        r"\btime\b",
        text,
    ):
        return "explicit_time"

    if orientation == "buffer_order_table":
        return "buffer_order"

    return "ordered_numeric_axis"


def infer_axis_unit(
    label,
    explicit_unit="",
):
    if explicit_unit:
        return explicit_unit

    text = norm(label)

    if re.search(
        r"\bmsec\b|\bms\b",
        text,
        re.I,
    ):
        return "ms"

    if re.search(
        r"\bsec\b|\bseconds?\b|\(s\)",
        text,
        re.I,
    ):
        return "s"

    if re.search(
        r"\bsample count\b",
        text,
        re.I,
    ):
        return "count"

    if re.search(
        r"\bbuffer address\b",
        text,
        re.I,
    ):
        return "buffer_address"

    return ""


# ============================================================
# Signal record helper
# ============================================================

def build_signal_id(
    series_id,
    source_signal_index,
):
    return (
        "g4sig_"
        + identifier(
            series_id,
            source_signal_index,
        )
    )


def create_signal_record(
    base,
    series_id,
    signal_position,
    source_column_index,
    source_row_index,
    raw_label,
    raw_unit,
    header_fragments,
    orientation,
):
    signal_id = build_signal_id(
        series_id,
        signal_position,
    )

    return {
        **base,

        "series_id":
            series_id,

        "signal_id":
            signal_id,

        "signal_position":
            signal_position,

        "source_column_index":
            source_column_index,

        "source_row_index":
            source_row_index,

        "signal_label_raw":
            raw_label,

        "signal_unit_raw":
            raw_unit,

        "header_fragments_json":
            json_compact(
                header_fragments
            ),

        "table_orientation":
            orientation,

        "semantic_normalization_status":
            "not_normalized",
    }


# ============================================================
# Transposed axis detection
# ============================================================

def detect_transposed_axis_row(rows):
    """
    Detect a time/sample axis running across columns.

    Examples:

        Time (sec)  -5  -4  -3  -2  -1  0(TRG)

    or:

        Pre-Crash Sample Count from TRG
                    -5 count ... 0(TRG)
    """

    best = None

    for row_index, row in enumerate(
        rows[:10]
    ):

        positions = populated_positions(
            row
        )

        if len(
            positions
        ) < 3:
            continue

        text = " ".join(
            value
            for _, value
            in positions
        )

        header_like = bool(
            re.search(
                r"\b(?:"
                r"time|"
                r"sec|"
                r"seconds?|"
                r"sample count|"
                r"TRG"
                r")\b",
                text,
                re.I,
            )
        )

        if not header_like:
            continue

        numeric_positions = [
            column
            for column, value
            in positions
            if axis_is_numeric(
                value
            )
        ]

        if len(
            numeric_positions
        ) < 2:
            continue

        candidate = (
            len(
                numeric_positions
            ),
            row_index,
            numeric_positions,
        )

        if (
            best is None
            or candidate[0]
            > best[0]
        ):
            best = candidate

    if best is None:
        return None

    _, row_index, sample_columns = (
        best
    )

    return (
        row_index,
        sample_columns,
    )


def has_transposed_time_axis(rows):
    return (
        detect_transposed_axis_row(
            rows
        )
        is not None
    )


# ============================================================
# Samples-by-rows extraction
# ============================================================

def find_sample_rows_by_rows(rows):
    result = []

    for row_index, row in enumerate(
        rows
    ):

        positions = populated_positions(
            row
        )

        if len(
            positions
        ) < 2:
            continue

        first_col, first_value = (
            positions[0]
        )

        if axis_is_numeric(
            first_value
        ):
            result.append(
                (
                    row_index,
                    first_col,
                )
            )

    return result


def modal_axis_column(
    sample_rows,
):
    if not sample_rows:
        return None

    counts = Counter(
        column
        for _, column
        in sample_rows
    )

    return counts.most_common(
        1
    )[0][0]


def parse_samples_by_rows(
    source,
    rows,
    series_id,
):
    sample_candidates = (
        find_sample_rows_by_rows(
            rows
        )
    )

    if len(
        sample_candidates
    ) < 2:

        raise ValueError(
            "Could not identify at least two "
            "numeric-axis sample rows."
        )

    axis_col = modal_axis_column(
        sample_candidates
    )

    sample_row_indexes = [
        row_index
        for row_index, column
        in sample_candidates
        if column == axis_col
    ]

    if len(
        sample_row_indexes
    ) < 2:

        raise ValueError(
            "No stable axis column found."
        )

    first_sample_row = min(
        sample_row_indexes
    )

    header_rows = rows[
        :first_sample_row
    ]

    # --------------------------------------------------------
    # Determine measurement columns
    # --------------------------------------------------------

    data_columns = set()

    for row_index in sample_row_indexes:

        row = rows[
            row_index
        ]

        for column_index, value in enumerate(
            row
        ):

            if (
                column_index
                == axis_col
            ):
                continue

            if norm(value):
                data_columns.add(
                    column_index
                )

    data_columns = sorted(
        data_columns
    )

    if not data_columns:
        raise ValueError(
            "No measurement columns found."
        )

    single_measurement_column = (
        len(
            data_columns
        )
        == 1
    )

    # --------------------------------------------------------
    # Axis header
    # --------------------------------------------------------

    axis_fragments = []

    for row in header_rows:

        if axis_col < len(row):

            value = norm(
                row[
                    axis_col
                ]
            )

            if value:
                axis_fragments.append(
                    value
                )

    (
        axis_label,
        axis_unit,
        axis_fragments,
    ) = derive_label_and_unit(
        axis_fragments,
        fallback_label="Ordered Axis",
    )

    axis_type = classify_axis_label(
        axis_label,
        source[
            "table_orientation"
        ],
    )

    axis_unit = infer_axis_unit(
        axis_label,
        axis_unit,
    )

    # --------------------------------------------------------
    # Signals
    # --------------------------------------------------------

    signals = []
    column_to_signal = {}

    for signal_position, column_index in enumerate(
        data_columns,
        1,
    ):

        fragments = []

        for row in header_rows:

            if column_index < len(
                row
            ):

                value = norm(
                    row[
                        column_index
                    ]
                )

                if value:
                    fragments.append(
                        value
                    )

        (
            label,
            unit,
            fragments,
        ) = derive_label_and_unit(
            fragments,
            fallback_label=(
                f"source_column_{column_index}"
            ),
        )

        # ----------------------------------------------------
        # Single-signal table with only a unit header:
        # use source section heading as measurement identity.
        # ----------------------------------------------------

        if (
            single_measurement_column
            and (
                label.startswith(
                    "source_column_"
                )
                or not label
            )
        ):

            source_heading = norm(
                source.get(
                    "source_heading",
                    "",
                )
            )

            if source_heading:
                label = source_heading

        signal = create_signal_record(
            base={
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },
            series_id=series_id,
            signal_position=signal_position,
            source_column_index=column_index,
            source_row_index="",
            raw_label=label,
            raw_unit=unit,
            header_fragments=fragments,
            orientation=source[
                "table_orientation"
            ],
        )

        signals.append(
            signal
        )

        column_to_signal[
            column_index
        ] = signal

    # --------------------------------------------------------
    # Samples and long values
    # --------------------------------------------------------

    samples = []
    values_long = []

    for sample_index, row_index in enumerate(
        sample_row_indexes
    ):

        row = rows[
            row_index
        ]

        axis_raw = (
            norm(
                row[
                    axis_col
                ]
            )
            if axis_col < len(row)
            else ""
        )

        sample_id = (
            "g4sample_"
            + identifier(
                series_id,
                sample_index,
            )
        )

        values_map = {}

        for column_index in data_columns:

            signal = column_to_signal[
                column_index
            ]

            raw_value = (
                norm(
                    row[
                        column_index
                    ]
                )
                if column_index < len(
                    row
                )
                else ""
            )

            values_map[
                signal[
                    "signal_id"
                ]
            ] = raw_value

            values_long.append({
                **{
                    key:
                        source.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "series_id":
                    series_id,

                "sample_id":
                    sample_id,

                "sample_index":
                    sample_index,

                "signal_id":
                    signal[
                        "signal_id"
                    ],

                "signal_position":
                    signal[
                        "signal_position"
                    ],

                "signal_label_raw":
                    signal[
                        "signal_label_raw"
                    ],

                "signal_unit_raw":
                    signal[
                        "signal_unit_raw"
                    ],

                "axis_type":
                    axis_type,

                "axis_label_raw":
                    axis_label,

                "axis_unit_raw":
                    axis_unit,

                "axis_value_raw":
                    axis_raw,

                "axis_value_numeric":
                    numeric_value(
                        axis_raw
                    ),

                "value_raw":
                    raw_value,

                "value_numeric":
                    (
                        numeric_value(
                            raw_value
                        )
                        if is_numeric(
                            raw_value
                        )
                        else ""
                    ),

                "value_is_missing_or_na":
                    is_na_like(
                        raw_value
                    ),

                "source_section_row_index":
                    row_index,

                "source_column_index":
                    column_index,

                "table_orientation":
                    source[
                        "table_orientation"
                    ],
            })

        samples.append({
            **{
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                series_id,

            "sample_id":
                sample_id,

            "sample_index":
                sample_index,

            "axis_type":
                axis_type,

            "axis_label_raw":
                axis_label,

            "axis_unit_raw":
                axis_unit,

            "axis_value_raw":
                axis_raw,

            "axis_value_numeric":
                numeric_value(
                    axis_raw
                ),

            "secondary_axes_json":
                "{}",

            "values_json":
                json_compact(
                    values_map
                ),

            "source_section_row_index":
                row_index,

            "table_orientation":
                source[
                    "table_orientation"
                ],
        })

    return {
        "signals":
            signals,

        "samples":
            samples,

        "values":
            values_long,

        "axis_type":
            axis_type,

        "axis_label_raw":
            axis_label,

        "axis_unit_raw":
            axis_unit,

        "axis_column_index":
            axis_col,

        "secondary_axis_columns":
            [],

        "header_row_count":
            len(
                header_rows
            ),

        "sample_count":
            len(
                samples
            ),

        "signal_count":
            len(
                signals
            ),
    }


# ============================================================
# Samples-by-columns extraction
# ============================================================

def parse_samples_by_columns(
    source,
    rows,
    series_id,
):
    detected = (
        detect_transposed_axis_row(
            rows
        )
    )

    if detected is None:
        raise ValueError(
            "Could not identify transposed time/sample axis."
        )

    (
        axis_row_index,
        sample_columns,
    ) = detected

    axis_row = rows[
        axis_row_index
    ]

    first_sample_column = min(
        sample_columns
    )

    axis_label_fragments = [
        norm(
            axis_row[index]
        )
        for index in range(
            min(
                first_sample_column,
                len(
                    axis_row
                ),
            )
        )
        if norm(
            axis_row[index]
        )
    ]

    axis_label = (
        join_header_fragments(
            axis_label_fragments
        )
        or "Ordered Axis"
    )

    axis_type = classify_axis_label(
        axis_label,
        source[
            "table_orientation"
        ],
    )

    axis_unit = infer_axis_unit(
        axis_label
    )

    # --------------------------------------------------------
    # Detect signal rows
    # --------------------------------------------------------

    signal_rows = []

    for row_index in range(
        axis_row_index + 1,
        len(
            rows
        ),
    ):

        row = rows[
            row_index
        ]

        positions = populated_positions(
            row
        )

        if len(
            positions
        ) < 2:
            continue

        values_on_axis = [
            (
                norm(
                    row[column]
                )
                if column < len(
                    row
                )
                else ""
            )
            for column
            in sample_columns
        ]

        populated_sample_values = sum(
            1
            for value
            in values_on_axis
            if norm(value)
        )

        if populated_sample_values < 2:
            continue

        label_fragments = []

        for column_index in range(
            first_sample_column
        ):

            if column_index < len(
                row
            ):

                value = norm(
                    row[
                        column_index
                    ]
                )

                if value:
                    label_fragments.append(
                        value
                    )

        if not label_fragments:
            continue

        signal_rows.append(
            (
                row_index,
                row,
                label_fragments,
            )
        )

    if not signal_rows:
        raise ValueError(
            "No signal rows found below transposed axis."
        )

    # --------------------------------------------------------
    # Build signal registry
    # --------------------------------------------------------

    signals = []
    row_to_signal = {}

    for signal_position, (
        row_index,
        row,
        label_fragments,
    ) in enumerate(
        signal_rows,
        1,
    ):

        (
            label,
            unit,
            fragments,
        ) = derive_label_and_unit(
            label_fragments,
            fallback_label=(
                f"source_row_{row_index}"
            ),
        )

        signal = create_signal_record(
            base={
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },
            series_id=series_id,
            signal_position=signal_position,
            source_column_index="",
            source_row_index=row_index,
            raw_label=label,
            raw_unit=unit,
            header_fragments=fragments,
            orientation="samples_by_columns",
        )

        signals.append(
            signal
        )

        row_to_signal[
            row_index
        ] = signal

    # --------------------------------------------------------
    # Build samples and values
    # --------------------------------------------------------

    samples = []
    values_long = []

    for sample_index, column_index in enumerate(
        sample_columns
    ):

        axis_raw = (
            norm(
                axis_row[
                    column_index
                ]
            )
            if column_index < len(
                axis_row
            )
            else ""
        )

        sample_id = (
            "g4sample_"
            + identifier(
                series_id,
                sample_index,
            )
        )

        values_map = {}

        for (
            row_index,
            row,
            _
        ) in signal_rows:

            signal = row_to_signal[
                row_index
            ]

            raw_value = (
                norm(
                    row[
                        column_index
                    ]
                )
                if column_index < len(
                    row
                )
                else ""
            )

            values_map[
                signal[
                    "signal_id"
                ]
            ] = raw_value

            values_long.append({
                **{
                    key:
                        source.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "series_id":
                    series_id,

                "sample_id":
                    sample_id,

                "sample_index":
                    sample_index,

                "signal_id":
                    signal[
                        "signal_id"
                    ],

                "signal_position":
                    signal[
                        "signal_position"
                    ],

                "signal_label_raw":
                    signal[
                        "signal_label_raw"
                    ],

                "signal_unit_raw":
                    signal[
                        "signal_unit_raw"
                    ],

                "axis_type":
                    axis_type,

                "axis_label_raw":
                    axis_label,

                "axis_unit_raw":
                    axis_unit,

                "axis_value_raw":
                    axis_raw,

                "axis_value_numeric":
                    numeric_value(
                        axis_raw
                    ),

                "value_raw":
                    raw_value,

                "value_numeric":
                    (
                        numeric_value(
                            raw_value
                        )
                        if is_numeric(
                            raw_value
                        )
                        else ""
                    ),

                "value_is_missing_or_na":
                    is_na_like(
                        raw_value
                    ),

                "source_section_row_index":
                    row_index,

                "source_column_index":
                    column_index,

                "table_orientation":
                    "samples_by_columns",
            })

        samples.append({
            **{
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                series_id,

            "sample_id":
                sample_id,

            "sample_index":
                sample_index,

            "axis_type":
                axis_type,

            "axis_label_raw":
                axis_label,

            "axis_unit_raw":
                axis_unit,

            "axis_value_raw":
                axis_raw,

            "axis_value_numeric":
                numeric_value(
                    axis_raw
                ),

            "secondary_axes_json":
                "{}",

            "values_json":
                json_compact(
                    values_map
                ),

            "source_section_row_index":
                axis_row_index,

            "table_orientation":
                "samples_by_columns",
        })

    return {
        "signals":
            signals,

        "samples":
            samples,

        "values":
            values_long,

        "axis_type":
            axis_type,

        "axis_label_raw":
            axis_label,

        "axis_unit_raw":
            axis_unit,

        "axis_column_index":
            "",

        "secondary_axis_columns":
            [],

        "header_row_count":
            axis_row_index + 1,

        "sample_count":
            len(
                samples
            ),

        "signal_count":
            len(
                signals
            ),
    }


# ============================================================
# PCM / buffer-order extraction
# ============================================================

def parse_buffer_order_table(
    source,
    rows,
    series_id,
):
    """
    Parse PCM/buffer-oriented tables.

    Buffer Address is structural and is not required to be a normal
    decimal time coordinate.

    Relative Time is preserved when present.
    """

    header_row_index = None
    axis_col = None

    for row_index, row in enumerate(
        rows[:10]
    ):

        for column_index, value in enumerate(
            row
        ):

            if re.search(
                r"\bbuffer\s+address\b",
                norm(value),
                re.I,
            ):

                header_row_index = (
                    row_index
                )

                axis_col = (
                    column_index
                )

                break

        if axis_col is not None:
            break

    if axis_col is None:

        raise ValueError(
            "Buffer Address column was not found."
        )

    # --------------------------------------------------------
    # Locate Relative Time
    # --------------------------------------------------------

    relative_time_col = None

    for row in rows[
        header_row_index:
        min(
            header_row_index + 3,
            len(rows),
        )
    ]:

        for column_index, value in enumerate(
            row
        ):

            if re.search(
                r"\brelative\s+time\b",
                norm(value),
                re.I,
            ):

                relative_time_col = (
                    column_index
                )

                break

        if relative_time_col is not None:
            break

    # --------------------------------------------------------
    # Detect PCM data rows
    # --------------------------------------------------------

    data_row_indexes = []

    for row_index in range(
        header_row_index + 1,
        len(
            rows
        ),
    ):

        row = rows[
            row_index
        ]

        axis_raw = (
            norm(
                row[
                    axis_col
                ]
            )
            if axis_col < len(row)
            else ""
        )

        if not axis_raw:
            continue

        if re.search(
            r"\b(?:"
            r"buffer\s+address|"
            r"relative\s+time|"
            r"units?|"
            r"seconds?|"
            r"msec|"
            r"milliseconds?"
            r")\b",
            axis_raw,
            re.I,
        ):
            continue

        other_values = [
            norm(value)
            for column_index, value
            in enumerate(row)
            if (
                column_index
                != axis_col
                and norm(value)
            )
        ]

        if not other_values:
            continue

        data_row_indexes.append(
            row_index
        )

    if len(
        data_row_indexes
    ) < 2:

        raise ValueError(
            "Could not identify at least two "
            "PCM buffer data rows."
        )

    first_data_row = min(
        data_row_indexes
    )

    header_rows = rows[
        :first_data_row
    ]

    # --------------------------------------------------------
    # Measurement columns
    # --------------------------------------------------------

    populated_data_columns = set()

    for row_index in data_row_indexes:

        row = rows[
            row_index
        ]

        for column_index, value in enumerate(
            row
        ):

            if not norm(value):
                continue

            if column_index == axis_col:
                continue

            if (
                relative_time_col is not None
                and column_index
                == relative_time_col
            ):
                continue

            populated_data_columns.add(
                column_index
            )

    data_columns = sorted(
        populated_data_columns
    )

    if not data_columns:

        raise ValueError(
            "No PCM measurement columns found."
        )

    # --------------------------------------------------------
    # Signals
    # --------------------------------------------------------

    signals = []
    column_to_signal = {}

    for signal_position, column_index in enumerate(
        data_columns,
        1,
    ):

        fragments = []

        for row in header_rows:

            if column_index >= len(
                row
            ):
                continue

            value = norm(
                row[
                    column_index
                ]
            )

            if value:
                fragments.append(
                    value
                )

        (
            label,
            unit,
            fragments,
        ) = derive_label_and_unit(
            fragments,
            fallback_label=(
                f"source_column_{column_index}"
            ),
        )

        signal = create_signal_record(
            base={
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },
            series_id=series_id,
            signal_position=signal_position,
            source_column_index=column_index,
            source_row_index="",
            raw_label=label,
            raw_unit=unit,
            header_fragments=fragments,
            orientation="buffer_order_table",
        )

        signals.append(
            signal
        )

        column_to_signal[
            column_index
        ] = signal

    # --------------------------------------------------------
    # Relative time availability
    # --------------------------------------------------------

    relative_time_values = []

    if relative_time_col is not None:

        for row_index in data_row_indexes:

            row = rows[
                row_index
            ]

            value = (
                norm(
                    row[
                        relative_time_col
                    ]
                )
                if relative_time_col
                < len(row)
                else ""
            )

            relative_time_values.append(
                value
            )

    numeric_relative_times = sum(
        1
        for value
        in relative_time_values
        if axis_is_numeric(
            value
        )
    )

    if numeric_relative_times >= 2:

        time_axis_status = (
            "relative_time_available"
        )

    else:

        time_axis_status = (
            "buffer_order_only"
        )

    # --------------------------------------------------------
    # Samples
    # --------------------------------------------------------

    samples = []
    values_long = []

    for sample_index, row_index in enumerate(
        data_row_indexes
    ):

        row = rows[
            row_index
        ]

        buffer_address_raw = (
            norm(
                row[
                    axis_col
                ]
            )
            if axis_col < len(row)
            else ""
        )

        relative_time_raw = ""

        if relative_time_col is not None:

            relative_time_raw = (
                norm(
                    row[
                        relative_time_col
                    ]
                )
                if relative_time_col
                < len(row)
                else ""
            )

        sample_id = (
            "g4sample_"
            + identifier(
                series_id,
                sample_index,
            )
        )

        values_map = {}

        for column_index in data_columns:

            signal = column_to_signal[
                column_index
            ]

            raw_value = (
                norm(
                    row[
                        column_index
                    ]
                )
                if column_index
                < len(row)
                else ""
            )

            values_map[
                signal[
                    "signal_id"
                ]
            ] = raw_value

            values_long.append({
                **{
                    key:
                        source.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "series_id":
                    series_id,

                "sample_id":
                    sample_id,

                "sample_index":
                    sample_index,

                "signal_id":
                    signal[
                        "signal_id"
                    ],

                "signal_position":
                    signal[
                        "signal_position"
                    ],

                "signal_label_raw":
                    signal[
                        "signal_label_raw"
                    ],

                "signal_unit_raw":
                    signal[
                        "signal_unit_raw"
                    ],

                "axis_type":
                    time_axis_status,

                "axis_label_raw":
                    "Buffer Address",

                "axis_unit_raw":
                    "buffer_address",

                "axis_value_raw":
                    buffer_address_raw,

                "axis_value_numeric":
                    (
                        numeric_value(
                            buffer_address_raw
                        )
                        if axis_is_numeric(
                            buffer_address_raw
                        )
                        else ""
                    ),

                "value_raw":
                    raw_value,

                "value_numeric":
                    (
                        numeric_value(
                            raw_value
                        )
                        if is_numeric(
                            raw_value
                        )
                        else ""
                    ),

                "value_is_missing_or_na":
                    is_na_like(
                        raw_value
                    ),

                "source_section_row_index":
                    row_index,

                "source_column_index":
                    column_index,

                "table_orientation":
                    "buffer_order_table",
            })

        secondary_axes = {
            "buffer_address":
                buffer_address_raw,
        }

        if relative_time_col is not None:

            secondary_axes[
                "relative_time"
            ] = relative_time_raw

        samples.append({
            **{
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                series_id,

            "sample_id":
                sample_id,

            "sample_index":
                sample_index,

            "axis_type":
                time_axis_status,

            "axis_label_raw":
                "Buffer Address",

            "axis_unit_raw":
                "buffer_address",

            "axis_value_raw":
                buffer_address_raw,

            "axis_value_numeric":
                (
                    numeric_value(
                        buffer_address_raw
                    )
                    if axis_is_numeric(
                        buffer_address_raw
                    )
                    else ""
                ),

            "secondary_axes_json":
                json_compact(
                    secondary_axes
                ),

            "values_json":
                json_compact(
                    values_map
                ),

            "source_section_row_index":
                row_index,

            "table_orientation":
                "buffer_order_table",
        })

    return {
        "signals":
            signals,

        "samples":
            samples,

        "values":
            values_long,

        "axis_type":
            time_axis_status,

        "axis_label_raw":
            "Buffer Address",

        "axis_unit_raw":
            "buffer_address",

        "axis_column_index":
            axis_col,

        "secondary_axis_columns":
            (
                [relative_time_col]
                if relative_time_col
                is not None
                else []
            ),

        "header_row_count":
            first_data_row,

        "sample_count":
            len(
                samples
            ),

        "signal_count":
            len(
                signals
            ),
    }


# ============================================================
# Companion metadata
# ============================================================

def build_companion_rows(rows):
    result = []

    for source in rows:

        source_rows = load_rows(
            source.get(
                "source_rows_json",
                ""
            )
        )

        companion_id = (
            "g4meta_"
            + identifier(
                source.get(
                    "report_id",
                    "",
                ),
                source.get(
                    "timeseries_candidate_id",
                    "",
                ),
                source.get(
                    "source_heading",
                    "",
                ),
            )
        )

        result.append({
            **{
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "companion_metadata_id":
                companion_id,

            "timeseries_candidate_id":
                source.get(
                    "timeseries_candidate_id",
                    "",
                ),

            "source_heading":
                source.get(
                    "source_heading",
                    "",
                ),

            "audited_family":
                source.get(
                    "audited_family",
                    "",
                ),

            "audited_component":
                source.get(
                    "audited_component",
                    "",
                ),

            "audit_reason":
                source.get(
                    "audit_reason",
                    "",
                ),

            "source_record_start":
                source.get(
                    "source_record_start",
                    "",
                ),

            "source_record_end":
                source.get(
                    "source_record_end",
                    "",
                ),

            "source_rows_json":
                json_compact(
                    source_rows
                ),

            "processing_status":
                "preserved_companion_metadata",

            "linkage_status":
                "not_yet_linked_to_series",
        })

    return result


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--audit-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_audit_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_structured_v1"
        ),
    )

    args = parser.parse_args()

    audit_dir = (
        args.audit_directory
    )

    accepted_path = (
        audit_dir
        / "accepted_timeseries_sections.csv"
    )

    companion_path = (
        audit_dir
        / "timeseries_companion_metadata_sections.csv"
    )

    if not accepted_path.exists():
        raise FileNotFoundError(
            accepted_path
        )

    if not companion_path.exists():
        raise FileNotFoundError(
            companion_path
        )

    accepted = read_csv(
        accepted_path
    )

    companion_input = read_csv(
        companion_path
    )

    registry = []
    signal_registry = []
    samples = []
    values_long = []
    audit_rows = []
    failures = []

    parser_orientation_counts = Counter()
    trimmed_pid_section_count = 0
    orientation_override_count = 0

    # ========================================================
    # Extract
    # ========================================================

    for index, source in enumerate(
        accepted,
        1,
    ):

        candidate_id = source.get(
            "timeseries_candidate_id",
            "",
        )

        series_id = (
            "g4csv_"
            + identifier(
                source.get(
                    "report_id",
                    "",
                ),
                candidate_id,
                source.get(
                    "source_heading",
                    "",
                ),
            )
        )

        audited_orientation = norm(
            source.get(
                "table_orientation",
                "",
            )
        )

        source_rows_original = load_rows(
            source.get(
                "source_rows_json",
                ""
            )
        )

        source_rows = trim_non_timeseries_tail(
            source_rows_original
        )

        if (
            len(source_rows)
            < len(
                source_rows_original
            )
        ):
            trimmed_pid_section_count += 1

        if not source_rows:

            failures.append({
                **{
                    key:
                        source.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "timeseries_candidate_id":
                    candidate_id,

                "series_id":
                    series_id,

                "source_heading":
                    source.get(
                        "source_heading",
                        "",
                    ),

                "table_orientation":
                    audited_orientation,

                "error_type":
                    "empty_source_rows",

                "error":
                    (
                        "source_rows_json was empty or became empty "
                        "after known tail trimming."
                    ),
            })

            continue

        try:

            if (
                audited_orientation
                == "buffer_order_table"
            ):

                parser_orientation = (
                    "buffer_order_table"
                )

                parsed = (
                    parse_buffer_order_table(
                        source,
                        source_rows,
                        series_id,
                    )
                )

            elif has_transposed_time_axis(
                source_rows
            ):

                parser_orientation = (
                    "samples_by_columns"
                )

                if (
                    audited_orientation
                    != "samples_by_columns"
                ):
                    orientation_override_count += 1

                parsed = (
                    parse_samples_by_columns(
                        source,
                        source_rows,
                        series_id,
                    )
                )

            elif (
                audited_orientation
                == "samples_by_rows"
            ):

                parser_orientation = (
                    "samples_by_rows"
                )

                parsed = (
                    parse_samples_by_rows(
                        source,
                        source_rows,
                        series_id,
                    )
                )

            elif (
                audited_orientation
                == "samples_by_columns"
            ):

                parser_orientation = (
                    "samples_by_columns"
                )

                parsed = (
                    parse_samples_by_columns(
                        source,
                        source_rows,
                        series_id,
                    )
                )

            else:

                raise ValueError(
                    "Unsupported table orientation: "
                    f"{audited_orientation}"
                )

        except Exception as exc:

            failures.append({
                **{
                    key:
                        source.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "timeseries_candidate_id":
                    candidate_id,

                "series_id":
                    series_id,

                "source_heading":
                    source.get(
                        "source_heading",
                        "",
                    ),

                "table_orientation":
                    audited_orientation,

                "error_type":
                    type(
                        exc
                    ).__name__,

                "error":
                    str(
                        exc
                    ),
            })

            continue

        parser_orientation_counts[
            parser_orientation
        ] += 1

        signal_registry.extend(
            parsed[
                "signals"
            ]
        )

        samples.extend(
            parsed[
                "samples"
            ]
        )

        values_long.extend(
            parsed[
                "values"
            ]
        )

        registry.append({
            **{
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                series_id,

            "timeseries_candidate_id":
                candidate_id,

            "source_heading":
                source.get(
                    "source_heading",
                    "",
                ),

            "source_path":
                source.get(
                    "source_path",
                    "",
                ),

            "source_record_start":
                source.get(
                    "source_record_start",
                    "",
                ),

            "source_record_end":
                source.get(
                    "source_record_end",
                    "",
                ),

            "family":
                source.get(
                    "audited_family",
                    "",
                ),

            "component":
                source.get(
                    "audited_component",
                    "",
                ),

            "audited_orientation":
                audited_orientation,

            "table_orientation":
                parser_orientation,

            "orientation_overridden":
                (
                    parser_orientation
                    != audited_orientation
                ),

            "pid_tail_trimmed":
                (
                    len(source_rows)
                    < len(
                        source_rows_original
                    )
                ),

            "axis_type":
                parsed[
                    "axis_type"
                ],

            "axis_label_raw":
                parsed[
                    "axis_label_raw"
                ],

            "axis_unit_raw":
                parsed[
                    "axis_unit_raw"
                ],

            "axis_column_index":
                parsed[
                    "axis_column_index"
                ],

            "secondary_axis_columns_json":
                json_compact(
                    parsed[
                        "secondary_axis_columns"
                    ]
                ),

            "header_row_count":
                parsed[
                    "header_row_count"
                ],

            "sample_count":
                parsed[
                    "sample_count"
                ],

            "signal_count":
                parsed[
                    "signal_count"
                ],

            "processing_status":
                "structured_extracted",

            "semantic_normalization_status":
                "not_normalized",

            "unit_conversion_status":
                "not_converted",
        })

        audit_rows.append({
            **{
                key:
                    source.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                series_id,

            "timeseries_candidate_id":
                candidate_id,

            "source_heading":
                source.get(
                    "source_heading",
                    "",
                ),

            "family":
                source.get(
                    "audited_family",
                    "",
                ),

            "component":
                source.get(
                    "audited_component",
                    "",
                ),

            "audited_orientation":
                audited_orientation,

            "table_orientation":
                parser_orientation,

            "pid_tail_trimmed":
                (
                    len(source_rows)
                    < len(
                        source_rows_original
                    )
                ),

            "axis_type":
                parsed[
                    "axis_type"
                ],

            "sample_count":
                parsed[
                    "sample_count"
                ],

            "signal_count":
                parsed[
                    "signal_count"
                ],

            "long_value_count":
                len(
                    parsed[
                        "values"
                    ]
                ),

            "status":
                "success",

            "issue":
                "",
        })

        if (
            index % 250 == 0
            or index
            == len(
                accepted
            )
        ):

            print(
                "Structured Group 4 CSV "
                f"{index}/{len(accepted)} sections...",
                flush=True,
            )

    companion_rows = (
        build_companion_rows(
            companion_input
        )
    )

    # ========================================================
    # Validation
    # ========================================================

    validation = []

    def add_check(
        name,
        condition,
        observed,
        expected,
        severity="hard",
    ):
        validation.append({
            "check":
                name,

            "status":
                (
                    "PASS"
                    if condition
                    else "FAIL"
                ),

            "severity":
                severity,

            "observed":
                str(
                    observed
                ),

            "expected":
                str(
                    expected
                ),
        })

    add_check(
        "accepted_sections_accounted_for",
        (
            len(
                registry
            )
            + len(
                failures
            )
            == len(
                accepted
            )
        ),
        (
            len(
                registry
            )
            + len(
                failures
            )
        ),
        len(
            accepted
        ),
    )

    add_check(
        "input_accepted_section_count",
        len(
            accepted
        )
        == 8265,
        len(
            accepted
        ),
        8265,
        severity="warning",
    )

    add_check(
        "companion_metadata_count",
        len(
            companion_rows
        )
        == len(
            companion_input
        ),
        len(
            companion_rows
        ),
        len(
            companion_input
        ),
    )

    series_ids = [
        row[
            "series_id"
        ]
        for row in registry
    ]

    signal_ids = [
        row[
            "signal_id"
        ]
        for row in signal_registry
    ]

    sample_ids = [
        row[
            "sample_id"
        ]
        for row in samples
    ]

    add_check(
        "series_ids_unique",
        len(
            series_ids
        )
        == len(
            set(
                series_ids
            )
        ),
        len(
            set(
                series_ids
            )
        ),
        len(
            series_ids
        ),
    )

    add_check(
        "signal_ids_unique",
        len(
            signal_ids
        )
        == len(
            set(
                signal_ids
            )
        ),
        len(
            set(
                signal_ids
            )
        ),
        len(
            signal_ids
        ),
    )

    add_check(
        "sample_ids_unique",
        len(
            sample_ids
        )
        == len(
            set(
                sample_ids
            )
        ),
        len(
            set(
                sample_ids
            )
        ),
        len(
            sample_ids
        ),
    )

    signal_id_set = set(
        signal_ids
    )

    sample_id_set = set(
        sample_ids
    )

    orphan_signal_values = sum(
        1
        for row in values_long
        if row[
            "signal_id"
        ]
        not in signal_id_set
    )

    orphan_sample_values = sum(
        1
        for row in values_long
        if row[
            "sample_id"
        ]
        not in sample_id_set
    )

    add_check(
        "long_values_have_known_signal",
        orphan_signal_values
        == 0,
        orphan_signal_values,
        0,
    )

    add_check(
        "long_values_have_known_sample",
        orphan_sample_values
        == 0,
        orphan_sample_values,
        0,
    )

    empty_sample_series = sum(
        1
        for row in registry
        if int(
            row[
                "sample_count"
            ]
        ) < 1
    )

    empty_signal_series = sum(
        1
        for row in registry
        if int(
            row[
                "signal_count"
            ]
        ) < 1
    )

    add_check(
        "successful_series_have_samples",
        empty_sample_series
        == 0,
        empty_sample_series,
        0,
    )

    add_check(
        "successful_series_have_signals",
        empty_signal_series
        == 0,
        empty_signal_series,
        0,
    )

    # ========================================================
    # Summaries
    # ========================================================

    family_counts = Counter(
        row[
            "family"
        ]
        for row in registry
    )

    component_counts = Counter(
        row[
            "component"
        ]
        for row in registry
    )

    orientation_counts = Counter(
        row[
            "table_orientation"
        ]
        for row in registry
    )

    axis_type_counts = Counter(
        row[
            "axis_type"
        ]
        for row in registry
    )

    signal_label_counts = Counter(
        row[
            "signal_label_raw"
        ]
        for row in signal_registry
    )

    signal_unit_counts = Counter(
        row[
            "signal_unit_raw"
        ]
        for row in signal_registry
        if row[
            "signal_unit_raw"
        ]
    )

    report_ids = {
        row[
            "report_id"
        ]
        for row in registry
    }

    # ========================================================
    # Write outputs
    # ========================================================

    out = (
        args.output_directory
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        out
        / "timeseries_registry.csv",
        registry,
        [
            *BASE,
            "series_id",
            "timeseries_candidate_id",
            "source_heading",
            "source_path",
            "source_record_start",
            "source_record_end",
            "family",
            "component",
            "audited_orientation",
            "table_orientation",
            "orientation_overridden",
            "pid_tail_trimmed",
            "axis_type",
            "axis_label_raw",
            "axis_unit_raw",
            "axis_column_index",
            "secondary_axis_columns_json",
            "header_row_count",
            "sample_count",
            "signal_count",
            "processing_status",
            "semantic_normalization_status",
            "unit_conversion_status",
        ],
    )

    write_csv(
        out
        / "timeseries_signal_registry.csv",
        signal_registry,
        [
            *BASE,
            "series_id",
            "signal_id",
            "signal_position",
            "source_column_index",
            "source_row_index",
            "signal_label_raw",
            "signal_unit_raw",
            "header_fragments_json",
            "table_orientation",
            "semantic_normalization_status",
        ],
    )

    write_csv(
        out
        / "timeseries_samples_wide.csv",
        samples,
        [
            *BASE,
            "series_id",
            "sample_id",
            "sample_index",
            "axis_type",
            "axis_label_raw",
            "axis_unit_raw",
            "axis_value_raw",
            "axis_value_numeric",
            "secondary_axes_json",
            "values_json",
            "source_section_row_index",
            "table_orientation",
        ],
    )

    write_csv(
        out
        / "timeseries_values_long.csv",
        values_long,
        [
            *BASE,
            "series_id",
            "sample_id",
            "sample_index",
            "signal_id",
            "signal_position",
            "signal_label_raw",
            "signal_unit_raw",
            "axis_type",
            "axis_label_raw",
            "axis_unit_raw",
            "axis_value_raw",
            "axis_value_numeric",
            "value_raw",
            "value_numeric",
            "value_is_missing_or_na",
            "source_section_row_index",
            "source_column_index",
            "table_orientation",
        ],
    )

    write_csv(
        out
        / "timeseries_companion_metadata.csv",
        companion_rows,
        [
            *BASE,
            "companion_metadata_id",
            "timeseries_candidate_id",
            "source_heading",
            "audited_family",
            "audited_component",
            "audit_reason",
            "source_record_start",
            "source_record_end",
            "source_rows_json",
            "processing_status",
            "linkage_status",
        ],
    )

    write_csv(
        out
        / "timeseries_audit.csv",
        audit_rows,
        [
            *BASE,
            "series_id",
            "timeseries_candidate_id",
            "source_heading",
            "family",
            "component",
            "audited_orientation",
            "table_orientation",
            "pid_tail_trimmed",
            "axis_type",
            "sample_count",
            "signal_count",
            "long_value_count",
            "status",
            "issue",
        ],
    )

    write_csv(
        out
        / "extraction_failures.csv",
        failures,
        [
            *BASE,
            "timeseries_candidate_id",
            "series_id",
            "source_heading",
            "table_orientation",
            "error_type",
            "error",
        ],
    )

    write_csv(
        out
        / "validation_report.csv",
        validation,
        [
            "check",
            "status",
            "severity",
            "observed",
            "expected",
        ],
    )

    # ========================================================
    # Metadata
    # ========================================================

    hard_failures = [
        row
        for row in validation
        if (
            row[
                "status"
            ]
            == "FAIL"
            and row[
                "severity"
            ]
            == "hard"
        )
    ]

    warning_failures = [
        row
        for row in validation
        if (
            row[
                "status"
            ]
            == "FAIL"
            and row[
                "severity"
            ]
            == "warning"
        )
    ]

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "CSV structural extraction",

        "input_accepted_sections":
            len(
                accepted
            ),

        "input_companion_metadata_sections":
            len(
                companion_input
            ),

        "structured_series_count":
            len(
                registry
            ),

        "failed_section_count":
            len(
                failures
            ),

        "reports_with_structured_timeseries":
            len(
                report_ids
            ),

        "signal_registry_rows":
            len(
                signal_registry
            ),

        "sample_rows":
            len(
                samples
            ),

        "long_value_rows":
            len(
                values_long
            ),

        "companion_metadata_rows":
            len(
                companion_rows
            ),

        "pid_tail_trimmed_section_count":
            trimmed_pid_section_count,

        "orientation_override_count":
            orientation_override_count,

        "parser_orientation_counts":
            dict(
                parser_orientation_counts
            ),

        "family_counts":
            dict(
                family_counts
            ),

        "component_counts":
            dict(
                component_counts
            ),

        "orientation_counts":
            dict(
                orientation_counts
            ),

        "axis_type_counts":
            dict(
                axis_type_counts
            ),

        "unique_raw_signal_labels":
            len(
                signal_label_counts
            ),

        "top_raw_signal_labels":
            signal_label_counts.most_common(
                40
            ),

        "raw_unit_counts":
            dict(
                signal_unit_counts
            ),

        "validation_checks":
            len(
                validation
            ),

        "validation_failures":
            sum(
                1
                for row
                in validation
                if row[
                    "status"
                ]
                == "FAIL"
            ),

        "hard_validation_failures":
            len(
                hard_failures
            ),

        "warning_validation_failures":
            len(
                warning_failures
            ),

        "scope":
            (
                "Structural extraction of accepted Group 4 CSV "
                "time-series sections. PID/hex tails beginning at "
                "PIDsStart are excluded from Group 4 parsing. "
                "Samples-by-rows, samples-by-columns, and PCM/buffer "
                "layouts are supported. Transposed structure is "
                "re-detected after PID trimming. Single-signal tables "
                "with unit-only column headers use the source section "
                "heading as the structural signal identity. Raw values, "
                "units, source labels, and provenance remain preserved. "
                "No semantic normalization, unit conversion, event "
                "identity inference, or PDF extraction is performed."
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
            ensure_ascii=False,
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
            ensure_ascii=False,
        )
    )

    print()
    print(
        f"Outputs: {out}"
    )

    if hard_failures:

        print()
        print(
            "GROUP 4 CSV STRUCTURAL EXTRACTION "
            "HAS HARD VALIDATION FAILURES."
        )

        for row in hard_failures:

            print(
                f"- {row['check']}: "
                f"observed={row['observed']} "
                f"expected={row['expected']}"
            )

        raise SystemExit(1)

    print()
    print(
        "GROUP 4 CSV STRUCTURAL EXTRACTION COMPLETE."
    )


if __name__ == "__main__":
    main()