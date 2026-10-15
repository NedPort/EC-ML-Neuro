"""
Build structured Group 4 PDF time-series datasets.

Targeted corrections in this version
------------------------------------
1. Samples-by-rows accepts both "Time" and "Times" axis headers.
   This fixes the four accepted pre-crash tables headed "Times (sec)".

2. Samples-by-columns supports repeated transposed blocks, e.g.:

       Time (milliseconds) | -70 ... 70
       Delta-V             | ...
       Time (milliseconds) |  80 ... 220
       Delta-V             | ...

   Later Time rows are treated as additional axis blocks, not signals.
   Signal identities are unified across blocks by their raw labels.

3. Physical PDF tables remain independent. Continuation groups are
   preserved but are NOT merged.

No semantic normalization, unit conversion, event-identity inference,
or CSV/PDF integration is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
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
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]):
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


# ============================================================
# General helpers
# ============================================================

def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").strip(),
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
    text = "|".join(norm(part) for part in parts)
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:24]


def load_rows(value):
    try:
        rows = json.loads(value)
        if isinstance(rows, list):
            return rows
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def json_compact(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def populated(row):
    return [
        norm(value)
        for value in row
        if norm(value)
    ]


def first_populated(row):
    for index, value in enumerate(row):
        value = norm(value)
        if value:
            return index, value
    return None, ""


def as_int_or_blank(value):
    text = norm(value)
    if not text:
        return ""
    try:
        return int(float(text))
    except ValueError:
        return ""


# ============================================================
# Missing / unavailable values
# ============================================================

MISSING_VALUES = {
    "",
    "n/a",
    "na",
    "sna",
    "not available",
    "data not available",
    "not applicable",
    "unknown",
    "not recorded",
    "invalid",
}


def is_missing_or_na(value):
    return norm(value).casefold() in MISSING_VALUES


# ============================================================
# Numeric helpers
# ============================================================

def strip_axis_annotation(value):
    text = norm(value)

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

    return norm(text)


def is_numeric(value):
    text = strip_axis_annotation(value).replace(",", "")
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


def numeric_value(value):
    text = strip_axis_annotation(value).replace(",", "")

    if not is_numeric(text):
        return ""

    try:
        number = float(text)
        if math.isfinite(number):
            return number
    except ValueError:
        pass

    return ""


# ============================================================
# Unit helpers
# ============================================================

UNIT_PATTERNS = [
    r"km/h",
    r"mph",
    r"rpm",
    r"\bg\b",
    r"m/s(?:\^?2|²)?",
    r"ft/s(?:\^?2|²)?",
    r"deg(?:ree)?s?",
    r"deg/sec",
    r"degrees?/sec",
    r"rad/s",
    r"percent",
    r"%",
    r"sec(?:onds?)?",
    r"msec",
    r"milliseconds?",
    r"\bms\b",
]


def extract_unit_from_text(value):
    text = norm(value)

    if not text:
        return ""

    matches = re.findall(
        r"\(([^()]*)\)",
        text,
    )

    for candidate in reversed(matches):
        candidate = norm(candidate)

        if any(
            re.search(pattern, candidate, re.I)
            for pattern in UNIT_PATTERNS
        ):
            return candidate

    # Be conservative outside parentheses. Only standalone unit-like
    # text should be treated as a unit; words such as "Percent Throttle"
    # are labels, not units.
    if re.fullmatch(
        r"\s*(?:"
        r"km/h|mph|rpm|g|"
        r"m/s(?:\^?2|²)?|"
        r"ft/s(?:\^?2|²)?|"
        r"deg(?:ree)?s?|"
        r"deg/sec|degrees?/sec|rad/s|"
        r"percent|%|"
        r"sec(?:onds?)?|msec|milliseconds?|ms"
        r")\s*",
        text,
        re.I,
    ):
        return text

    return ""


# ============================================================
# Axis helpers
# ============================================================

def is_axis_header_text(value):
    text = norm(value)

    return bool(
        re.search(
            r"\b(?:"
            r"times?|"
            r"seconds?\s+before|"
            r"seconds?\s+after|"
            r"sample\s+count|"
            r"parameter"
            r")\b",
            text,
            re.I,
        )
    )


def classify_axis_type(label):
    text = norm_key(label)

    if "sample count" in text:
        return "sample_count_relative_to_trigger"

    if (
        "seconds before" in text
        or "sec before" in text
    ):
        return "relative_time_before_event"

    if (
        "seconds after" in text
        or "sec after" in text
    ):
        return "relative_time_after_event"

    if "time" in text:
        return "explicit_time"

    return "ordered_numeric_axis"


def infer_axis_unit(label, values=None):
    text = norm(label)

    if re.search(
        r"\bmsec\b|\bms\b|milliseconds?",
        text,
        re.I,
    ):
        return "ms"

    if re.search(
        r"\bsec\b|\bseconds?\b",
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

    if values:
        sample_text = " ".join(
            norm(value)
            for value in values[:10]
        )

        if re.search(
            r"\bsec\b|\bseconds?\b",
            sample_text,
            re.I,
        ):
            return "s"

        if re.search(
            r"\bms\b|\bmsec\b",
            sample_text,
            re.I,
        ):
            return "ms"

    return ""


# ============================================================
# Signal helper
# ============================================================

def make_signal(
    source,
    series_id,
    signal_position,
    label,
    unit,
    source_row_index="",
    source_column_index="",
    header_fragments=None,
    orientation="",
):
    signal_id = (
        "g4pdfsig_"
        + identifier(
            series_id,
            signal_position,
        )
    )

    return {
        **{
            key: source.get(key, "")
            for key in BASE
        },

        "series_id":
            series_id,

        "signal_id":
            signal_id,

        "signal_position":
            signal_position,

        "source_row_index":
            source_row_index,

        "source_column_index":
            source_column_index,

        "signal_label_raw":
            norm(label),

        "signal_unit_raw":
            norm(unit),

        "header_fragments_json":
            json_compact(
                header_fragments or []
            ),

        "table_orientation":
            orientation,

        "semantic_normalization_status":
            "not_normalized",
    }


# ============================================================
# Samples-by-rows parser
# ============================================================

def detect_row_axis_structure(rows):
    """
    Detect row-oriented temporal tables.

    Targeted correction:
        accepts "Time (...)" and "Times (...)".
    """

    best = None

    for header_index in range(
        min(len(rows), 10)
    ):
        header = rows[header_index]

        for axis_col, header_value in enumerate(header):
            header_value = norm(header_value)

            if not header_value:
                continue

            if not is_axis_header_text(
                header_value
            ):
                continue

            # "Parameter" generally belongs to transposed layout,
            # not row-wise layout.
            if (
                norm(header_value).casefold()
                == "parameter"
            ):
                continue

            sample_rows = []

            for row_index in range(
                header_index + 1,
                len(rows),
            ):
                row = rows[row_index]

                if axis_col >= len(row):
                    continue

                axis_value = norm(
                    row[axis_col]
                )

                if not is_numeric(axis_value):
                    continue

                if len(populated(row)) < 2:
                    continue

                sample_rows.append(
                    row_index
                )

            if len(sample_rows) < 2:
                continue

            candidate = {
                "header_row_index":
                    header_index,

                "axis_column_index":
                    axis_col,

                "axis_label":
                    header_value,

                "sample_row_indexes":
                    sample_rows,

                "sample_count":
                    len(sample_rows),
            }

            if (
                best is None
                or candidate["sample_count"]
                > best["sample_count"]
            ):
                best = candidate

    return best


def parse_samples_by_rows(
    source,
    rows,
    series_id,
):
    structure = detect_row_axis_structure(
        rows
    )

    if structure is None:
        raise ValueError(
            "Could not reconstruct samples-by-rows temporal axis."
        )

    header_row_index = (
        structure["header_row_index"]
    )

    axis_col = (
        structure["axis_column_index"]
    )

    axis_label = (
        structure["axis_label"]
    )

    sample_row_indexes = (
        structure["sample_row_indexes"]
    )

    header = rows[
        header_row_index
    ]

    measurement_columns = []

    max_width = max(
        len(rows[row_index])
        for row_index
        in sample_row_indexes
    )

    for column_index in range(
        max_width
    ):
        if column_index == axis_col:
            continue

        nonblank_count = 0

        for row_index in sample_row_indexes:
            row = rows[row_index]

            if (
                column_index < len(row)
                and norm(
                    row[column_index]
                )
            ):
                nonblank_count += 1

        if nonblank_count >= 1:
            measurement_columns.append(
                column_index
            )

    if not measurement_columns:
        raise ValueError(
            "No measurement columns found."
        )

    signals = []
    signal_by_column = {}

    for signal_position, column_index in enumerate(
        measurement_columns,
        1,
    ):
        raw_header = (
            norm(header[column_index])
            if column_index < len(header)
            else ""
        )

        fragments = []

        for row_index in range(
            header_row_index + 1
        ):
            row = rows[row_index]

            if column_index < len(row):
                value = norm(
                    row[column_index]
                )

                if value:
                    fragments.append(
                        value
                    )

        if not raw_header:
            raw_header = (
                fragments[-1]
                if fragments
                else (
                    f"source_column_"
                    f"{column_index}"
                )
            )

        unit = extract_unit_from_text(
            raw_header
        )

        label = raw_header

        only_unit_like = bool(
            unit
            and norm_key(raw_header)
            == norm_key(unit)
        )

        if (
            only_unit_like
            or label.startswith(
                "source_column_"
            )
        ):
            heading = norm(
                source.get(
                    "source_heading_hint",
                    "",
                )
            )

            if heading:
                label = heading

        signal = make_signal(
            source=source,
            series_id=series_id,
            signal_position=signal_position,
            label=label,
            unit=unit,
            source_row_index=header_row_index,
            source_column_index=column_index,
            header_fragments=(
                fragments
                if fragments
                else [raw_header]
            ),
            orientation="samples_by_rows",
        )

        signals.append(signal)
        signal_by_column[
            column_index
        ] = signal

    axis_values_raw = [
        norm(
            rows[row_index][axis_col]
        )
        for row_index
        in sample_row_indexes
    ]

    axis_type = classify_axis_type(
        axis_label
    )

    axis_unit = infer_axis_unit(
        axis_label,
        axis_values_raw,
    )

    samples = []
    values_long = []

    for sample_index, row_index in enumerate(
        sample_row_indexes
    ):
        row = rows[row_index]

        axis_raw = (
            norm(row[axis_col])
            if axis_col < len(row)
            else ""
        )

        sample_id = (
            "g4pdfsample_"
            + identifier(
                series_id,
                sample_index,
            )
        )

        values_map = {}

        for column_index in measurement_columns:
            signal = signal_by_column[
                column_index
            ]

            raw_value = (
                norm(row[column_index])
                if column_index < len(row)
                else ""
            )

            values_map[
                signal["signal_id"]
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
                    signal["signal_id"],

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
                    is_missing_or_na(
                        raw_value
                    ),

                "source_page_number":
                    source.get(
                        "page_number",
                        "",
                    ),

                "source_table_index_on_page":
                    source.get(
                        "table_index_on_page",
                        "",
                    ),

                "source_table_row_index":
                    row_index,

                "source_table_column_index":
                    column_index,

                "table_orientation":
                    "samples_by_rows",
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

            "source_page_number":
                source.get(
                    "page_number",
                    "",
                ),

            "source_table_index_on_page":
                source.get(
                    "table_index_on_page",
                    "",
                ),

            "source_table_row_index":
                row_index,

            "table_orientation":
                "samples_by_rows",
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

        "sample_count":
            len(samples),

        "signal_count":
            len(signals),

        "header_row_index":
            header_row_index,

        "axis_column_index":
            axis_col,

        "transposed_block_count":
            "",
    }


# ============================================================
# Samples-by-columns parser
# ============================================================

def find_transposed_blocks(rows):
    """
    Find ALL transposed temporal blocks in a physical PDF table.

    Example:

        Time (milliseconds) | -70 ... 70
        Delta-V             | ...
        Time (milliseconds) |  80 ... 220
        Delta-V             | ...

    Returns one block record for each axis row.
    """

    axis_rows = []

    for row_index in range(
        min(len(rows), 1000)
    ):
        row = rows[row_index]

        axis_label_col, axis_label = (
            first_populated(row)
        )

        if axis_label_col is None:
            continue

        if not is_axis_header_text(
            axis_label
        ):
            continue

        sample_columns = []

        for column_index, value in enumerate(
            row
        ):
            if column_index == axis_label_col:
                continue

            if is_numeric(value):
                sample_columns.append(
                    column_index
                )

        if len(sample_columns) < 2:
            continue

        axis_rows.append({
            "axis_row_index":
                row_index,

            "axis_label_column":
                axis_label_col,

            "axis_label":
                axis_label,

            "sample_columns":
                sample_columns,
        })

    if not axis_rows:
        return []

    blocks = []

    for block_index, axis_info in enumerate(
        axis_rows
    ):
        axis_row_index = (
            axis_info[
                "axis_row_index"
            ]
        )

        next_axis_row_index = (
            axis_rows[
                block_index + 1
            ][
                "axis_row_index"
            ]
            if block_index + 1
            < len(axis_rows)
            else len(rows)
        )

        sample_columns = (
            axis_info[
                "sample_columns"
            ]
        )

        signal_rows = []

        for signal_row_index in range(
            axis_row_index + 1,
            next_axis_row_index,
        ):
            signal_row = rows[
                signal_row_index
            ]

            label_col, label = (
                first_populated(
                    signal_row
                )
            )

            if label_col is None:
                continue

            # Never treat another axis-like row as a signal.
            if is_axis_header_text(
                label
            ):
                continue

            value_count = 0

            for column_index in sample_columns:
                if (
                    column_index
                    < len(signal_row)
                    and norm(
                        signal_row[
                            column_index
                        ]
                    )
                ):
                    value_count += 1

            if value_count >= 2:
                signal_rows.append({
                    "row_index":
                        signal_row_index,

                    "label_column":
                        label_col,

                    "label":
                        label,
                })

        if signal_rows:
            blocks.append({
                **axis_info,

                "signal_rows":
                    signal_rows,

                "sample_count":
                    len(
                        sample_columns
                    ),
            })

    return blocks


def parse_samples_by_columns(
    source,
    rows,
    series_id,
):
    blocks = find_transposed_blocks(
        rows
    )

    if not blocks:
        raise ValueError(
            "Could not reconstruct samples-by-columns temporal axis."
        )

    # --------------------------------------------------------
    # Build one signal registry across all repeated blocks.
    # The same raw signal label in multiple blocks is one signal.
    # --------------------------------------------------------

    signal_key_to_info = {}

    for block in blocks:
        for signal_row in block[
            "signal_rows"
        ]:
            raw_label = norm(
                signal_row[
                    "label"
                ]
            )

            key = norm_key(
                raw_label
            )

            if not key:
                continue

            if key not in signal_key_to_info:
                signal_key_to_info[
                    key
                ] = {
                    "raw_label":
                        raw_label,

                    "source_row_index":
                        signal_row[
                            "row_index"
                        ],

                    "source_column_index":
                        signal_row[
                            "label_column"
                        ],
                }

    if not signal_key_to_info:
        raise ValueError(
            "No signals found in transposed temporal blocks."
        )

    signals = []
    signal_by_key = {}

    for signal_position, (
        key,
        info,
    ) in enumerate(
        signal_key_to_info.items(),
        1,
    ):
        raw_label = info[
            "raw_label"
        ]

        unit = extract_unit_from_text(
            raw_label
        )

        signal = make_signal(
            source=source,
            series_id=series_id,
            signal_position=signal_position,
            label=raw_label,
            unit=unit,
            source_row_index=(
                info[
                    "source_row_index"
                ]
            ),
            source_column_index=(
                info[
                    "source_column_index"
                ]
            ),
            header_fragments=[
                raw_label
            ],
            orientation="samples_by_columns",
        )

        signals.append(
            signal
        )

        signal_by_key[
            key
        ] = signal

    # --------------------------------------------------------
    # Choose effective axis metadata from first block.
    # --------------------------------------------------------

    first_block = blocks[0]

    first_axis_row = rows[
        first_block[
            "axis_row_index"
        ]
    ]

    first_axis_values = [
        norm(
            first_axis_row[
                column_index
            ]
        )
        for column_index
        in first_block[
            "sample_columns"
        ]
    ]

    first_axis_label = norm(
        first_block[
            "axis_label"
        ]
    )

    if (
        first_axis_label.casefold()
        == "parameter"
    ):
        sample_text = " ".join(
            first_axis_values
        )

        if re.search(
            r"\bsec\b|\bseconds?\b",
            sample_text,
            re.I,
        ):
            axis_label_effective = (
                "Seconds Before Event"
            )
        else:
            axis_label_effective = (
                first_axis_label
            )
    else:
        axis_label_effective = (
            first_axis_label
        )

    axis_type = classify_axis_type(
        axis_label_effective
    )

    all_axis_values = []

    for block in blocks:
        axis_row = rows[
            block[
                "axis_row_index"
            ]
        ]

        for column_index in block[
            "sample_columns"
        ]:
            if column_index < len(
                axis_row
            ):
                all_axis_values.append(
                    norm(
                        axis_row[
                            column_index
                        ]
                    )
                )

    axis_unit = infer_axis_unit(
        axis_label_effective,
        all_axis_values,
    )

    # --------------------------------------------------------
    # Build samples sequentially across all blocks.
    # --------------------------------------------------------

    samples = []
    values_long = []
    sample_index = 0

    for block_index, block in enumerate(
        blocks
    ):
        axis_row_index = (
            block[
                "axis_row_index"
            ]
        )

        axis_row = rows[
            axis_row_index
        ]

        # Map signal key -> source row for this block.
        block_signal_rows = {}

        for signal_row in block[
            "signal_rows"
        ]:
            key = norm_key(
                signal_row[
                    "label"
                ]
            )

            if key:
                block_signal_rows[
                    key
                ] = signal_row[
                    "row_index"
                ]

        for column_index in block[
            "sample_columns"
        ]:
            axis_raw = (
                norm(
                    axis_row[
                        column_index
                    ]
                )
                if column_index
                < len(axis_row)
                else ""
            )

            sample_id = (
                "g4pdfsample_"
                + identifier(
                    series_id,
                    sample_index,
                )
            )

            values_map = {}

            for key, signal in signal_by_key.items():
                source_row_index = (
                    block_signal_rows.get(
                        key
                    )
                )

                if source_row_index is None:
                    raw_value = ""
                else:
                    signal_row = rows[
                        source_row_index
                    ]

                    raw_value = (
                        norm(
                            signal_row[
                                column_index
                            ]
                        )
                        if column_index
                        < len(signal_row)
                        else ""
                    )

                values_map[
                    signal[
                        "signal_id"
                    ]
                ] = raw_value

                values_long.append({
                    **{
                        base_key:
                            source.get(
                                base_key,
                                ""
                            )
                        for base_key in BASE
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
                        axis_label_effective,

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
                        is_missing_or_na(
                            raw_value
                        ),

                    "source_page_number":
                        source.get(
                            "page_number",
                            "",
                        ),

                    "source_table_index_on_page":
                        source.get(
                            "table_index_on_page",
                            "",
                        ),

                    "source_table_row_index":
                        (
                            source_row_index
                            if source_row_index
                            is not None
                            else ""
                        ),

                    "source_table_column_index":
                        column_index,

                    "table_orientation":
                        "samples_by_columns",
                })

            samples.append({
                **{
                    base_key:
                        source.get(
                            base_key,
                            ""
                        )
                    for base_key in BASE
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
                    axis_label_effective,

                "axis_unit_raw":
                    axis_unit,

                "axis_value_raw":
                    axis_raw,

                "axis_value_numeric":
                    numeric_value(
                        axis_raw
                    ),

                "secondary_axes_json":
                    json_compact({
                        "transposed_block_index":
                            block_index,
                    }),

                "values_json":
                    json_compact(
                        values_map
                    ),

                "source_page_number":
                    source.get(
                        "page_number",
                        "",
                    ),

                "source_table_index_on_page":
                    source.get(
                        "table_index_on_page",
                        "",
                    ),

                "source_table_row_index":
                    axis_row_index,

                "table_orientation":
                    "samples_by_columns",
            })

            sample_index += 1

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
            axis_label_effective,

        "axis_unit_raw":
            axis_unit,

        "sample_count":
            len(samples),

        "signal_count":
            len(signals),

        "header_row_index":
            first_block[
                "axis_row_index"
            ],

        "axis_column_index":
            "",

        "transposed_block_count":
            len(blocks),
    }


# ============================================================
# Companion metadata
# ============================================================

def build_companion_rows(rows):
    result = []

    for source in rows:
        companion_id = (
            "g4pdfmeta_"
            + identifier(
                source.get(
                    "report_id",
                    "",
                ),
                source.get(
                    "pdf_candidate_id",
                    "",
                ),
                source.get(
                    "page_number",
                    "",
                ),
                source.get(
                    "table_index_on_page",
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

            "pdf_candidate_id":
                source.get(
                    "pdf_candidate_id",
                    "",
                ),

            "source_path":
                source.get(
                    "source_path",
                    "",
                ),

            "page_number":
                source.get(
                    "page_number",
                    "",
                ),

            "table_index_on_page":
                source.get(
                    "table_index_on_page",
                    "",
                ),

            "source_heading_hint":
                source.get(
                    "source_heading_hint",
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

            "source_rows_json":
                source.get(
                    "source_rows_json",
                    "",
                ),

            "processing_status":
                "preserved_pdf_companion_metadata",

            "linkage_status":
                "not_yet_linked_to_logical_series",
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
        "--resolved-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_resolved_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_structured_v1"
        ),
    )

    args = parser.parse_args()

    resolved = (
        args.resolved_directory
    )

    accepted_path = (
        resolved
        / "accepted_timeseries_tables.csv"
    )

    companion_path = (
        resolved
        / "companion_metadata_tables.csv"
    )

    graphical_path = (
        resolved
        / "graphical_review_tables.csv"
    )

    for path in (
        accepted_path,
        companion_path,
        graphical_path,
    ):
        if not path.exists():
            raise FileNotFoundError(
                path
            )

    accepted = read_csv(
        accepted_path
    )

    companion_input = read_csv(
        companion_path
    )

    graphical_review = read_csv(
        graphical_path
    )

    registry = []
    signal_registry = []
    samples = []
    values_long = []
    audit_rows = []
    failures = []

    orientation_counts = Counter()
    transposed_block_counts = Counter()

    # ========================================================
    # Extract accepted physical tables
    # ========================================================

    for index, source in enumerate(
        accepted,
        1,
    ):
        candidate_id = norm(
            source.get(
                "pdf_candidate_id",
                ""
            )
        )

        orientation = norm(
            source.get(
                "audited_orientation",
                ""
            )
        )

        source_rows = load_rows(
            source.get(
                "source_rows_json",
                ""
            )
        )

        series_id = (
            "g4pdf_"
            + identifier(
                source.get(
                    "report_id",
                    "",
                ),
                candidate_id,
                source.get(
                    "page_number",
                    "",
                ),
                source.get(
                    "table_index_on_page",
                    "",
                ),
            )
        )

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

                "pdf_candidate_id":
                    candidate_id,

                "series_id":
                    series_id,

                "source_heading_hint":
                    source.get(
                        "source_heading_hint",
                        "",
                    ),

                "audited_orientation":
                    orientation,

                "error_type":
                    "empty_source_rows",

                "error":
                    "source_rows_json is empty.",
            })

            continue

        try:
            if (
                orientation
                == "samples_by_rows"
            ):
                parsed = (
                    parse_samples_by_rows(
                        source,
                        source_rows,
                        series_id,
                    )
                )

            elif (
                orientation
                == "samples_by_columns"
            ):
                parsed = (
                    parse_samples_by_columns(
                        source,
                        source_rows,
                        series_id,
                    )
                )

            else:
                raise ValueError(
                    "Unsupported audited orientation: "
                    f"{orientation}"
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

                "pdf_candidate_id":
                    candidate_id,

                "series_id":
                    series_id,

                "source_heading_hint":
                    source.get(
                        "source_heading_hint",
                        "",
                    ),

                "audited_orientation":
                    orientation,

                "error_type":
                    type(exc).__name__,

                "error":
                    str(exc),
            })

            continue

        orientation_counts[
            orientation
        ] += 1

        block_count = (
            parsed.get(
                "transposed_block_count",
                "",
            )
        )

        if block_count != "":
            transposed_block_counts[
                int(block_count)
            ] += 1

        signal_registry.extend(
            parsed["signals"]
        )

        samples.extend(
            parsed["samples"]
        )

        values_long.extend(
            parsed["values"]
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

            "pdf_candidate_id":
                candidate_id,

            "source_path":
                source.get(
                    "source_path",
                    "",
                ),

            "page_number":
                source.get(
                    "page_number",
                    "",
                ),

            "table_index_on_page":
                source.get(
                    "table_index_on_page",
                    "",
                ),

            "source_heading_hint":
                source.get(
                    "source_heading_hint",
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

            "table_orientation":
                orientation,

            "axis_type":
                parsed["axis_type"],

            "axis_label_raw":
                parsed[
                    "axis_label_raw"
                ],

            "axis_unit_raw":
                parsed[
                    "axis_unit_raw"
                ],

            "header_row_index":
                parsed[
                    "header_row_index"
                ],

            "axis_column_index":
                parsed[
                    "axis_column_index"
                ],

            "sample_count":
                parsed[
                    "sample_count"
                ],

            "signal_count":
                parsed[
                    "signal_count"
                ],

            "transposed_block_count":
                block_count,

            "table_part_index":
                as_int_or_blank(
                    source.get(
                        "table_part_index",
                        "",
                    )
                ),

            "table_part_total":
                as_int_or_blank(
                    source.get(
                        "table_part_total",
                        "",
                    )
                ),

            "continuation_candidate_key":
                source.get(
                    "continuation_candidate_key",
                    "",
                ),

            "continuation_merge_status":
                (
                    "candidate_not_merged"
                    if norm(
                        source.get(
                            "continuation_candidate_key",
                            "",
                        )
                    )
                    else "not_applicable"
                ),

            "group2_handoff_page_support":
                source.get(
                    "group2_handoff_page_support",
                    "",
                ),

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

            "pdf_candidate_id":
                candidate_id,

            "page_number":
                source.get(
                    "page_number",
                    "",
                ),

            "table_index_on_page":
                source.get(
                    "table_index_on_page",
                    "",
                ),

            "source_heading_hint":
                source.get(
                    "source_heading_hint",
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

            "table_orientation":
                orientation,

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

            "transposed_block_count":
                block_count,

            "table_part_index":
                source.get(
                    "table_part_index",
                    "",
                ),

            "table_part_total":
                source.get(
                    "table_part_total",
                    "",
                ),

            "continuation_candidate_key":
                source.get(
                    "continuation_candidate_key",
                    "",
                ),

            "status":
                "success",

            "issue":
                "",
        })

        if (
            index % 100 == 0
            or index
            == len(accepted)
        ):
            print(
                "Structured Group 4 PDF "
                f"{index}/{len(accepted)} tables...",
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

    def check(
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
                str(observed),

            "expected":
                str(expected),
        })

    check(
        "accepted_tables_accounted_for",
        (
            len(registry)
            + len(failures)
            == len(accepted)
        ),
        (
            len(registry)
            + len(failures)
        ),
        len(accepted),
    )

    check(
        "input_accepted_table_count",
        len(accepted) == 861,
        len(accepted),
        861,
        severity="warning",
    )

    check(
        "all_accepted_tables_structured",
        len(failures) == 0,
        len(failures),
        0,
    )

    series_ids = [
        row["series_id"]
        for row in registry
    ]

    signal_ids = [
        row["signal_id"]
        for row in signal_registry
    ]

    sample_ids = [
        row["sample_id"]
        for row in samples
    ]

    check(
        "series_ids_unique",
        len(series_ids)
        == len(set(series_ids)),
        len(set(series_ids)),
        len(series_ids),
    )

    check(
        "signal_ids_unique",
        len(signal_ids)
        == len(set(signal_ids)),
        len(set(signal_ids)),
        len(signal_ids),
    )

    check(
        "sample_ids_unique",
        len(sample_ids)
        == len(set(sample_ids)),
        len(set(sample_ids)),
        len(sample_ids),
    )

    known_series = set(
        series_ids
    )

    known_signals = set(
        signal_ids
    )

    known_samples = set(
        sample_ids
    )

    orphan_signal_series = sum(
        1
        for row in signal_registry
        if row["series_id"]
        not in known_series
    )

    orphan_sample_series = sum(
        1
        for row in samples
        if row["series_id"]
        not in known_series
    )

    orphan_value_series = sum(
        1
        for row in values_long
        if row["series_id"]
        not in known_series
    )

    orphan_value_signal = sum(
        1
        for row in values_long
        if row["signal_id"]
        not in known_signals
    )

    orphan_value_sample = sum(
        1
        for row in values_long
        if row["sample_id"]
        not in known_samples
    )

    check(
        "orphan_signal_series_refs",
        orphan_signal_series == 0,
        orphan_signal_series,
        0,
    )

    check(
        "orphan_sample_series_refs",
        orphan_sample_series == 0,
        orphan_sample_series,
        0,
    )

    check(
        "orphan_value_series_refs",
        orphan_value_series == 0,
        orphan_value_series,
        0,
    )

    check(
        "orphan_value_signal_refs",
        orphan_value_signal == 0,
        orphan_value_signal,
        0,
    )

    check(
        "orphan_value_sample_refs",
        orphan_value_sample == 0,
        orphan_value_sample,
        0,
    )

    # --------------------------------------------------------
    # "Time (...)" must never survive as a measurement signal.
    # --------------------------------------------------------

    axis_like_signal_rows = [
        row
        for row in signal_registry
        if re.fullmatch(
            r"times?\s*\([^)]*\)",
            norm(
                row.get(
                    "signal_label_raw",
                    "",
                )
            ),
            re.I,
        )
    ]

    check(
        "axis_like_signal_labels",
        len(
            axis_like_signal_rows
        )
        == 0,
        len(
            axis_like_signal_rows
        ),
        0,
    )

    # --------------------------------------------------------
    # Dense sample x signal consistency
    # --------------------------------------------------------

    signals_by_series = defaultdict(
        int
    )

    samples_by_series = defaultdict(
        int
    )

    values_by_series = defaultdict(
        int
    )

    for row in signal_registry:
        signals_by_series[
            row["series_id"]
        ] += 1

    for row in samples:
        samples_by_series[
            row["series_id"]
        ] += 1

    for row in values_long:
        values_by_series[
            row["series_id"]
        ] += 1

    count_mismatch_series = []

    for row in registry:
        series_id = row["series_id"]

        declared_samples = int(
            row["sample_count"]
        )

        declared_signals = int(
            row["signal_count"]
        )

        actual_samples = (
            samples_by_series[
                series_id
            ]
        )

        actual_signals = (
            signals_by_series[
                series_id
            ]
        )

        actual_values = (
            values_by_series[
                series_id
            ]
        )

        expected_values = (
            actual_samples
            * actual_signals
        )

        if (
            declared_samples
            != actual_samples
            or declared_signals
            != actual_signals
            or actual_values
            != expected_values
        ):
            count_mismatch_series.append(
                series_id
            )

    check(
        "series_count_consistency",
        len(
            count_mismatch_series
        )
        == 0,
        len(
            count_mismatch_series
        ),
        0,
    )

    # ========================================================
    # Summaries
    # ========================================================

    family_counts = Counter(
        row["family"]
        for row in registry
    )

    component_counts = Counter(
        row["component"]
        for row in registry
    )

    orientation_counts = Counter(
        row[
            "table_orientation"
        ]
        for row in registry
    )

    axis_type_counts = Counter(
        row["axis_type"]
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

    reports_with_series = {
        row["report_id"]
        for row in registry
    }

    continuation_series = [
        row
        for row in registry
        if norm(
            row.get(
                "continuation_candidate_key",
                "",
            )
        )
    ]

    continuation_groups = {
        row[
            "continuation_candidate_key"
        ]
        for row in continuation_series
    }

    repeated_transposed_series_count = sum(
        1
        for row in registry
        if (
            row.get(
                "transposed_block_count",
                ""
            )
            not in (
                "",
                1,
                "1",
            )
        )
    )

    values_grouped = defaultdict(
        list
    )

    for row in values_long:
        values_grouped[
            row["series_id"]
        ].append(
            row
        )

    all_unavailable_series_count = 0

    for row in registry:
        series_values = (
            values_grouped[
                row["series_id"]
            ]
        )

        if (
            series_values
            and all(
                is_missing_or_na(
                    value_row[
                        "value_raw"
                    ]
                )
                for value_row
                in series_values
            )
        ):
            all_unavailable_series_count += 1

    # ========================================================
    # Write output
    # ========================================================

    out = args.output_directory
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
            "pdf_candidate_id",
            "source_path",
            "page_number",
            "table_index_on_page",
            "source_heading_hint",
            "family",
            "component",
            "table_orientation",
            "axis_type",
            "axis_label_raw",
            "axis_unit_raw",
            "header_row_index",
            "axis_column_index",
            "sample_count",
            "signal_count",
            "transposed_block_count",
            "table_part_index",
            "table_part_total",
            "continuation_candidate_key",
            "continuation_merge_status",
            "group2_handoff_page_support",
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
            "source_row_index",
            "source_column_index",
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
            "source_page_number",
            "source_table_index_on_page",
            "source_table_row_index",
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
            "source_page_number",
            "source_table_index_on_page",
            "source_table_row_index",
            "source_table_column_index",
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
            "pdf_candidate_id",
            "source_path",
            "page_number",
            "table_index_on_page",
            "source_heading_hint",
            "audited_family",
            "audited_component",
            "source_rows_json",
            "processing_status",
            "linkage_status",
        ],
    )

    graphical_columns = (
        list(
            graphical_review[
                0
            ].keys()
        )
        if graphical_review
        else []
    )

    write_csv(
        out
        / "graphical_review_tables.csv",
        graphical_review,
        graphical_columns,
    )

    write_csv(
        out
        / "timeseries_audit.csv",
        audit_rows,
        [
            *BASE,
            "series_id",
            "pdf_candidate_id",
            "page_number",
            "table_index_on_page",
            "source_heading_hint",
            "family",
            "component",
            "table_orientation",
            "sample_count",
            "signal_count",
            "long_value_count",
            "transposed_block_count",
            "table_part_index",
            "table_part_total",
            "continuation_candidate_key",
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
            "pdf_candidate_id",
            "series_id",
            "source_heading_hint",
            "audited_orientation",
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
            row["status"]
            == "FAIL"
            and row["severity"]
            == "hard"
        )
    ]

    warning_failures = [
        row
        for row in validation
        if (
            row["status"]
            == "FAIL"
            and row["severity"]
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
            "PDF structural extraction",

        "input_accepted_tables":
            len(accepted),

        "structured_series_count":
            len(registry),

        "failed_table_count":
            len(failures),

        "reports_with_structured_timeseries":
            len(
                reports_with_series
            ),

        "signal_registry_rows":
            len(signal_registry),

        "sample_rows":
            len(samples),

        "long_value_rows":
            len(values_long),

        "companion_metadata_rows":
            len(companion_rows),

        "graphical_review_table_count":
            len(graphical_review),

        "family_counts":
            dict(family_counts),

        "component_counts":
            dict(component_counts),

        "orientation_counts":
            dict(orientation_counts),

        "axis_type_counts":
            dict(axis_type_counts),

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

        "continuation_candidate_series_count":
            len(
                continuation_series
            ),

        "continuation_candidate_group_count":
            len(
                continuation_groups
            ),

        "repeated_transposed_series_count":
            repeated_transposed_series_count,

        "transposed_block_count_distribution":
            {
                str(key):
                    value
                for key, value
                in sorted(
                    transposed_block_counts.items()
                )
            },

        "axis_like_signal_label_count":
            len(
                axis_like_signal_rows
            ),

        "all_values_unavailable_series_count":
            all_unavailable_series_count,

        "validation_checks":
            len(validation),

        "validation_failures":
            sum(
                1
                for row in validation
                if row["status"]
                == "FAIL"
            ),

        "hard_validation_failures":
            len(hard_failures),

        "warning_validation_failures":
            len(
                warning_failures
            ),

        "scope":
            (
                "Structural extraction of accepted Group 4 PDF-only "
                "time-series tables. Each physical PDF table remains "
                "independent. Repeated transposed Time/measurement "
                "blocks inside one physical PDF table are concatenated "
                "structurally into one series, preventing later Time "
                "rows from being misclassified as signals. Row-oriented "
                "tables accept both Time and Times axis headings. "
                "Multi-part continuation candidates are preserved but "
                "not merged. Raw values, labels, units, axes, missing "
                "source values, and PDF provenance are retained. No "
                "semantic normalization, unit conversion, event identity "
                "inference, continuation merging, or CSV/PDF integration "
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

    if hard_failures:
        print()
        print(
            "GROUP 4 PDF STRUCTURAL EXTRACTION "
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
        "GROUP 4 PDF STRUCTURAL EXTRACTION COMPLETE."
    )


if __name__ == "__main__":
    main()
