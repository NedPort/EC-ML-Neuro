"""
Build the final integrated Group 4 package from the frozen CSV and PDF sources.

Inputs
------
data/processed/edr/group4_csv_final_v1/
data/processed/edr/group4_pdf_final_v1/

Output
------
data/processed/edr/group4_final_v1/

Core outputs
------------
timeseries_registry.csv
timeseries_signal_registry.csv
timeseries_samples_wide.csv
timeseries_values_long.csv
timeseries_companion_metadata.csv
validation_report.csv
metadata.json

Review evidence
---------------
review_evidence/
    csv/
    pdf/

Purpose
-------
Combine the already frozen Group 4 CSV-backed and PDF-only structural
time-series packages without re-extracting or modifying either source.

Important rules
---------------
- Frozen CSV and PDF inputs are read-only.
- No semantic normalization is performed.
- No unit conversion is performed.
- No event identity inference is performed.
- No continuation-group merging is performed.
- PDF graphical review evidence remains review evidence.
- Source-specific provenance is preserved.
- Every integrated row receives:
      source_format  = csv | pdf
      source_package = group4_csv_final_v1 | group4_pdf_final_v1
- CSV-backed and PDF-only report populations must be disjoint.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

csv.field_size_limit(100_000_000)


# ============================================================
# Expected frozen package summaries
# ============================================================

EXPECTED_CSV = {
    "structured_series_count": 8265,
    "signal_count": 36722,
    "sample_count": 415343,
    "long_value_count": 1135766,
    "extraction_failure_count": 0,
}

EXPECTED_PDF = {
    "structured_series_count": 861,
    "signal_count": 2491,
    "sample_count": 14211,
    "long_value_count": 30643,
    "companion_metadata_count": 764,
    "graphical_review_count": 37,
    "extraction_failure_count": 0,
}


# ============================================================
# Filename aliases
# ============================================================

ALIASES = {
    "registry": [
        "timeseries_registry.csv",
        "series_registry.csv",
        "registry.csv",
    ],
    "signals": [
        "timeseries_signal_registry.csv",
        "signal_registry.csv",
        "signals.csv",
    ],
    "samples": [
        "timeseries_samples_wide.csv",
        "samples_wide.csv",
        "samples.csv",
    ],
    "values": [
        "timeseries_values_long.csv",
        "values_long.csv",
        "long_values.csv",
    ],
    "companions": [
        "timeseries_companion_metadata.csv",
        "companion_metadata.csv",
    ],
    "failures": [
        "extraction_failures.csv",
        "failures.csv",
    ],
    "graphical": [
        "graphical_review_tables.csv",
    ],
}


# ============================================================
# I/O helpers
# ============================================================

def read_csv(path: Path):
    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


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
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def union_columns(*row_sets):
    seen = set()
    columns = []

    preferred = [
        "source_format",
        "source_package",
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
    ]

    for column in preferred:
        seen.add(column)
        columns.append(column)

    for rows in row_sets:
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    columns.append(key)

    return columns


def find_existing(
    directory: Path,
    names: list[str],
    required: bool = True,
):
    for name in names:
        path = directory / name
        if path.exists():
            return path

    if required:
        raise FileNotFoundError(
            "None of the expected files exist in "
            f"{directory}: {names}"
        )

    return None


def add_source_fields(
    rows: list[dict],
    source_format: str,
    source_package: str,
):
    return [
        {
            "source_format":
                source_format,

            "source_package":
                source_package,

            **row,
        }
        for row in rows
    ]


def safe_copy(
    src: Path,
    dst: Path,
):
    if not src.exists():
        return

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


# ============================================================
# Package loader
# ============================================================

def load_package(
    directory: Path,
    source_format: str,
    package_name: str,
):
    registry_path = find_existing(
        directory,
        ALIASES["registry"],
    )

    signals_path = find_existing(
        directory,
        ALIASES["signals"],
    )

    samples_path = find_existing(
        directory,
        ALIASES["samples"],
    )

    values_path = find_existing(
        directory,
        ALIASES["values"],
    )

    companions_path = find_existing(
        directory,
        ALIASES["companions"],
        required=False,
    )

    failures_path = find_existing(
        directory,
        ALIASES["failures"],
        required=False,
    )

    graphical_path = find_existing(
        directory,
        ALIASES["graphical"],
        required=False,
    )

    freeze_metadata_path = (
        directory
        / "freeze_metadata.json"
    )

    metadata_path = (
        directory
        / "metadata.json"
    )

    freeze_metadata = (
        read_json(
            freeze_metadata_path
        )
        if freeze_metadata_path.exists()
        else {}
    )

    metadata = (
        read_json(
            metadata_path
        )
        if metadata_path.exists()
        else {}
    )

    registry = add_source_fields(
        read_csv(
            registry_path
        ),
        source_format,
        package_name,
    )

    signals = add_source_fields(
        read_csv(
            signals_path
        ),
        source_format,
        package_name,
    )

    samples = add_source_fields(
        read_csv(
            samples_path
        ),
        source_format,
        package_name,
    )

    values = add_source_fields(
        read_csv(
            values_path
        ),
        source_format,
        package_name,
    )

    companions = (
        add_source_fields(
            read_csv(
                companions_path
            ),
            source_format,
            package_name,
        )
        if companions_path
        else []
    )

    failures = (
        add_source_fields(
            read_csv(
                failures_path
            ),
            source_format,
            package_name,
        )
        if failures_path
        else []
    )

    graphical = (
        add_source_fields(
            read_csv(
                graphical_path
            ),
            source_format,
            package_name,
        )
        if graphical_path
        else []
    )

    return {
        "directory":
            directory,

        "package_name":
            package_name,

        "source_format":
            source_format,

        "registry":
            registry,

        "signals":
            signals,

        "samples":
            samples,

        "values":
            values,

        "companions":
            companions,

        "failures":
            failures,

        "graphical":
            graphical,

        "freeze_metadata":
            freeze_metadata,

        "metadata":
            metadata,

        "paths": {
            "registry":
                registry_path,

            "signals":
                signals_path,

            "samples":
                samples_path,

            "values":
                values_path,

            "companions":
                companions_path,

            "failures":
                failures_path,

            "graphical":
                graphical_path,
        },
    }


# ============================================================
# Validation helpers
# ============================================================

def unique_nonblank(
    rows,
    field,
):
    return {
        str(
            row.get(
                field,
                ""
            )
        ).strip()
        for row in rows
        if str(
            row.get(
                field,
                ""
            )
        ).strip()
    }


def count_duplicates(
    rows,
    field,
):
    counter = Counter(
        str(
            row.get(
                field,
                ""
            )
        ).strip()
        for row in rows
        if str(
            row.get(
                field,
                ""
            )
        ).strip()
    )

    return sum(
        1
        for count in counter.values()
        if count > 1
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--csv-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_csv_final_v1"
        ),
    )

    parser.add_argument(
        "--pdf-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_pdf_final_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_final_v1"
        ),
    )

    args = parser.parse_args()

    csv_pkg = load_package(
        args.csv_directory,
        "csv",
        "group4_csv_final_v1",
    )

    pdf_pkg = load_package(
        args.pdf_directory,
        "pdf",
        "group4_pdf_final_v1",
    )

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Frozen-package sanity checks
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
                str(observed),

            "expected":
                str(expected),

            "note":
                note,
        })

    # CSV counts
    check(
        "csv_structured_series_count",
        len(
            csv_pkg["registry"]
        )
        == EXPECTED_CSV[
            "structured_series_count"
        ],
        len(
            csv_pkg["registry"]
        ),
        EXPECTED_CSV[
            "structured_series_count"
        ],
    )

    check(
        "csv_signal_count",
        len(
            csv_pkg["signals"]
        )
        == EXPECTED_CSV[
            "signal_count"
        ],
        len(
            csv_pkg["signals"]
        ),
        EXPECTED_CSV[
            "signal_count"
        ],
    )

    check(
        "csv_sample_count",
        len(
            csv_pkg["samples"]
        )
        == EXPECTED_CSV[
            "sample_count"
        ],
        len(
            csv_pkg["samples"]
        ),
        EXPECTED_CSV[
            "sample_count"
        ],
    )

    check(
        "csv_long_value_count",
        len(
            csv_pkg["values"]
        )
        == EXPECTED_CSV[
            "long_value_count"
        ],
        len(
            csv_pkg["values"]
        ),
        EXPECTED_CSV[
            "long_value_count"
        ],
    )

    check(
        "csv_extraction_failure_count",
        len(
            csv_pkg["failures"]
        )
        == EXPECTED_CSV[
            "extraction_failure_count"
        ],
        len(
            csv_pkg["failures"]
        ),
        EXPECTED_CSV[
            "extraction_failure_count"
        ],
    )

    # PDF counts
    check(
        "pdf_structured_series_count",
        len(
            pdf_pkg["registry"]
        )
        == EXPECTED_PDF[
            "structured_series_count"
        ],
        len(
            pdf_pkg["registry"]
        ),
        EXPECTED_PDF[
            "structured_series_count"
        ],
    )

    check(
        "pdf_signal_count",
        len(
            pdf_pkg["signals"]
        )
        == EXPECTED_PDF[
            "signal_count"
        ],
        len(
            pdf_pkg["signals"]
        ),
        EXPECTED_PDF[
            "signal_count"
        ],
    )

    check(
        "pdf_sample_count",
        len(
            pdf_pkg["samples"]
        )
        == EXPECTED_PDF[
            "sample_count"
        ],
        len(
            pdf_pkg["samples"]
        ),
        EXPECTED_PDF[
            "sample_count"
        ],
    )

    check(
        "pdf_long_value_count",
        len(
            pdf_pkg["values"]
        )
        == EXPECTED_PDF[
            "long_value_count"
        ],
        len(
            pdf_pkg["values"]
        ),
        EXPECTED_PDF[
            "long_value_count"
        ],
    )

    check(
        "pdf_companion_metadata_count",
        len(
            pdf_pkg["companions"]
        )
        == EXPECTED_PDF[
            "companion_metadata_count"
        ],
        len(
            pdf_pkg["companions"]
        ),
        EXPECTED_PDF[
            "companion_metadata_count"
        ],
    )

    check(
        "pdf_graphical_review_count",
        len(
            pdf_pkg["graphical"]
        )
        == EXPECTED_PDF[
            "graphical_review_count"
        ],
        len(
            pdf_pkg["graphical"]
        ),
        EXPECTED_PDF[
            "graphical_review_count"
        ],
    )

    check(
        "pdf_extraction_failure_count",
        len(
            pdf_pkg["failures"]
        )
        == EXPECTED_PDF[
            "extraction_failure_count"
        ],
        len(
            pdf_pkg["failures"]
        ),
        EXPECTED_PDF[
            "extraction_failure_count"
        ],
    )

    # ========================================================
    # Report population separation
    # ========================================================

    csv_reports = unique_nonblank(
        csv_pkg["registry"],
        "report_id",
    )

    pdf_reports = unique_nonblank(
        pdf_pkg["registry"],
        "report_id",
    )

    overlap_reports = sorted(
        csv_reports
        & pdf_reports
    )

    check(
        "csv_pdf_report_populations_disjoint",
        len(
            overlap_reports
        )
        == 0,
        len(
            overlap_reports
        ),
        0,
        "hard",
        (
            "CSV-backed and PDF-only report populations "
            "must not overlap."
        ),
    )

    # ========================================================
    # Integrate
    # ========================================================

    registry = (
        csv_pkg["registry"]
        + pdf_pkg["registry"]
    )

    signals = (
        csv_pkg["signals"]
        + pdf_pkg["signals"]
    )

    samples = (
        csv_pkg["samples"]
        + pdf_pkg["samples"]
    )

    values = (
        csv_pkg["values"]
        + pdf_pkg["values"]
    )

    companions = (
        csv_pkg["companions"]
        + pdf_pkg["companions"]
    )

    failures = (
        csv_pkg["failures"]
        + pdf_pkg["failures"]
    )

    graphical = (
        csv_pkg["graphical"]
        + pdf_pkg["graphical"]
    )

    # ========================================================
    # Integrated count validation
    # ========================================================

    expected_series = (
        EXPECTED_CSV[
            "structured_series_count"
        ]
        + EXPECTED_PDF[
            "structured_series_count"
        ]
    )

    expected_signals = (
        EXPECTED_CSV[
            "signal_count"
        ]
        + EXPECTED_PDF[
            "signal_count"
        ]
    )

    expected_samples = (
        EXPECTED_CSV[
            "sample_count"
        ]
        + EXPECTED_PDF[
            "sample_count"
        ]
    )

    expected_values = (
        EXPECTED_CSV[
            "long_value_count"
        ]
        + EXPECTED_PDF[
            "long_value_count"
        ]
    )

    check(
        "integrated_series_count",
        len(registry)
        == expected_series,
        len(registry),
        expected_series,
    )

    check(
        "integrated_signal_count",
        len(signals)
        == expected_signals,
        len(signals),
        expected_signals,
    )

    check(
        "integrated_sample_count",
        len(samples)
        == expected_samples,
        len(samples),
        expected_samples,
    )

    check(
        "integrated_long_value_count",
        len(values)
        == expected_values,
        len(values),
        expected_values,
    )

    check(
        "integrated_extraction_failure_count",
        len(failures) == 0,
        len(failures),
        0,
    )

    # ========================================================
    # Integrated ID uniqueness
    # ========================================================

    series_id_duplicates = count_duplicates(
        registry,
        "series_id",
    )

    signal_id_duplicates = count_duplicates(
        signals,
        "signal_id",
    )

    sample_id_duplicates = count_duplicates(
        samples,
        "sample_id",
    )

    check(
        "integrated_series_ids_unique",
        series_id_duplicates == 0,
        series_id_duplicates,
        0,
    )

    check(
        "integrated_signal_ids_unique",
        signal_id_duplicates == 0,
        signal_id_duplicates,
        0,
    )

    check(
        "integrated_sample_ids_unique",
        sample_id_duplicates == 0,
        sample_id_duplicates,
        0,
    )

    # ========================================================
    # Integrated referential integrity
    # ========================================================

    known_series = unique_nonblank(
        registry,
        "series_id",
    )

    known_signals = unique_nonblank(
        signals,
        "signal_id",
    )

    known_samples = unique_nonblank(
        samples,
        "sample_id",
    )

    orphan_signal_series = sum(
        1
        for row in signals
        if (
            str(
                row.get(
                    "series_id",
                    ""
                )
            ).strip()
            not in known_series
        )
    )

    orphan_sample_series = sum(
        1
        for row in samples
        if (
            str(
                row.get(
                    "series_id",
                    ""
                )
            ).strip()
            not in known_series
        )
    )

    orphan_value_series = sum(
        1
        for row in values
        if (
            str(
                row.get(
                    "series_id",
                    ""
                )
            ).strip()
            not in known_series
        )
    )

    orphan_value_signals = sum(
        1
        for row in values
        if (
            str(
                row.get(
                    "signal_id",
                    ""
                )
            ).strip()
            not in known_signals
        )
    )

    orphan_value_samples = sum(
        1
        for row in values
        if (
            str(
                row.get(
                    "sample_id",
                    ""
                )
            ).strip()
            not in known_samples
        )
    )

    check(
        "integrated_orphan_signal_series_refs",
        orphan_signal_series == 0,
        orphan_signal_series,
        0,
    )

    check(
        "integrated_orphan_sample_series_refs",
        orphan_sample_series == 0,
        orphan_sample_series,
        0,
    )

    check(
        "integrated_orphan_value_series_refs",
        orphan_value_series == 0,
        orphan_value_series,
        0,
    )

    check(
        "integrated_orphan_value_signal_refs",
        orphan_value_signals == 0,
        orphan_value_signals,
        0,
    )

    check(
        "integrated_orphan_value_sample_refs",
        orphan_value_samples == 0,
        orphan_value_samples,
        0,
    )

    # ========================================================
    # Source-label validation
    # ========================================================

    bad_registry_source_labels = [
        row
        for row in registry
        if row.get(
            "source_format"
        )
        not in {
            "csv",
            "pdf",
        }
    ]

    bad_signal_source_labels = [
        row
        for row in signals
        if row.get(
            "source_format"
        )
        not in {
            "csv",
            "pdf",
        }
    ]

    bad_sample_source_labels = [
        row
        for row in samples
        if row.get(
            "source_format"
        )
        not in {
            "csv",
            "pdf",
        }
    ]

    bad_value_source_labels = [
        row
        for row in values
        if row.get(
            "source_format"
        )
        not in {
            "csv",
            "pdf",
        }
    ]

    check(
        "registry_source_format_complete",
        len(
            bad_registry_source_labels
        )
        == 0,
        len(
            bad_registry_source_labels
        ),
        0,
    )

    check(
        "signal_source_format_complete",
        len(
            bad_signal_source_labels
        )
        == 0,
        len(
            bad_signal_source_labels
        ),
        0,
    )

    check(
        "sample_source_format_complete",
        len(
            bad_sample_source_labels
        )
        == 0,
        len(
            bad_sample_source_labels
        ),
        0,
    )

    check(
        "value_source_format_complete",
        len(
            bad_value_source_labels
        )
        == 0,
        len(
            bad_value_source_labels
        ),
        0,
    )

    # ========================================================
    # Write integrated package
    # ========================================================

    write_csv(
        out / "timeseries_registry.csv",
        registry,
        union_columns(registry),
    )

    write_csv(
        out
        / "timeseries_signal_registry.csv",
        signals,
        union_columns(signals),
    )

    write_csv(
        out
        / "timeseries_samples_wide.csv",
        samples,
        union_columns(samples),
    )

    write_csv(
        out
        / "timeseries_values_long.csv",
        values,
        union_columns(values),
    )

    write_csv(
        out
        / "timeseries_companion_metadata.csv",
        companions,
        union_columns(companions),
    )

    write_csv(
        out
        / "extraction_failures.csv",
        failures,
        union_columns(failures),
    )

    write_csv(
        out
        / "graphical_review_tables.csv",
        graphical,
        union_columns(graphical),
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
            "note",
        ],
    )

    # ========================================================
    # Preserve frozen-source validation/review evidence
    # ========================================================

    review_root = (
        out / "review_evidence"
    )

    for source_name, package in (
        ("csv", csv_pkg),
        ("pdf", pdf_pkg),
    ):
        source_dir = (
            package["directory"]
        )

        destination = (
            review_root / source_name
        )

        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        for filename in (
            "freeze_metadata.json",
            "freeze_validation.csv",
            "validation_report.csv",
            "metadata.json",
            "graphical_review_tables.csv",
            "series_review_flags.csv",
            "duplicate_signal_label_groups.csv",
            "axis_review.csv",
            "continuation_review.csv",
        ):
            safe_copy(
                source_dir / filename,
                destination / filename,
            )

        # PDF freeze stores its dedicated validation package here.
        safe_copy(
            source_dir / "validation",
            destination / "validation",
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

    source_series_counts = Counter(
        row["source_format"]
        for row in registry
    )

    source_signal_counts = Counter(
        row["source_format"]
        for row in signals
    )

    source_sample_counts = Counter(
        row["source_format"]
        for row in samples
    )

    source_value_counts = Counter(
        row["source_format"]
        for row in values
    )

    family_counts = Counter(
        str(
            row.get(
                "family",
                row.get(
                    "series_family",
                    "",
                )
            )
        ).strip()
        for row in registry
        if str(
            row.get(
                "family",
                row.get(
                    "series_family",
                    "",
                )
            )
        ).strip()
    )

    reports_with_series = unique_nonblank(
        registry,
        "report_id",
    )

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "stage":
            "final CSV + PDF integration",

        "integration_status":
            (
                "validated_ready_for_final_freeze"
                if not hard_failures
                else "blocked_by_hard_validation_failure"
            ),

        "input_packages": {
            "csv":
                "group4_csv_final_v1",

            "pdf":
                "group4_pdf_final_v1",
        },

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

        "reports_with_structured_timeseries":
            len(
                reports_with_series
            ),

        "csv_report_count":
            len(csv_reports),

        "pdf_report_count":
            len(pdf_reports),

        "csv_pdf_report_overlap_count":
            len(
                overlap_reports
            ),

        "source_series_counts":
            dict(
                source_series_counts
            ),

        "source_signal_counts":
            dict(
                source_signal_counts
            ),

        "source_sample_counts":
            dict(
                source_sample_counts
            ),

        "source_long_value_counts":
            dict(
                source_value_counts
            ),

        "family_counts":
            dict(
                family_counts
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
                "Integration of the frozen Group 4 CSV-backed and "
                "PDF-only structural time-series packages. No source "
                "package is modified. The integrated package adds "
                "source_format and source_package provenance while "
                "preserving source-specific fields. No re-extraction, "
                "semantic normalization, unit conversion, event identity "
                "inference, PDF continuation merging, or graphical plot "
                "digitization is performed."
            ),
    }

    tmp = (
        out / "metadata.json.part"
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
        out / "metadata.json"
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
            "GROUP 4 FINAL INTEGRATION HAS HARD VALIDATION FAILURES."
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
        "GROUP 4 FINAL INTEGRATION COMPLETE."
    )


if __name__ == "__main__":
    main()
