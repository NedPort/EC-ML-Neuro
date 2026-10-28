"""
Group 4 PDF-only discovery: Time-series measurements.

Purpose
-------
Discover time-series-like structures directly from ORIGINAL PDF reports
for reports where no CSV source is available.

Source hierarchy
----------------
1. CSV available:
       NOT processed here.

2. CSV unavailable + PDF available:
       original PDF is inspected directly.

3. Existing Group 2 PDF time-series handoff:
       used only as locator/supporting evidence when available.
       It is NOT treated as the measurement source.

This is a discovery pass only.

It does NOT:
- create the final structured PDF time-series dataset,
- normalize signal names,
- convert units,
- infer event identities,
- interpolate missing time,
- merge PDF and CSV data,
- or modify the frozen CSV Group 4 package.

Outputs
-------
data/processed/edr/group4_pdf_discovery_v1/

    pdf_timeseries_candidate_tables.csv
    pdf_timeseries_candidate_rows.csv
    pdf_review_tables.csv
    pdf_report_coverage.csv
    pdf_heading_summary.csv
    pdf_family_summary.csv
    errors.csv
    metadata.json

Dependencies
------------
pdfplumber
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


def first_nonblank(
    row: dict,
    keys: list[str],
):
    for key in keys:

        value = norm(
            row.get(
                key,
                ""
            )
        )

        if value:
            return value

    return ""


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
        remove_axis_annotation(
            value
        )
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


def is_na(value):
    return (
        norm(value).casefold()
        in {
            "n/a",
            "na",
            "sna",
            "not available",
            "not applicable",
            "unknown",
            "not recorded",
        }
    )


def row_values(row):
    return [
        norm(value)
        for value in row
        if norm(value)
    ]


def row_text(row):
    return " ".join(
        row_values(
            row
        )
    )


def table_text(rows):
    return " ".join(
        row_text(row)
        for row in rows
    )


# ============================================================
# Report-source helpers
# ============================================================

def get_csv_path_value(row):
    return first_nonblank(
        row,
        [
            "csv_path",
            "source_csv_path",
            "csv_file",
        ],
    )


def get_pdf_path_value(row):
    return first_nonblank(
        row,
        [
            "pdf_path",
            "source_pdf_path",
            "pdf_file",
        ],
    )


# ============================================================
# Group 2 handoff locator
# ============================================================

def load_group2_handoff(
    path: Path,
):
    """
    Build lightweight locator maps from the frozen Group 2 handoff.

    This is SUPPORTING evidence only.
    """

    if not path.exists():
        return {
            "by_report":
                defaultdict(
                    list
                ),

            "count":
                0,
        }

    rows = read_csv(
        path
    )

    by_report = defaultdict(
        list
    )

    for row in rows:

        report_id = norm(
            row.get(
                "report_id",
                ""
            )
        )

        if not report_id:
            continue

        by_report[
            report_id
        ].append(
            row
        )

    return {
        "by_report":
            by_report,

        "count":
            len(
                rows
            ),
    }


def handoff_matches_page(
    handoff_rows,
    page_number,
):
    """
    Return Group 2 locator evidence matching this PDF page.

    Accept both zero-based and one-based page conventions conservatively.
    """

    matches = []

    for row in handoff_rows:

        raw_page = first_nonblank(
            row,
            [
                "source_page",
                "page",
                "page_number",
            ],
        )

        if not raw_page:
            continue

        try:
            value = int(
                float(
                    raw_page
                )
            )

        except ValueError:
            continue

        if value in {
            page_number,
            page_number - 1,
        }:
            matches.append(
                row
            )

    return matches


# ============================================================
# Heading / family detection
# ============================================================

FAMILY_RULES = [
    (
        "pcm_edr",
        r"\bPCM\s+EDR\s+DATA\b",
    ),

    (
        "pre_crash",
        r"\bPRE[-_ ]?CRASH\b",
    ),

    (
        "post_crash",
        r"\bPOST[-_ ]?CRASH\b",
    ),

    (
        "crash_pulse",
        r"\bCRASH\s+PULSE\b",
    ),

    (
        "delta_v",
        r"\b(?:DELTA[- ]?V|VELOCITY\s+CHANGE)\b",
    ),

    (
        "roll_angle",
        r"\bROLL\s+ANGLE\b",
    ),

    (
        "angular_rate",
        r"\b(?:ROLL\s+RATE|ANGULAR\s+RATE)\b",
    ),

    (
        "acceleration",
        r"\bACCELERATION\b",
    ),

    (
        "rollover_sensor",
        r"\bROLLOVER\s+SENSOR\b",
    ),

    (
        "sensor_timeseries",
        r"\b(?:"
        r"PERIPHERAL\s+SENSOR|"
        r"PRESSURE\s+SENSOR|"
        r"SATELLITE\s+SENSOR"
        r")\b",
    ),
]


def detect_family(text):
    text = norm(text)

    for family, pattern in FAMILY_RULES:

        if re.search(
            pattern,
            text,
            re.I,
        ):
            return family

    return "other_timeseries"


def detect_component(text):
    upper = norm(
        text
    ).upper()

    has_long = (
        "LONGITUDINAL"
        in upper
    )

    has_lat = (
        "LATERAL"
        in upper
    )

    if (
        has_long
        and has_lat
    ):
        return "longitudinal_lateral"

    if has_long:
        return "longitudinal"

    if has_lat:
        return "lateral"

    if (
        "NORMAL"
        in upper
        or "VERTICAL"
        in upper
    ):
        return "normal_vertical"

    if (
        "ROLL"
        in upper
        or "ANGULAR"
        in upper
    ):
        return "roll_angular"

    return "unspecified"


def extract_heading_hint(
    page_text,
    table_rows,
):
    """
    PDF tables do not always preserve section headings inside the table.

    Use:
    1. table text when it clearly contains a structural heading;
    2. otherwise page text as a broad heading/context hint.

    No semantic identity is inferred.
    """

    candidate_text = table_text(
        table_rows
    )

    for family, pattern in FAMILY_RULES:

        match = re.search(
            pattern,
            candidate_text,
            re.I,
        )

        if match:

            lines = [
                norm(line)
                for line
                in candidate_text.split(
                    "\n"
                )
                if norm(line)
            ]

            if lines:
                return lines[0]

    page_lines = [
        norm(line)
        for line
        in (
            page_text
            or ""
        ).splitlines()
        if norm(line)
    ]

    # Prefer lines with known temporal family wording.
    for line in page_lines:

        if any(
            re.search(
                pattern,
                line,
                re.I,
            )
            for _, pattern
            in FAMILY_RULES
        ):
            return line

    # Otherwise preserve a short page-context string.
    return (
        page_lines[0]
        if page_lines
        else ""
    )


# ============================================================
# Known non-time-series structures
# ============================================================

NON_TIMESERIES_PATTERNS = [
    (
        "group2_summary",
        r"\bEVENT\s+RECORD\s+SUMMARY\b",
    ),

    (
        "dtc_structure",
        r"\bDTCS?\s+PRESENT\b",
    ),

    (
        "status_configuration",
        r"\bSYSTEM\s+(?:STATUS|CONFIGURATION)\b",
    ),

    (
        "deployment_scalar",
        r"\bDEPLOYMENT\s+(?:COMMAND\s+)?DATA\b",
    ),
]


def known_non_timeseries_reason(
    text,
):
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
# Time-series structural evidence
# ============================================================

TIME_PATTERNS = [
    r"\btime\b",
    r"\bseconds?\s+before\b",
    r"\bseconds?\s+after\b",
    r"\bsec\b",
    r"\bmsec\b",
    r"\bmilliseconds?\b",
    r"\brelative\s+time\b",
    r"\bsample\s+count\b",
    r"\bbuffer\s+address\b",
]


SIGNAL_PATTERNS = [
    r"\bvehicle\s+speed\b",
    r"\bengine\s+(?:speed|rpm)\b",
    r"\bthrottle\b",
    r"\baccelerator\b",
    r"\bbrake\b",
    r"\bacceleration\b",
    r"\bdelta[- ]?v\b",
    r"\bvelocity\b",
    r"\byaw\b",
    r"\bsteering\b",
    r"\broll\b",
]


def detect_samples_by_rows(rows):
    """
    Find repeated numeric-axis rows.

    Returns:
        numeric_row_count
        modal_first_populated_column
    """

    columns = []

    for row in rows:

        positions = [
            (
                index,
                norm(value),
            )
            for index, value
            in enumerate(row)
            if norm(value)
        ]

        if len(
            positions
        ) < 2:
            continue

        first_column, first_value = (
            positions[0]
        )

        if (
            is_numeric(
                first_value
            )
            or is_na(
                first_value
            )
        ):
            columns.append(
                first_column
            )

    if not columns:
        return (
            0,
            "",
        )

    counts = Counter(
        columns
    )

    modal_column, modal_count = (
        counts.most_common(
            1
        )[0]
    )

    return (
        modal_count,
        modal_column,
    )


def detect_samples_by_columns(rows):
    """
    Detect transposed tables such as:

        Time (sec)   -5  -4  -3  -2  -1
        Speed        20  18  ...
    """

    for row_index, row in enumerate(
        rows[:10]
    ):

        values = row_values(
            row
        )

        if len(
            values
        ) < 3:
            continue

        text = " ".join(
            values
        )

        if not re.search(
            r"\b(?:"
            r"time|"
            r"seconds?|"
            r"sec|"
            r"msec|"
            r"sample\s+count|"
            r"TRG"
            r")\b",
            text,
            re.I,
        ):
            continue

        numeric_count = sum(
            1
            for value
            in values
            if is_numeric(
                value
            )
        )

        if numeric_count >= 2:
            return (
                True,
                row_index,
                numeric_count,
            )

    return (
        False,
        "",
        0,
    )


def detect_buffer_axis(rows):
    text = " ".join(
        row_text(row)
        for row in rows[:8]
    )

    return bool(
        re.search(
            r"\bbuffer\s+address\b",
            text,
            re.I,
        )
    )


def detect_explicit_time_header(rows):
    text = " ".join(
        row_text(row)
        for row in rows[:8]
    )

    matches = [
        pattern
        for pattern in TIME_PATTERNS
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


def detect_signal_headers(rows):
    text = " ".join(
        row_text(row)
        for row in rows[:10]
    )

    matches = [
        pattern
        for pattern
        in SIGNAL_PATTERNS
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


def repeated_width_evidence(rows):
    widths = []

    for row in rows:

        width = len(
            row_values(
                row
            )
        )

        if width >= 2:
            widths.append(
                width
            )

    if not widths:
        return (
            0,
            0,
        )

    counts = Counter(
        widths
    )

    return counts.most_common(
        1
    )[0]


# ============================================================
# Candidate analysis
# ============================================================

def analyze_table(
    rows,
    heading_hint,
    page_text,
    handoff_page_matches,
):
    combined_text = " ".join(
        [
            norm(
                heading_hint
            ),
            table_text(
                rows
            ),
        ]
    )

    exclusion_reason = (
        known_non_timeseries_reason(
            combined_text
        )
    )

    (
        numeric_row_count,
        numeric_axis_column,
    ) = detect_samples_by_rows(
        rows
    )

    (
        transposed,
        transposed_axis_row,
        transposed_sample_count,
    ) = detect_samples_by_columns(
        rows
    )

    buffer_axis = (
        detect_buffer_axis(
            rows
        )
    )

    (
        time_header_count,
        time_header_patterns,
    ) = detect_explicit_time_header(
        rows
    )

    (
        signal_header_count,
        signal_patterns,
    ) = detect_signal_headers(
        rows
    )

    (
        modal_width,
        modal_width_count,
    ) = repeated_width_evidence(
        rows
    )

    family = detect_family(
        combined_text
    )

    component = detect_component(
        combined_text
    )

    family_evidence = (
        family
        != "other_timeseries"
    )

    score = 0
    reasons = []

    if numeric_row_count >= 2:
        score += 4
        reasons.append(
            "repeated_numeric_axis_rows"
        )

    if transposed:
        score += 5
        reasons.append(
            "transposed_time_axis"
        )

    if buffer_axis:
        score += 5
        reasons.append(
            "buffer_axis"
        )

    if time_header_count:
        score += 2
        reasons.append(
            "time_or_index_header"
        )

    if signal_header_count:
        score += 1
        reasons.append(
            "measurement_signal_header"
        )

    if modal_width_count >= 3:
        score += 1
        reasons.append(
            "repeated_table_width"
        )

    if family_evidence:
        score += 2
        reasons.append(
            "known_temporal_family"
        )

    if handoff_page_matches:
        score += 1
        reasons.append(
            "group2_handoff_page_support"
        )

    # --------------------------------------------------------
    # Structural orientation
    # --------------------------------------------------------

    if buffer_axis:

        orientation = (
            "buffer_order_table"
        )

    elif transposed:

        orientation = (
            "samples_by_columns"
        )

    elif numeric_row_count >= 2:

        orientation = (
            "samples_by_rows"
        )

    else:

        orientation = (
            "unknown"
        )

    # --------------------------------------------------------
    # Candidate decision
    # --------------------------------------------------------

    if exclusion_reason:

        candidate = False
        review = False
        decision = (
            "known_non_timeseries"
        )

    else:

        strong_structure = (
            buffer_axis
            or transposed
            or numeric_row_count >= 2
        )

        candidate = (
            strong_structure
            and score >= 5
        )

        review = (
            not candidate
            and score >= 3
        )

        decision = (
            "candidate"
            if candidate
            else (
                "review"
                if review
                else "ignore"
            )
        )

    return {
        "decision":
            decision,

        "candidate":
            candidate,

        "review":
            review,

        "score":
            score,

        "family":
            family,

        "component":
            component,

        "orientation":
            orientation,

        "numeric_row_count":
            numeric_row_count,

        "numeric_axis_column":
            numeric_axis_column,

        "transposed_axis_detected":
            transposed,

        "transposed_axis_row":
            transposed_axis_row,

        "transposed_sample_count":
            transposed_sample_count,

        "buffer_axis":
            buffer_axis,

        "time_header_count":
            time_header_count,

        "time_header_patterns":
            time_header_patterns,

        "signal_header_count":
            signal_header_count,

        "signal_patterns":
            signal_patterns,

        "modal_width":
            modal_width,

        "modal_width_count":
            modal_width_count,

        "known_non_timeseries_reason":
            exclusion_reason,

        "reasons":
            reasons,
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
        "--group2-handoff",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_final_v1/"
            "group4_pdf_timeseries_handoff_sections.csv"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_discovery_v1"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    index_rows = read_csv(
        args.index
    )

    handoff = load_group2_handoff(
        args.group2_handoff
    )

    candidates = []
    candidate_rows = []
    reviews = []
    coverage = []
    errors = []

    # ========================================================
    # Determine PDF-only population first
    # ========================================================

    pdf_only_reports = []

    for report in index_rows:

        csv_value = get_csv_path_value(
            report
        )

        csv_path = resolve_path(
            csv_value,
            args.source_root,
        )

        # CSV exists -> this report is already handled
        # by frozen Group 4 CSV.
        if csv_path is not None:
            continue

        pdf_only_reports.append(
            report
        )

    if args.limit is not None:

        pdf_only_reports = (
            pdf_only_reports[
                :args.limit
            ]
        )

    print(
        "PDF-only reports selected: "
        f"{len(pdf_only_reports)}",
        flush=True,
    )

    # ========================================================
    # Process original PDFs
    # ========================================================

    for report_number, report in enumerate(
        pdf_only_reports,
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

        report_id = norm(
            report.get(
                "report_id",
                ""
            )
        )

        pdf_value = get_pdf_path_value(
            report
        )

        pdf_path = resolve_path(
            pdf_value,
            args.source_root,
        )

        handoff_rows = (
            handoff[
                "by_report"
            ].get(
                report_id,
                [],
            )
        )

        if pdf_path is None:

            coverage.append({
                **base,

                "pdf_available":
                    False,

                "pdf_processed":
                    False,

                "page_count":
                    0,

                "table_count":
                    0,

                "candidate_table_count":
                    0,

                "review_table_count":
                    0,

                "group2_handoff_locator_count":
                    len(
                        handoff_rows
                    ),

                "status":
                    "pdf_missing",

                "issue":
                    norm(
                        pdf_value
                    ),
            })

            continue

        report_table_count = 0
        report_candidate_count = 0
        report_review_count = 0
        page_count = 0

        try:

            with pdfplumber.open(
                pdf_path
            ) as pdf:

                page_count = len(
                    pdf.pages
                )

                for page_number, page in enumerate(
                    pdf.pages,
                    1,
                ):

                    try:

                        page_text = (
                            page.extract_text()
                            or ""
                        )

                    except Exception:

                        page_text = ""

                    page_handoff_matches = (
                        handoff_matches_page(
                            handoff_rows,
                            page_number,
                        )
                    )

                    # ----------------------------------------
                    # Extract page tables
                    # ----------------------------------------

                    try:

                        tables = (
                            page.extract_tables()
                            or []
                        )

                    except Exception as exc:

                        errors.append({
                            **base,

                            "source_path":
                                str(
                                    pdf_path
                                ),

                            "page_number":
                                page_number,

                            "stage":
                                "extract_tables",

                            "error":
                                (
                                    f"{type(exc).__name__}: "
                                    f"{exc}"
                                ),
                        })

                        continue

                    for table_index, table in enumerate(
                        tables
                    ):

                        if not table:
                            continue

                        cleaned_rows = [
                            [
                                norm(cell)
                                for cell in row
                            ]
                            for row in table
                            if row is not None
                        ]

                        cleaned_rows = [
                            row
                            for row
                            in cleaned_rows
                            if row_values(
                                row
                            )
                        ]

                        if len(
                            cleaned_rows
                        ) < 2:
                            continue

                        report_table_count += 1

                        heading_hint = (
                            extract_heading_hint(
                                page_text,
                                cleaned_rows,
                            )
                        )

                        analysis = (
                            analyze_table(
                                cleaned_rows,
                                heading_hint,
                                page_text,
                                page_handoff_matches,
                            )
                        )

                        if (
                            not analysis[
                                "candidate"
                            ]
                            and not analysis[
                                "review"
                            ]
                        ):
                            continue

                        candidate_id = (
                            "g4pdf_"
                            + identifier(
                                report_id,
                                page_number,
                                table_index,
                                heading_hint,
                            )
                        )

                        handoff_headings = [
                            first_nonblank(
                                row,
                                [
                                    "source_heading",
                                    "heading",
                                ],
                            )
                            for row
                            in page_handoff_matches
                        ]

                        common = {
                            **base,

                            "pdf_candidate_id":
                                candidate_id,

                            "source_path":
                                str(
                                    pdf_path
                                ),

                            "page_number":
                                page_number,

                            "table_index_on_page":
                                table_index,

                            "source_heading_hint":
                                heading_hint,

                            "family_candidate":
                                analysis[
                                    "family"
                                ],

                            "component_candidate":
                                analysis[
                                    "component"
                                ],

                            "table_orientation_candidate":
                                analysis[
                                    "orientation"
                                ],

                            "discovery_score":
                                analysis[
                                    "score"
                                ],

                            "numeric_axis_row_count":
                                analysis[
                                    "numeric_row_count"
                                ],

                            "numeric_axis_column":
                                analysis[
                                    "numeric_axis_column"
                                ],

                            "transposed_axis_detected":
                                analysis[
                                    "transposed_axis_detected"
                                ],

                            "transposed_axis_row":
                                analysis[
                                    "transposed_axis_row"
                                ],

                            "transposed_sample_count":
                                analysis[
                                    "transposed_sample_count"
                                ],

                            "buffer_axis_detected":
                                analysis[
                                    "buffer_axis"
                                ],

                            "time_header_match_count":
                                analysis[
                                    "time_header_count"
                                ],

                            "signal_header_match_count":
                                analysis[
                                    "signal_header_count"
                                ],

                            "modal_populated_width":
                                analysis[
                                    "modal_width"
                                ],

                            "modal_width_row_count":
                                analysis[
                                    "modal_width_count"
                                ],

                            "group2_handoff_page_support":
                                bool(
                                    page_handoff_matches
                                ),

                            "group2_handoff_match_count":
                                len(
                                    page_handoff_matches
                                ),

                            "group2_handoff_headings_json":
                                json.dumps(
                                    handoff_headings,
                                    ensure_ascii=False,
                                ),

                            "discovery_reasons":
                                "|".join(
                                    analysis[
                                        "reasons"
                                    ]
                                ),

                            "source_rows_json":
                                json.dumps(
                                    cleaned_rows,
                                    ensure_ascii=False,
                                ),

                            "page_text_context":
                                norm(
                                    page_text
                                )[:4000],
                        }

                        if analysis[
                            "candidate"
                        ]:

                            report_candidate_count += 1

                            candidates.append({
                                **common,

                                "processing_status":
                                    "pdf_timeseries_candidate",

                                "requires_review":
                                    True,
                            })

                            for row_index, row in enumerate(
                                cleaned_rows
                            ):

                                candidate_rows.append({
                                    **base,

                                    "pdf_candidate_id":
                                        candidate_id,

                                    "page_number":
                                        page_number,

                                    "table_index_on_page":
                                        table_index,

                                    "source_heading_hint":
                                        heading_hint,

                                    "family_candidate":
                                        analysis[
                                            "family"
                                        ],

                                    "table_orientation_candidate":
                                        analysis[
                                            "orientation"
                                        ],

                                    "table_row_index":
                                        row_index,

                                    "source_row_json":
                                        json.dumps(
                                            row,
                                            ensure_ascii=False,
                                        ),

                                    "populated_cell_count":
                                        len(
                                            row_values(
                                                row
                                            )
                                        ),

                                    "first_populated_value":
                                        (
                                            row_values(
                                                row
                                            )[0]
                                            if row_values(
                                                row
                                            )
                                            else ""
                                        ),
                                })

                        elif analysis[
                            "review"
                        ]:

                            report_review_count += 1

                            reviews.append({
                                **common,

                                "processing_status":
                                    "pdf_near_threshold_review",

                                "requires_review":
                                    True,
                            })

        except Exception as exc:

            errors.append({
                **base,

                "source_path":
                    str(
                        pdf_path
                    ),

                "page_number":
                    "",

                "stage":
                    "open_pdf",

                "error":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            })

            coverage.append({
                **base,

                "pdf_available":
                    True,

                "pdf_processed":
                    False,

                "page_count":
                    0,

                "table_count":
                    0,

                "candidate_table_count":
                    0,

                "review_table_count":
                    0,

                "group2_handoff_locator_count":
                    len(
                        handoff_rows
                    ),

                "status":
                    "pdf_processing_failed",

                "issue":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            })

            continue

        # ----------------------------------------------------
        # Report coverage
        # ----------------------------------------------------

        coverage.append({
            **base,

            "pdf_available":
                True,

            "pdf_processed":
                True,

            "page_count":
                page_count,

            "table_count":
                report_table_count,

            "candidate_table_count":
                report_candidate_count,

            "review_table_count":
                report_review_count,

            "group2_handoff_locator_count":
                len(
                    handoff_rows
                ),

            "status":
                (
                    "timeseries_candidates_found"
                    if report_candidate_count
                    else (
                        "review_only"
                        if report_review_count
                        else "no_timeseries_candidates"
                    )
                ),

            "issue":
                "",
        })

        print(
            "Discovered Group 4 PDF "
            f"{report_number}/"
            f"{len(pdf_only_reports)} reports...",
            flush=True,
        )

    # ========================================================
    # Summaries
    # ========================================================

    family_counts = Counter(
        row[
            "family_candidate"
        ]
        for row in candidates
    )

    orientation_counts = Counter(
        row[
            "table_orientation_candidate"
        ]
        for row in candidates
    )

    heading_counts = Counter(
        row[
            "source_heading_hint"
        ]
        for row in candidates
    )

    coverage_counts = Counter(
        row[
            "status"
        ]
        for row in coverage
    )

    family_summary = []

    grouped_family = defaultdict(
        list
    )

    for row in candidates:

        grouped_family[
            (
                row[
                    "family_candidate"
                ],
                row[
                    "component_candidate"
                ],
                row[
                    "table_orientation_candidate"
                ],
            )
        ].append(
            row
        )

    for (
        family,
        component,
        orientation,
    ), rows in sorted(
        grouped_family.items()
    ):

        reports = {
            row[
                "report_id"
            ]
            for row in rows
        }

        headings = Counter(
            row[
                "source_heading_hint"
            ]
            for row in rows
        )

        family_summary.append({
            "family_candidate":
                family,

            "component_candidate":
                component,

            "table_orientation_candidate":
                orientation,

            "table_count":
                len(
                    rows
                ),

            "report_count":
                len(
                    reports
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

    heading_summary = [
        {
            "source_heading_hint":
                heading,

            "candidate_table_count":
                count,
        }
        for heading, count
        in heading_counts.most_common()
    ]

    # ========================================================
    # Write outputs
    # ========================================================

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidate_columns = [
        *BASE,
        "pdf_candidate_id",
        "source_path",
        "page_number",
        "table_index_on_page",
        "source_heading_hint",
        "family_candidate",
        "component_candidate",
        "table_orientation_candidate",
        "discovery_score",
        "numeric_axis_row_count",
        "numeric_axis_column",
        "transposed_axis_detected",
        "transposed_axis_row",
        "transposed_sample_count",
        "buffer_axis_detected",
        "time_header_match_count",
        "signal_header_match_count",
        "modal_populated_width",
        "modal_width_row_count",
        "group2_handoff_page_support",
        "group2_handoff_match_count",
        "group2_handoff_headings_json",
        "discovery_reasons",
        "processing_status",
        "requires_review",
        "source_rows_json",
        "page_text_context",
    ]

    write_csv(
        out
        / "pdf_timeseries_candidate_tables.csv",
        candidates,
        candidate_columns,
    )

    write_csv(
        out
        / "pdf_review_tables.csv",
        reviews,
        candidate_columns,
    )

    write_csv(
        out
        / "pdf_timeseries_candidate_rows.csv",
        candidate_rows,
        [
            *BASE,
            "pdf_candidate_id",
            "page_number",
            "table_index_on_page",
            "source_heading_hint",
            "family_candidate",
            "table_orientation_candidate",
            "table_row_index",
            "source_row_json",
            "populated_cell_count",
            "first_populated_value",
        ],
    )

    write_csv(
        out
        / "pdf_report_coverage.csv",
        coverage,
        [
            *BASE,
            "pdf_available",
            "pdf_processed",
            "page_count",
            "table_count",
            "candidate_table_count",
            "review_table_count",
            "group2_handoff_locator_count",
            "status",
            "issue",
        ],
    )

    write_csv(
        out
        / "pdf_heading_summary.csv",
        heading_summary,
        [
            "source_heading_hint",
            "candidate_table_count",
        ],
    )

    write_csv(
        out
        / "pdf_family_summary.csv",
        family_summary,
        [
            "family_candidate",
            "component_candidate",
            "table_orientation_candidate",
            "table_count",
            "report_count",
            "unique_heading_count",
            "top_headings_json",
        ],
    )

    write_csv(
        out
        / "errors.csv",
        errors,
        [
            *BASE,
            "source_path",
            "page_number",
            "stage",
            "error",
        ],
    )

    # ========================================================
    # Metadata
    # ========================================================

    processed_count = sum(
        1
        for row in coverage
        if str(
            row[
                "pdf_processed"
            ]
        ).casefold()
        == "true"
    )

    reports_with_candidates = sum(
        1
        for row in coverage
        if int(
            row[
                "candidate_table_count"
            ]
        ) > 0
    )

    candidates_with_handoff_support = sum(
        1
        for row in candidates
        if str(
            row[
                "group2_handoff_page_support"
            ]
        ).casefold()
        == "true"
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "PDF-only discovery",

        "reports_in_index":
            len(
                index_rows
            ),

        "pdf_only_reports_selected":
            len(
                pdf_only_reports
            ),

        "pdf_reports_processed":
            processed_count,

        "reports_with_timeseries_candidates":
            reports_with_candidates,

        "candidate_table_count":
            len(
                candidates
            ),

        "candidate_row_count":
            len(
                candidate_rows
            ),

        "review_table_count":
            len(
                reviews
            ),

        "candidate_family_counts":
            dict(
                family_counts
            ),

        "candidate_orientation_counts":
            dict(
                orientation_counts
            ),

        "unique_candidate_heading_hints":
            len(
                heading_counts
            ),

        "top_candidate_heading_hints":
            heading_counts.most_common(
                30
            ),

        "coverage_status_counts":
            dict(
                coverage_counts
            ),

        "group2_handoff_total_locator_sections":
            handoff[
                "count"
            ],

        "candidate_tables_with_group2_handoff_page_support":
            candidates_with_handoff_support,

        "source_errors":
            len(
                errors
            ),

        "scope":
            (
                "PDF-only discovery for Group 4 time-series "
                "measurements. Only reports without an available CSV "
                "source are processed. Original PDFs are the discovery "
                "source. The frozen Group 2 PDF time-series handoff is "
                "used only as supporting page-level locator evidence. "
                "Candidate detection uses repeated numeric-axis rows, "
                "transposed time axes, buffer axes, time/index headers, "
                "measurement headers, repeated table geometry, and "
                "known temporal family headings. No final structured "
                "extraction, semantic normalization, unit conversion, "
                "event identity inference, or CSV/PDF integration is "
                "performed."
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
        "GROUP 4 PDF-ONLY DISCOVERY COMPLETE."
    )


if __name__ == "__main__":
    main()