"""
Group 4 CSV discovery: Time-series measurements.

Purpose
-------
Discover all time-series-like structures directly from the original
CISS/CDR CSV exports.

This is a discovery pass only.

It does NOT:
- normalize signal semantics,
- convert units,
- infer missing time values,
- merge different table families,
- assign crash-event identities,
- use PDF content,
- replace source labels,
- or build the final Group 4 dataset.

The objective is to identify all repeated/ordered measurement tables
present in CSV reports so that Group 4 extraction can later be built
from the original CSV sources.

Outputs
-------
timeseries_candidate_sections.csv
timeseries_candidate_rows.csv
timeseries_family_summary.csv
report_coverage.csv
review_sections.csv
errors.csv
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

from build_edr_collection_discovery import load_rows


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

def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )


def norm_key(value):
    value = norm(value).casefold()

    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            value,
        )
    )


def identifier(*parts):
    text = "|".join(
        str(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode()
    ).hexdigest()[:24]


def resolve_path(
    value,
    source_root: Path,
):
    raw = norm(value)

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


def is_number(value):
    text = norm(value)

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


def is_na(value):
    return (
        norm(value).casefold()
        in {
            "n/a",
            "na",
            "not available",
            "not applicable",
            "sna",
        }
    )


def populated_cells(row):
    return [
        norm(cell)
        for cell in row
        if norm(cell)
    ]


# ============================================================
# Section heading detection
# ============================================================

NON_SECTION_TEXT = {
    "DATA LIMITATIONS",
    "DISCLAIMER",
    "COMMENTS",
    "NOTES",
}


def looks_like_heading(row):
    """
    Detect likely CSV section headings.

    CDR exports commonly use rows containing one populated
    all-uppercase cell as section boundaries.
    """

    filled = populated_cells(row)

    if len(filled) != 1:
        return False

    text = filled[0]

    if not text:
        return False

    if text.upper() in NON_SECTION_TEXT:
        return True

    if len(text) < 4:
        return False

    # Strong uppercase section pattern.
    letters = [
        char
        for char in text
        if char.isalpha()
    ]

    if letters and all(
        char.isupper()
        for char in letters
    ):
        return True

    # Known structural section wording can sometimes
    # contain mixed case.
    if re.search(
        r"\b(?:"
        r"pre[- ]?crash|"
        r"crash pulse|"
        r"event data|"
        r"system status|"
        r"pcm|"
        r"rollover|"
        r"deployment|"
        r"longitudinal|"
        r"lateral|"
        r"acceleration|"
        r"velocity change"
        r")\b",
        text,
        re.I,
    ):
        return True

    return False


def segment_sections(rows):
    """
    Return:
        [
            {
                heading,
                start,
                end,
                rows
            }
        ]

    start/end are zero-based source-row indexes.
    """

    headings = []

    for index, row in enumerate(rows):

        if looks_like_heading(row):
            headings.append(
                (
                    index,
                    populated_cells(row)[0],
                )
            )

    sections = []

    for pos, (
        start,
        heading,
    ) in enumerate(headings):

        end = (
            headings[pos + 1][0]
            if pos + 1 < len(headings)
            else len(rows)
        )

        content = rows[
            start + 1:end
        ]

        sections.append({
            "heading":
                heading,

            "start":
                start,

            "end":
                end,

            "rows":
                content,
        })

    return sections


# ============================================================
# Time-series evidence
# ============================================================

TIME_AXIS_PATTERNS = [
    r"\bseconds?\s+before\b",
    r"\bseconds?\s+after\b",
    r"\btime\b",
    r"\brelative\s+time\b",
    r"\btime\s*\(s\)",
    r"\btime\s*\(ms\)",
    r"\bbuffer\s+address\b",
    r"\bsample\s+number\b",
    r"\bsample\s+index\b",
]


SIGNAL_PATTERNS = [
    r"\bvehicle\s+speed\b",
    r"\bengine\s+speed\b",
    r"\brpm\b",
    r"\bthrottle\b",
    r"\baccelerator\b",
    r"\bbrake\b",
    r"\bacceleration\b",
    r"\bdelta[- ]?v\b",
    r"\bvelocity\s+change\b",
    r"\blongitudinal\b",
    r"\blateral\b",
    r"\broll(?:over)?\b",
    r"\byaw\b",
    r"\bangular\b",
    r"\bcrash\s+pulse\b",
]


HEADING_FAMILY_PATTERNS = [
    (
        "pcm_edr",
        r"\bPCM\s+EDR\s+DATA\b",
    ),

    (
        "pre_crash",
        r"\bPRE[- ]?CRASH\b",
    ),

    (
        "crash_pulse",
        r"\bCRASH\s+PULSE\b",
    ),

    (
        "longitudinal",
        r"\bLONGITUDINAL\b",
    ),

    (
        "lateral",
        r"\bLATERAL\b",
    ),

    (
        "rollover",
        r"\bROLLOVER\b",
    ),

    (
        "velocity_change",
        r"\b(?:DELTA[- ]?V|VELOCITY\s+CHANGE)\b",
    ),

    (
        "deployment_temporal",
        r"\bDEPLOYMENT\b",
    ),
]


def detect_heading_family(heading):
    for family, pattern in HEADING_FAMILY_PATTERNS:

        if re.search(
            pattern,
            heading,
            re.I,
        ):
            return family

    return "generic_timeseries"


def row_text(row):
    return norm(
        " ".join(
            norm(cell)
            for cell in row
            if norm(cell)
        )
    )


def header_time_axis_score(rows):
    """
    Search the first few meaningful rows for time/index
    header evidence.
    """

    useful = [
        row
        for row in rows
        if populated_cells(row)
    ]

    header_rows = useful[:6]

    combined = " ".join(
        row_text(row)
        for row in header_rows
    )

    matches = [
        pattern
        for pattern
        in TIME_AXIS_PATTERNS
        if re.search(
            pattern,
            combined,
            re.I,
        )
    ]

    return (
        len(matches),
        matches,
        combined,
    )


def signal_header_score(rows):
    useful = [
        row
        for row in rows
        if populated_cells(row)
    ]

    combined = " ".join(
        row_text(row)
        for row in useful[:6]
    )

    matches = [
        pattern
        for pattern
        in SIGNAL_PATTERNS
        if re.search(
            pattern,
            combined,
            re.I,
        )
    ]

    return (
        len(matches),
        matches,
    )


def numeric_leading_rows(rows):
    """
    Count rows where the first populated cell is numeric/N/A
    and there is at least one additional populated cell.
    """

    result = []

    for index, row in enumerate(rows):

        filled = populated_cells(row)

        if len(filled) < 2:
            continue

        if (
            is_number(
                filled[0]
            )
            or is_na(
                filled[0]
            )
        ):
            result.append(index)

    return result


def repeated_width_evidence(rows):
    """
    Return evidence that multiple data rows share a repeated
    populated-column count.
    """

    widths = []

    for row in rows:
        count = len(
            populated_cells(row)
        )

        if count >= 2:
            widths.append(count)

    if not widths:
        return (
            0,
            0,
        )

    counts = Counter(widths)

    width, count = counts.most_common(1)[0]

    return (
        width,
        count,
    )


def detect_explicit_relative_time(rows):
    """
    Look for a likely relative-time column with actual numeric
    values.

    This is discovery only and does not identify final column
    position.
    """

    useful = [
        row
        for row in rows
        if populated_cells(row)
    ]

    for header_index, row in enumerate(
        useful[:6]
    ):

        for cell_index, cell in enumerate(row):

            text = norm(cell)

            if not re.search(
                r"\b(?:relative\s+time|seconds?\s+(?:before|after)|time)\b",
                text,
                re.I,
            ):
                continue

            numeric_count = 0

            for candidate in useful[
                header_index + 1:
                header_index + 12
            ]:

                if cell_index >= len(candidate):
                    continue

                value = norm(
                    candidate[
                        cell_index
                    ]
                )

                if is_number(value):
                    numeric_count += 1

            if numeric_count >= 2:
                return True

    return False


def detect_buffer_axis(rows):

    combined = " ".join(
        row_text(row)
        for row in rows[:6]
    )

    return bool(
        re.search(
            r"\bbuffer\s+address\b",
            combined,
            re.I,
        )
    )


# ============================================================
# Candidate scoring
# ============================================================

def analyze_section(
    heading,
    rows,
):
    """
    Conservative candidate scoring.

    A section is considered a time-series candidate when
    multiple independent pieces of evidence support repeated
    ordered measurements.
    """

    time_score, time_patterns, header_text = (
        header_time_axis_score(
            rows
        )
    )

    signal_score, signal_patterns = (
        signal_header_score(
            rows
        )
    )

    numeric_rows = numeric_leading_rows(
        rows
    )

    modal_width, modal_width_count = (
        repeated_width_evidence(
            rows
        )
    )

    explicit_time = (
        detect_explicit_relative_time(
            rows
        )
    )

    buffer_axis = (
        detect_buffer_axis(
            rows
        )
    )

    family = detect_heading_family(
        heading
    )

    heading_temporal = (
        family
        != "generic_timeseries"
    )

    score = 0
    reasons = []

    if time_score:
        score += 3
        reasons.append(
            "time_or_index_header"
        )

    if explicit_time:
        score += 3
        reasons.append(
            "numeric_time_axis"
        )

    if buffer_axis:
        score += 3
        reasons.append(
            "buffer_axis"
        )

    if len(numeric_rows) >= 2:
        score += 2
        reasons.append(
            "repeated_numeric_leading_rows"
        )

    if modal_width_count >= 3:
        score += 1
        reasons.append(
            "repeated_row_width"
        )

    if signal_score:
        score += 1
        reasons.append(
            "measurement_signal_headers"
        )

    if heading_temporal:
        score += 2
        reasons.append(
            "temporal_section_heading"
        )

    # Strong structural candidate.
    candidate = (
        score >= 5
        and (
            len(numeric_rows) >= 2
            or buffer_axis
        )
    )

    # Very strong explicit time axis should qualify even if
    # numeric-leading rows are not in the first column.
    if (
        explicit_time
        and modal_width_count >= 2
    ):
        candidate = True

    # PCM buffer tables qualify structurally.
    if (
        family == "pcm_edr"
        and buffer_axis
    ):
        candidate = True

    # Sections close to threshold are retained for review.
    review = (
        not candidate
        and score >= 3
    )

    if explicit_time:
        time_axis_type = (
            "relative_or_explicit_time"
        )

    elif buffer_axis:
        time_axis_type = (
            "buffer_order_or_relative_time"
        )

    elif len(numeric_rows) >= 2:
        time_axis_type = (
            "ordered_numeric_axis_candidate"
        )

    else:
        time_axis_type = (
            "unknown"
        )

    return {
        "candidate":
            candidate,

        "review":
            review,

        "score":
            score,

        "family":
            family,

        "time_axis_type":
            time_axis_type,

        "explicit_time":
            explicit_time,

        "buffer_axis":
            buffer_axis,

        "time_header_match_count":
            time_score,

        "signal_header_match_count":
            signal_score,

        "numeric_leading_row_count":
            len(
                numeric_rows
            ),

        "numeric_leading_indexes":
            numeric_rows,

        "modal_populated_width":
            modal_width,

        "modal_width_row_count":
            modal_width_count,

        "reasons":
            reasons,

        "header_text":
            header_text,
    }


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--index",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group1_v4/"
            "report_index.csv"
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
            "group4_csv_discovery_v1"
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

    index = read_csv(
        args.index
    )

    selected = (
        index[
            :args.limit
        ]
        if args.limit
        else index
    )

    # ========================================================
    # Outputs
    # ========================================================

    candidate_sections = []
    candidate_rows = []
    review_sections = []
    coverage = []
    errors = []

    # ========================================================
    # Scan reports
    # ========================================================

    for number, report in enumerate(
        selected,
        1,
    ):

        base = {
            key:
                report.get(
                    key,
                    ""
                )
            for key in BASE
        }

        csv_path = resolve_path(
            report.get(
                "csv_path",
                ""
            ),
            args.source_root,
        )

        if csv_path is None:

            coverage.append({
                **base,

                "csv_available":
                    False,

                "csv_processed":
                    False,

                "section_count":
                    0,

                "timeseries_candidate_count":
                    0,

                "review_section_count":
                    0,

                "status":
                    "no_csv_available",

                "issue":
                    "",
            })

            continue

        try:
            (
                rows,
                _,
                _,
                _,
                _,
                warnings,
            ) = load_rows(
                csv_path
            )

        except Exception as exc:

            errors.append({
                **base,

                "source_path":
                    str(
                        csv_path
                    ),

                "error":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            })

            coverage.append({
                **base,

                "csv_available":
                    True,

                "csv_processed":
                    False,

                "section_count":
                    0,

                "timeseries_candidate_count":
                    0,

                "review_section_count":
                    0,

                "status":
                    "csv_read_failed",

                "issue":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            })

            continue

        sections = segment_sections(
            rows
        )

        report_candidate_count = 0
        report_review_count = 0

        for section_index, section in enumerate(
            sections
        ):

            heading = section[
                "heading"
            ]

            content = section[
                "rows"
            ]

            analysis = analyze_section(
                heading,
                content,
            )

            if not (
                analysis[
                    "candidate"
                ]
                or analysis[
                    "review"
                ]
            ):
                continue

            section_id = (
                "g4csv_"
                + identifier(
                    base[
                        "report_id"
                    ],
                    section[
                        "start"
                    ],
                    heading,
                )
            )

            common = {
                **base,

                "timeseries_candidate_id":
                    section_id,

                "source_path":
                    str(
                        csv_path
                    ),

                "source_heading":
                    heading,

                "source_record_start":
                    section[
                        "start"
                    ]
                    + 1,

                "source_record_end":
                    section[
                        "end"
                    ],

                "candidate_family":
                    analysis[
                        "family"
                    ],

                "time_axis_type_candidate":
                    analysis[
                        "time_axis_type"
                    ],

                "discovery_score":
                    analysis[
                        "score"
                    ],

                "explicit_time_axis":
                    analysis[
                        "explicit_time"
                    ],

                "buffer_axis":
                    analysis[
                        "buffer_axis"
                    ],

                "time_header_match_count":
                    analysis[
                        "time_header_match_count"
                    ],

                "signal_header_match_count":
                    analysis[
                        "signal_header_match_count"
                    ],

                "numeric_leading_row_count":
                    analysis[
                        "numeric_leading_row_count"
                    ],

                "modal_populated_width":
                    analysis[
                        "modal_populated_width"
                    ],

                "modal_width_row_count":
                    analysis[
                        "modal_width_row_count"
                    ],

                "discovery_reasons":
                    "|".join(
                        analysis[
                            "reasons"
                        ]
                    ),

                "csv_warning_count":
                    len(
                        warnings
                    ),
            }

            if analysis[
                "candidate"
            ]:

                report_candidate_count += 1

                candidate_sections.append({
                    **common,

                    "processing_status":
                        "timeseries_candidate",

                    "requires_review":
                        True,

                    "source_rows_json":
                        json.dumps(
                            content,
                            ensure_ascii=False,
                        ),
                })

                # Preserve every row in the candidate section.
                for row_offset, row in enumerate(
                    content
                ):

                    candidate_rows.append({
                        **base,

                        "timeseries_candidate_id":
                            section_id,

                        "source_heading":
                            heading,

                        "candidate_family":
                            analysis[
                                "family"
                            ],

                        "source_record":
                            (
                                section[
                                    "start"
                                ]
                                + 2
                                + row_offset
                            ),

                        "section_row_index":
                            row_offset,

                        "source_row_json":
                            json.dumps(
                                row,
                                ensure_ascii=False,
                            ),

                        "populated_cell_count":
                            len(
                                populated_cells(
                                    row
                                )
                            ),

                        "first_populated_value":
                            (
                                populated_cells(
                                    row
                                )[0]
                                if populated_cells(
                                    row
                                )
                                else ""
                            ),

                        "numeric_leading_row":
                            (
                                bool(
                                    populated_cells(
                                        row
                                    )
                                )
                                and (
                                    is_number(
                                        populated_cells(
                                            row
                                        )[0]
                                    )
                                    or is_na(
                                        populated_cells(
                                            row
                                        )[0]
                                    )
                                )
                            ),

                        "requires_review":
                            True,
                    })

            else:

                report_review_count += 1

                review_sections.append({
                    **common,

                    "processing_status":
                        "near_threshold_review",

                    "requires_review":
                        True,

                    "source_rows_json":
                        json.dumps(
                            content,
                            ensure_ascii=False,
                        ),
                })

        coverage.append({
            **base,

            "csv_available":
                True,

            "csv_processed":
                True,

            "section_count":
                len(
                    sections
                ),

            "timeseries_candidate_count":
                report_candidate_count,

            "review_section_count":
                report_review_count,

            "status":
                (
                    "timeseries_candidates_found"
                    if report_candidate_count
                    else "no_timeseries_candidates"
                ),

            "issue":
                (
                    f"csv_format_warnings:"
                    f"{len(warnings)}"
                    if warnings
                    else ""
                ),
        })

        if (
            number % 25 == 0
            or number
            == len(selected)
        ):
            print(
                "Discovered Group 4 CSV "
                f"{number}/{len(selected)} reports...",
                flush=True,
            )

    # ========================================================
    # Family summary
    # ========================================================

    family_groups = defaultdict(
        list
    )

    for row in candidate_sections:

        family_groups[
            row[
                "candidate_family"
            ]
        ].append(
            row
        )

    family_summary = []

    for family, rows in sorted(
        family_groups.items()
    ):

        headings = Counter(
            row[
                "source_heading"
            ]
            for row in rows
        )

        axis_types = Counter(
            row[
                "time_axis_type_candidate"
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
            "candidate_family":
                family,

            "section_count":
                len(rows),

            "report_count":
                len(
                    report_ids
                ),

            "heading_count":
                len(
                    headings
                ),

            "top_headings_json":
                json.dumps(
                    headings.most_common(
                        20
                    ),
                    ensure_ascii=False,
                ),

            "time_axis_type_counts_json":
                json.dumps(
                    dict(
                        axis_types
                    ),
                    ensure_ascii=False,
                ),
        })

    # ========================================================
    # Metadata
    # ========================================================

    reports_with_csv = sum(
        1
        for row in coverage
        if str(
            row[
                "csv_available"
            ]
        ).casefold()
        == "true"
    )

    reports_processed = sum(
        1
        for row in coverage
        if str(
            row[
                "csv_processed"
            ]
        ).casefold()
        == "true"
    )

    reports_with_candidates = sum(
        1
        for row in coverage
        if (
            int(
                row[
                    "timeseries_candidate_count"
                ]
            )
            > 0
        )
    )

    candidate_family_counts = Counter(
        row[
            "candidate_family"
        ]
        for row in candidate_sections
    )

    time_axis_counts = Counter(
        row[
            "time_axis_type_candidate"
        ]
        for row in candidate_sections
    )

    heading_counts = Counter(
        row[
            "source_heading"
        ]
        for row in candidate_sections
    )

    coverage_status_counts = Counter(
        row[
            "status"
        ]
        for row in coverage
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "CSV discovery",

        "reports_in_index":
            len(
                selected
            ),

        "reports_with_csv":
            reports_with_csv,

        "reports_csv_processed":
            reports_processed,

        "reports_with_timeseries_candidates":
            reports_with_candidates,

        "candidate_section_count":
            len(
                candidate_sections
            ),

        "candidate_row_count":
            len(
                candidate_rows
            ),

        "near_threshold_review_section_count":
            len(
                review_sections
            ),

        "candidate_family_counts":
            dict(
                candidate_family_counts
            ),

        "time_axis_type_counts":
            dict(
                time_axis_counts
            ),

        "unique_candidate_headings":
            len(
                heading_counts
            ),

        "top_candidate_headings":
            heading_counts.most_common(
                30
            ),

        "coverage_status_counts":
            dict(
                coverage_status_counts
            ),

        "source_errors":
            len(
                errors
            ),

        "scope":
            (
                "CSV-first discovery for Group 4 time-series "
                "measurements. Original CSV sources are scanned "
                "directly for repeated ordered measurement tables. "
                "Candidate detection uses structural evidence "
                "including time/index headers, numeric sample rows, "
                "buffer axes, repeated row widths, measurement "
                "headers, and temporal section headings. This stage "
                "does not perform semantic normalization, unit "
                "conversion, event identity inference, PDF fallback, "
                "or final time-series extraction."
            ),
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

    section_columns = [
        *BASE,
        "timeseries_candidate_id",
        "source_path",
        "source_heading",
        "source_record_start",
        "source_record_end",
        "candidate_family",
        "time_axis_type_candidate",
        "discovery_score",
        "explicit_time_axis",
        "buffer_axis",
        "time_header_match_count",
        "signal_header_match_count",
        "numeric_leading_row_count",
        "modal_populated_width",
        "modal_width_row_count",
        "discovery_reasons",
        "csv_warning_count",
        "processing_status",
        "requires_review",
        "source_rows_json",
    ]

    write_csv(
        out
        / "timeseries_candidate_sections.csv",
        candidate_sections,
        section_columns,
    )

    write_csv(
        out
        / "timeseries_candidate_rows.csv",
        candidate_rows,
        [
            *BASE,
            "timeseries_candidate_id",
            "source_heading",
            "candidate_family",
            "source_record",
            "section_row_index",
            "source_row_json",
            "populated_cell_count",
            "first_populated_value",
            "numeric_leading_row",
            "requires_review",
        ],
    )

    write_csv(
        out
        / "review_sections.csv",
        review_sections,
        section_columns,
    )

    write_csv(
        out
        / "timeseries_family_summary.csv",
        family_summary,
        [
            "candidate_family",
            "section_count",
            "report_count",
            "heading_count",
            "top_headings_json",
            "time_axis_type_counts_json",
        ],
    )

    write_csv(
        out
        / "report_coverage.csv",
        coverage,
        [
            *BASE,
            "csv_available",
            "csv_processed",
            "section_count",
            "timeseries_candidate_count",
            "review_section_count",
            "status",
            "issue",
        ],
    )

    write_csv(
        out
        / "errors.csv",
        errors,
        [
            *BASE,
            "source_path",
            "error",
        ],
    )

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