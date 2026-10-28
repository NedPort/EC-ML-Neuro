"""
Final-validate and freeze the integrated Group 6 package.

Input
-----
data/processed/edr/group6_final_v1/

Output
------
data/processed/edr/group6_final_frozen_v1/

The script performs final integrity validation only.
It does not re-extract, normalize, convert units, infer semantics,
or modify the frozen CSV/PDF source packages.
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
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def norm(value):
    return " ".join(str(value if value is not None else "").split())


def sha256_file(path: Path):
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
        default=Path("data/processed/edr/group6_final_v1"),
    )

    parser.add_argument(
        "--final-directory",
        type=Path,
        default=Path("data/processed/edr/group6_final_frozen_v1"),
    )

    args = parser.parse_args()

    src = args.integrated_directory
    out = args.final_directory

    required = {
        "registry": src / "technical_registry.csv",
        "values": src / "technical_values.csv",
        "review": src / "explicit_review_evidence.csv",
        "source_summary": src / "source_package_summary.csv",
        "family_summary": src / "family_summary.csv",
        "validation_checks": src / "validation_checks.csv",
        "metadata": src / "metadata.json",
    }

    for name, path in required.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {name}: {path}")

    registry = read_csv(required["registry"])
    values = read_csv(required["values"])
    review = read_csv(required["review"])
    prior_checks = read_csv(required["validation_checks"])
    metadata = json.loads(required["metadata"].read_text(encoding="utf-8"))

    checks = []

    def check(name, condition, observed, expected, severity="hard", note=""):
        checks.append({
            "check": name,
            "status": "PASS" if condition else "FAIL",
            "severity": severity,
            "observed": str(observed),
            "expected": str(expected),
            "note": note,
        })

    check("registry_expected_count", len(registry) == 13618, len(registry), 13618)
    check("values_expected_count", len(values) == 13618, len(values), 13618)
    check("review_expected_count", len(review) == 8637, len(review), 8637)

    registry_ids = [norm(r.get("group6_technical_id", "")) for r in registry]
    value_ids = [norm(r.get("group6_technical_id", "")) for r in values]

    check(
        "blank_technical_ids",
        sum(1 for x in registry_ids if not x) == 0,
        sum(1 for x in registry_ids if not x),
        0,
    )

    duplicate_ids = len(registry_ids) - len(set(registry_ids))

    check(
        "duplicate_technical_ids",
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

    source_package_counts = Counter(
        norm(r.get("source_package", ""))
        for r in registry
    )

    source_format_counts = Counter(
        norm(r.get("source_format", ""))
        for r in registry
    )

    check(
        "source_package_counts_expected",
        (
            source_package_counts.get("group6_csv_final_v1", 0) == 13202
            and source_package_counts.get("group6_pdf_final_v1", 0) == 416
        ),
        dict(source_package_counts),
        {
            "group6_csv_final_v1": 13202,
            "group6_pdf_final_v1": 416,
        },
    )

    check(
        "source_format_counts_expected",
        (
            source_format_counts.get("csv", 0) == 13202
            and source_format_counts.get("pdf", 0) == 416
        ),
        dict(source_format_counts),
        {"csv": 13202, "pdf": 416},
    )

    csv_reports = {
        norm(r.get("report_id", ""))
        for r in registry
        if (
            norm(r.get("source_format", "")) == "csv"
            and norm(r.get("report_id", ""))
        )
    }

    pdf_reports = {
        norm(r.get("report_id", ""))
        for r in registry
        if (
            norm(r.get("source_format", "")) == "pdf"
            and norm(r.get("report_id", ""))
        )
    }

    all_reports = csv_reports | pdf_reports
    report_overlap = csv_reports & pdf_reports

    check("report_count_expected", len(all_reports) == 1391, len(all_reports), 1391)
    check("csv_pdf_report_overlap_zero", len(report_overlap) == 0, len(report_overlap), 0)

    all_cases = {
        norm(r.get("case_id", ""))
        for r in registry
        if norm(r.get("case_id", ""))
    }

    check("case_count_expected", len(all_cases) == 1170, len(all_cases), 1170)

    family_counts = Counter(
        norm(row.get("family", ""))
        for row in registry
    )

    check(
        "family_counts_sum_to_registry",
        sum(family_counts.values()) == 13618,
        sum(family_counts.values()),
        13618,
    )

    inherited_hard = sum(
        1
        for row in prior_checks
        if (
            norm(row.get("status", "")).upper() == "FAIL"
            and norm(row.get("severity", "")).casefold() == "hard"
        )
    )

    inherited_warning = sum(
        1
        for row in prior_checks
        if (
            norm(row.get("status", "")).upper() == "FAIL"
            and norm(row.get("severity", "")).casefold() == "warning"
        )
    )

    check(
        "inherited_integration_hard_failures",
        inherited_hard == 0,
        inherited_hard,
        0,
    )

    check(
        "inherited_integration_warning_failures",
        inherited_warning == 0,
        inherited_warning,
        0,
        severity="warning",
    )

    check(
        "integration_status_ready_for_freeze",
        metadata.get("integration_status") == "validated_ready_for_final_freeze",
        metadata.get("integration_status"),
        "validated_ready_for_final_freeze",
    )

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

    validation_metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "group": "Group 6 - Other structured technical and investigation information",
        "stage": "final integrated validation",
        "structured_technical_count": len(registry),
        "technical_value_count": len(values),
        "explicit_review_evidence_count": len(review),
        "report_count": len(all_reports),
        "case_count": len(all_cases),
        "source_technical_counts": {
            "csv": source_format_counts.get("csv", 0),
            "pdf": source_format_counts.get("pdf", 0),
        },
        "csv_pdf_report_overlap": len(report_overlap),
        "validation_checks": len(checks),
        "validation_failures": sum(
            1 for row in checks if row["status"] == "FAIL"
        ),
        "hard_validation_failures": len(hard_failures),
        "warning_validation_failures": len(warning_failures),
        "validation_status": (
            "validated_ready_for_final_freeze"
            if not hard_failures
            else "validation_failed"
        ),
        "scope": (
            "Final integrity validation of the integrated Group 6 CSV + PDF "
            "package. Counts, IDs, source provenance, report/case coverage, "
            "family accounting, and inherited integration checks are validated. "
            "No extraction, semantic normalization, unit conversion, fuzzy "
            "inference, or source mutation is performed."
        ),
    }

    print()
    print(json.dumps(validation_metadata, indent=2, ensure_ascii=False))

    if hard_failures:
        raise SystemExit(
            "GROUP 6 FINAL VALIDATION FAILED. Package was not frozen."
        )

    if out.exists():
        shutil.rmtree(out)

    out.mkdir(parents=True, exist_ok=True)

    core_files = [
        "technical_registry.csv",
        "technical_values.csv",
        "explicit_review_evidence.csv",
        "source_package_summary.csv",
        "family_summary.csv",
        "validation_checks.csv",
        "metadata.json",
    ]

    for filename in core_files:
        shutil.copy2(src / filename, out / filename)

    validation_dir = out / "final_validation"
    validation_dir.mkdir(parents=True, exist_ok=True)

    write_csv(
        validation_dir / "final_validation_checks.csv",
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
        validation_dir / "metadata.json"
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
                "relative_path": str(path.relative_to(out)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })

    freeze_manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "group": "Group 6 - Other structured technical and investigation information",
        "source_package": str(src),
        "freeze_status": "frozen_validated_with_explicit_review_evidence",
        "structured_technical_count": len(registry),
        "technical_value_count": len(values),
        "explicit_review_evidence_count": len(review),
        "report_count": len(all_reports),
        "case_count": len(all_cases),
        "source_technical_counts": {
            "csv": source_format_counts.get("csv", 0),
            "pdf": source_format_counts.get("pdf", 0),
        },
        "csv_pdf_report_overlap": len(report_overlap),
        "hard_validation_failures": len(hard_failures),
        "warning_validation_failures": len(warning_failures),
        "immutable_intent": (
            "This package is the final frozen integrated Group 6 dataset. "
            "Do not modify unless a concrete validation or source-extraction "
            "error is demonstrated."
        ),
        "files": frozen_files,
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
    print(json.dumps(freeze_manifest, indent=2, ensure_ascii=False))
    print()
    print(f"Frozen package: {out}")
    print()
    print("GROUP 6 FINAL VALIDATION AND FREEZE COMPLETE.")


if __name__ == "__main__":
    main()
