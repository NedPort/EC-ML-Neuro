"""
Validate structured Group 4 CSV time-series extraction.

Input
-----
data/processed/edr/group4_csv_structured_v1/

Output
------
data/processed/edr/group4_csv_validation_v1/

    validation_report.csv
    series_quality_audit.csv
    signal_quality_audit.csv
    fallback_signal_labels.csv
    invalid_signal_labels.csv
    duplicate_signal_labels.csv
    suspicious_axis_series.csv
    all_values_unavailable_series.csv
    value_count_mismatches.csv
    pcm_validation.csv
    metadata.json

Important
---------
A time-series whose source explicitly contains only N/A/SNA/unavailable
measurement values is NOT considered an extraction failure.

Such series are preserved as:

    all_values_unavailable

because their structural information and time/index axis remain valid.
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


def as_int(
    value,
    default=0,
):
    try:
        return int(
            float(
                norm(value)
            )
        )

    except (
        ValueError,
        TypeError,
    ):
        return default


def boolish(value):
    return (
        norm(value).casefold()
        in {
            "true",
            "1",
            "yes",
        }
    )


def is_blank_or_na(value):
    return (
        norm(value).casefold()
        in {
            "",
            "n/a",
            "na",
            "not available",
            "not applicable",
            "unknown",
            "not recorded",
            "sna",
        }
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
            "group4_csv_structured_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_validation_v1"
        ),
    )

    args = parser.parse_args()

    src = args.structured_directory

    required = {
        "registry":
            src
            / "timeseries_registry.csv",

        "signals":
            src
            / "timeseries_signal_registry.csv",

        "samples":
            src
            / "timeseries_samples_wide.csv",

        "values":
            src
            / "timeseries_values_long.csv",

        "companions":
            src
            / "timeseries_companion_metadata.csv",

        "failures":
            src
            / "extraction_failures.csv",
    }

    for name, path in required.items():

        if not path.exists():
            raise FileNotFoundError(
                f"Missing required input "
                f"{name}: {path}"
            )

    registry = read_csv(
        required[
            "registry"
        ]
    )

    signals = read_csv(
        required[
            "signals"
        ]
    )

    samples = read_csv(
        required[
            "samples"
        ]
    )

    values = read_csv(
        required[
            "values"
        ]
    )

    companions = read_csv(
        required[
            "companions"
        ]
    )

    failures = read_csv(
        required[
            "failures"
        ]
    )

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Indexes
    # ========================================================

    registry_by_series = {
        row[
            "series_id"
        ]:
            row
        for row in registry
    }

    signals_by_series = defaultdict(
        list
    )

    for row in signals:
        signals_by_series[
            row[
                "series_id"
            ]
        ].append(
            row
        )

    samples_by_series = defaultdict(
        list
    )

    for row in samples:
        samples_by_series[
            row[
                "series_id"
            ]
        ].append(
            row
        )

    values_by_series = defaultdict(
        list
    )

    values_by_signal = defaultdict(
        list
    )

    for row in values:

        values_by_series[
            row[
                "series_id"
            ]
        ].append(
            row
        )

        values_by_signal[
            row[
                "signal_id"
            ]
        ].append(
            row
        )

    # ========================================================
    # Validation report
    # ========================================================

    validation = []

    def check(
        name,
        condition,
        observed,
        expected,
        severity="hard",
        note="",
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

            "note":
                note,
        })

    check(
        "structured_series_count",
        len(
            registry
        )
        == 8265,
        len(
            registry
        ),
        8265,
        severity="warning",
        note=(
            "Expected count from finalized CSV candidate audit."
        ),
    )

    check(
        "extraction_failure_count",
        len(
            failures
        )
        == 0,
        len(
            failures
        ),
        0,
    )

    check(
        "series_ids_unique",
        len(
            {
                row[
                    "series_id"
                ]
                for row in registry
            }
        )
        == len(
            registry
        ),
        len(
            {
                row[
                    "series_id"
                ]
                for row in registry
            }
        ),
        len(
            registry
        ),
    )

    check(
        "signal_ids_unique",
        len(
            {
                row[
                    "signal_id"
                ]
                for row in signals
            }
        )
        == len(
            signals
        ),
        len(
            {
                row[
                    "signal_id"
                ]
                for row in signals
            }
        ),
        len(
            signals
        ),
    )

    check(
        "sample_ids_unique",
        len(
            {
                row[
                    "sample_id"
                ]
                for row in samples
            }
        )
        == len(
            samples
        ),
        len(
            {
                row[
                    "sample_id"
                ]
                for row in samples
            }
        ),
        len(
            samples
        ),
    )

    # ========================================================
    # Signal labels
    # ========================================================

    fallback_pattern = re.compile(
        r"^source_(?:column|row)_\d+$",
        re.I,
    )

    fallback_signal_labels = [
        row
        for row in signals
        if fallback_pattern.match(
            norm(
                row.get(
                    "signal_label_raw",
                    "",
                )
            )
        )
    ]

    invalid_signal_labels = [
        row
        for row in signals
        if norm(
            row.get(
                "signal_label_raw",
                "",
            )
        ).casefold()
        in {
            "invalid",
            "invalid data",
            "invalid value",
        }
    ]

    blank_signal_labels = [
        row
        for row in signals
        if not norm(
            row.get(
                "signal_label_raw",
                "",
            )
        )
    ]

    check(
        "blank_signal_labels",
        len(
            blank_signal_labels
        )
        == 0,
        len(
            blank_signal_labels
        ),
        0,
    )

    # ========================================================
    # Duplicate labels
    # ========================================================

    duplicate_signal_labels = []

    for series_id, rows in (
        signals_by_series.items()
    ):

        grouped = defaultdict(
            list
        )

        for row in rows:

            label_key = norm_key(
                row.get(
                    "signal_label_raw",
                    "",
                )
            )

            if not label_key:
                continue

            grouped[
                label_key
            ].append(
                row
            )

        for label_key, dup_rows in (
            grouped.items()
        ):

            if len(
                dup_rows
            ) <= 1:
                continue

            source = (
                registry_by_series.get(
                    series_id,
                    {},
                )
            )

            duplicate_signal_labels.append({
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

                "source_heading":
                    source.get(
                        "source_heading",
                        "",
                    ),

                "family":
                    source.get(
                        "family",
                        "",
                    ),

                "component":
                    source.get(
                        "component",
                        "",
                    ),

                "duplicate_label_key":
                    label_key,

                "duplicate_count":
                    len(
                        dup_rows
                    ),

                "signal_ids_json":
                    json.dumps(
                        [
                            row[
                                "signal_id"
                            ]
                            for row
                            in dup_rows
                        ]
                    ),

                "raw_labels_json":
                    json.dumps(
                        [
                            row[
                                "signal_label_raw"
                            ]
                            for row
                            in dup_rows
                        ],
                        ensure_ascii=False,
                    ),
            })

    # ========================================================
    # Series-level structural validation
    # ========================================================

    series_quality_audit = []
    value_count_mismatches = []
    all_values_unavailable_series = []
    suspicious_axis_series = []

    for row in registry:

        series_id = row[
            "series_id"
        ]

        series_signals = (
            signals_by_series.get(
                series_id,
                [],
            )
        )

        series_samples = (
            samples_by_series.get(
                series_id,
                [],
            )
        )

        series_values = (
            values_by_series.get(
                series_id,
                [],
            )
        )

        declared_signal_count = as_int(
            row.get(
                "signal_count",
                0,
            )
        )

        declared_sample_count = as_int(
            row.get(
                "sample_count",
                0,
            )
        )

        actual_signal_count = len(
            series_signals
        )

        actual_sample_count = len(
            series_samples
        )

        actual_value_count = len(
            series_values
        )

        expected_dense_count = (
            actual_signal_count
            * actual_sample_count
        )

        dense_match = (
            actual_value_count
            == expected_dense_count
        )

        registry_signal_match = (
            declared_signal_count
            == actual_signal_count
        )

        registry_sample_match = (
            declared_sample_count
            == actual_sample_count
        )

        # ----------------------------------------------------
        # Measurement availability
        # ----------------------------------------------------

        available_values = sum(
            1
            for value_row
            in series_values
            if not is_blank_or_na(
                value_row.get(
                    "value_raw",
                    "",
                )
            )
        )

        unavailable_values = (
            actual_value_count
            - available_values
        )

        if actual_value_count:

            available_fraction = (
                available_values
                / actual_value_count
            )

        else:
            available_fraction = 0.0

        if (
            actual_value_count > 0
            and available_values == 0
        ):

            all_values_unavailable_series.append({
                **{
                    key:
                        row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "series_id":
                    series_id,

                "source_heading":
                    row.get(
                        "source_heading",
                        "",
                    ),

                "family":
                    row.get(
                        "family",
                        "",
                    ),

                "component":
                    row.get(
                        "component",
                        "",
                    ),

                "axis_type":
                    row.get(
                        "axis_type",
                        "",
                    ),

                "sample_count":
                    actual_sample_count,

                "signal_count":
                    actual_signal_count,

                "value_count":
                    actual_value_count,

                "available_value_count":
                    0,

                "processing_status":
                    "all_values_unavailable",
            })

        # ----------------------------------------------------
        # Axis validation
        # ----------------------------------------------------

        blank_axis_values = sum(
            1
            for sample
            in series_samples
            if not norm(
                sample.get(
                    "axis_value_raw",
                    "",
                )
            )
        )

        axis_values = [
            norm(
                sample.get(
                    "axis_value_raw",
                    "",
                )
            )
            for sample
            in series_samples
            if norm(
                sample.get(
                    "axis_value_raw",
                    "",
                )
            )
        ]

        repeated_axis_values = (
            len(
                axis_values
            )
            - len(
                set(
                    axis_values
                )
            )
        )

        if (
            blank_axis_values > 0
            or repeated_axis_values > 0
        ):

            issue_parts = []

            if blank_axis_values:
                issue_parts.append(
                    f"{blank_axis_values} blank axis values"
                )

            if repeated_axis_values:
                issue_parts.append(
                    f"{repeated_axis_values} repeated axis values"
                )

            suspicious_axis_series.append({
                **{
                    key:
                        row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "series_id":
                    series_id,

                "source_heading":
                    row.get(
                        "source_heading",
                        "",
                    ),

                "family":
                    row.get(
                        "family",
                        "",
                    ),

                "table_orientation":
                    row.get(
                        "table_orientation",
                        "",
                    ),

                "axis_type":
                    row.get(
                        "axis_type",
                        "",
                    ),

                "sample_count":
                    actual_sample_count,

                "blank_axis_values":
                    blank_axis_values,

                "repeated_axis_values":
                    repeated_axis_values,

                "issue":
                    "; ".join(
                        issue_parts
                    ),
            })

        # ----------------------------------------------------
        # Count consistency
        # ----------------------------------------------------

        if not (
            registry_signal_match
            and registry_sample_match
            and dense_match
        ):

            value_count_mismatches.append({
                **{
                    key:
                        row.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "series_id":
                    series_id,

                "source_heading":
                    row.get(
                        "source_heading",
                        "",
                    ),

                "declared_signal_count":
                    declared_signal_count,

                "actual_signal_count":
                    actual_signal_count,

                "declared_sample_count":
                    declared_sample_count,

                "actual_sample_count":
                    actual_sample_count,

                "expected_dense_value_count":
                    expected_dense_count,

                "actual_value_count":
                    actual_value_count,

                "registry_signal_match":
                    registry_signal_match,

                "registry_sample_match":
                    registry_sample_match,

                "dense_value_count_match":
                    dense_match,
            })

        series_quality_audit.append({
            **{
                key:
                    row.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                series_id,

            "source_heading":
                row.get(
                    "source_heading",
                    "",
                ),

            "family":
                row.get(
                    "family",
                    "",
                ),

            "component":
                row.get(
                    "component",
                    "",
                ),

            "audited_orientation":
                row.get(
                    "audited_orientation",
                    "",
                ),

            "table_orientation":
                row.get(
                    "table_orientation",
                    "",
                ),

            "pid_tail_trimmed":
                row.get(
                    "pid_tail_trimmed",
                    "",
                ),

            "axis_type":
                row.get(
                    "axis_type",
                    "",
                ),

            "declared_sample_count":
                declared_sample_count,

            "actual_sample_count":
                actual_sample_count,

            "declared_signal_count":
                declared_signal_count,

            "actual_signal_count":
                actual_signal_count,

            "actual_value_count":
                actual_value_count,

            "expected_dense_value_count":
                expected_dense_count,

            "available_value_count":
                available_values,

            "unavailable_value_count":
                unavailable_values,

            "available_value_fraction":
                round(
                    available_fraction,
                    6,
                ),

            "all_values_unavailable":
                (
                    actual_value_count > 0
                    and available_values == 0
                ),

            "blank_axis_value_count":
                blank_axis_values,

            "repeated_axis_value_count":
                repeated_axis_values,

            "registry_sample_count_match":
                registry_sample_match,

            "registry_signal_count_match":
                registry_signal_match,

            "dense_value_count_match":
                dense_match,
        })

    # ========================================================
    # Count consistency checks
    # ========================================================

    sample_count_mismatch_count = sum(
        1
        for row
        in value_count_mismatches
        if not boolish(
            row[
                "registry_sample_match"
            ]
        )
    )

    signal_count_mismatch_count = sum(
        1
        for row
        in value_count_mismatches
        if not boolish(
            row[
                "registry_signal_match"
            ]
        )
    )

    dense_count_mismatch_count = sum(
        1
        for row
        in value_count_mismatches
        if not boolish(
            row[
                "dense_value_count_match"
            ]
        )
    )

    check(
        "series_registry_sample_counts_match",
        sample_count_mismatch_count
        == 0,
        sample_count_mismatch_count,
        0,
    )

    check(
        "series_registry_signal_counts_match",
        signal_count_mismatch_count
        == 0,
        signal_count_mismatch_count,
        0,
    )

    check(
        "dense_value_counts_match_samples_x_signals",
        dense_count_mismatch_count
        == 0,
        dense_count_mismatch_count,
        0,
    )

    # --------------------------------------------------------
    # All-N/A/SNA series are explicit valid source outcomes.
    # --------------------------------------------------------

    check(
        "all_values_unavailable_series",
        True,
        len(
            all_values_unavailable_series
        ),
        "review_only",
        severity="review",
        note=(
            "Series containing only N/A/SNA/unavailable source "
            "measurements remain valid structural time-series and "
            "are preserved explicitly."
        ),
    )

    # ========================================================
    # Orphan references
    # ========================================================

    registry_ids = set(
        registry_by_series
    )

    orphan_signal_series = [
        row
        for row in signals
        if row[
            "series_id"
        ]
        not in registry_ids
    ]

    orphan_sample_series = [
        row
        for row in samples
        if row[
            "series_id"
        ]
        not in registry_ids
    ]

    orphan_value_series = [
        row
        for row in values
        if row[
            "series_id"
        ]
        not in registry_ids
    ]

    known_signal_ids = {
        row[
            "signal_id"
        ]
        for row in signals
    }

    known_sample_ids = {
        row[
            "sample_id"
        ]
        for row in samples
    }

    orphan_value_signals = [
        row
        for row in values
        if row[
            "signal_id"
        ]
        not in known_signal_ids
    ]

    orphan_value_samples = [
        row
        for row in values
        if row[
            "sample_id"
        ]
        not in known_sample_ids
    ]

    check(
        "orphan_signal_series_refs",
        len(
            orphan_signal_series
        )
        == 0,
        len(
            orphan_signal_series
        ),
        0,
    )

    check(
        "orphan_sample_series_refs",
        len(
            orphan_sample_series
        )
        == 0,
        len(
            orphan_sample_series
        ),
        0,
    )

    check(
        "orphan_value_series_refs",
        len(
            orphan_value_series
        )
        == 0,
        len(
            orphan_value_series
        ),
        0,
    )

    check(
        "orphan_value_signal_refs",
        len(
            orphan_value_signals
        )
        == 0,
        len(
            orphan_value_signals
        ),
        0,
    )

    check(
        "orphan_value_sample_refs",
        len(
            orphan_value_samples
        )
        == 0,
        len(
            orphan_value_samples
        ),
        0,
    )

    # ========================================================
    # PCM
    # ========================================================

    pcm_rows = [
        row
        for row in registry
        if row.get(
            "family",
            ""
        )
        == "pcm_edr"
    ]

    pcm_validation = []

    for row in pcm_rows:

        pcm_validation.append({
            **{
                key:
                    row.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                row[
                    "series_id"
                ],

            "source_heading":
                row.get(
                    "source_heading",
                    "",
                ),

            "axis_type":
                row.get(
                    "axis_type",
                    "",
                ),

            "sample_count":
                row.get(
                    "sample_count",
                    "",
                ),

            "signal_count":
                row.get(
                    "signal_count",
                    "",
                ),

            "relative_time_available":
                (
                    row.get(
                        "axis_type",
                        ""
                    )
                    == "relative_time_available"
                ),

            "buffer_order_only":
                (
                    row.get(
                        "axis_type",
                        ""
                    )
                    == "buffer_order_only"
                ),

            "status":
                "reviewed_pcm_series",
        })

    pcm_axis_counts = Counter(
        row[
            "axis_type"
        ]
        for row in pcm_rows
    )

    check(
        "pcm_series_count",
        len(
            pcm_rows
        )
        == 10,
        len(
            pcm_rows
        ),
        10,
        severity="warning",
    )

    check(
        "pcm_relative_time_available_count",
        pcm_axis_counts.get(
            "relative_time_available",
            0,
        )
        == 5,
        pcm_axis_counts.get(
            "relative_time_available",
            0,
        ),
        5,
        severity="warning",
    )

    check(
        "pcm_buffer_order_only_count",
        pcm_axis_counts.get(
            "buffer_order_only",
            0,
        )
        == 5,
        pcm_axis_counts.get(
            "buffer_order_only",
            0,
        ),
        5,
        severity="warning",
    )

    # ========================================================
    # Signal-level quality
    # ========================================================

    signal_quality_audit = []

    for row in signals:

        label = norm(
            row.get(
                "signal_label_raw",
                "",
            )
        )

        fallback = bool(
            fallback_pattern.match(
                label
            )
        )

        invalid_label = (
            label.casefold()
            in {
                "invalid",
                "invalid data",
                "invalid value",
            }
        )

        signal_values = values_by_signal.get(
            row[
                "signal_id"
            ],
            [],
        )

        available_count = sum(
            1
            for value
            in signal_values
            if not is_blank_or_na(
                value.get(
                    "value_raw",
                    "",
                )
            )
        )

        signal_quality_audit.append({
            **{
                key:
                    row.get(
                        key,
                        ""
                    )
                for key in BASE
            },

            "series_id":
                row.get(
                    "series_id",
                    "",
                ),

            "signal_id":
                row.get(
                    "signal_id",
                    "",
                ),

            "signal_position":
                row.get(
                    "signal_position",
                    "",
                ),

            "signal_label_raw":
                label,

            "signal_unit_raw":
                row.get(
                    "signal_unit_raw",
                    "",
                ),

            "fallback_label":
                fallback,

            "invalid_label":
                invalid_label,

            "blank_label":
                not label,

            "sample_value_count":
                len(
                    signal_values
                ),

            "available_value_count":
                available_count,

            "all_values_unavailable":
                (
                    len(
                        signal_values
                    )
                    > 0
                    and available_count == 0
                ),

            "header_fragments_json":
                row.get(
                    "header_fragments_json",
                    "",
                ),
        })

    all_unavailable_signals = [
        row
        for row in signal_quality_audit
        if row[
            "all_values_unavailable"
        ]
    ]

    # ========================================================
    # Review-only checks
    # ========================================================

    check(
        "fallback_signal_labels",
        True,
        len(
            fallback_signal_labels
        ),
        "review_only",
        severity="review",
        note=(
            "Fallback signal labels are preserved for inspection."
        ),
    )

    check(
        "invalid_signal_labels",
        True,
        len(
            invalid_signal_labels
        ),
        "review_only",
        severity="review",
        note=(
            "Raw signal labels equal to Invalid are preserved "
            "for inspection; expected to decrease after PID-tail fix."
        ),
    )

    check(
        "duplicate_signal_label_groups",
        True,
        len(
            duplicate_signal_labels
        ),
        "review_only",
        severity="review",
    )

    check(
        "signals_with_all_values_unavailable",
        True,
        len(
            all_unavailable_signals
        ),
        "review_only",
        severity="review",
    )

    check(
        "suspicious_axis_series",
        True,
        len(
            suspicious_axis_series
        ),
        "review_only",
        severity="review",
    )

    # ========================================================
    # Write outputs
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
        / "series_quality_audit.csv",
        series_quality_audit,
        [
            *BASE,
            "series_id",
            "source_heading",
            "family",
            "component",
            "audited_orientation",
            "table_orientation",
            "pid_tail_trimmed",
            "axis_type",
            "declared_sample_count",
            "actual_sample_count",
            "declared_signal_count",
            "actual_signal_count",
            "actual_value_count",
            "expected_dense_value_count",
            "available_value_count",
            "unavailable_value_count",
            "available_value_fraction",
            "all_values_unavailable",
            "blank_axis_value_count",
            "repeated_axis_value_count",
            "registry_sample_count_match",
            "registry_signal_count_match",
            "dense_value_count_match",
        ],
    )

    write_csv(
        out
        / "signal_quality_audit.csv",
        signal_quality_audit,
        [
            *BASE,
            "series_id",
            "signal_id",
            "signal_position",
            "signal_label_raw",
            "signal_unit_raw",
            "fallback_label",
            "invalid_label",
            "blank_label",
            "sample_value_count",
            "available_value_count",
            "all_values_unavailable",
            "header_fragments_json",
        ],
    )

    signal_columns = (
        list(
            signals[0].keys()
        )
        if signals
        else []
    )

    write_csv(
        out
        / "fallback_signal_labels.csv",
        fallback_signal_labels,
        signal_columns,
    )

    write_csv(
        out
        / "invalid_signal_labels.csv",
        invalid_signal_labels,
        signal_columns,
    )

    write_csv(
        out
        / "duplicate_signal_labels.csv",
        duplicate_signal_labels,
        [
            *BASE,
            "series_id",
            "source_heading",
            "family",
            "component",
            "duplicate_label_key",
            "duplicate_count",
            "signal_ids_json",
            "raw_labels_json",
        ],
    )

    write_csv(
        out
        / "suspicious_axis_series.csv",
        suspicious_axis_series,
        [
            *BASE,
            "series_id",
            "source_heading",
            "family",
            "table_orientation",
            "axis_type",
            "sample_count",
            "blank_axis_values",
            "repeated_axis_values",
            "issue",
        ],
    )

    write_csv(
        out
        / "all_values_unavailable_series.csv",
        all_values_unavailable_series,
        [
            *BASE,
            "series_id",
            "source_heading",
            "family",
            "component",
            "axis_type",
            "sample_count",
            "signal_count",
            "value_count",
            "available_value_count",
            "processing_status",
        ],
    )

    write_csv(
        out
        / "value_count_mismatches.csv",
        value_count_mismatches,
        [
            *BASE,
            "series_id",
            "source_heading",
            "declared_signal_count",
            "actual_signal_count",
            "declared_sample_count",
            "actual_sample_count",
            "expected_dense_value_count",
            "actual_value_count",
            "registry_signal_match",
            "registry_sample_match",
            "dense_value_count_match",
        ],
    )

    write_csv(
        out
        / "pcm_validation.csv",
        pcm_validation,
        [
            *BASE,
            "series_id",
            "source_heading",
            "axis_type",
            "sample_count",
            "signal_count",
            "relative_time_available",
            "buffer_order_only",
            "status",
        ],
    )

    # ========================================================
    # Metadata
    # ========================================================

    fallback_heading_counts = Counter(
        registry_by_series[
            row[
                "series_id"
            ]
        ].get(
            "source_heading",
            "",
        )
        for row in fallback_signal_labels
        if row[
            "series_id"
        ]
        in registry_by_series
    )

    invalid_heading_counts = Counter(
        registry_by_series[
            row[
                "series_id"
            ]
        ].get(
            "source_heading",
            "",
        )
        for row in invalid_signal_labels
        if row[
            "series_id"
        ]
        in registry_by_series
    )

    validation_status_counts = Counter(
        row[
            "status"
        ]
        for row in validation
    )

    validation_failure_severity_counts = Counter(
        row[
            "severity"
        ]
        for row in validation
        if row[
            "status"
        ]
        == "FAIL"
    )

    pid_tail_trimmed_count = sum(
        1
        for row in registry
        if boolish(
            row.get(
                "pid_tail_trimmed",
                ""
            )
        )
    )

    orientation_override_count = sum(
        1
        for row in registry
        if boolish(
            row.get(
                "orientation_overridden",
                ""
            )
        )
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "CSV structural validation",

        "structured_series_count":
            len(
                registry
            ),

        "signal_count":
            len(
                signals
            ),

        "sample_count":
            len(
                samples
            ),

        "long_value_count":
            len(
                values
            ),

        "companion_metadata_count":
            len(
                companions
            ),

        "extraction_failure_count":
            len(
                failures
            ),

        "pid_tail_trimmed_series_count":
            pid_tail_trimmed_count,

        "orientation_override_series_count":
            orientation_override_count,

        "fallback_signal_label_count":
            len(
                fallback_signal_labels
            ),

        "invalid_signal_label_count":
            len(
                invalid_signal_labels
            ),

        "blank_signal_label_count":
            len(
                blank_signal_labels
            ),

        "duplicate_signal_label_group_count":
            len(
                duplicate_signal_labels
            ),

        "all_values_unavailable_signal_count":
            len(
                all_unavailable_signals
            ),

        "all_values_unavailable_series_count":
            len(
                all_values_unavailable_series
            ),

        "value_count_mismatch_series_count":
            len(
                value_count_mismatches
            ),

        "suspicious_axis_series_count":
            len(
                suspicious_axis_series
            ),

        "pcm_series_count":
            len(
                pcm_rows
            ),

        "pcm_axis_type_counts":
            dict(
                pcm_axis_counts
            ),

        "fallback_label_top_headings":
            fallback_heading_counts.most_common(
                30
            ),

        "invalid_label_top_headings":
            invalid_heading_counts.most_common(
                30
            ),

        "validation_check_count":
            len(
                validation
            ),

        "validation_status_counts":
            dict(
                validation_status_counts
            ),

        "validation_failure_severity_counts":
            dict(
                validation_failure_severity_counts
            ),

        "scope":
            (
                "Validation of Group 4 CSV structural extraction. "
                "All-N/A/SNA source series are treated as valid "
                "structural series with unavailable measurements, "
                "rather than extraction failures. Identifier integrity, "
                "count consistency, orphan references, signal labels, "
                "axes, PID-tail handling, and PCM structure are audited. "
                "No extracted data are modified."
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

    if hard_failures:

        print()
        print(
            "GROUP 4 CSV VALIDATION "
            "HAS HARD FAILURES."
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
        "GROUP 4 CSV VALIDATION COMPLETE."
    )


if __name__ == "__main__":
    main()