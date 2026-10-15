"""
Freeze validated Group 4 PDF-only time-series outputs.

Inputs
------
data/processed/edr/group4_pdf_structured_v1/
data/processed/edr/group4_pdf_validation_v1/

Output
------
data/processed/edr/group4_pdf_final_v1/

The freeze copies the validated structural package and validation evidence
into an immutable final-version directory and writes freeze_metadata.json.

No extraction, normalization, merging, or source modification is performed.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


EXPECTED = {
    "structured_series_count": 861,
    "signal_count": 2491,
    "sample_count": 14211,
    "long_value_count": 30643,
    "companion_metadata_count": 764,
    "graphical_review_count": 37,
    "extraction_failure_count": 0,
    "blank_signal_label_count": 0,
    "fallback_signal_label_count": 0,
    "axis_like_signal_label_count": 0,
    "duplicate_signal_label_group_count": 0,
    "all_values_unavailable_series_count": 18,
    "blank_axis_series_count": 0,
    "nonnumeric_axis_series_count": 0,
    "repeated_axis_series_count": 0,
    "nonmonotonic_axis_series_count": 0,
    "repeated_transposed_series_count": 177,
    "continuation_candidate_series_count": 84,
    "continuation_candidate_group_count": 47,
    "series_with_review_flags": 18,
    "validation_checks": 29,
    "validation_passes": 29,
    "validation_failures": 0,
    "hard_validation_failures": 0,
    "warning_validation_failures": 0,
}


STRUCTURED_FILES = [
    "timeseries_registry.csv",
    "timeseries_signal_registry.csv",
    "timeseries_samples_wide.csv",
    "timeseries_values_long.csv",
    "timeseries_companion_metadata.csv",
    "graphical_review_tables.csv",
    "timeseries_audit.csv",
    "extraction_failures.csv",
    "validation_report.csv",
    "metadata.json",
]

VALIDATION_FILES = [
    "validation_report.csv",
    "series_review_flags.csv",
    "duplicate_signal_label_groups.csv",
    "axis_review.csv",
    "continuation_review.csv",
    "metadata.json",
]


def read_json(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def read_csv(path: Path):
    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(
            csv.DictReader(f)
        )


def copy_file(
    src: Path,
    dst: Path,
):
    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        src,
        dst,
    )


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
        "--validation-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_validation_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_final_v1"
        ),
    )

    args = parser.parse_args()

    structured = args.structured_directory
    validation = args.validation_directory
    out = args.output_directory

    # --------------------------------------------------------
    # Verify required files
    # --------------------------------------------------------

    for filename in STRUCTURED_FILES:
        path = structured / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Missing structured file: {path}"
            )

    for filename in VALIDATION_FILES:
        path = validation / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Missing validation file: {path}"
            )

    structured_metadata = read_json(
        structured / "metadata.json"
    )

    validation_metadata = read_json(
        validation / "metadata.json"
    )

    # --------------------------------------------------------
    # Freeze gates
    # --------------------------------------------------------

    checks = []

    def check(
        name,
        condition,
        observed,
        expected,
    ):
        checks.append({
            "check": name,
            "status":
                "PASS"
                if condition
                else "FAIL",
            "observed": observed,
            "expected": expected,
        })

    for key, expected in EXPECTED.items():

        observed = (
            validation_metadata.get(
                key,
                structured_metadata.get(
                    key,
                ),
            )
        )

        check(
            key,
            observed == expected,
            observed,
            expected,
        )

    # Explicit source-package accounting.
    registry = read_csv(
        structured / "timeseries_registry.csv"
    )

    signals = read_csv(
        structured
        / "timeseries_signal_registry.csv"
    )

    samples = read_csv(
        structured
        / "timeseries_samples_wide.csv"
    )

    values = read_csv(
        structured
        / "timeseries_values_long.csv"
    )

    companions = read_csv(
        structured
        / "timeseries_companion_metadata.csv"
    )

    graphical = read_csv(
        structured
        / "graphical_review_tables.csv"
    )

    failures = read_csv(
        structured
        / "extraction_failures.csv"
    )

    review_flags = read_csv(
        validation
        / "series_review_flags.csv"
    )

    check(
        "registry_row_count",
        len(registry)
        == EXPECTED[
            "structured_series_count"
        ],
        len(registry),
        EXPECTED[
            "structured_series_count"
        ],
    )

    check(
        "signal_row_count",
        len(signals)
        == EXPECTED[
            "signal_count"
        ],
        len(signals),
        EXPECTED[
            "signal_count"
        ],
    )

    check(
        "sample_row_count",
        len(samples)
        == EXPECTED[
            "sample_count"
        ],
        len(samples),
        EXPECTED[
            "sample_count"
        ],
    )

    check(
        "long_value_row_count",
        len(values)
        == EXPECTED[
            "long_value_count"
        ],
        len(values),
        EXPECTED[
            "long_value_count"
        ],
    )

    check(
        "companion_row_count",
        len(companions)
        == EXPECTED[
            "companion_metadata_count"
        ],
        len(companions),
        EXPECTED[
            "companion_metadata_count"
        ],
    )

    check(
        "graphical_review_row_count",
        len(graphical)
        == EXPECTED[
            "graphical_review_count"
        ],
        len(graphical),
        EXPECTED[
            "graphical_review_count"
        ],
    )

    check(
        "extraction_failure_row_count",
        len(failures) == 0,
        len(failures),
        0,
    )

    check(
        "series_review_flag_row_count",
        len(review_flags)
        == EXPECTED[
            "series_with_review_flags"
        ],
        len(review_flags),
        EXPECTED[
            "series_with_review_flags"
        ],
    )

    failed_checks = [
        row
        for row in checks
        if row["status"] == "FAIL"
    ]

    if failed_checks:
        print(
            json.dumps(
                {
                    "freeze_status":
                        "blocked",

                    "failed_checks":
                        failed_checks,
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        raise SystemExit(
            "PDF freeze blocked by validation mismatch."
        )

    # --------------------------------------------------------
    # Create output
    # --------------------------------------------------------

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Copy structured package at final root.
    for filename in STRUCTURED_FILES:
        copy_file(
            structured / filename,
            out / filename,
        )

    # Preserve dedicated validation artifacts separately.
    validation_out = (
        out / "validation"
    )

    for filename in VALIDATION_FILES:
        copy_file(
            validation / filename,
            validation_out / filename,
        )

    # --------------------------------------------------------
    # Freeze metadata
    # --------------------------------------------------------

    freeze_metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "source_scope":
            "PDF-only reports",

        "freeze_version":
            "group4_pdf_final_v1",

        "freeze_status":
            "frozen_validated_with_explicit_review_evidence",

        "structured_series_count":
            len(registry),

        "reports_with_structured_timeseries":
            structured_metadata.get(
                "reports_with_structured_timeseries"
            ),

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

        "families":
            structured_metadata.get(
                "family_counts",
                {},
            ),

        "orientations":
            structured_metadata.get(
                "orientation_counts",
                {},
            ),

        "axes":
            structured_metadata.get(
                "axis_type_counts",
                {},
            ),

        "repeated_transposed_series_count":
            validation_metadata.get(
                "repeated_transposed_series_count"
            ),

        "continuation_candidate_series_count":
            validation_metadata.get(
                "continuation_candidate_series_count"
            ),

        "continuation_candidate_group_count":
            validation_metadata.get(
                "continuation_candidate_group_count"
            ),

        "all_values_unavailable_series_count":
            validation_metadata.get(
                "all_values_unavailable_series_count"
            ),

        "series_with_review_flags":
            validation_metadata.get(
                "series_with_review_flags"
            ),

        "blank_signal_label_count":
            validation_metadata.get(
                "blank_signal_label_count"
            ),

        "fallback_signal_label_count":
            validation_metadata.get(
                "fallback_signal_label_count"
            ),

        "axis_like_signal_label_count":
            validation_metadata.get(
                "axis_like_signal_label_count"
            ),

        "duplicate_signal_label_group_count":
            validation_metadata.get(
                "duplicate_signal_label_group_count"
            ),

        "blank_axis_series_count":
            validation_metadata.get(
                "blank_axis_series_count"
            ),

        "nonnumeric_axis_series_count":
            validation_metadata.get(
                "nonnumeric_axis_series_count"
            ),

        "repeated_axis_series_count":
            validation_metadata.get(
                "repeated_axis_series_count"
            ),

        "nonmonotonic_axis_series_count":
            validation_metadata.get(
                "nonmonotonic_axis_series_count"
            ),

        "validation_checks":
            validation_metadata.get(
                "validation_checks"
            ),

        "validation_passes":
            validation_metadata.get(
                "validation_passes"
            ),

        "validation_failures":
            validation_metadata.get(
                "validation_failures"
            ),

        "hard_validation_failures":
            validation_metadata.get(
                "hard_validation_failures"
            ),

        "warning_validation_failures":
            validation_metadata.get(
                "warning_validation_failures"
            ),

        "freeze_validation_checks":
            len(checks),

        "freeze_validation_failures":
            0,

        "review_evidence_policy":
            (
                "18 all-values-unavailable structural series and "
                "37 graphical PDF review tables are explicitly "
                "preserved as evidence and are not treated as "
                "extraction failures. The 84 series belonging to "
                "47 continuation-candidate groups remain independent "
                "physical PDF tables and are not merged in this freeze."
            ),

        "scope":
            (
                "Frozen validated Group 4 PDF-only structural "
                "time-series package. Raw signal labels, units, axis "
                "values, unavailable source values, provenance, "
                "companion metadata, graphical review evidence, and "
                "continuation metadata are preserved. No semantic "
                "normalization, unit conversion, event identity "
                "inference, logical continuation merging, or CSV/PDF "
                "integration is performed."
            ),
    }

    tmp = (
        out / "freeze_metadata.json.part"
    )

    tmp.write_text(
        json.dumps(
            freeze_metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        out / "freeze_metadata.json"
    )

    # Freeze gate evidence.
    with (
        out / "freeze_validation.csv"
    ).open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "check",
                "status",
                "observed",
                "expected",
            ],
        )
        writer.writeheader()
        writer.writerows(checks)

    print()
    print(
        json.dumps(
            freeze_metadata,
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
        "GROUP 4 PDF FREEZE COMPLETE."
    )


if __name__ == "__main__":
    main()
