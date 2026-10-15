"""
Resolve remaining Group 4 PDF audit review tables.

Inputs
------
data/processed/edr/group4_pdf_audit_v1/
    remaining_review_tables.csv
    companion_metadata_tables.csv
    accepted_timeseries_tables.csv
    excluded_non_timeseries_tables.csv

Outputs
-------
data/processed/edr/group4_pdf_resolved_v1/

    accepted_timeseries_tables.csv
    companion_metadata_tables.csv
    excluded_non_timeseries_tables.csv
    graphical_review_tables.csv
    remaining_review_tables.csv
    review_resolution_all.csv
    resolution_summary.csv
    metadata.json

Purpose
-------
Resolve the residual Group 4 PDF review population conservatively.

The first PDF audit already accepted explicit sampled time-series.

This resolver addresses tables that lacked an explicit repeated temporal
axis and separates them into:

1. companion metadata
2. single-snapshot exclusions
3. static/report/documentation exclusions
4. graphical time-series evidence that cannot be safely reconstructed
   from PDF table extraction
5. any genuinely unresolved residual

Important
---------
Graphical crash-pulse and Delta-V plots are NOT force-parsed.

Examples of known PDF graphical corruption include strings such as:

    DDeellttaa--VV
    LLoonnggiittuuddiinnaall
    CCrraasshh PPuullssee

and collapsed axis text such as:

    0 20 40 60 ... 260 msec

These remain explicit review evidence.

No accepted time-series from the first audit are modified.
"""

from __future__ import annotations

import argparse
import csv
import json
import re

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


csv.field_size_limit(100_000_000)


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

    tmp.replace(
        path
    )


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
        row_text(row)
        for row in rows
    )


def populated_count(row):
    return len(
        populated(
            row
        )
    )


# ============================================================
# Graphical PDF detection
# ============================================================

GRAPHICAL_CORRUPTION_PATTERNS = [
    r"DDeellttaa",
    r"LLoonnggiittuuddiinnaall",
    r"LLaatteerraall",
    r"CCrraasshh",
    r"PPuullssee",
    r"AAAcc?c?e?l?e?r?a?t?i?o?n",
]


def looks_like_doubled_pdf_text(
    text,
):
    return any(
        re.search(
            pattern,
            text,
        )
        for pattern
        in GRAPHICAL_CORRUPTION_PATTERNS
    )


def has_collapsed_time_axis(
    text,
):
    """
    Detect graphical x-axis text collapsed into a single cell.

    Examples:
        0 20 40 60 ... 260 msec
        -60 -50 -40 ... 60 Time (msec)
    """

    if not re.search(
        r"\b(?:msec|ms|milliseconds?)\b",
        text,
        re.I,
    ):
        return False

    numbers = re.findall(
        r"(?<![A-Za-z])"
        r"[-+]?\d+(?:\.\d+)?",
        text,
    )

    return (
        len(numbers) >= 6
    )


def is_graphical_timeseries(
    rows,
    page_text,
):
    table = table_text(
        rows
    )

    context = (
        table
        + " "
        + norm(
            page_text
        )
    )

    temporal_family = bool(
        re.search(
            r"\b(?:"
            r"delta[- ]?v|"
            r"crash pulse|"
            r"acceleration|"
            r"cumulative delta"
            r")\b",
            context,
            re.I,
        )
        or looks_like_doubled_pdf_text(
            context
        )
    )

    return (
        temporal_family
        and (
            looks_like_doubled_pdf_text(
                table
            )
            or has_collapsed_time_axis(
                table
            )
        )
    )


# ============================================================
# Single-sample temporal tables
# ============================================================

def is_time_header(value):
    return bool(
        re.search(
            r"\btime\b",
            norm(value),
            re.I,
        )
    )


def is_numeric(value):
    text = norm(
        value
    )

    text = re.sub(
        r"\([^)]*\)",
        "",
        text,
    )

    text = re.sub(
        r"\s*(?:"
        r"msec|"
        r"ms|"
        r"milliseconds?|"
        r"seconds?|"
        r"secs?"
        r")\s*$",
        "",
        text,
        flags=re.I,
    )

    text = norm(
        text
    )

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)",
            text,
        )
    )


def is_single_sample_temporal(
    rows,
):
    """
    Example:

        Time (ms) | Normal Acceleration (g)
        250       | 0.3

    A single timestamp is a snapshot, not a repeated Group 4 series.
    """

    if len(
        rows
    ) != 2:
        return False

    header = populated(
        rows[0]
    )

    data = populated(
        rows[1]
    )

    if len(
        header
    ) < 2:
        return False

    if len(
        data
    ) < 2:
        return False

    if not is_time_header(
        header[0]
    ):
        return False

    return is_numeric(
        data[0]
    )


# ============================================================
# Scalar-table detection
# ============================================================

def is_scalar_two_column_table(
    rows,
):
    """
    Most residual PDF context consists of repeated:

        field | value

    rows.

    These are not sampled time-series.
    """

    if len(
        rows
    ) < 2:
        return False

    populated_counts = [
        populated_count(
            row
        )
        for row in rows
    ]

    useful = [
        count
        for count
        in populated_counts
        if count > 0
    ]

    if not useful:
        return False

    two_or_less = sum(
        1
        for count
        in useful
        if count <= 2
    )

    return (
        two_or_less
        / len(
            useful
        )
        >= 0.90
    )


# ============================================================
# Companion metadata rules
# ============================================================

COMPANION_PATTERNS = [
    r"\brecording status\b",
    r"\btime series data\b",
    r"\btime from trg to next sample\b",

    r"\bmaximum delta[- ]?v\b",
    r"\bmaximum .*velocity change\b",
    r"\btime,?\s*maximum delta[- ]?v\b",
    r"\btime .* maximum .* velocity change\b",

    r"\bclipping time\b",
    r"\blength of delta[- ]?v\b",

    r"\broll angle at .*trg\b",
    r"\brollangle peak\b",
    r"\broll angle peak\b",

    r"\bevent recording complete\b",
    r"\bcomplete file recorded\b",
    r"\bcrash record locked\b",

    r"\btime between events\b",
    r"\bevent counter\b",
    r"\bdeployment event counter\b",

    r"\bpre[- ]?crash.*associated\b",
    r"\bvehicle event data .*pre[- ]?crash\b",

    r"\btime from algorithm enable\b",
    r"\bdeployment time\b",

    r"\balgorithm run time\b",
    r"\bvelocity change during algorithm run time\b",

    r"\btrg count\b",
    r"\btime zero\b",
]


PRECRASH_CONTEXT_PATTERNS = [
    r"\bpre[-_ ]?crash data\b",
    r"\bassociated events not recorded\b",
    r"\bextended concatenated event\b",
    r"\bvehicle power mode\b",
    r"\bremote start status\b",
    r"\blow tire pressure warning\b",
]


def companion_match_count(
    text,
):
    return sum(
        1
        for pattern
        in COMPANION_PATTERNS
        if re.search(
            pattern,
            text,
            re.I,
        )
    )


def is_precrash_context(
    text,
):
    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern
        in PRECRASH_CONTEXT_PATTERNS
    )


# ============================================================
# Static / documentation exclusions
# ============================================================

STATIC_PATTERNS = [
    r"\buser entered vin\b",
    r"\bvehicle identification number\b",
    r"\bmodule serial number\b",
    r"\bpart number\b",
    r"\bsoftware version\b",
    r"\bsoftware date\b",

    r"\bdata element name\b",
    r"\bpositive sign notation\b",

    r"\bcase number\b",
    r"\bprinted on\b",
    r"\buser\b",

    r"\bminimum resultant\b",
    r"\bdoes not deploy the air bag\b",

    r"\brestraints system faults\b",
]


def is_static_documentation(
    text,
):
    matches = sum(
        1
        for pattern
        in STATIC_PATTERNS
        if re.search(
            pattern,
            text,
            re.I,
        )
    )

    return (
        matches >= 1
    )


# ============================================================
# Deployment / status context
# ============================================================

STATUS_PATTERNS = [
    r"\bsir warning lamp\b",
    r"\bbelt switch\b",
    r"\bseat position\b",
    r"\bpassenger classification\b",
    r"\bair bag indicator\b",
    r"\bdiagnostic trouble codes?\b",
    r"\bignition cycles?\b",
    r"\bdeployment loop commanded\b",
    r"\brollover sensor status\b",
    r"\bside air bag deployment status\b",
    r"\bevent severity status\b",
    r"\balgorithm active\b",
]


def is_event_status_context(
    text,
):
    match_count = sum(
        1
        for pattern
        in STATUS_PATTERNS
        if re.search(
            pattern,
            text,
            re.I,
        )
    )

    return (
        match_count >= 2
    )


# ============================================================
# Resolve one residual table
# ============================================================

def resolve_table(
    source,
):
    rows = load_rows(
        source.get(
            "source_rows_json",
            ""
        )
    )

    table = table_text(
        rows
    )

    heading = norm(
        source.get(
            "source_heading_hint",
            ""
        )
    )

    page_text = norm(
        source.get(
            "page_text_context",
            ""
        )
    )

    context = " ".join(
        [
            heading,
            table,
            page_text,
        ]
    )

    # --------------------------------------------------------
    # 1. Graphical / garbled time-series
    # --------------------------------------------------------

    if is_graphical_timeseries(
        rows,
        page_text,
    ):

        return {
            "resolution_decision":
                "graphical_review",

            "resolution_status":
                "preserved_graphical_timeseries_evidence",

            "resolution_reason":
                "pdf_graph_or_plot_not_safely_reconstructable_from_table_text",
        }

    # --------------------------------------------------------
    # 2. One-sample snapshots
    # --------------------------------------------------------

    if is_single_sample_temporal(
        rows
    ):

        return {
            "resolution_decision":
                "exclude",

            "resolution_status":
                "excluded_single_snapshot",

            "resolution_reason":
                "single_temporal_measurement_not_repeated_timeseries",
        }

    # --------------------------------------------------------
    # 3. Two-column scalar/context structures
    # --------------------------------------------------------

    scalar_table = (
        is_scalar_two_column_table(
            rows
        )
    )

    companion_matches = (
        companion_match_count(
            context
        )
    )

    if (
        scalar_table
        and (
            companion_matches > 0
            or is_precrash_context(
                context
            )
            or is_event_status_context(
                context
            )
        )
    ):

        return {
            "resolution_decision":
                "companion",

            "resolution_status":
                "companion_metadata_resolved",

            "resolution_reason":
                "scalar_event_or_timeseries_context_without_sample_axis",
        }

    # --------------------------------------------------------
    # 4. Static documentation / sign conventions
    # --------------------------------------------------------

    if (
        scalar_table
        and is_static_documentation(
            context
        )
    ):

        return {
            "resolution_decision":
                "exclude",

            "resolution_status":
                "excluded_static_documentation",

            "resolution_reason":
                "report_or_module_documentation_not_timeseries",
        }

    # --------------------------------------------------------
    # 5. Generic scalar structure
    # --------------------------------------------------------

    if scalar_table:

        return {
            "resolution_decision":
                "companion",

            "resolution_status":
                "companion_scalar_context",

            "resolution_reason":
                "scalar_field_value_structure_without_sample_axis",
        }

    # --------------------------------------------------------
    # 6. Remaining pre-crash context
    # --------------------------------------------------------

    if is_precrash_context(
        context
    ):

        return {
            "resolution_decision":
                "companion",

            "resolution_status":
                "companion_precrash_context",

            "resolution_reason":
                "precrash_context_without_repeated_sample_axis",
        }

    # --------------------------------------------------------
    # 7. Unresolved
    # --------------------------------------------------------

    return {
        "resolution_decision":
            "review",

        "resolution_status":
            "remaining_review",

        "resolution_reason":
            "no_safe_structural_resolution_rule",
    }


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
            "group4_pdf_audit_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_resolved_v1"
        ),
    )

    args = parser.parse_args()

    audit_dir = (
        args.audit_directory
    )

    required = {
        "accepted":
            audit_dir
            / "accepted_timeseries_tables.csv",

        "companions":
            audit_dir
            / "companion_metadata_tables.csv",

        "excluded":
            audit_dir
            / "excluded_non_timeseries_tables.csv",

        "review":
            audit_dir
            / "remaining_review_tables.csv",
    }

    for name, path in required.items():

        if not path.exists():

            raise FileNotFoundError(
                f"Missing required {name}: "
                f"{path}"
            )

    accepted_existing = read_csv(
        required[
            "accepted"
        ]
    )

    companions_existing = read_csv(
        required[
            "companions"
        ]
    )

    excluded_existing = read_csv(
        required[
            "excluded"
        ]
    )

    review_input = read_csv(
        required[
            "review"
        ]
    )

    # ========================================================
    # Resolve residual review population
    # ========================================================

    resolved_rows = []

    for index, source in enumerate(
        review_input,
        1,
    ):

        result = resolve_table(
            source
        )

        resolved_rows.append({
            **source,
            **result,
        })

        if (
            index % 100 == 0
            or index
            == len(
                review_input
            )
        ):

            print(
                "Resolved Group 4 PDF review "
                f"{index}/"
                f"{len(review_input)} tables...",
                flush=True,
            )

    # ========================================================
    # Split
    # ========================================================

    resolved_companions = [
        row
        for row
        in resolved_rows
        if row[
            "resolution_decision"
        ]
        == "companion"
    ]

    resolved_excluded = [
        row
        for row
        in resolved_rows
        if row[
            "resolution_decision"
        ]
        == "exclude"
    ]

    graphical_review = [
        row
        for row
        in resolved_rows
        if row[
            "resolution_decision"
        ]
        == "graphical_review"
    ]

    remaining_review = [
        row
        for row
        in resolved_rows
        if row[
            "resolution_decision"
        ]
        == "review"
    ]

    # ========================================================
    # Combine with first audit
    # ========================================================

    final_accepted = list(
        accepted_existing
    )

    final_companions = (
        list(
            companions_existing
        )
        + resolved_companions
    )

    final_excluded = (
        list(
            excluded_existing
        )
        + resolved_excluded
    )

    # ========================================================
    # Decision accounting
    # ========================================================

    resolution_counts = Counter(
        row[
            "resolution_decision"
        ]
        for row in resolved_rows
    )

    status_counts = Counter(
        row[
            "resolution_status"
        ]
        for row in resolved_rows
    )

    original_total = (
        len(
            accepted_existing
        )
        + len(
            companions_existing
        )
        + len(
            excluded_existing
        )
        + len(
            review_input
        )
    )

    final_total = (
        len(
            final_accepted
        )
        + len(
            final_companions
        )
        + len(
            final_excluded
        )
        + len(
            graphical_review
        )
        + len(
            remaining_review
        )
    )

    if (
        original_total
        != final_total
    ):

        raise RuntimeError(
            "Resolution accounting mismatch: "
            f"{original_total} != {final_total}"
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

    accepted_columns = (
        list(
            accepted_existing[
                0
            ].keys()
        )
        if accepted_existing
        else []
    )

    companion_columns = list(
        {
            key: None
            for row in final_companions
            for key in row.keys()
        }.keys()
    )

    excluded_columns = list(
        {
            key: None
            for row in final_excluded
            for key in row.keys()
        }.keys()
    )

    resolved_columns = (
        list(
            resolved_rows[
                0
            ].keys()
        )
        if resolved_rows
        else []
    )

    write_csv(
        out
        / "accepted_timeseries_tables.csv",
        final_accepted,
        accepted_columns,
    )

    write_csv(
        out
        / "companion_metadata_tables.csv",
        final_companions,
        companion_columns,
    )

    write_csv(
        out
        / "excluded_non_timeseries_tables.csv",
        final_excluded,
        excluded_columns,
    )

    write_csv(
        out
        / "graphical_review_tables.csv",
        graphical_review,
        resolved_columns,
    )

    write_csv(
        out
        / "remaining_review_tables.csv",
        remaining_review,
        resolved_columns,
    )

    write_csv(
        out
        / "review_resolution_all.csv",
        resolved_rows,
        resolved_columns,
    )

    resolution_summary = []

    for (
        decision,
        status,
    ), count in sorted(
        Counter(
            (
                row[
                    "resolution_decision"
                ],
                row[
                    "resolution_status"
                ],
            )
            for row in resolved_rows
        ).items()
    ):

        resolution_summary.append({
            "resolution_decision":
                decision,

            "resolution_status":
                status,

            "table_count":
                count,
        })

    write_csv(
        out
        / "resolution_summary.csv",
        resolution_summary,
        [
            "resolution_decision",
            "resolution_status",
            "table_count",
        ],
    )

    # ========================================================
    # Metadata
    # ========================================================

    reports_with_accepted = {
        row[
            "report_id"
        ]
        for row
        in final_accepted
    }

    accepted_family_counts = Counter(
        row.get(
            "audited_family",
            ""
        )
        for row
        in final_accepted
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "PDF residual review resolution",

        "input_remaining_review_tables":
            len(
                review_input
            ),

        "resolved_companion_tables":
            len(
                resolved_companions
            ),

        "resolved_excluded_tables":
            len(
                resolved_excluded
            ),

        "graphical_review_tables":
            len(
                graphical_review
            ),

        "remaining_review_tables":
            len(
                remaining_review
            ),

        "resolution_decision_counts":
            dict(
                resolution_counts
            ),

        "resolution_status_counts":
            dict(
                status_counts
            ),

        "final_accepted_timeseries_tables":
            len(
                final_accepted
            ),

        "final_companion_metadata_tables":
            len(
                final_companions
            ),

        "final_excluded_non_timeseries_tables":
            len(
                final_excluded
            ),

        "reports_with_accepted_timeseries":
            len(
                reports_with_accepted
            ),

        "accepted_family_counts":
            dict(
                accepted_family_counts
            ),

        "input_accounting_total":
            original_total,

        "output_accounting_total":
            final_total,

        "all_tables_accounted_for":
            (
                original_total
                == final_total
            ),

        "scope":
            (
                "Targeted resolution of the residual Group 4 PDF "
                "review population. Repeated sampled time-series "
                "accepted in the first PDF audit are unchanged. "
                "Scalar event/pre-crash/time-series context is routed "
                "to companion metadata. Single temporal snapshots and "
                "static documentation are excluded from Group 4 "
                "sampled time-series. Garbled PDF graph/plot structures "
                "are preserved explicitly as graphical review evidence "
                "and are not force-reconstructed from unreliable table "
                "text. No semantic normalization, unit conversion, "
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
        "GROUP 4 PDF REVIEW RESOLUTION COMPLETE."
    )


if __name__ == "__main__":
    main()