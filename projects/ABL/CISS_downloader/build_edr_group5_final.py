"""
Integrate the frozen Group 5 CSV and PDF-only packages.

Inputs
------
data/processed/edr/group5_csv_final_v1/
    measurement_registry.csv
    measurement_values.csv
    companion_context.csv
    freeze_manifest.json

data/processed/edr/group5_pdf_final_v1/
    measurement_registry.csv
    measurement_values.csv
    freeze_manifest.json

Output
------
data/processed/edr/group5_final_v1/

    measurement_registry.csv
    measurement_values.csv
    companion_context.csv
    source_package_summary.csv
    family_summary.csv
    validation_checks.csv
    metadata.json

Purpose
-------
Create the integrated Group 5 dataset without re-extracting or mutating
either frozen source package.

Expected current source totals
------------------------------
CSV measurements: 10,595
PDF measurements:    617
Integrated total: 11,212

CSV companion context: 1,166

Integration rules
-----------------
- preserve all source rows exactly
- preserve source-specific provenance
- add source_package to every integrated record
- retain source_format = csv|pdf
- do not normalize labels/values
- do not convert units
- do not infer event identity
- do not alter frozen source packages
"""

from __future__ import annotations

import argparse
import csv
import json
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
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


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
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "measurement_id",
        "source_format",
        "source_package",
        "family",
        "field_label_raw",
        "field_value_raw",
        "field_value_numeric",
        "field_value_is_missing_or_na",
        "unit_raw",
        "event_hint",
        "event_link_status",
        "source_path",
        "source_record_index",
        "source_page_number",
        "source_line_number_on_page",
        "source_section_heading",
        "source_row_json",
        "source_line_raw",
        "processing_status",
        "semantic_normalization_status",
        "unit_conversion_status",
    ]

    for column in preferred:
        if column not in seen:
            seen.add(column)
            columns.append(column)

    for rows in row_sets:
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    columns.append(key)

    return columns


def norm(value):
    return " ".join(
        str(
            value
            if value is not None
            else ""
        ).split()
    )


# ============================================================
# Frozen package validation
# ============================================================

def load_manifest(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def validate_frozen_manifest(
    manifest: dict,
    package_name: str,
):
    status = manifest.get(
        "freeze_status",
        ""
    )

    if status != (
        "frozen_validated_with_explicit_review_evidence"
    ):
        raise RuntimeError(
            f"{package_name} is not frozen/validated. "
            f"freeze_status={status!r}"
        )


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--csv-package",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_final_v1"
        ),
    )

    parser.add_argument(
        "--pdf-package",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_pdf_final_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_final_v1"
        ),
    )

    args = parser.parse_args()

    csv_pkg = args.csv_package
    pdf_pkg = args.pdf_package
    out = args.output_directory

    required_csv = {
        "registry":
            csv_pkg
            / "measurement_registry.csv",

        "values":
            csv_pkg
            / "measurement_values.csv",

        "companion":
            csv_pkg
            / "companion_context.csv",

        "manifest":
            csv_pkg
            / "freeze_manifest.json",
    }

    required_pdf = {
        "registry":
            pdf_pkg
            / "measurement_registry.csv",

        "values":
            pdf_pkg
            / "measurement_values.csv",

        "manifest":
            pdf_pkg
            / "freeze_manifest.json",
    }

    for name, path in {
        **{
            f"csv_{k}": v
            for k, v
            in required_csv.items()
        },
        **{
            f"pdf_{k}": v
            for k, v
            in required_pdf.items()
        },
    }.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {name}: {path}"
            )

    csv_manifest = load_manifest(
        required_csv[
            "manifest"
        ]
    )

    pdf_manifest = load_manifest(
        required_pdf[
            "manifest"
        ]
    )

    validate_frozen_manifest(
        csv_manifest,
        "CSV package",
    )

    validate_frozen_manifest(
        pdf_manifest,
        "PDF package",
    )

    csv_registry = read_csv(
        required_csv[
            "registry"
        ]
    )

    csv_values = read_csv(
        required_csv[
            "values"
        ]
    )

    csv_companion = read_csv(
        required_csv[
            "companion"
        ]
    )

    pdf_registry = read_csv(
        required_pdf[
            "registry"
        ]
    )

    pdf_values = read_csv(
        required_pdf[
            "values"
        ]
    )

    # ========================================================
    # Add source_package while preserving original rows
    # ========================================================

    csv_source_package = (
        "group5_csv_final_v1"
    )

    pdf_source_package = (
        "group5_pdf_final_v1"
    )

    integrated_registry = []

    for row in csv_registry:
        integrated_registry.append({
            **row,
            "source_package":
                csv_source_package,
        })

    for row in pdf_registry:
        integrated_registry.append({
            **row,
            "source_package":
                pdf_source_package,
        })

    integrated_values = []

    for row in csv_values:
        integrated_values.append({
            **row,
            "source_package":
                csv_source_package,
        })

    for row in pdf_values:
        integrated_values.append({
            **row,
            "source_package":
                pdf_source_package,
        })

    integrated_companion = [
        {
            **row,
            "source_package":
                csv_source_package,
        }
        for row in csv_companion
    ]

    # ========================================================
    # Validation
    # ========================================================

    checks = []

    def check(
        name,
        condition,
        observed,
        expected,
        severity="hard",
        note="",
    ):
        checks.append({
            "check":
                name,

            "status":
                "PASS"
                if condition
                else "FAIL",

            "severity":
                severity,

            "observed":
                str(observed),

            "expected":
                str(expected),

            "note":
                note,
        })

    # Expected counts
    check(
        "csv_registry_expected_count",
        len(csv_registry) == 10595,
        len(csv_registry),
        10595,
        severity="warning",
    )

    check(
        "pdf_registry_expected_count",
        len(pdf_registry) == 617,
        len(pdf_registry),
        617,
        severity="warning",
    )

    check(
        "integrated_registry_expected_count",
        len(
            integrated_registry
        )
        == 11212,
        len(
            integrated_registry
        ),
        11212,
        severity="warning",
    )

    check(
        "integrated_values_expected_count",
        len(
            integrated_values
        )
        == 11212,
        len(
            integrated_values
        ),
        11212,
        severity="warning",
    )

    check(
        "companion_context_expected_count",
        len(
            integrated_companion
        )
        == 1166,
        len(
            integrated_companion
        ),
        1166,
        severity="warning",
    )

    # Registry/value accounting
    check(
        "registry_values_same_row_count",
        len(
            integrated_registry
        )
        == len(
            integrated_values
        ),
        len(
            integrated_registry
        ),
        len(
            integrated_values
        ),
    )

    registry_ids = [
        norm(
            row.get(
                "measurement_id",
                "",
            )
        )
        for row in integrated_registry
    ]

    values_ids = [
        norm(
            row.get(
                "measurement_id",
                "",
            )
        )
        for row in integrated_values
    ]

    duplicate_measurement_ids = (
        len(registry_ids)
        - len(
            set(
                registry_ids
            )
        )
    )

    check(
        "measurement_ids_unique",
        duplicate_measurement_ids
        == 0,
        duplicate_measurement_ids,
        0,
    )

    check(
        "registry_values_measurement_id_sets_equal",
        set(
            registry_ids
        )
        == set(
            values_ids
        ),
        len(
            set(registry_ids)
            ^ set(values_ids)
        ),
        0,
    )

    # Source format/package integrity
    source_format_counts = Counter(
        norm(
            row.get(
                "source_format",
                "",
            )
        )
        for row in integrated_registry
    )

    source_package_counts = Counter(
        norm(
            row.get(
                "source_package",
                "",
            )
        )
        for row in integrated_registry
    )

    check(
        "source_format_values_valid",
        set(
            source_format_counts
        )
        <= {
            "csv",
            "pdf",
        },
        sorted(
            source_format_counts
        ),
        "csv|pdf",
    )

    csv_source_mismatch = sum(
        1
        for row in integrated_registry
        if (
            row.get(
                "source_package"
            )
            == csv_source_package
            and row.get(
                "source_format"
            )
            != "csv"
        )
    )

    pdf_source_mismatch = sum(
        1
        for row in integrated_registry
        if (
            row.get(
                "source_package"
            )
            == pdf_source_package
            and row.get(
                "source_format"
            )
            != "pdf"
        )
    )

    check(
        "csv_source_format_matches_package",
        csv_source_mismatch
        == 0,
        csv_source_mismatch,
        0,
    )

    check(
        "pdf_source_format_matches_package",
        pdf_source_mismatch
        == 0,
        pdf_source_mismatch,
        0,
    )

    # Report overlap check
    csv_reports = {
        norm(
            row.get(
                "report_id",
                "",
            )
        )
        for row in csv_registry
        if norm(
            row.get(
                "report_id",
                "",
            )
        )
    }

    pdf_reports = {
        norm(
            row.get(
                "report_id",
                "",
            )
        )
        for row in pdf_registry
        if norm(
            row.get(
                "report_id",
                "",
            )
        )
    }

    report_overlap = (
        csv_reports
        & pdf_reports
    )

    check(
        "csv_pdf_report_overlap",
        len(
            report_overlap
        )
        == 0,
        len(
            report_overlap
        ),
        0,
        note=json.dumps(
            sorted(
                report_overlap
            )[:20],
            ensure_ascii=False,
        ),
    )

    # Case overlap is allowed.
    csv_cases = {
        norm(
            row.get(
                "case_id",
                "",
            )
        )
        for row in csv_registry
        if norm(
            row.get(
                "case_id",
                "",
            )
        )
    }

    pdf_cases = {
        norm(
            row.get(
                "case_id",
                "",
            )
        )
        for row in pdf_registry
        if norm(
            row.get(
                "case_id",
                "",
            )
        )
    }

    case_overlap = (
        csv_cases
        & pdf_cases
    )

    # Frozen-source count checks from manifests
    check(
        "csv_manifest_registry_count_matches",
        int(
            csv_manifest.get(
                "registry_rows",
                -1,
            )
        )
        == len(
            csv_registry
        ),
        csv_manifest.get(
            "registry_rows",
            -1,
        ),
        len(
            csv_registry
        ),
    )

    check(
        "pdf_manifest_registry_count_matches",
        int(
            pdf_manifest.get(
                "registry_rows",
                -1,
            )
        )
        == len(
            pdf_registry
        ),
        pdf_manifest.get(
            "registry_rows",
            -1,
        ),
        len(
            pdf_registry
        ),
    )

    # No empty core identifiers
    blank_core_ids = sum(
        1
        for row in integrated_registry
        if (
            not norm(
                row.get(
                    "report_id",
                    "",
                )
            )
            or not norm(
                row.get(
                    "case_id",
                    "",
                )
            )
            or not norm(
                row.get(
                    "measurement_id",
                    "",
                )
            )
            or not norm(
                row.get(
                    "family",
                    "",
                )
            )
        )
    )

    check(
        "blank_core_identifier_rows",
        blank_core_ids
        == 0,
        blank_core_ids,
        0,
    )

    # ========================================================
    # Summaries
    # ========================================================

    family_counts = Counter(
        norm(
            row.get(
                "family",
                "",
            )
        )
        for row in integrated_registry
    )

    csv_family_counts = Counter(
        norm(
            row.get(
                "family",
                "",
            )
        )
        for row in csv_registry
    )

    pdf_family_counts = Counter(
        norm(
            row.get(
                "family",
                "",
            )
        )
        for row in pdf_registry
    )

    family_summary = []

    for family in sorted(
        family_counts
    ):
        family_summary.append({
            "family":
                family,

            "integrated_count":
                family_counts[
                    family
                ],

            "csv_count":
                csv_family_counts[
                    family
                ],

            "pdf_count":
                pdf_family_counts[
                    family
                ],
        })

    source_package_summary = [
        {
            "source_package":
                csv_source_package,

            "source_format":
                "csv",

            "measurement_count":
                len(
                    csv_registry
                ),

            "report_count":
                len(
                    csv_reports
                ),

            "case_count":
                len(
                    csv_cases
                ),

            "companion_context_count":
                len(
                    csv_companion
                ),

            "freeze_status":
                csv_manifest.get(
                    "freeze_status",
                    "",
                ),
        },
        {
            "source_package":
                pdf_source_package,

            "source_format":
                "pdf",

            "measurement_count":
                len(
                    pdf_registry
                ),

            "report_count":
                len(
                    pdf_reports
                ),

            "case_count":
                len(
                    pdf_cases
                ),

            "companion_context_count":
                0,

            "freeze_status":
                pdf_manifest.get(
                    "freeze_status",
                    "",
                ),
        },
    ]

    # ========================================================
    # Write
    # ========================================================

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    registry_columns = union_columns(
        integrated_registry
    )

    value_columns = union_columns(
        integrated_values
    )

    companion_columns = union_columns(
        integrated_companion
    )

    write_csv(
        out
        / "measurement_registry.csv",
        integrated_registry,
        registry_columns,
    )

    write_csv(
        out
        / "measurement_values.csv",
        integrated_values,
        value_columns,
    )

    write_csv(
        out
        / "companion_context.csv",
        integrated_companion,
        companion_columns,
    )

    write_csv(
        out
        / "source_package_summary.csv",
        source_package_summary,
        [
            "source_package",
            "source_format",
            "measurement_count",
            "report_count",
            "case_count",
            "companion_context_count",
            "freeze_status",
        ],
    )

    write_csv(
        out
        / "family_summary.csv",
        family_summary,
        [
            "family",
            "integrated_count",
            "csv_count",
            "pdf_count",
        ],
    )

    write_csv(
        out
        / "validation_checks.csv",
        checks,
        [
            "check",
            "status",
            "severity",
            "observed",
            "expected",
            "note",
        ],
    )

    hard_failures = [
        row
        for row in checks
        if (
            row["status"]
            == "FAIL"
            and row["severity"]
            == "hard"
        )
    ]

    warning_failures = [
        row
        for row in checks
        if (
            row["status"]
            == "FAIL"
            and row["severity"]
            == "warning"
        )
    ]

    integrated_reports = (
        csv_reports
        | pdf_reports
    )

    integrated_cases = (
        csv_cases
        | pdf_cases
    )

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "CSV + PDF integration",

        "integration_status":
            (
                "validated_ready_for_final_freeze"
                if not hard_failures
                else "integration_validation_failed"
            ),

        "structured_measurement_count":
            len(
                integrated_registry
            ),

        "measurement_value_count":
            len(
                integrated_values
            ),

        "companion_context_count":
            len(
                integrated_companion
            ),

        "reports_with_structured_measurements":
            len(
                integrated_reports
            ),

        "cases_with_structured_measurements":
            len(
                integrated_cases
            ),

        "source_measurement_counts": {
            "csv":
                len(
                    csv_registry
                ),

            "pdf":
                len(
                    pdf_registry
                ),
        },

        "source_report_counts": {
            "csv":
                len(
                    csv_reports
                ),

            "pdf":
                len(
                    pdf_reports
                ),
        },

        "source_case_counts": {
            "csv":
                len(
                    csv_cases
                ),

            "pdf":
                len(
                    pdf_cases
                ),
        },

        "csv_pdf_report_overlap":
            len(
                report_overlap
            ),

        "csv_pdf_case_overlap":
            len(
                case_overlap
            ),

        "family_counts":
            dict(
                family_counts
            ),

        "validation_checks":
            len(
                checks
            ),

        "validation_failures":
            sum(
                1
                for row in checks
                if row[
                    "status"
                ]
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
                "Integration of the frozen Group 5 CSV and PDF-only "
                "source packages. Frozen source rows are preserved and "
                "only source_package provenance is added. No extraction, "
                "semantic normalization, unit conversion, fuzzy event "
                "linking, or mutation of either source package is "
                "performed. CSV-backed and PDF-only report populations "
                "must remain disjoint."
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
            "GROUP 5 INTEGRATION HAS HARD VALIDATION FAILURES."
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
        "GROUP 5 CSV + PDF INTEGRATION COMPLETE."
    )


if __name__ == "__main__":
    main()
