"""
Final-validate and freeze the integrated Group 5 package.

Input
-----
data/processed/edr/group5_final_v1/

    measurement_registry.csv
    measurement_values.csv
    companion_context.csv
    source_package_summary.csv
    family_summary.csv
    validation_checks.csv
    metadata.json

Output
------
data/processed/edr/group5_final_frozen_v1/

    measurement_registry.csv
    measurement_values.csv
    companion_context.csv
    source_package_summary.csv
    family_summary.csv
    validation_checks.csv
    metadata.json
    final_validation/
        final_validation_checks.csv
        metadata.json
    freeze_manifest.json

Purpose
-------
Perform a final integrity check on the integrated Group 5 package and freeze
it without modifying the underlying CSV/PDF frozen source packages.

Expected current totals
-----------------------
Measurements:       11,212
Companion context:   1,166
Reports:             1,278
Cases:               1,102
CSV source rows:    10,595
PDF source rows:       617
CSV/PDF report overlap: 0

Rules
-----
- no re-extraction
- no semantic normalization
- no unit conversion
- no event-link inference
- preserve source_package and source_format provenance
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

csv.field_size_limit(100_000_000)


def read_csv(path: Path):
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")

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


def norm(value):
    return " ".join(
        str(value if value is not None else "").split()
    )


def file_sha256(path: Path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--integrated-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group5_final_v1"
        ),
    )

    parser.add_argument(
        "--final-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group5_final_frozen_v1"
        ),
    )

    args = parser.parse_args()

    src = args.integrated_directory
    out = args.final_directory

    required = {
        "registry":
            src / "measurement_registry.csv",
        "values":
            src / "measurement_values.csv",
        "companion":
            src / "companion_context.csv",
        "source_summary":
            src / "source_package_summary.csv",
        "family_summary":
            src / "family_summary.csv",
        "validation_checks":
            src / "validation_checks.csv",
        "metadata":
            src / "metadata.json",
    }

    for name, path in required.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {name}: {path}"
            )

    registry = read_csv(required["registry"])
    values = read_csv(required["values"])
    companion = read_csv(required["companion"])
    source_summary = read_csv(required["source_summary"])
    family_summary = read_csv(required["family_summary"])
    prior_checks = read_csv(required["validation_checks"])

    metadata = json.loads(
        required["metadata"].read_text(
            encoding="utf-8"
        )
    )

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

    # --------------------------------------------------------
    # Count integrity
    # --------------------------------------------------------

    check(
        "registry_expected_count",
        len(registry) == 11212,
        len(registry),
        11212,
    )

    check(
        "values_expected_count",
        len(values) == 11212,
        len(values),
        11212,
    )

    check(
        "companion_expected_count",
        len(companion) == 1166,
        len(companion),
        1166,
    )

    check(
        "registry_values_same_count",
        len(registry) == len(values),
        len(registry),
        len(values),
    )

    # --------------------------------------------------------
    # ID integrity
    # --------------------------------------------------------

    registry_ids = [
        norm(row.get("measurement_id", ""))
        for row in registry
    ]

    value_ids = [
        norm(row.get("measurement_id", ""))
        for row in values
    ]

    check(
        "blank_measurement_ids",
        all(registry_ids),
        sum(1 for value in registry_ids if not value),
        0,
    )

    duplicate_ids = (
        len(registry_ids)
        - len(set(registry_ids))
    )

    check(
        "duplicate_measurement_ids",
        duplicate_ids == 0,
        duplicate_ids,
        0,
    )

    check(
        "registry_values_id_sets_equal",
        set(registry_ids) == set(value_ids),
        len(set(registry_ids) ^ set(value_ids)),
        0,
    )

    # --------------------------------------------------------
    # Source package / format integrity
    # --------------------------------------------------------

    source_package_counts = Counter(
        norm(row.get("source_package", ""))
        for row in registry
    )

    source_format_counts = Counter(
        norm(row.get("source_format", ""))
        for row in registry
    )

    check(
        "csv_source_count",
        source_package_counts[
            "group5_csv_final_v1"
        ] == 10595,
        source_package_counts[
            "group5_csv_final_v1"
        ],
        10595,
    )

    check(
        "pdf_source_count",
        source_package_counts[
            "group5_pdf_final_v1"
        ] == 617,
        source_package_counts[
            "group5_pdf_final_v1"
        ],
        617,
    )

    check(
        "source_formats_valid",
        set(source_format_counts)
        <= {"csv", "pdf"},
        sorted(source_format_counts),
        "csv|pdf",
    )

    csv_mismatch = sum(
        1
        for row in registry
        if (
            norm(row.get("source_package", ""))
            == "group5_csv_final_v1"
            and norm(row.get("source_format", ""))
            != "csv"
        )
    )

    pdf_mismatch = sum(
        1
        for row in registry
        if (
            norm(row.get("source_package", ""))
            == "group5_pdf_final_v1"
            and norm(row.get("source_format", ""))
            != "pdf"
        )
    )

    check(
        "csv_source_format_consistency",
        csv_mismatch == 0,
        csv_mismatch,
        0,
    )

    check(
        "pdf_source_format_consistency",
        pdf_mismatch == 0,
        pdf_mismatch,
        0,
    )

    # --------------------------------------------------------
    # Report/case integrity
    # --------------------------------------------------------

    csv_reports = {
        norm(row.get("report_id", ""))
        for row in registry
        if (
            norm(row.get("source_format", ""))
            == "csv"
            and norm(row.get("report_id", ""))
        )
    }

    pdf_reports = {
        norm(row.get("report_id", ""))
        for row in registry
        if (
            norm(row.get("source_format", ""))
            == "pdf"
            and norm(row.get("report_id", ""))
        )
    }

    report_overlap = csv_reports & pdf_reports

    check(
        "csv_pdf_report_overlap_zero",
        len(report_overlap) == 0,
        len(report_overlap),
        0,
    )

    all_reports = csv_reports | pdf_reports

    check(
        "integrated_report_count",
        len(all_reports) == 1278,
        len(all_reports),
        1278,
    )

    all_cases = {
        norm(row.get("case_id", ""))
        for row in registry
        if norm(row.get("case_id", ""))
    }

    check(
        "integrated_case_count",
        len(all_cases) == 1102,
        len(all_cases),
        1102,
    )

    # --------------------------------------------------------
    # Core provenance completeness
    # --------------------------------------------------------

    required_fields = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "measurement_id",
        "source_format",
        "source_package",
        "family",
        "field_label_raw",
        "source_path",
    ]

    blank_required = Counter()

    for row in registry:
        for field in required_fields:
            if not norm(row.get(field, "")):
                blank_required[field] += 1

    check(
        "required_provenance_blank_cells",
        sum(blank_required.values()) == 0,
        sum(blank_required.values()),
        0,
        note=json.dumps(
            dict(blank_required),
            ensure_ascii=False,
        ),
    )

    # --------------------------------------------------------
    # Inherited integration validation
    # --------------------------------------------------------

    inherited_hard_failures = sum(
        1
        for row in prior_checks
        if (
            norm(row.get("status", "")).upper()
            == "FAIL"
            and norm(row.get("severity", "")).casefold()
            == "hard"
        )
    )

    inherited_warning_failures = sum(
        1
        for row in prior_checks
        if (
            norm(row.get("status", "")).upper()
            == "FAIL"
            and norm(row.get("severity", "")).casefold()
            == "warning"
        )
    )

    check(
        "inherited_integration_hard_failures",
        inherited_hard_failures == 0,
        inherited_hard_failures,
        0,
    )

    check(
        "inherited_integration_warning_failures",
        inherited_warning_failures == 0,
        inherited_warning_failures,
        0,
        severity="warning",
    )

    check(
        "integration_status_ready_for_freeze",
        metadata.get("integration_status")
        == "validated_ready_for_final_freeze",
        metadata.get("integration_status"),
        "validated_ready_for_final_freeze",
    )

    # --------------------------------------------------------
    # Final metadata
    # --------------------------------------------------------

    hard_failures = [
        row
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"] == "hard"
        )
    ]

    warning_failures = [
        row
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"] == "warning"
        )
    ]

    validation_metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "final integrated validation",

        "structured_measurement_count":
            len(registry),

        "measurement_value_count":
            len(values),

        "companion_context_count":
            len(companion),

        "report_count":
            len(all_reports),

        "case_count":
            len(all_cases),

        "source_measurement_counts":
            {
                "csv":
                    source_format_counts[
                        "csv"
                    ],
                "pdf":
                    source_format_counts[
                        "pdf"
                    ],
            },

        "csv_pdf_report_overlap":
            len(report_overlap),

        "validation_checks":
            len(checks),

        "validation_failures":
            sum(
                1
                for row in checks
                if row["status"] == "FAIL"
            ),

        "hard_validation_failures":
            len(hard_failures),

        "warning_validation_failures":
            len(warning_failures),

        "validation_status":
            (
                "validated_ready_for_final_freeze"
                if not hard_failures
                else "validation_failed"
            ),

        "scope":
            (
                "Final integrity validation of the integrated Group 5 "
                "CSV + PDF package. The process validates counts, IDs, "
                "source-package provenance, source-format consistency, "
                "report/case coverage, and inherited integration checks. "
                "No extraction, semantic normalization, unit conversion, "
                "or event-link inference is performed."
            ),
    }

    if hard_failures:
        print(
            json.dumps(
                validation_metadata,
                indent=2,
                ensure_ascii=False,
            )
        )
        raise SystemExit(
            "GROUP 5 FINAL VALIDATION FAILED."
        )

    # --------------------------------------------------------
    # Freeze
    # --------------------------------------------------------

    if out.exists():
        shutil.rmtree(out)

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    core_files = [
        "measurement_registry.csv",
        "measurement_values.csv",
        "companion_context.csv",
        "source_package_summary.csv",
        "family_summary.csv",
        "validation_checks.csv",
        "metadata.json",
    ]

    for filename in core_files:
        shutil.copy2(
            src / filename,
            out / filename,
        )

    final_validation_dir = (
        out / "final_validation"
    )

    final_validation_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        final_validation_dir
        / "final_validation_checks.csv",
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

    (
        final_validation_dir
        / "metadata.json"
    ).write_text(
        json.dumps(
            validation_metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    frozen_files = []

    for path in sorted(out.rglob("*")):
        if path.is_file():
            frozen_files.append({
                "relative_path":
                    str(
                        path.relative_to(out)
                    ),
                "size_bytes":
                    path.stat().st_size,
                "sha256":
                    file_sha256(path),
            })

    freeze_manifest = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "source_package":
            str(src),

        "freeze_status":
            "frozen_validated_with_explicit_review_evidence",

        "structured_measurement_count":
            len(registry),

        "measurement_value_count":
            len(values),

        "companion_context_count":
            len(companion),

        "report_count":
            len(all_reports),

        "case_count":
            len(all_cases),

        "source_measurement_counts":
            {
                "csv":
                    source_format_counts["csv"],
                "pdf":
                    source_format_counts["pdf"],
            },

        "csv_pdf_report_overlap":
            len(report_overlap),

        "hard_validation_failures":
            len(hard_failures),

        "warning_validation_failures":
            len(warning_failures),

        "immutable_intent":
            (
                "This package is the final frozen integrated Group 5 "
                "dataset. Do not modify unless a concrete validation or "
                "source-extraction error is demonstrated."
            ),

        "files":
            frozen_files,
    }

    (
        out / "freeze_manifest.json"
    ).write_text(
        json.dumps(
            freeze_manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(
        json.dumps(
            validation_metadata,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        json.dumps(
            freeze_manifest,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        f"Frozen package: {out}"
    )

    print()
    print(
        "GROUP 5 FINAL VALIDATION AND FREEZE COMPLETE."
    )


if __name__ == "__main__":
    main()
