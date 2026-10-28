"""
Freeze validated Group 4 CSV time-series outputs.

Input
-----
data/processed/edr/group4_csv_structured_v1/
data/processed/edr/group4_csv_validation_v1/

Output
------
data/processed/edr/group4_csv_final_v1/

Purpose
-------
This script does NOT re-extract or reinterpret any data.

It validates the already completed Group 4 CSV structural extraction
and packages the stable outputs into a frozen release directory.

Freeze policy
-------------
The CSV side of Group 4 is considered frozen when:

- 8,265 structured time-series are present,
- extraction failures = 0,
- value-count mismatches = 0,
- blank signal labels = 0,
- all validation checks pass,
- PCM structure remains 5 relative-time + 5 buffer-order-only,
- residual review evidence is preserved explicitly.

Residual review evidence such as:
- fallback signal labels,
- duplicate signal labels,
- suspicious axes,
- all-values-unavailable series

does not prevent freezing when those cases are explicitly preserved
and do not represent hard structural validation failures.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil

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


def read_json(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
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


def copy_file(
    source: Path,
    destination: Path,
):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = destination.with_suffix(
        destination.suffix + ".part"
    )

    shutil.copyfile(
        source,
        tmp,
    )

    tmp.replace(
        destination
    )


def require_file(
    directory: Path,
    filename: str,
):
    path = (
        directory
        / filename
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing required file: {path}"
        )

    return path


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
        "--validation-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_validation_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_final_v1"
        ),
    )

    args = parser.parse_args()

    structured = args.structured_directory
    validation_dir = args.validation_directory
    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Required structured files
    # ========================================================

    structured_files = {
        "timeseries_registry.csv":
            require_file(
                structured,
                "timeseries_registry.csv",
            ),

        "timeseries_signal_registry.csv":
            require_file(
                structured,
                "timeseries_signal_registry.csv",
            ),

        "timeseries_samples_wide.csv":
            require_file(
                structured,
                "timeseries_samples_wide.csv",
            ),

        "timeseries_values_long.csv":
            require_file(
                structured,
                "timeseries_values_long.csv",
            ),

        "timeseries_companion_metadata.csv":
            require_file(
                structured,
                "timeseries_companion_metadata.csv",
            ),

        "timeseries_audit.csv":
            require_file(
                structured,
                "timeseries_audit.csv",
            ),

        "extraction_failures.csv":
            require_file(
                structured,
                "extraction_failures.csv",
            ),

        "structured_validation_report.csv":
            require_file(
                structured,
                "validation_report.csv",
            ),

        "structured_metadata.json":
            require_file(
                structured,
                "metadata.json",
            ),
    }

    # ========================================================
    # Required validation files
    # ========================================================

    validation_files = {
        "validation_report.csv":
            require_file(
                validation_dir,
                "validation_report.csv",
            ),

        "series_quality_audit.csv":
            require_file(
                validation_dir,
                "series_quality_audit.csv",
            ),

        "signal_quality_audit.csv":
            require_file(
                validation_dir,
                "signal_quality_audit.csv",
            ),

        "fallback_signal_labels.csv":
            require_file(
                validation_dir,
                "fallback_signal_labels.csv",
            ),

        "invalid_signal_labels.csv":
            require_file(
                validation_dir,
                "invalid_signal_labels.csv",
            ),

        "duplicate_signal_labels.csv":
            require_file(
                validation_dir,
                "duplicate_signal_labels.csv",
            ),

        "suspicious_axis_series.csv":
            require_file(
                validation_dir,
                "suspicious_axis_series.csv",
            ),

        "all_values_unavailable_series.csv":
            require_file(
                validation_dir,
                "all_values_unavailable_series.csv",
            ),

        "value_count_mismatches.csv":
            require_file(
                validation_dir,
                "value_count_mismatches.csv",
            ),

        "pcm_validation.csv":
            require_file(
                validation_dir,
                "pcm_validation.csv",
            ),

        "validation_metadata.json":
            require_file(
                validation_dir,
                "metadata.json",
            ),
    }

    # ========================================================
    # Read core inputs
    # ========================================================

    registry = read_csv(
        structured_files[
            "timeseries_registry.csv"
        ]
    )

    signals = read_csv(
        structured_files[
            "timeseries_signal_registry.csv"
        ]
    )

    samples = read_csv(
        structured_files[
            "timeseries_samples_wide.csv"
        ]
    )

    values = read_csv(
        structured_files[
            "timeseries_values_long.csv"
        ]
    )

    companions = read_csv(
        structured_files[
            "timeseries_companion_metadata.csv"
        ]
    )

    failures = read_csv(
        structured_files[
            "extraction_failures.csv"
        ]
    )

    validation_report = read_csv(
        validation_files[
            "validation_report.csv"
        ]
    )

    fallback_labels = read_csv(
        validation_files[
            "fallback_signal_labels.csv"
        ]
    )

    invalid_labels = read_csv(
        validation_files[
            "invalid_signal_labels.csv"
        ]
    )

    duplicate_labels = read_csv(
        validation_files[
            "duplicate_signal_labels.csv"
        ]
    )

    suspicious_axes = read_csv(
        validation_files[
            "suspicious_axis_series.csv"
        ]
    )

    unavailable_series = read_csv(
        validation_files[
            "all_values_unavailable_series.csv"
        ]
    )

    value_mismatches = read_csv(
        validation_files[
            "value_count_mismatches.csv"
        ]
    )

    pcm_validation = read_csv(
        validation_files[
            "pcm_validation.csv"
        ]
    )

    structured_metadata = read_json(
        structured_files[
            "structured_metadata.json"
        ]
    )

    validation_metadata = read_json(
        validation_files[
            "validation_metadata.json"
        ]
    )

    # ========================================================
    # Freeze validation
    # ========================================================

    checks = []

    def check(
        name,
        condition,
        observed,
        expected,
        severity="hard",
    ):
        checks.append({
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

    # --------------------------------------------------------
    # Core counts
    # --------------------------------------------------------

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
        "value_count_mismatch_count",
        len(
            value_mismatches
        )
        == 0,
        len(
            value_mismatches
        ),
        0,
    )

    check(
        "invalid_signal_label_count",
        len(
            invalid_labels
        )
        == 0,
        len(
            invalid_labels
        ),
        0,
    )

    # --------------------------------------------------------
    # Validation report
    # --------------------------------------------------------

    validation_failures = [
        row
        for row in validation_report
        if str(
            row.get(
                "status",
                "",
            )
        ).upper()
        == "FAIL"
    ]

    hard_validation_failures = [
        row
        for row in validation_failures
        if str(
            row.get(
                "severity",
                "",
            )
        ).lower()
        == "hard"
    ]

    check(
        "validation_report_failures",
        len(
            validation_failures
        )
        == 0,
        len(
            validation_failures
        ),
        0,
    )

    check(
        "hard_validation_failures",
        len(
            hard_validation_failures
        )
        == 0,
        len(
            hard_validation_failures
        ),
        0,
    )

    # --------------------------------------------------------
    # Identifier uniqueness
    # --------------------------------------------------------

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
        for row in signals
    ]

    sample_ids = [
        row[
            "sample_id"
        ]
        for row in samples
    ]

    check(
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

    check(
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

    check(
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

    # --------------------------------------------------------
    # PCM consistency
    # --------------------------------------------------------

    pcm_axis_counts = Counter(
        row.get(
            "axis_type",
            ""
        )
        for row in pcm_validation
    )

    check(
        "pcm_series_count",
        len(
            pcm_validation
        )
        == 10,
        len(
            pcm_validation
        ),
        10,
    )

    check(
        "pcm_relative_time_count",
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
    )

    # --------------------------------------------------------
    # Residual review evidence
    # --------------------------------------------------------

    check(
        "fallback_labels_preserved",
        True,
        len(
            fallback_labels
        ),
        "explicit_review_evidence",
        severity="review",
    )

    check(
        "duplicate_labels_preserved",
        True,
        len(
            duplicate_labels
        ),
        "explicit_review_evidence",
        severity="review",
    )

    check(
        "suspicious_axes_preserved",
        True,
        len(
            suspicious_axes
        ),
        "explicit_review_evidence",
        severity="review",
    )

    check(
        "all_values_unavailable_preserved",
        True,
        len(
            unavailable_series
        ),
        "explicit_review_evidence",
        severity="review",
    )

    # ========================================================
    # Decide freeze status
    # ========================================================

    hard_failures = [
        row
        for row in checks
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

        freeze_status = (
            "freeze_failed_validation"
        )

    else:

        freeze_status = (
            "frozen_validated_with_explicit_review_evidence"
        )

    # ========================================================
    # Copy final stable package
    # ========================================================

    for output_name, source_path in (
        structured_files.items()
    ):

        copy_file(
            source_path,
            out
            / output_name,
        )

    for output_name, source_path in (
        validation_files.items()
    ):

        copy_file(
            source_path,
            out
            / output_name,
        )

    # ========================================================
    # Freeze report
    # ========================================================

    write_csv(
        out
        / "freeze_validation_report.csv",
        checks,
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

    report_ids = {
        row.get(
            "report_id",
            ""
        )
        for row in registry
        if row.get(
            "report_id",
            ""
        )
    }

    family_counts = Counter(
        row.get(
            "family",
            ""
        )
        for row in registry
    )

    orientation_counts = Counter(
        row.get(
            "table_orientation",
            ""
        )
        for row in registry
    )

    axis_type_counts = Counter(
        row.get(
            "axis_type",
            ""
        )
        for row in registry
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "CSV freeze",

        "freeze_status":
            freeze_status,

        "structured_series_count":
            len(
                registry
            ),

        "reports_with_structured_timeseries":
            len(
                report_ids
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

        "family_counts":
            dict(
                family_counts
            ),

        "orientation_counts":
            dict(
                orientation_counts
            ),

        "axis_type_counts":
            dict(
                axis_type_counts
            ),

        "pid_tail_trimmed_series_count":
            structured_metadata.get(
                "pid_tail_trimmed_section_count",
                0,
            ),

        "orientation_override_count":
            structured_metadata.get(
                "orientation_override_count",
                0,
            ),

        "fallback_signal_label_count":
            len(
                fallback_labels
            ),

        "invalid_signal_label_count":
            len(
                invalid_labels
            ),

        "duplicate_signal_label_group_count":
            len(
                duplicate_labels
            ),

        "suspicious_axis_series_count":
            len(
                suspicious_axes
            ),

        "all_values_unavailable_series_count":
            len(
                unavailable_series
            ),

        "value_count_mismatch_series_count":
            len(
                value_mismatches
            ),

        "pcm_series_count":
            len(
                pcm_validation
            ),

        "pcm_axis_type_counts":
            dict(
                pcm_axis_counts
            ),

        "freeze_validation_checks":
            len(
                checks
            ),

        "freeze_validation_failures":
            sum(
                1
                for row in checks
                if row[
                    "status"
                ]
                == "FAIL"
            ),

        "hard_freeze_failures":
            len(
                hard_failures
            ),

        "source_structured_metadata":
            structured_metadata,

        "source_validation_metadata":
            validation_metadata,

        "scope":
            (
                "Frozen validated CSV portion of Group 4. "
                "The package contains structurally extracted time-series "
                "from reports with CSV sources. Raw values, source labels, "
                "units, axes, and provenance are preserved. PID/hex tails "
                "are excluded from Group 4 parsing. All-N/A/SNA time-series "
                "remain explicitly preserved as structurally valid series "
                "with unavailable measurements. Residual fallback labels, "
                "duplicate signal labels, and suspicious axes are retained "
                "as explicit review evidence. No semantic signal "
                "normalization, unit conversion, event identity inference, "
                "or PDF fallback is included in this freeze."
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
            "GROUP 4 CSV FREEZE FAILED."
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
        "GROUP 4 CSV FREEZE COMPLETE."
    )


if __name__ == "__main__":
    main()