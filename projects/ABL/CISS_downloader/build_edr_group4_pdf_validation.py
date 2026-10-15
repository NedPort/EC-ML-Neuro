"""
Validate Group 4 PDF structural time-series extraction.

Input
-----
data/processed/edr/group4_pdf_structured_v1/

Required files
--------------
timeseries_registry.csv
timeseries_signal_registry.csv
timeseries_samples_wide.csv
timeseries_values_long.csv
timeseries_companion_metadata.csv
graphical_review_tables.csv
timeseries_audit.csv
extraction_failures.csv

Output
------
data/processed/edr/group4_pdf_validation_v1/

validation_report.csv
series_review_flags.csv
duplicate_signal_label_groups.csv
axis_review.csv
continuation_review.csv
metadata.json

Purpose
-------
Perform a dedicated validation pass over the Group 4 PDF-only structured
time-series package before freezing it.

The validator checks:

- expected structured-series count
- extraction failures
- unique series/signal/sample IDs
- orphan references
- per-series sample/signal/value count consistency
- blank/fallback-like signal labels
- axis-like signal labels
- duplicate signal labels within a series
- all-values-unavailable series
- blank/non-numeric/repeated axes
- repeated-transposed-block consistency
- continuation-group consistency
- preservation of companion metadata and graphical review evidence

This stage does not modify the structured extraction.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
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
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


# ============================================================
# Helpers
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


def truthy(value):
    return norm(value).casefold() in {
        "true",
        "1",
        "yes",
        "y",
    }


def int_or_zero(value):
    try:
        return int(float(norm(value)))
    except (ValueError, TypeError):
        return 0


def numeric_or_none(value):
    text = norm(value)

    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        return None


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


def is_fallback_like_label(value):
    text = norm(value)

    if not text:
        return False

    return bool(
        re.fullmatch(
            r"(?:"
            r"source[_ ]column[_ ]\d+|"
            r"column[_ ]\d+|"
            r"signal[_ ]\d+|"
            r"value[_ ]\d+"
            r")",
            text,
            re.I,
        )
    )


def is_axis_like_signal_label(value):
    text = norm(value)

    return bool(
        re.fullmatch(
            r"(?:"
            r"time|times"
            r")\s*(?:\([^)]*\))?",
            text,
            re.I,
        )
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--structured-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_structured_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_validation_v1"
        ),
    )

    args = parser.parse_args()

    src = args.structured_directory
    out = args.output_directory

    required = {
        "registry":
            src / "timeseries_registry.csv",

        "signals":
            src / "timeseries_signal_registry.csv",

        "samples":
            src / "timeseries_samples_wide.csv",

        "values":
            src / "timeseries_values_long.csv",

        "companions":
            src / "timeseries_companion_metadata.csv",

        "graphical":
            src / "graphical_review_tables.csv",

        "audit":
            src / "timeseries_audit.csv",

        "failures":
            src / "extraction_failures.csv",
    }

    for name, path in required.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Missing required {name}: {path}"
            )

    registry = read_csv(
        required["registry"]
    )

    signals = read_csv(
        required["signals"]
    )

    samples = read_csv(
        required["samples"]
    )

    values = read_csv(
        required["values"]
    )

    companions = read_csv(
        required["companions"]
    )

    graphical = read_csv(
        required["graphical"]
    )

    audit = read_csv(
        required["audit"]
    )

    failures = read_csv(
        required["failures"]
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    validation = []

    def add_check(
        check,
        condition,
        observed,
        expected,
        severity="hard",
        note="",
    ):
        validation.append({
            "check":
                check,

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

            "note":
                note,
        })

    # ========================================================
    # Basic package counts
    # ========================================================

    add_check(
        "structured_series_count",
        len(registry) == 861,
        len(registry),
        861,
        "hard",
    )

    add_check(
        "extraction_failure_count",
        len(failures) == 0,
        len(failures),
        0,
        "hard",
    )

    add_check(
        "companion_metadata_count",
        len(companions) == 764,
        len(companions),
        764,
        "warning",
    )

    add_check(
        "graphical_review_count",
        len(graphical) == 37,
        len(graphical),
        37,
        "warning",
        (
            "Graphical review evidence should be preserved, "
            "not treated as extraction failure."
        ),
    )

    add_check(
        "audit_success_rows",
        len(audit) == len(registry),
        len(audit),
        len(registry),
        "hard",
    )

    # ========================================================
    # ID uniqueness
    # ========================================================

    series_ids = [
        row["series_id"]
        for row in registry
    ]

    signal_ids = [
        row["signal_id"]
        for row in signals
    ]

    sample_ids = [
        row["sample_id"]
        for row in samples
    ]

    duplicate_series_ids = [
        key
        for key, count
        in Counter(series_ids).items()
        if count > 1
    ]

    duplicate_signal_ids = [
        key
        for key, count
        in Counter(signal_ids).items()
        if count > 1
    ]

    duplicate_sample_ids = [
        key
        for key, count
        in Counter(sample_ids).items()
        if count > 1
    ]

    add_check(
        "series_ids_unique",
        not duplicate_series_ids,
        len(duplicate_series_ids),
        0,
        "hard",
    )

    add_check(
        "signal_ids_unique",
        not duplicate_signal_ids,
        len(duplicate_signal_ids),
        0,
        "hard",
    )

    add_check(
        "sample_ids_unique",
        not duplicate_sample_ids,
        len(duplicate_sample_ids),
        0,
        "hard",
    )

    # ========================================================
    # Referential integrity
    # ========================================================

    known_series = set(series_ids)
    known_signals = set(signal_ids)
    known_samples = set(sample_ids)

    orphan_signals = [
        row
        for row in signals
        if row["series_id"]
        not in known_series
    ]

    orphan_samples = [
        row
        for row in samples
        if row["series_id"]
        not in known_series
    ]

    orphan_value_series = [
        row
        for row in values
        if row["series_id"]
        not in known_series
    ]

    orphan_value_signals = [
        row
        for row in values
        if row["signal_id"]
        not in known_signals
    ]

    orphan_value_samples = [
        row
        for row in values
        if row["sample_id"]
        not in known_samples
    ]

    add_check(
        "orphan_signal_series_refs",
        len(orphan_signals) == 0,
        len(orphan_signals),
        0,
        "hard",
    )

    add_check(
        "orphan_sample_series_refs",
        len(orphan_samples) == 0,
        len(orphan_samples),
        0,
        "hard",
    )

    add_check(
        "orphan_value_series_refs",
        len(orphan_value_series) == 0,
        len(orphan_value_series),
        0,
        "hard",
    )

    add_check(
        "orphan_value_signal_refs",
        len(orphan_value_signals) == 0,
        len(orphan_value_signals),
        0,
        "hard",
    )

    add_check(
        "orphan_value_sample_refs",
        len(orphan_value_samples) == 0,
        len(orphan_value_samples),
        0,
        "hard",
    )

    # ========================================================
    # Per-series count consistency
    # ========================================================

    signals_by_series = defaultdict(
        list
    )

    samples_by_series = defaultdict(
        list
    )

    values_by_series = defaultdict(
        list
    )

    for row in signals:
        signals_by_series[
            row["series_id"]
        ].append(row)

    for row in samples:
        samples_by_series[
            row["series_id"]
        ].append(row)

    for row in values:
        values_by_series[
            row["series_id"]
        ].append(row)

    mismatch_series = []

    for row in registry:
        series_id = row["series_id"]

        declared_signal_count = int_or_zero(
            row["signal_count"]
        )

        declared_sample_count = int_or_zero(
            row["sample_count"]
        )

        actual_signal_count = len(
            signals_by_series[
                series_id
            ]
        )

        actual_sample_count = len(
            samples_by_series[
                series_id
            ]
        )

        actual_value_count = len(
            values_by_series[
                series_id
            ]
        )

        expected_value_count = (
            actual_signal_count
            * actual_sample_count
        )

        if (
            declared_signal_count
            != actual_signal_count
            or declared_sample_count
            != actual_sample_count
            or actual_value_count
            != expected_value_count
        ):
            mismatch_series.append({
                "series_id":
                    series_id,

                "declared_signal_count":
                    declared_signal_count,

                "actual_signal_count":
                    actual_signal_count,

                "declared_sample_count":
                    declared_sample_count,

                "actual_sample_count":
                    actual_sample_count,

                "actual_value_count":
                    actual_value_count,

                "expected_value_count":
                    expected_value_count,
            })

    add_check(
        "series_sample_signal_value_consistency",
        len(mismatch_series) == 0,
        len(mismatch_series),
        0,
        "hard",
    )

    # ========================================================
    # Signal label review
    # ========================================================

    blank_signal_labels = [
        row
        for row in signals
        if not norm(
            row["signal_label_raw"]
        )
    ]

    fallback_signal_labels = [
        row
        for row in signals
        if is_fallback_like_label(
            row["signal_label_raw"]
        )
    ]

    axis_like_signal_labels = [
        row
        for row in signals
        if is_axis_like_signal_label(
            row["signal_label_raw"]
        )
    ]

    add_check(
        "blank_signal_label_count",
        len(blank_signal_labels) == 0,
        len(blank_signal_labels),
        0,
        "hard",
    )

    add_check(
        "fallback_signal_label_count",
        len(fallback_signal_labels) == 0,
        len(fallback_signal_labels),
        0,
        "warning",
    )

    add_check(
        "axis_like_signal_label_count",
        len(axis_like_signal_labels) == 0,
        len(axis_like_signal_labels),
        0,
        "hard",
    )

    # ========================================================
    # Duplicate labels within series
    # ========================================================

    duplicate_signal_label_groups = []

    for series_id, series_signals in (
        signals_by_series.items()
    ):
        label_counts = Counter(
            norm_key(
                row[
                    "signal_label_raw"
                ]
            )
            for row in series_signals
            if norm(
                row[
                    "signal_label_raw"
                ]
            )
        )

        for label_key, count in (
            label_counts.items()
        ):
            if count > 1:
                examples = [
                    row[
                        "signal_label_raw"
                    ]
                    for row in series_signals
                    if norm_key(
                        row[
                            "signal_label_raw"
                        ]
                    )
                    == label_key
                ]

                duplicate_signal_label_groups.append({
                    "series_id":
                        series_id,

                    "normalized_signal_label":
                        label_key,

                    "duplicate_count":
                        count,

                    "raw_labels_json":
                        json.dumps(
                            examples,
                            ensure_ascii=False,
                        ),
                })

    add_check(
        "duplicate_signal_label_groups",
        len(
            duplicate_signal_label_groups
        )
        == 0,
        len(
            duplicate_signal_label_groups
        ),
        0,
        "warning",
        (
            "Duplicates may be legitimate in rare PDF layouts, "
            "but require explicit evidence."
        ),
    )

    # ========================================================
    # Axis review
    # ========================================================

    axis_review = []

    series_registry_by_id = {
        row["series_id"]:
            row
        for row in registry
    }

    blank_axis_series = 0
    nonnumeric_axis_series = 0
    repeated_axis_series = 0
    nonmonotonic_axis_series = 0

    for series_id, series_samples in (
        samples_by_series.items()
    ):
        ordered = sorted(
            series_samples,
            key=lambda row:
                int_or_zero(
                    row[
                        "sample_index"
                    ]
                ),
        )

        raw_axis = [
            norm(
                row[
                    "axis_value_raw"
                ]
            )
            for row in ordered
        ]

        numeric_axis = [
            numeric_or_none(
                row[
                    "axis_value_numeric"
                ]
            )
            for row in ordered
        ]

        blank_count = sum(
            1
            for value in raw_axis
            if not value
        )

        numeric_count = sum(
            1
            for value in numeric_axis
            if value is not None
        )

        repeated_count = (
            len(raw_axis)
            - len(set(raw_axis))
        )

        nonmonotonic = False

        numeric_clean = [
            value
            for value in numeric_axis
            if value is not None
        ]

        if len(
            numeric_clean
        ) >= 2:
            nondecreasing = all(
                numeric_clean[index]
                <= numeric_clean[index + 1]
                for index in range(
                    len(numeric_clean) - 1
                )
            )

            nonincreasing = all(
                numeric_clean[index]
                >= numeric_clean[index + 1]
                for index in range(
                    len(numeric_clean) - 1
                )
            )

            nonmonotonic = not (
                nondecreasing
                or nonincreasing
            )

        if blank_count:
            blank_axis_series += 1

        if (
            raw_axis
            and numeric_count
            != len(raw_axis)
        ):
            nonnumeric_axis_series += 1

        if repeated_count:
            repeated_axis_series += 1

        if nonmonotonic:
            nonmonotonic_axis_series += 1

        if (
            blank_count
            or (
                raw_axis
                and numeric_count
                != len(raw_axis)
            )
            or repeated_count
            or nonmonotonic
        ):
            reg = (
                series_registry_by_id.get(
                    series_id,
                    {},
                )
            )

            axis_review.append({
                "series_id":
                    series_id,

                "report_id":
                    reg.get(
                        "report_id",
                        "",
                    ),

                "family":
                    reg.get(
                        "family",
                        "",
                    ),

                "table_orientation":
                    reg.get(
                        "table_orientation",
                        "",
                    ),

                "axis_type":
                    reg.get(
                        "axis_type",
                        "",
                    ),

                "axis_label_raw":
                    reg.get(
                        "axis_label_raw",
                        "",
                    ),

                "sample_count":
                    len(raw_axis),

                "blank_axis_value_count":
                    blank_count,

                "nonnumeric_axis_value_count":
                    (
                        len(raw_axis)
                        - numeric_count
                    ),

                "repeated_axis_value_count":
                    repeated_count,

                "nonmonotonic_axis":
                    nonmonotonic,

                "axis_values_preview_json":
                    json.dumps(
                        raw_axis[:40],
                        ensure_ascii=False,
                    ),
            })

    add_check(
        "blank_axis_series_count",
        blank_axis_series == 0,
        blank_axis_series,
        0,
        "hard",
    )

    add_check(
        "nonnumeric_axis_series_count",
        nonnumeric_axis_series == 0,
        nonnumeric_axis_series,
        0,
        "warning",
    )

    add_check(
        "repeated_axis_series_count",
        repeated_axis_series == 0,
        repeated_axis_series,
        0,
        "warning",
        (
            "Repeated axis values can be legitimate only if "
            "supported by source layout or multi-block structure."
        ),
    )

    add_check(
        "nonmonotonic_axis_series_count",
        nonmonotonic_axis_series == 0,
        nonmonotonic_axis_series,
        0,
        "warning",
        (
            "Non-monotonic axes should be reviewed before freeze."
        ),
    )

    # ========================================================
    # All-values-unavailable series
    # ========================================================

    all_unavailable_series = []

    for series_id, series_values in (
        values_by_series.items()
    ):
        if (
            series_values
            and all(
                is_missing_or_na(
                    row[
                        "value_raw"
                    ]
                )
                for row in series_values
            )
        ):
            reg = (
                series_registry_by_id.get(
                    series_id,
                    {},
                )
            )

            all_unavailable_series.append({
                "series_id":
                    series_id,

                "report_id":
                    reg.get(
                        "report_id",
                        "",
                    ),

                "family":
                    reg.get(
                        "family",
                        "",
                    ),

                "source_heading_hint":
                    reg.get(
                        "source_heading_hint",
                        "",
                    ),

                "sample_count":
                    reg.get(
                        "sample_count",
                        "",
                    ),

                "signal_count":
                    reg.get(
                        "signal_count",
                        "",
                    ),

                "review_flag":
                    "all_values_unavailable",
            })

    add_check(
        "all_values_unavailable_series_preserved",
        len(
            all_unavailable_series
        )
        == 18,
        len(
            all_unavailable_series
        ),
        18,
        "warning",
        (
            "These are structural series with source values such "
            "as N/A or Data Not Available; preserving them is valid."
        ),
    )

    # ========================================================
    # Repeated transposed blocks
    # ========================================================

    repeated_transposed = [
        row
        for row in registry
        if int_or_zero(
            row.get(
                "transposed_block_count",
                "",
            )
        ) > 1
    ]

    one_block_transposed = [
        row
        for row in registry
        if (
            row.get(
                "table_orientation",
                ""
            )
            == "samples_by_columns"
            and int_or_zero(
                row.get(
                    "transposed_block_count",
                    "",
                )
            )
            == 1
        )
    ]

    missing_block_count = [
        row
        for row in registry
        if (
            row.get(
                "table_orientation",
                ""
            )
            == "samples_by_columns"
            and int_or_zero(
                row.get(
                    "transposed_block_count",
                    "",
                )
            )
            < 1
        )
    ]

    add_check(
        "repeated_transposed_series_count",
        len(
            repeated_transposed
        )
        == 177,
        len(
            repeated_transposed
        ),
        177,
        "warning",
    )

    add_check(
        "transposed_series_have_block_count",
        len(
            missing_block_count
        )
        == 0,
        len(
            missing_block_count
        ),
        0,
        "hard",
    )

    add_check(
        "samples_by_columns_series_count",
        (
            len(
                repeated_transposed
            )
            + len(
                one_block_transposed
            )
            == 411
        ),
        (
            len(
                repeated_transposed
            )
            + len(
                one_block_transposed
            )
        ),
        411,
        "warning",
    )

    # ========================================================
    # Continuation groups
    # ========================================================

    continuation_groups = defaultdict(
        list
    )

    for row in registry:
        key = norm(
            row.get(
                "continuation_candidate_key",
                "",
            )
        )

        if key:
            continuation_groups[
                key
            ].append(row)

    continuation_review = []

    for key, rows in sorted(
        continuation_groups.items()
    ):
        totals = {
            int_or_zero(
                row.get(
                    "table_part_total",
                    "",
                )
            )
            for row in rows
            if int_or_zero(
                row.get(
                    "table_part_total",
                    "",
                )
            )
            > 0
        }

        indexes = sorted(
            {
                int_or_zero(
                    row.get(
                        "table_part_index",
                        "",
                    )
                )
                for row in rows
                if int_or_zero(
                    row.get(
                        "table_part_index",
                        "",
                    )
                )
                > 0
            }
        )

        expected_total = (
            next(iter(totals))
            if len(totals) == 1
            else 0
        )

        complete = bool(
            expected_total
            and indexes
            == list(
                range(
                    1,
                    expected_total + 1,
                )
            )
        )

        continuation_review.append({
            "continuation_candidate_key":
                key,

            "series_count":
                len(rows),

            "declared_totals_json":
                json.dumps(
                    sorted(totals)
                ),

            "part_indexes_json":
                json.dumps(indexes),

            "expected_total":
                expected_total,

            "all_parts_present":
                complete,

            "families_json":
                json.dumps(
                    sorted(
                        {
                            row.get(
                                "family",
                                "",
                            )
                            for row in rows
                        }
                    ),
                    ensure_ascii=False,
                ),

            "components_json":
                json.dumps(
                    sorted(
                        {
                            row.get(
                                "component",
                                "",
                            )
                            for row in rows
                        }
                    ),
                    ensure_ascii=False,
                ),
        })

    inconsistent_continuation_groups = [
        row
        for row in continuation_review
        if (
            len(
                json.loads(
                    row[
                        "declared_totals_json"
                    ]
                )
            )
            > 1
        )
    ]

    add_check(
        "continuation_candidate_series_count",
        sum(
            len(rows)
            for rows in continuation_groups.values()
        )
        == 84,
        sum(
            len(rows)
            for rows in continuation_groups.values()
        ),
        84,
        "warning",
    )

    add_check(
        "continuation_candidate_group_count",
        len(
            continuation_groups
        )
        == 47,
        len(
            continuation_groups
        ),
        47,
        "warning",
    )

    add_check(
        "continuation_group_declared_total_consistency",
        len(
            inconsistent_continuation_groups
        )
        == 0,
        len(
            inconsistent_continuation_groups
        ),
        0,
        "warning",
    )

    # ========================================================
    # Series review flags
    # ========================================================

    flagged_series = {}

    def flag_series(
        series_id,
        flag,
    ):
        if series_id not in flagged_series:
            flagged_series[
                series_id
            ] = set()

        flagged_series[
            series_id
        ].add(flag)

    for row in blank_signal_labels:
        flag_series(
            row["series_id"],
            "blank_signal_label",
        )

    for row in fallback_signal_labels:
        flag_series(
            row["series_id"],
            "fallback_signal_label",
        )

    for row in axis_like_signal_labels:
        flag_series(
            row["series_id"],
            "axis_like_signal_label",
        )

    for row in duplicate_signal_label_groups:
        flag_series(
            row["series_id"],
            "duplicate_signal_label",
        )

    for row in axis_review:
        flags = []

        if int_or_zero(
            row[
                "blank_axis_value_count"
            ]
        ):
            flags.append(
                "blank_axis_value"
            )

        if int_or_zero(
            row[
                "nonnumeric_axis_value_count"
            ]
        ):
            flags.append(
                "nonnumeric_axis_value"
            )

        if int_or_zero(
            row[
                "repeated_axis_value_count"
            ]
        ):
            flags.append(
                "repeated_axis_value"
            )

        if truthy(
            row[
                "nonmonotonic_axis"
            ]
        ):
            flags.append(
                "nonmonotonic_axis"
            )

        for flag in flags:
            flag_series(
                row["series_id"],
                flag,
            )

    for row in all_unavailable_series:
        flag_series(
            row["series_id"],
            "all_values_unavailable",
        )

    series_review_flags = []

    for series_id, flags in sorted(
        flagged_series.items()
    ):
        reg = (
            series_registry_by_id.get(
                series_id,
                {},
            )
        )

        series_review_flags.append({
            "series_id":
                series_id,

            "report_id":
                reg.get(
                    "report_id",
                    "",
                ),

            "family":
                reg.get(
                    "family",
                    "",
                ),

            "component":
                reg.get(
                    "component",
                    "",
                ),

            "table_orientation":
                reg.get(
                    "table_orientation",
                    "",
                ),

            "source_heading_hint":
                reg.get(
                    "source_heading_hint",
                    "",
                ),

            "review_flags_json":
                json.dumps(
                    sorted(flags),
                    ensure_ascii=False,
                ),
        })

    # ========================================================
    # Output CSVs
    # ========================================================

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
            "note",
        ],
    )

    write_csv(
        out
        / "series_review_flags.csv",
        series_review_flags,
        [
            "series_id",
            "report_id",
            "family",
            "component",
            "table_orientation",
            "source_heading_hint",
            "review_flags_json",
        ],
    )

    write_csv(
        out
        / "duplicate_signal_label_groups.csv",
        duplicate_signal_label_groups,
        [
            "series_id",
            "normalized_signal_label",
            "duplicate_count",
            "raw_labels_json",
        ],
    )

    write_csv(
        out
        / "axis_review.csv",
        axis_review,
        [
            "series_id",
            "report_id",
            "family",
            "table_orientation",
            "axis_type",
            "axis_label_raw",
            "sample_count",
            "blank_axis_value_count",
            "nonnumeric_axis_value_count",
            "repeated_axis_value_count",
            "nonmonotonic_axis",
            "axis_values_preview_json",
        ],
    )

    write_csv(
        out
        / "continuation_review.csv",
        continuation_review,
        [
            "continuation_candidate_key",
            "series_count",
            "declared_totals_json",
            "part_indexes_json",
            "expected_total",
            "all_parts_present",
            "families_json",
            "components_json",
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
            "PDF validation",

        "structured_series_count":
            len(registry),

        "signal_count":
            len(signals),

        "sample_count":
            len(samples),

        "long_value_count":
            len(values),

        "companion_metadata_count":
            len(companions),

        "graphical_review_count":
            len(graphical),

        "extraction_failure_count":
            len(failures),

        "blank_signal_label_count":
            len(blank_signal_labels),

        "fallback_signal_label_count":
            len(fallback_signal_labels),

        "axis_like_signal_label_count":
            len(axis_like_signal_labels),

        "duplicate_signal_label_group_count":
            len(
                duplicate_signal_label_groups
            ),

        "all_values_unavailable_series_count":
            len(
                all_unavailable_series
            ),

        "blank_axis_series_count":
            blank_axis_series,

        "nonnumeric_axis_series_count":
            nonnumeric_axis_series,

        "repeated_axis_series_count":
            repeated_axis_series,

        "nonmonotonic_axis_series_count":
            nonmonotonic_axis_series,

        "repeated_transposed_series_count":
            len(
                repeated_transposed
            ),

        "continuation_candidate_series_count":
            sum(
                len(rows)
                for rows in continuation_groups.values()
            ),

        "continuation_candidate_group_count":
            len(
                continuation_groups
            ),

        "series_with_review_flags":
            len(
                series_review_flags
            ),

        "validation_checks":
            len(validation),

        "validation_passes":
            sum(
                1
                for row in validation
                if row["status"]
                == "PASS"
            ),

        "validation_failures":
            sum(
                1
                for row in validation
                if row["status"]
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
                "Validation of the Group 4 PDF-only structured "
                "time-series package before freeze. Structural counts, "
                "referential integrity, signal labels, axes, repeated "
                "transposed blocks, continuation metadata, unavailable "
                "series, companion metadata, and preserved graphical "
                "review evidence are checked. No source data or "
                "structured extraction outputs are modified."
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
            "GROUP 4 PDF VALIDATION HAS HARD FAILURES."
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
        "GROUP 4 PDF VALIDATION COMPLETE."
    )


if __name__ == "__main__":
    main()
