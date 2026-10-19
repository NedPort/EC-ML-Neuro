"""
Integrate frozen Group 3 CSV and PDF-only source packages.

Inputs
------
data/processed/edr/group3_csv_final_v1/
data/processed/edr/group3_pdf_final_v1/

Output
------
data/processed/edr/group3_final_v1/

    condition_registry.csv
    condition_values.csv
    explicit_review_evidence.csv
    source_package_summary.csv
    family_summary.csv
    validation_checks.csv
    metadata.json

Purpose
-------
Combine the already frozen Group 3 CSV and PDF-only source packages without
re-extraction or mutation.

Rules
-----
- Preserve every frozen source row.
- Add source_package provenance.
- Preserve source_format.
- CSV-backed and PDF-only report populations must remain disjoint.
- Case overlap is allowed.
- No semantic normalization.
- No unit conversion.
- No fuzzy event linking.
- No source modification.
"""

from __future__ import annotations

import argparse
import csv
import json
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


def union_columns(*rowsets):
    seen = set()
    cols = []

    preferred = [
        "group3_condition_id",
        "source_candidate_id",
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "source_format",
        "source_package",
        "source_path",
        "source_record_index",
        "pdf_page",
        "pdf_line_number",
        "source_section_heading",
        "event_hint",
        "source_line_raw",
        "family",
        "field_label_raw",
        "field_value_raw",
        "raw_unit",
        "event_link_status",
        "semantic_normalization_status",
        "unit_conversion_status",
    ]

    for col in preferred:
        if col not in seen:
            seen.add(col)
            cols.append(col)

    for rows in rowsets:
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    cols.append(key)

    return cols


def load_freeze_manifest(package_dir: Path):
    path = package_dir / "freeze_manifest.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Missing freeze manifest: {path}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    status = data.get("freeze_status")

    if status != "frozen_validated_with_explicit_review_evidence":
        raise RuntimeError(
            f"{package_dir} is not frozen as expected: {status}"
        )

    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--csv-package",
        type=Path,
        default=Path(
            "data/processed/edr/group3_csv_final_v1"
        ),
    )

    parser.add_argument(
        "--pdf-package",
        type=Path,
        default=Path(
            "data/processed/edr/group3_pdf_final_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_final_v1"
        ),
    )

    args = parser.parse_args()

    csv_dir = args.csv_package
    pdf_dir = args.pdf_package
    out = args.output_directory

    csv_manifest = load_freeze_manifest(csv_dir)
    pdf_manifest = load_freeze_manifest(pdf_dir)

    required_names = [
        "condition_registry.csv",
        "condition_values.csv",
        "explicit_review_evidence.csv",
    ]

    for package in [csv_dir, pdf_dir]:
        for filename in required_names:
            path = package / filename
            if not path.exists():
                raise FileNotFoundError(path)

    csv_registry = read_csv(
        csv_dir / "condition_registry.csv"
    )
    pdf_registry = read_csv(
        pdf_dir / "condition_registry.csv"
    )

    csv_values = read_csv(
        csv_dir / "condition_values.csv"
    )
    pdf_values = read_csv(
        pdf_dir / "condition_values.csv"
    )

    csv_review = read_csv(
        csv_dir / "explicit_review_evidence.csv"
    )
    pdf_review = read_csv(
        pdf_dir / "explicit_review_evidence.csv"
    )

    for row in csv_registry:
        row["source_package"] = "group3_csv_final_v1"

    for row in pdf_registry:
        row["source_package"] = "group3_pdf_final_v1"

    for row in csv_values:
        row["source_package"] = "group3_csv_final_v1"

    for row in pdf_values:
        row["source_package"] = "group3_pdf_final_v1"

    for row in csv_review:
        row["source_package"] = "group3_csv_final_v1"

    for row in pdf_review:
        row["source_package"] = "group3_pdf_final_v1"

    registry = csv_registry + pdf_registry
    values = csv_values + pdf_values
    review = csv_review + pdf_review

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
            "check": name,
            "status": "PASS" if condition else "FAIL",
            "severity": severity,
            "observed": str(observed),
            "expected": str(expected),
            "note": note,
        })

    # --------------------------------------------------------
    # Expected counts
    # --------------------------------------------------------

    check(
        "csv_registry_expected_count",
        len(csv_registry) == 37065,
        len(csv_registry),
        37065,
    )

    check(
        "pdf_registry_expected_count",
        len(pdf_registry) == 538,
        len(pdf_registry),
        538,
    )

    check(
        "integrated_registry_expected_count",
        len(registry) == 37603,
        len(registry),
        37603,
    )

    check(
        "integrated_values_expected_count",
        len(values) == 37603,
        len(values),
        37603,
    )

    check(
        "integrated_review_expected_count",
        len(review) == 23757,
        len(review),
        23757,
        severity="warning",
        note=(
            "Expected from 23,264 CSV + 493 PDF textual/non-scalar "
            "explicit review-evidence rows."
        ),
    )

    # --------------------------------------------------------
    # IDs
    # --------------------------------------------------------

    registry_ids = [
        norm(row.get("group3_condition_id", ""))
        for row in registry
    ]

    value_ids = [
        norm(row.get("group3_condition_id", ""))
        for row in values
    ]

    check(
        "blank_condition_ids",
        sum(1 for x in registry_ids if not x) == 0,
        sum(1 for x in registry_ids if not x),
        0,
    )

    duplicate_ids = (
        len(registry_ids)
        - len(set(registry_ids))
    )

    check(
        "duplicate_condition_ids",
        duplicate_ids == 0,
        duplicate_ids,
        0,
    )

    check(
        "registry_value_id_sets_equal",
        set(registry_ids) == set(value_ids),
        len(set(registry_ids) ^ set(value_ids)),
        0,
    )

    # --------------------------------------------------------
    # Source provenance
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
        "source_package_counts_expected",
        (
            source_package_counts.get(
                "group3_csv_final_v1", 0
            ) == 37065
            and source_package_counts.get(
                "group3_pdf_final_v1", 0
            ) == 538
        ),
        dict(source_package_counts),
        {
            "group3_csv_final_v1": 37065,
            "group3_pdf_final_v1": 538,
        },
    )

    check(
        "source_format_counts_expected",
        (
            source_format_counts.get("csv", 0) == 37065
            and source_format_counts.get("pdf", 0) == 538
        ),
        dict(source_format_counts),
        {
            "csv": 37065,
            "pdf": 538,
        },
    )

    csv_format_mismatch = sum(
        1
        for row in registry
        if (
            norm(row.get("source_package", ""))
            == "group3_csv_final_v1"
            and norm(row.get("source_format", ""))
            != "csv"
        )
    )

    pdf_format_mismatch = sum(
        1
        for row in registry
        if (
            norm(row.get("source_package", ""))
            == "group3_pdf_final_v1"
            and norm(row.get("source_format", ""))
            != "pdf"
        )
    )

    check(
        "csv_source_format_consistency",
        csv_format_mismatch == 0,
        csv_format_mismatch,
        0,
    )

    check(
        "pdf_source_format_consistency",
        pdf_format_mismatch == 0,
        pdf_format_mismatch,
        0,
    )

    # --------------------------------------------------------
    # Reports / cases
    # --------------------------------------------------------

    csv_reports = {
        norm(row.get("report_id", ""))
        for row in csv_registry
        if norm(row.get("report_id", ""))
    }

    pdf_reports = {
        norm(row.get("report_id", ""))
        for row in pdf_registry
        if norm(row.get("report_id", ""))
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
        "integrated_report_count_expected",
        len(all_reports) == 1352,
        len(all_reports),
        1352,
    )

    csv_cases = {
        norm(row.get("case_id", ""))
        for row in csv_registry
        if norm(row.get("case_id", ""))
    }

    pdf_cases = {
        norm(row.get("case_id", ""))
        for row in pdf_registry
        if norm(row.get("case_id", ""))
    }

    case_overlap = csv_cases & pdf_cases
    all_cases = csv_cases | pdf_cases

    # Case overlap is valid and preserved.
    check(
        "case_union_accounting",
        len(all_cases)
        == (
            len(csv_cases)
            + len(pdf_cases)
            - len(case_overlap)
        ),
        len(all_cases),
        len(csv_cases)
        + len(pdf_cases)
        - len(case_overlap),
    )

    # --------------------------------------------------------
    # Family accounting
    # --------------------------------------------------------

    family_counts = Counter(
        norm(row.get("family", ""))
        for row in registry
    )

    check(
        "family_counts_sum_to_registry",
        sum(family_counts.values()) == 37603,
        sum(family_counts.values()),
        37603,
    )

    # --------------------------------------------------------
    # Frozen-source manifests agree with loaded counts
    # --------------------------------------------------------

    check(
        "csv_manifest_registry_count",
        csv_manifest.get("condition_registry_count")
        == len(csv_registry),
        csv_manifest.get("condition_registry_count"),
        len(csv_registry),
    )

    check(
        "pdf_manifest_registry_count",
        pdf_manifest.get("condition_registry_count")
        == len(pdf_registry),
        pdf_manifest.get("condition_registry_count"),
        len(pdf_registry),
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    hard_failures = [
        row
        for row in checks
        if row["status"] == "FAIL"
        and row["severity"] == "hard"
    ]

    warning_failures = [
        row
        for row in checks
        if row["status"] == "FAIL"
        and row["severity"] == "warning"
    ]

    out.mkdir(parents=True, exist_ok=True)

    registry_columns = union_columns(
        csv_registry,
        pdf_registry,
    )

    value_columns = union_columns(
        csv_values,
        pdf_values,
    )

    review_columns = union_columns(
        csv_review,
        pdf_review,
    )

    write_csv(
        out / "condition_registry.csv",
        registry,
        registry_columns,
    )

    write_csv(
        out / "condition_values.csv",
        values,
        value_columns,
    )

    write_csv(
        out / "explicit_review_evidence.csv",
        review,
        review_columns,
    )

    source_package_summary = [
        {
            "source_package": "group3_csv_final_v1",
            "source_format": "csv",
            "condition_count": len(csv_registry),
            "report_count": len(csv_reports),
            "case_count": len(csv_cases),
            "review_evidence_count": len(csv_review),
        },
        {
            "source_package": "group3_pdf_final_v1",
            "source_format": "pdf",
            "condition_count": len(pdf_registry),
            "report_count": len(pdf_reports),
            "case_count": len(pdf_cases),
            "review_evidence_count": len(pdf_review),
        },
    ]

    write_csv(
        out / "source_package_summary.csv",
        source_package_summary,
        [
            "source_package",
            "source_format",
            "condition_count",
            "report_count",
            "case_count",
            "review_evidence_count",
        ],
    )

    family_summary = [
        {
            "family": family,
            "condition_count": count,
        }
        for family, count
        in family_counts.most_common()
    ]

    write_csv(
        out / "family_summary.csv",
        family_summary,
        [
            "family",
            "condition_count",
        ],
    )

    write_csv(
        out / "validation_checks.csv",
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

    metadata = {
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 3 - Event conditions, deployment, and status information",

        "stage":
            "CSV + PDF integration",

        "integration_status":
            (
                "validated_ready_for_final_freeze"
                if not hard_failures
                else "integration_failed"
            ),

        "structured_condition_count":
            len(registry),

        "condition_value_count":
            len(values),

        "explicit_review_evidence_count":
            len(review),

        "reports_with_structured_conditions":
            len(all_reports),

        "cases_with_structured_conditions":
            len(all_cases),

        "source_condition_counts":
            {
                "csv": len(csv_registry),
                "pdf": len(pdf_registry),
            },

        "source_report_counts":
            {
                "csv": len(csv_reports),
                "pdf": len(pdf_reports),
            },

        "source_case_counts":
            {
                "csv": len(csv_cases),
                "pdf": len(pdf_cases),
            },

        "csv_pdf_report_overlap":
            len(report_overlap),

        "csv_pdf_case_overlap":
            len(case_overlap),

        "family_counts":
            dict(family_counts),

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

        "scope":
            (
                "Integration of the frozen Group 3 CSV and PDF-only source "
                "packages. Frozen source rows are preserved and only "
                "source_package provenance is added. No extraction, semantic "
                "normalization, unit conversion, fuzzy event linking, or "
                "mutation of either source package is performed. CSV-backed "
                "and PDF-only report populations must remain disjoint."
            ),
    }

    tmp = out / "metadata.json.part"
    tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(out / "metadata.json")

    print()
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print()
    print(f"Outputs: {out}")

    if hard_failures:
        print()
        print("GROUP 3 FINAL INTEGRATION HAS HARD VALIDATION FAILURES.")
        raise SystemExit(1)

    print()
    print("GROUP 3 CSV + PDF INTEGRATION COMPLETE.")


if __name__ == "__main__":
    main()
