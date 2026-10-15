"""
Second-stage conservative structured extraction of Group 2 PDF evidence.

Revision 5
----------
This revision separates three structural modes found inside Group 2 PDF
evidence:

1. Ordinary field/value information
2. Genuine retrieval/event summary tables
3. Embedded time-series candidate blocks

Important revision:
A single PDF section may contain MULTIPLE embedded temporal tables.
This version detects multiple non-overlapping temporal blocks and
quarantines all of them for Group 4.

The purpose is extraction accuracy, not semantic classification.

Outputs
-------
pdf_fields_long.csv
pdf_table_rows.csv
pdf_unresolved_lines.csv
pdf_timeseries_candidate_rows.csv
pdf_timeseries_candidate_sections.csv
pdf_section_audit.csv
metadata.json
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

import pdfplumber


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
# General helpers
# ============================================================

def normalize_space(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )


def normalize_key(value):
    value = normalize_space(value)
    value = value.casefold()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return normalize_space(value)


def identifier(*parts):
    text = "|".join(
        str(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode()
    ).hexdigest()[:24]


def value_state(value):
    text = normalize_space(
        value
    ).casefold()

    if not text:
        return "blank"

    if text in {
        "n/a",
        "na",
        "sna",
        "not available",
        "not applicable",
        "unknown",
    }:
        return "not_available"

    return "present"


def safe_json(
    value,
    default=None,
):
    if default is None:
        default = []

    try:
        return json.loads(value)

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return default


def resolve_source_path(
    value,
    source_root: Path,
):
    raw = normalize_space(value)

    if not raw:
        return None

    path = Path(raw)

    if path.exists():
        return path

    candidate = (
        source_root
        / path
    )

    if candidate.exists():
        return candidate

    return None


# ============================================================
# Bounding boxes
# ============================================================

def parse_bbox(
    bbox_json,
    page,
):
    bbox = safe_json(
        bbox_json,
        default=[],
    )

    if (
        isinstance(bbox, list)
        and len(bbox) == 4
    ):
        try:
            x0 = float(bbox[0])
            top = float(bbox[1])
            x1 = float(bbox[2])
            bottom = float(bbox[3])

            x0 = max(
                0.0,
                x0,
            )

            top = max(
                0.0,
                top,
            )

            x1 = min(
                float(page.width),
                x1,
            )

            bottom = min(
                float(page.height),
                bottom,
            )

            if (
                x1 > x0
                and bottom > top
            ):
                return (
                    x0,
                    top,
                    x1,
                    bottom,
                )

        except (
            TypeError,
            ValueError,
        ):
            pass

    return (
        0.0,
        0.0,
        float(page.width),
        float(page.height),
    )


# ============================================================
# PDF table extraction
# ============================================================

def clean_table(table):
    cleaned = []

    for row in table or []:

        if row is None:
            continue

        values = [
            normalize_space(cell)
            for cell in row
        ]

        if any(values):
            cleaned.append(values)

    return cleaned


def table_is_useful(table):

    if len(table) < 1:
        return False

    max_columns = max(
        len(row)
        for row in table
    )

    if max_columns < 2:
        return False

    useful_rows = sum(
        1
        for row in table
        if sum(
            bool(
                normalize_space(value)
            )
            for value in row
        ) >= 2
    )

    return (
        useful_rows >= 1
    )


def extract_candidate_tables(
    cropped_page,
):
    strategies = [
        (
            "lines",
            {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
                "join_tolerance": 3,
                "intersection_tolerance": 3,
            },
        ),
        (
            "text",
            {
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "min_words_vertical": 2,
                "min_words_horizontal": 1,
                "text_x_tolerance": 2,
                "text_y_tolerance": 3,
            },
        ),
    ]

    candidates = []

    for method, settings in strategies:

        try:
            extracted = (
                cropped_page.extract_tables(
                    table_settings=settings
                )
                or []
            )

        except Exception:
            continue

        for table_index, table in enumerate(extracted):

            cleaned = clean_table(table)

            if table_is_useful(cleaned):
                candidates.append({
                    "method": method,
                    "table_index": table_index,
                    "rows": cleaned,
                })

    return candidates


def choose_best_table(candidates):

    if not candidates:
        return None

    def score(candidate):

        rows = candidate["rows"]

        multi_cell_rows = sum(
            1
            for row in rows
            if sum(
                bool(
                    normalize_space(cell)
                )
                for cell in row
            ) >= 2
        )

        populated = sum(
            sum(
                bool(
                    normalize_space(cell)
                )
                for cell in row
            )
            for row in rows
        )

        return (
            multi_cell_rows,
            populated,
            len(rows),
        )

    return max(
        candidates,
        key=score,
    )


# ============================================================
# Fragment reconstruction
# ============================================================

def join_label_fragments(parts):

    parts = [
        normalize_space(part)
        for part in parts
        if normalize_space(part)
    ]

    if not parts:
        return ""

    result = parts[0]

    for part in parts[1:]:

        if not part:
            continue

        if (
            part[0].islower()
            or result.endswith("-")
        ):
            result += part

        else:
            result += (
                " "
                + part
            )

    return normalize_space(result)


# ============================================================
# Units
# ============================================================

KNOWN_UNITS = {
    "mph",
    "km/h",
    "kmh",
    "kph",
    "rpm",
    "%",
    "percent",
    "g",
    "ms",
    "msec",
    "milliseconds",
    "s",
    "sec",
    "seconds",
    "degrees",
    "degree",
    "deg",
    "rad/s",
    "deg/s",
    "psi",
    "kpa",
    "volts",
    "volt",
    "v",
}


def looks_like_unit(value):
    return (
        normalize_space(
            value
        ).casefold()
        in KNOWN_UNITS
    )


# ============================================================
# Time-series detection
# ============================================================

TIME_HEADER_PATTERNS = [
    r"\bseconds?\s+before\b",
    r"\bseconds?\s+after\b",
    r"\btime\b",
    r"\brelative\s+time\b",
    r"\bvehicle\s+speed\b",
    r"\bengine\s+speed\b",
    r"\bengine\s+rpm\b",
    r"\bthrottle\b",
    r"\baccelerator\b",
    r"\bbrake\s+switch\b",
    r"\blongitudinal\b",
    r"\blateral\b",
    r"\bdelta[- ]?v\b",
    r"\bacceleration\b",
    r"\bangular\s+velocity\b",
    r"\broll\s+rate\b",
]


def row_text(row):
    return normalize_space(
        " ".join(
            normalize_space(cell)
            for cell in row
            if normalize_space(cell)
        )
    )


def looks_like_timeseries_header_text(text):

    text = normalize_space(
        text
    ).casefold()

    if not text:
        return False

    matches = sum(
        1
        for pattern
        in TIME_HEADER_PATTERNS
        if re.search(
            pattern,
            text,
            re.I,
        )
    )

    return (
        matches >= 2
    )


def looks_numeric_token(value):

    text = normalize_space(value)

    if not text:
        return False

    if text.casefold() in {
        "n/a",
        "na",
    }:
        return True

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def looks_like_timeseries_data_row(row):

    populated = [
        normalize_space(cell)
        for cell in row
        if normalize_space(cell)
    ]

    if len(populated) < 2:
        return False

    if not looks_numeric_token(
        populated[0]
    ):
        return False

    return any(
        normalize_space(value)
        for value in populated[1:]
    )


def find_timeseries_header_window(
    rows,
    start,
    max_header_rows=6,
    data_lookahead=10,
):
    """
    Test whether a temporal block starts at `start`.

    Returns:
        {
            "header_start": int,
            "header_end": int,
            "first_data_index": int
        }

    or None.
    """

    for header_len in range(
        1,
        max_header_rows + 1,
    ):

        header_end = (
            start
            + header_len
        )

        if header_end > len(rows):
            break

        header_rows = rows[
            start:header_end
        ]

        combined_header = (
            " ".join(
                row_text(row)
                for row in header_rows
            )
        )

        if not looks_like_timeseries_header_text(
            combined_header
        ):
            continue

        future_end = min(
            len(rows),
            header_end
            + data_lookahead,
        )

        future_rows = rows[
            header_end:future_end
        ]

        numeric_positions = [
            index
            for index, candidate
            in enumerate(future_rows)
            if looks_like_timeseries_data_row(
                candidate
            )
        ]

        if len(
            numeric_positions
        ) < 2:
            continue

        if numeric_positions[0] > 3:
            continue

        first_data_index = (
            header_end
            + numeric_positions[0]
        )

        return {
            "header_start":
                start,

            "header_end":
                header_end,

            "first_data_index":
                first_data_index,
        }

    return None


def extend_timeseries_block(
    rows,
    first_data_index,
):
    """
    Extend a detected time-series block through repeated sample rows.

    Allow occasional header/unit/continuation rows inside the table,
    but stop once the sequence clearly returns to ordinary text.

    Returns exclusive end index.
    """

    index = first_data_index

    last_data_index = (
        first_data_index - 1
    )

    nondata_run = 0
    max_nondata_run = 3

    while index < len(rows):

        row = rows[index]

        if looks_like_timeseries_data_row(
            row
        ):
            last_data_index = index
            nondata_run = 0
            index += 1
            continue

        # Empty/fragmented/unit-like rows can appear inside
        # a temporal table.
        text = row_text(row)

        if not text:
            nondata_run += 1

        else:
            # If another strong temporal header starts here,
            # stop so it can become a separate block.
            if (
                index > first_data_index
                and find_timeseries_header_window(
                    rows,
                    index,
                )
                is not None
            ):
                break

            nondata_run += 1

        if nondata_run > max_nondata_run:
            break

        index += 1

    if last_data_index < first_data_index:
        return first_data_index

    return (
        last_data_index + 1
    )


def detect_timeseries_blocks(rows):
    """
    Detect ALL non-overlapping temporal blocks in a PDF table.

    A block contains:
    - one or more temporal header rows
    - optional unit/continuation rows
    - repeated numeric-leading samples

    Returns a list of dicts:
        {
            "start": int,
            "header_end": int,
            "first_data_index": int,
            "end": int
        }

    `end` is exclusive.
    """

    blocks = []

    index = 0

    while index < len(rows):

        detected = (
            find_timeseries_header_window(
                rows,
                index,
            )
        )

        if detected is None:
            index += 1
            continue

        block_end = extend_timeseries_block(
            rows,
            detected[
                "first_data_index"
            ],
        )

        # Must contain at least two actual sample rows.
        sample_count = sum(
            1
            for row in rows[
                detected[
                    "first_data_index"
                ]:
                block_end
            ]
            if looks_like_timeseries_data_row(
                row
            )
        )

        if sample_count < 2:
            index += 1
            continue

        blocks.append({
            "start":
                detected[
                    "header_start"
                ],

            "header_end":
                detected[
                    "header_end"
                ],

            "first_data_index":
                detected[
                    "first_data_index"
                ],

            "end":
                block_end,
        })

        index = max(
            block_end,
            index + 1,
        )

    return blocks


def classify_timeseries_row(
    row,
    row_index,
    block,
):
    if (
        block["start"]
        <= row_index
        < block["first_data_index"]
    ):
        if (
            row_index
            == block["start"]
        ):
            return "header_candidate"

        return (
            "header_or_unit_continuation"
        )

    if looks_like_timeseries_data_row(
        row
    ):
        return "data_candidate"

    return (
        "header_or_unit_continuation"
    )


# ============================================================
# Field reconstruction
# ============================================================

def reconstruct_field_row(
    row,
    section_heading,
):

    populated = [
        normalize_space(cell)
        for cell in row
        if normalize_space(cell)
    ]

    if len(populated) < 2:
        return None

    entire_row = join_label_fragments(
        populated
    )

    if (
        normalize_key(
            entire_row
        )
        == normalize_key(
            section_heading
        )
    ):
        return None

    value = populated[-1]

    before_value = populated[:-1]

    unit = ""

    if (
        len(before_value) >= 2
        and looks_like_unit(
            before_value[-1]
        )
    ):
        unit = before_value[-1]
        label_parts = before_value[:-1]

    else:
        label_parts = before_value

    label = join_label_fragments(
        label_parts
    )

    if (
        not label
        or not value
    ):
        return None

    if (
        normalize_key(
            label
        )
        == normalize_key(
            section_heading
        )
    ):
        return None

    if not re.search(
        r"[A-Za-z]",
        label,
    ):
        return None

    return {
        "field_label_raw":
            label,

        "value_raw":
            value,

        "unit_raw":
            unit,

        "extraction_method":
            "table_row_reconstruction",
    }


# ============================================================
# Visual-line fallback
# ============================================================

def extract_words_from_crop(
    cropped_page,
):
    try:
        return (
            cropped_page.extract_words(
                x_tolerance=2,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=True,
            )
            or []
        )

    except Exception:
        return []


def group_words_into_lines(
    words,
    y_tolerance=3.0,
):

    if not words:
        return []

    ordered = sorted(
        words,
        key=lambda word: (
            float(
                word.get(
                    "top",
                    0,
                )
            ),
            float(
                word.get(
                    "x0",
                    0,
                )
            ),
        ),
    )

    lines = []

    for word in ordered:

        top = float(
            word.get(
                "top",
                0,
            )
        )

        best = None
        best_distance = None

        for line in lines:

            distance = abs(
                line["top"]
                - top
            )

            if (
                distance <= y_tolerance
                and (
                    best_distance is None
                    or distance
                    < best_distance
                )
            ):
                best = line
                best_distance = distance

        if best is None:

            lines.append({
                "top":
                    top,

                "words":
                    [word],
            })

        else:
            best["words"].append(word)

    for line in lines:

        line["words"].sort(
            key=lambda word:
                float(
                    word.get(
                        "x0",
                        0,
                    )
                )
        )

        line["text"] = normalize_space(
            " ".join(
                word.get(
                    "text",
                    ""
                )
                for word
                in line["words"]
            )
        )

    return sorted(
        lines,
        key=lambda line:
            line["top"],
    )


def split_colon_field(text):

    text = normalize_space(text)

    if ":" not in text:
        return None

    left, right = text.split(
        ":",
        1,
    )

    left = normalize_space(left)
    right = normalize_space(right)

    if (
        not left
        or not right
    ):
        return None

    return {
        "field_label_raw":
            left,

        "value_raw":
            right,

        "unit_raw":
            "",

        "extraction_method":
            "colon_split",
    }


def split_line_by_visual_gap(words):

    if len(words) < 2:
        return None

    ordered = sorted(
        words,
        key=lambda word:
            float(
                word.get(
                    "x0",
                    0,
                )
            ),
    )

    gaps = []

    for index in range(
        len(ordered) - 1
    ):

        left = ordered[index]

        right = ordered[
            index + 1
        ]

        gap = (
            float(
                right.get(
                    "x0",
                    0,
                )
            )
            - float(
                left.get(
                    "x1",
                    0,
                )
            )
        )

        gaps.append(
            (
                gap,
                index,
            )
        )

    if not gaps:
        return None

    largest_gap, split_index = max(
        gaps,
        key=lambda item:
            item[0],
    )

    positive_gaps = sorted(
        gap
        for gap, _
        in gaps
        if gap > 0
    )

    if positive_gaps:

        typical_gap = (
            positive_gaps[
                len(
                    positive_gaps
                )
                // 2
            ]
        )

    else:
        typical_gap = 0

    threshold = max(
        24.0,
        typical_gap * 3.0,
    )

    if largest_gap < threshold:
        return None

    left_words = ordered[
        :split_index + 1
    ]

    right_words = ordered[
        split_index + 1:
    ]

    label = normalize_space(
        " ".join(
            word.get(
                "text",
                ""
            )
            for word
            in left_words
        )
    )

    value = normalize_space(
        " ".join(
            word.get(
                "text",
                ""
            )
            for word
            in right_words
        )
    )

    if (
        not label
        or not value
    ):
        return None

    return {
        "field_label_raw":
            label,

        "value_raw":
            value,

        "unit_raw":
            "",

        "extraction_method":
            "visual_gap_split",
    }


def parse_visual_line(line):

    text = normalize_space(
        line.get(
            "text",
            ""
        )
    )

    colon = split_colon_field(text)

    if colon:
        return colon

    return split_line_by_visual_gap(
        line.get(
            "words",
            [],
        )
    )


# ============================================================
# Summary sections
# ============================================================

def is_true_table_section(heading):

    return (
        "summary"
        in normalize_space(
            heading
        ).casefold()
    )


# ============================================================
# Row masks
# ============================================================

def build_timeseries_row_map(
    rows,
    blocks,
):
    """
    Map each row index to its temporal block index.
    """

    row_to_block = {}

    for block_index, block in enumerate(
        blocks
    ):

        for row_index in range(
            block["start"],
            block["end"],
        ):
            row_to_block[
                row_index
            ] = block_index

    return row_to_block


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--section-evidence",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_extract_v2/"
            "section_evidence.csv"
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
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_pdf_structured_v2"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
    )

    args = parser.parse_args()

    if (
        args.limit is not None
        and args.limit < 1
    ):
        parser.error(
            "--limit must be positive"
        )

    sections = read_csv(
        args.section_evidence
    )

    pdf_sections = [
        row
        for row in sections
        if (
            row.get(
                "source_format",
                ""
            ).casefold()
            == "pdf"

            and row.get(
                "availability",
                ""
            )
            == "content_present"
        )
    ]

    if args.limit:
        pdf_sections = (
            pdf_sections[
                :args.limit
            ]
        )

    fields = []
    table_rows = []
    unresolved = []

    timeseries_rows = []
    timeseries_sections = []

    audit = []

    sections_by_pdf = defaultdict(
        list
    )

    for section in pdf_sections:

        source_path = resolve_source_path(
            section.get(
                "source_path",
                ""
            ),
            args.source_root,
        )

        if source_path is None:

            audit.append({
                **{
                    key:
                        section.get(
                            key,
                            ""
                        )
                    for key
                    in BASE
                },

                "section_id":
                    section.get(
                        "section_id",
                        ""
                    ),

                "source_page":
                    section.get(
                        "source_page",
                        ""
                    ),

                "source_heading":
                    section.get(
                        "source_heading",
                        ""
                    ),

                "section_mode":
                    "",

                "status":
                    "source_path_unresolved",

                "field_count":
                    0,

                "table_row_count":
                    0,

                "timeseries_block_count":
                    0,

                "timeseries_row_count":
                    0,

                "unresolved_count":
                    0,

                "issue":
                    section.get(
                        "source_path",
                        ""
                    ),
            })

            continue

        sections_by_pdf[
            source_path
        ].append(section)

    processed = 0

    # ========================================================
    # Process each PDF
    # ========================================================

    for pdf_path, pdf_group in (
        sections_by_pdf.items()
    ):

        try:
            pdf = pdfplumber.open(
                pdf_path
            )

        except Exception as exc:

            for section in pdf_group:

                audit.append({
                    **{
                        key:
                            section.get(
                                key,
                                ""
                            )
                        for key
                        in BASE
                    },

                    "section_id":
                        section.get(
                            "section_id",
                            ""
                        ),

                    "source_page":
                        section.get(
                            "source_page",
                            ""
                        ),

                    "source_heading":
                        section.get(
                            "source_heading",
                            ""
                        ),

                    "section_mode":
                        "",

                    "status":
                        "pdf_open_failed",

                    "field_count":
                        0,

                    "table_row_count":
                        0,

                    "timeseries_block_count":
                        0,

                    "timeseries_row_count":
                        0,

                    "unresolved_count":
                        0,

                    "issue":
                        (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                })

            continue

        try:

            for section in pdf_group:

                processed += 1

                try:
                    page_number = int(
                        section.get(
                            "source_page",
                            ""
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    page_number = 0

                if (
                    page_number < 1
                    or page_number
                    > len(pdf.pages)
                ):

                    audit.append({
                        **{
                            key:
                                section.get(
                                    key,
                                    ""
                                )
                            for key
                            in BASE
                        },

                        "section_id":
                            section[
                                "section_id"
                            ],

                        "source_page":
                            section.get(
                                "source_page",
                                ""
                            ),

                        "source_heading":
                            section.get(
                                "source_heading",
                                ""
                            ),

                        "section_mode":
                            "",

                        "status":
                            "invalid_page_number",

                        "field_count":
                            0,

                        "table_row_count":
                            0,

                        "timeseries_block_count":
                            0,

                        "timeseries_row_count":
                            0,

                        "unresolved_count":
                            0,

                        "issue":
                            "",
                    })

                    continue

                page = pdf.pages[
                    page_number - 1
                ]

                bbox = parse_bbox(
                    section.get(
                        "source_bbox_json",
                        ""
                    ),
                    page,
                )

                try:
                    crop = page.crop(
                        bbox
                    )

                except Exception:
                    crop = page

                heading = section.get(
                    "source_heading",
                    ""
                )

                section_id = (
                    section[
                        "section_id"
                    ]
                )

                candidates = (
                    extract_candidate_tables(
                        crop
                    )
                )

                best_table = (
                    choose_best_table(
                        candidates
                    )
                )

                true_summary = (
                    is_true_table_section(
                        heading
                    )
                )

                section_field_count = 0
                section_table_count = 0
                section_timeseries_block_count = 0
                section_timeseries_count = 0
                section_unresolved_count = 0

                # ============================================
                # MODE 1: Summary
                # ============================================

                if true_summary:

                    section_mode = (
                        "summary_table"
                    )

                    if best_table is None:

                        section_status = (
                            "summary_requires_review"
                        )

                    else:

                        rows = (
                            best_table[
                                "rows"
                            ]
                        )

                        candidate_header = (
                            rows[0]
                            if rows
                            else []
                        )

                        data_row_count = 0

                        for row_index, values in enumerate(
                            rows
                        ):

                            role = (
                                "header_candidate"
                                if row_index == 0
                                else "data_candidate"
                            )

                            if (
                                role
                                == "data_candidate"
                            ):
                                data_row_count += 1

                            table_rows.append({
                                **{
                                    key:
                                        section.get(
                                            key,
                                            ""
                                        )
                                    for key
                                    in BASE
                                },

                                "section_id":
                                    section_id,

                                "record_candidate_id":
                                    section.get(
                                        "record_candidate_id",
                                        ""
                                    ),

                                "scope_candidate":
                                    section.get(
                                        "scope_candidate",
                                        ""
                                    ),

                                "source_page":
                                    page_number,

                                "source_heading":
                                    heading,

                                "pdf_row_index":
                                    row_index,

                                "row_role":
                                    role,

                                "source_header_json":
                                    json.dumps(
                                        candidate_header,
                                        ensure_ascii=False,
                                    ),

                                "source_row_json":
                                    json.dumps(
                                        values,
                                        ensure_ascii=False,
                                    ),

                                "extraction_method":
                                    (
                                        "pdf_table_"
                                        + best_table[
                                            "method"
                                        ]
                                    ),

                                "requires_review":
                                    True,
                            })

                            section_table_count += 1

                        if data_row_count:

                            section_status = (
                                "summary_table_candidate_extracted"
                            )

                        else:

                            section_status = (
                                "summary_header_only_requires_review"
                            )

                # ============================================
                # MODE 2:
                # scalar fields + zero/multiple TS blocks
                # ============================================

                else:

                    section_mode = (
                        "field_value"
                    )

                    rows = (
                        best_table[
                            "rows"
                        ]
                        if best_table
                        else []
                    )

                    blocks = (
                        detect_timeseries_blocks(
                            rows
                        )
                        if rows
                        else []
                    )

                    row_to_block = (
                        build_timeseries_row_map(
                            rows,
                            blocks,
                        )
                    )

                    # ----------------------------------------
                    # Emit every detected TS block
                    # ----------------------------------------

                    for block_index, block in enumerate(
                        blocks
                    ):

                        ts_id = (
                            "g4pdf_ts_"
                            + identifier(
                                section_id,
                                page_number,
                                block_index,
                                block["start"],
                                block["end"],
                            )
                        )

                        block_rows = rows[
                            block["start"]:
                            block["end"]
                        ]

                        sample_count = sum(
                            1
                            for row
                            in block_rows
                            if looks_like_timeseries_data_row(
                                row
                            )
                        )

                        timeseries_sections.append({
                            **{
                                key:
                                    section.get(
                                        key,
                                        ""
                                    )
                                for key
                                in BASE
                            },

                            "timeseries_candidate_id":
                                ts_id,

                            "section_id":
                                section_id,

                            "record_candidate_id":
                                section.get(
                                    "record_candidate_id",
                                    ""
                                ),

                            "scope_candidate":
                                section.get(
                                    "scope_candidate",
                                    ""
                                ),

                            "source_page":
                                page_number,

                            "source_heading":
                                heading,

                            "block_index":
                                block_index,

                            "start_pdf_row_index":
                                block["start"],

                            "first_data_pdf_row_index":
                                block["first_data_index"],

                            "end_pdf_row_index_exclusive":
                                block["end"],

                            "row_count":
                                len(block_rows),

                            "data_candidate_count":
                                sample_count,

                            "extraction_method":
                                "embedded_pdf_table_sequence",

                            "target_extraction_group":
                                "group4_timeseries",

                            "requires_review":
                                True,
                        })

                        section_timeseries_block_count += 1

                        for row_index in range(
                            block["start"],
                            block["end"],
                        ):

                            row = rows[
                                row_index
                            ]

                            role = (
                                classify_timeseries_row(
                                    row,
                                    row_index,
                                    block,
                                )
                            )

                            timeseries_rows.append({
                                **{
                                    key:
                                        section.get(
                                            key,
                                            ""
                                        )
                                    for key
                                    in BASE
                                },

                                "timeseries_candidate_id":
                                    ts_id,

                                "section_id":
                                    section_id,

                                "record_candidate_id":
                                    section.get(
                                        "record_candidate_id",
                                        ""
                                    ),

                                "scope_candidate":
                                    section.get(
                                        "scope_candidate",
                                        ""
                                    ),

                                "source_page":
                                    page_number,

                                "source_heading":
                                    heading,

                                "block_index":
                                    block_index,

                                "pdf_row_index":
                                    row_index,

                                "row_role":
                                    role,

                                "source_row_json":
                                    json.dumps(
                                        row,
                                        ensure_ascii=False,
                                    ),

                                "target_extraction_group":
                                    "group4_timeseries",

                                "requires_review":
                                    True,
                            })

                            section_timeseries_count += 1

                    # ----------------------------------------
                    # Process only NON-time-series table rows
                    # as scalar Group 2 evidence.
                    # ----------------------------------------

                    if rows:

                        for row_index, row in enumerate(
                            rows
                        ):

                            if row_index in row_to_block:
                                continue

                            reconstructed = (
                                reconstruct_field_row(
                                    row,
                                    heading,
                                )
                            )

                            if reconstructed is None:

                                populated = [
                                    normalize_space(
                                        cell
                                    )
                                    for cell
                                    in row
                                    if normalize_space(
                                        cell
                                    )
                                ]

                                if populated:

                                    text = (
                                        " | ".join(
                                            populated
                                        )
                                    )

                                    unresolved.append({
                                        **{
                                            key:
                                                section.get(
                                                    key,
                                                    ""
                                                )
                                            for key
                                            in BASE
                                        },

                                        "pdf_unresolved_id":
                                            (
                                                "g2pdf_unresolved_"
                                                + identifier(
                                                    section_id,
                                                    page_number,
                                                    row_index,
                                                    text,
                                                )
                                            ),

                                        "section_id":
                                            section_id,

                                        "record_candidate_id":
                                            section.get(
                                                "record_candidate_id",
                                                ""
                                            ),

                                        "scope_candidate":
                                            section.get(
                                                "scope_candidate",
                                                ""
                                            ),

                                        "source_page":
                                            page_number,

                                        "source_heading":
                                            heading,

                                        "source_index":
                                            row_index,

                                        "text_raw":
                                            text,

                                        "reason":
                                            "field_row_not_conservatively_reconstructed",

                                        "requires_review":
                                            True,
                                    })

                                    section_unresolved_count += 1

                                continue

                            fields.append({
                                **{
                                    key:
                                        section.get(
                                            key,
                                            ""
                                        )
                                    for key
                                    in BASE
                                },

                                "pdf_field_id":
                                    (
                                        "g2pdf_field_"
                                        + identifier(
                                            section_id,
                                            page_number,
                                            row_index,
                                            reconstructed[
                                                "field_label_raw"
                                            ],
                                            reconstructed[
                                                "value_raw"
                                            ],
                                        )
                                    ),

                                "section_id":
                                    section_id,

                                "record_candidate_id":
                                    section.get(
                                        "record_candidate_id",
                                        ""
                                    ),

                                "scope_candidate":
                                    section.get(
                                        "scope_candidate",
                                        ""
                                    ),

                                "source_page":
                                    page_number,

                                "source_heading":
                                    heading,

                                "source_index":
                                    row_index,

                                "field_label_raw":
                                    reconstructed[
                                        "field_label_raw"
                                    ],

                                "value_raw":
                                    reconstructed[
                                        "value_raw"
                                    ],

                                "value_status":
                                    value_state(
                                        reconstructed[
                                            "value_raw"
                                        ]
                                    ),

                                "unit_raw":
                                    reconstructed[
                                        "unit_raw"
                                    ],

                                "extraction_method":
                                    reconstructed[
                                        "extraction_method"
                                    ],

                                "semantic_status":
                                    "unmapped_source_field",

                                "requires_review":
                                    True,
                            })

                            section_field_count += 1

                    # ----------------------------------------
                    # No table geometry fallback
                    # ----------------------------------------

                    if best_table is None:

                        words = (
                            extract_words_from_crop(
                                crop
                            )
                        )

                        visual_lines = (
                            group_words_into_lines(
                                words
                            )
                        )

                        for line_index, line in enumerate(
                            visual_lines
                        ):

                            text = normalize_space(
                                line.get(
                                    "text",
                                    ""
                                )
                            )

                            if not text:
                                continue

                            if (
                                normalize_key(
                                    text
                                )
                                == normalize_key(
                                    heading
                                )
                            ):
                                continue

                            reconstructed = (
                                parse_visual_line(
                                    line
                                )
                            )

                            if reconstructed is None:

                                unresolved.append({
                                    **{
                                        key:
                                            section.get(
                                                key,
                                                ""
                                            )
                                        for key
                                        in BASE
                                    },

                                    "pdf_unresolved_id":
                                        (
                                            "g2pdf_unresolved_"
                                            + identifier(
                                                section_id,
                                                page_number,
                                                line_index,
                                                text,
                                            )
                                        ),

                                    "section_id":
                                        section_id,

                                    "record_candidate_id":
                                        section.get(
                                            "record_candidate_id",
                                            ""
                                        ),

                                    "scope_candidate":
                                        section.get(
                                            "scope_candidate",
                                            ""
                                        ),

                                    "source_page":
                                        page_number,

                                    "source_heading":
                                        heading,

                                    "source_index":
                                        line_index,

                                    "text_raw":
                                        text,

                                    "reason":
                                        "no_conservative_field_value_split",

                                    "requires_review":
                                        True,
                                })

                                section_unresolved_count += 1

                                continue

                            fields.append({
                                **{
                                    key:
                                        section.get(
                                            key,
                                            ""
                                        )
                                    for key
                                    in BASE
                                },

                                "pdf_field_id":
                                    (
                                        "g2pdf_field_"
                                        + identifier(
                                            section_id,
                                            page_number,
                                            line_index,
                                            reconstructed[
                                                "field_label_raw"
                                            ],
                                            reconstructed[
                                                "value_raw"
                                            ],
                                        )
                                    ),

                                "section_id":
                                    section_id,

                                "record_candidate_id":
                                    section.get(
                                        "record_candidate_id",
                                        ""
                                    ),

                                "scope_candidate":
                                    section.get(
                                        "scope_candidate",
                                        ""
                                    ),

                                "source_page":
                                    page_number,

                                "source_heading":
                                    heading,

                                "source_index":
                                    line_index,

                                "field_label_raw":
                                    reconstructed[
                                        "field_label_raw"
                                    ],

                                "value_raw":
                                    reconstructed[
                                        "value_raw"
                                    ],

                                "value_status":
                                    value_state(
                                        reconstructed[
                                            "value_raw"
                                        ]
                                    ),

                                "unit_raw":
                                    reconstructed[
                                        "unit_raw"
                                    ],

                                "extraction_method":
                                    reconstructed[
                                        "extraction_method"
                                    ],

                                "semantic_status":
                                    "unmapped_source_field",

                                "requires_review":
                                    True,
                            })

                            section_field_count += 1

                    # ----------------------------------------
                    # Section status
                    # ----------------------------------------

                    if section_timeseries_block_count:

                        if section_field_count:

                            section_status = (
                                "fields_and_timeseries_candidates_extracted"
                            )

                        else:

                            section_status = (
                                "timeseries_candidate_only"
                            )

                    elif section_field_count:

                        if section_unresolved_count:

                            section_status = (
                                "fields_extracted_with_unresolved_rows"
                            )

                        else:

                            section_status = (
                                "fields_extracted"
                            )

                    elif section_unresolved_count:

                        section_status = (
                            "unresolved_text_only"
                        )

                    else:

                        section_status = (
                            "no_structured_content_extracted"
                        )

                # ============================================
                # Audit
                # ============================================

                audit.append({
                    **{
                        key:
                            section.get(
                                key,
                                ""
                            )
                        for key
                        in BASE
                    },

                    "section_id":
                        section_id,

                    "source_page":
                        page_number,

                    "source_heading":
                        heading,

                    "section_mode":
                        section_mode,

                    "status":
                        section_status,

                    "field_count":
                        section_field_count,

                    "table_row_count":
                        section_table_count,

                    "timeseries_block_count":
                        section_timeseries_block_count,

                    "timeseries_row_count":
                        section_timeseries_count,

                    "unresolved_count":
                        section_unresolved_count,

                    "issue":
                        "",
                })

                if (
                    processed % 25 == 0
                    or processed
                    == len(pdf_sections)
                ):
                    print(
                        "Structured PDF sections: "
                        f"{processed}/"
                        f"{len(pdf_sections)}",
                        flush=True,
                    )

        finally:
            pdf.close()

    # ========================================================
    # Output directory
    # ========================================================

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Write CSVs
    # ========================================================

    write_csv(
        out / "pdf_fields_long.csv",
        fields,
        (
            list(fields[0])
            if fields
            else BASE
            + [
                "pdf_field_id",
                "section_id",
                "record_candidate_id",
                "scope_candidate",
                "source_page",
                "source_heading",
                "source_index",
                "field_label_raw",
                "value_raw",
                "value_status",
                "unit_raw",
                "extraction_method",
                "semantic_status",
                "requires_review",
            ]
        ),
    )

    write_csv(
        out / "pdf_table_rows.csv",
        table_rows,
        (
            list(table_rows[0])
            if table_rows
            else BASE
            + [
                "section_id",
                "record_candidate_id",
                "scope_candidate",
                "source_page",
                "source_heading",
                "pdf_row_index",
                "row_role",
                "source_header_json",
                "source_row_json",
                "extraction_method",
                "requires_review",
            ]
        ),
    )

    write_csv(
        out / "pdf_unresolved_lines.csv",
        unresolved,
        (
            list(unresolved[0])
            if unresolved
            else BASE
            + [
                "pdf_unresolved_id",
                "section_id",
                "record_candidate_id",
                "scope_candidate",
                "source_page",
                "source_heading",
                "source_index",
                "text_raw",
                "reason",
                "requires_review",
            ]
        ),
    )

    write_csv(
        out / "pdf_timeseries_candidate_rows.csv",
        timeseries_rows,
        (
            list(timeseries_rows[0])
            if timeseries_rows
            else BASE
            + [
                "timeseries_candidate_id",
                "section_id",
                "record_candidate_id",
                "scope_candidate",
                "source_page",
                "source_heading",
                "block_index",
                "pdf_row_index",
                "row_role",
                "source_row_json",
                "target_extraction_group",
                "requires_review",
            ]
        ),
    )

    write_csv(
        out / "pdf_timeseries_candidate_sections.csv",
        timeseries_sections,
        (
            list(timeseries_sections[0])
            if timeseries_sections
            else BASE
            + [
                "timeseries_candidate_id",
                "section_id",
                "record_candidate_id",
                "scope_candidate",
                "source_page",
                "source_heading",
                "block_index",
                "start_pdf_row_index",
                "first_data_pdf_row_index",
                "end_pdf_row_index_exclusive",
                "row_count",
                "data_candidate_count",
                "extraction_method",
                "target_extraction_group",
                "requires_review",
            ]
        ),
    )

    write_csv(
        out / "pdf_section_audit.csv",
        audit,
        (
            list(audit[0])
            if audit
            else BASE
            + [
                "section_id",
                "source_page",
                "source_heading",
                "section_mode",
                "status",
                "field_count",
                "table_row_count",
                "timeseries_block_count",
                "timeseries_row_count",
                "unresolved_count",
                "issue",
            ]
        ),
    )

    # ========================================================
    # Metadata
    # ========================================================

    status_counts = Counter(
        row["status"]
        for row in audit
    )

    mode_counts = Counter(
        row["section_mode"]
        for row in audit
        if row["section_mode"]
    )

    field_method_counts = Counter(
        row["extraction_method"]
        for row in fields
    )

    ts_role_counts = Counter(
        row["row_role"]
        for row in timeseries_rows
    )

    scope_counts = Counter(
        section.get(
            "scope_candidate",
            ""
        )
        for section in pdf_sections
    )

    summary_header_only_count = sum(
        1
        for row in audit
        if row["status"]
        == "summary_header_only_requires_review"
    )

    sections_with_multiple_ts_blocks = sum(
        1
        for row in audit
        if row["timeseries_block_count"] > 1
    )

    ts_blocks_per_section_counts = Counter(
        row["timeseries_block_count"]
        for row in audit
        if row["timeseries_block_count"] > 0
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "input_section_evidence":
            str(
                args.section_evidence
            ),

        "pdf_content_sections":
            len(pdf_sections),

        "pdf_scope_candidate_counts":
            dict(scope_counts),

        "section_mode_counts":
            dict(mode_counts),

        "structured_field_observations":
            len(fields),

        "structured_summary_table_rows":
            len(table_rows),

        "summary_header_only_sections":
            summary_header_only_count,

        "timeseries_candidate_sections":
            len(timeseries_sections),

        "timeseries_candidate_rows":
            len(timeseries_rows),

        "timeseries_candidate_role_counts":
            dict(ts_role_counts),

        "sections_with_multiple_timeseries_blocks":
            sections_with_multiple_ts_blocks,

        "timeseries_blocks_per_section_counts":
            {
                str(key): value
                for key, value
                in sorted(
                    ts_blocks_per_section_counts.items()
                )
            },

        "unresolved_pdf_rows":
            len(unresolved),

        "section_audit_status_counts":
            dict(status_counts),

        "field_extraction_method_counts":
            dict(
                field_method_counts
            ),

        "source_errors":
            sum(
                1
                for row in audit
                if row["status"]
                in {
                    "source_path_unresolved",
                    "pdf_open_failed",
                    "invalid_page_number",
                }
            ),

        "scope":
            (
                "Revised Group 2 PDF structural extraction. "
                "Ordinary scalar/status field-value evidence is "
                "retained in pdf_fields_long.csv. Multiple embedded "
                "repeated temporal structures may be detected within "
                "a single PDF section and are quarantined as separate "
                "Group 4 time-series candidates. Summary sections "
                "remain separate and header-only summary extraction "
                "is explicitly marked for review. Original PDF "
                "evidence remains unchanged. No event identity, "
                "CSV-PDF equivalence, semantic normalization, "
                "cross-label merging, or hex decoding is inferred."
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