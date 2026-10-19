"""
Validate and freeze the structured Group 3 PDF-only package.

Input
-----
data/processed/edr/group3_pdf_structured_v1/

Output
------
data/processed/edr/group3_pdf_final_v1/

Checks
------
- expected row counts
- registry/value ID consistency
- duplicate IDs
- report/case identifiers
- family completeness
- PDF provenance completeness
- independent numeric parsing
- missing/unavailable flags
- duplicate source observations
- inherited extraction validation

No OCR, re-extraction, semantic normalization, unit conversion,
or fuzzy event linking is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
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
    return re.sub(r"\s+", " ", str(value if value is not None else "").strip())


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


MISSING_VALUES = {
    "",
    "n/a",
    "na",
    "sna",
    "not available",
    "not applicable",
    "unknown",
    "invalid",
    "data not available",
    "no data",
}

NUMERIC_RE = re.compile(
    r"""
    ^\s*
    (?P<num>
        [-+]?
        (?:
            \d+(?:\.\d*)?
            |
            \.\d+
        )
        (?:[eE][-+]?\d+)?
    )
    \s*
    (?P<unit>
        %
        |
        mph
        |
        km/h
        |
        kph
        |
        m/s
        |
        m/s\^2
        |
        m/s2
        |
        g
        |
        ms
        |
        msec
        |
        milliseconds?
        |
        sec
        |
        seconds?
        |
        s
        |
        V
        |
        volts?
        |
        cycles?
        |
        min
        |
        minutes?
        |
        deg
        |
        degrees?
    )?
    \s*$
    """,
    re.I | re.X,
)


def independent_parse(raw):
    text = norm(raw)

    if text.casefold() in MISSING_VALUES:
        return "missing_or_unavailable", None

    match = NUMERIC_RE.fullmatch(text.replace(",", ""))

    if not match:
        return "textual_or_non_scalar", None

    try:
        return "numeric_scalar", float(match.group("num"))
    except Exception:
        return "numeric_parse_failed", None


def safe_float(value):
    text = norm(value)
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--structured-directory",
        type=Path,
        default=Path("data/processed/edr/group3_pdf_structured_v1"),
    )

    parser.add_argument(
        "--final-directory",
        type=Path,
        default=Path("data/processed/edr/group3_pdf_final_v1"),
    )

    args = parser.parse_args()

    src = args.structured_directory
    out = args.final_directory

    required = {
        "registry": src / "condition_registry.csv",
        "values": src / "condition_values.csv",
        "failures": src / "extraction_failures.csv",
        "family_summary": src / "family_summary.csv",
        "validation_checks": src / "validation_checks.csv",
        "metadata": src / "metadata.json",
    }

    for name, path in required.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {name}: {path}")

    registry = read_csv(required["registry"])
    values = read_csv(required["values"])
    failures = read_csv(required["failures"])
    family_summary = read_csv(required["family_summary"])
    inherited_checks = read_csv(required["validation_checks"])
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

    # Counts
    check("registry_expected_count", len(registry) == 538, len(registry), 538)
    check("values_expected_count", len(values) == 538, len(values), 538)
    check("extraction_failures_zero", len(failures) == 0, len(failures), 0)

    # IDs
    registry_ids = [norm(r.get("group3_condition_id", "")) for r in registry]
    value_ids = [norm(r.get("group3_condition_id", "")) for r in values]

    check(
        "blank_condition_ids",
        sum(1 for x in registry_ids if not x) == 0,
        sum(1 for x in registry_ids if not x),
        0,
    )

    duplicate_ids = len(registry_ids) - len(set(registry_ids))

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

    # Required provenance
    required_fields = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "source_format",
        "source_path",
        "pdf_page",
        "pdf_line_number",
        "source_line_raw",
        "family",
        "field_label_raw",
    ]

    blank_required = Counter()

    for row in registry:
        for field in required_fields:
            if not norm(row.get(field, "")):
                blank_required[field] += 1

    check(
        "required_pdf_provenance_complete",
        sum(blank_required.values()) == 0,
        sum(blank_required.values()),
        0,
        note=json.dumps(dict(blank_required), ensure_ascii=False),
    )

    # Source format
    source_formats = Counter(
        norm(row.get("source_format", ""))
        for row in registry
    )

    check(
        "source_format_pdf_only",
        set(source_formats) == {"pdf"},
        dict(source_formats),
        "{'pdf': 538}",
    )

    # Reports/cases
    reports = {
        norm(row.get("report_id", ""))
        for row in registry
        if norm(row.get("report_id", ""))
    }

    cases = {
        norm(row.get("case_id", ""))
        for row in registry
        if norm(row.get("case_id", ""))
    }

    check("report_count_expected", len(reports) == 163, len(reports), 163)
    check("case_count_expected", len(cases) == 158, len(cases), 158)

    # Family accounting
    family_counts = Counter(
        norm(row.get("family", ""))
        for row in registry
    )

    check(
        "family_counts_sum_to_registry",
        sum(family_counts.values()) == len(registry),
        sum(family_counts.values()),
        len(registry),
    )

    # Value audit
    values_by_id = {
        norm(row.get("group3_condition_id", "")): row
        for row in values
    }

    parse_disagreements = []
    missing_flag_disagreements = []
    numeric_value_disagreements = []

    for reg in registry:
        cid = norm(reg.get("group3_condition_id", ""))
        raw = norm(reg.get("field_value_raw", ""))

        val = values_by_id.get(cid)

        if val is None:
            continue

        expected_status, expected_number = independent_parse(raw)
        stored_status = norm(val.get("value_parse_status", ""))
        stored_number = safe_float(val.get("numeric_value", ""))

        if expected_status != stored_status:
            parse_disagreements.append(cid)

        expected_missing = expected_status == "missing_or_unavailable"
        stored_missing = (
            norm(val.get("missing_or_unavailable", "")).casefold() == "true"
        )

        if expected_missing != stored_missing:
            missing_flag_disagreements.append(cid)

        if expected_status == "numeric_scalar":
            if (
                stored_number is None
                or expected_number is None
                or not math.isclose(
                    stored_number,
                    expected_number,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            ):
                numeric_value_disagreements.append(cid)

    check(
        "numeric_parse_status_disagreements",
        len(parse_disagreements) == 0,
        len(parse_disagreements),
        0,
    )

    check(
        "missing_flag_disagreements",
        len(missing_flag_disagreements) == 0,
        len(missing_flag_disagreements),
        0,
    )

    check(
        "numeric_value_disagreements",
        len(numeric_value_disagreements) == 0,
        len(numeric_value_disagreements),
        0,
    )

    # Duplicate source observations
    source_keys = [
        (
            norm(row.get("source_path", "")),
            norm(row.get("pdf_page", "")),
            norm(row.get("pdf_line_number", "")),
            norm(row.get("field_label_raw", "")),
            norm(row.get("field_value_raw", "")),
        )
        for row in registry
    ]

    duplicate_source_observations = (
        len(source_keys) - len(set(source_keys))
    )

    check(
        "duplicate_source_observations",
        duplicate_source_observations == 0,
        duplicate_source_observations,
        0,
    )

    # Inherited validation
    inherited_hard = sum(
        1
        for row in inherited_checks
        if (
            norm(row.get("status", "")).upper() == "FAIL"
            and norm(row.get("severity", "")).casefold() == "hard"
        )
    )

    inherited_warning = sum(
        1
        for row in inherited_checks
        if (
            norm(row.get("status", "")).upper() == "FAIL"
            and norm(row.get("severity", "")).casefold() == "warning"
        )
    )

    check(
        "inherited_hard_validation_failures",
        inherited_hard == 0,
        inherited_hard,
        0,
    )

    check(
        "inherited_warning_validation_failures",
        inherited_warning == 0,
        inherited_warning,
        0,
        severity="warning",
    )

    # Explicit review evidence for textual values
    registry_by_id = {
        norm(row.get("group3_condition_id", "")): row
        for row in registry
    }

    textual_rows = [
        row
        for row in values
        if norm(row.get("value_parse_status", ""))
        == "textual_or_non_scalar"
    ]

    missing_rows = [
        row
        for row in values
        if norm(row.get("value_parse_status", ""))
        == "missing_or_unavailable"
    ]

    numeric_rows = [
        row
        for row in values
        if norm(row.get("value_parse_status", ""))
        == "numeric_scalar"
    ]

    review_rows = []

    for row in textual_rows:
        cid = norm(row.get("group3_condition_id", ""))
        reg = registry_by_id.get(cid)

        if reg is not None:
            review_rows.append({
                "group3_condition_id": cid,
                "report_id": reg.get("report_id", ""),
                "case_id": reg.get("case_id", ""),
                "vehicle_number": reg.get("vehicle_number", ""),
                "pdf_page": reg.get("pdf_page", ""),
                "pdf_line_number": reg.get("pdf_line_number", ""),
                "family": reg.get("family", ""),
                "field_label_raw": reg.get("field_label_raw", ""),
                "field_value_raw": reg.get("field_value_raw", ""),
                "review_reason":
                    "textual_or_non_scalar_value_preserved_as_raw_state",
            })

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
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 3 - Event conditions, deployment, and status information",

        "stage":
            "PDF-only validation and freeze",

        "condition_registry_count":
            len(registry),

        "condition_values_count":
            len(values),

        "extraction_failure_count":
            len(failures),

        "report_count":
            len(reports),

        "case_count":
            len(cases),

        "numeric_value_count":
            len(numeric_rows),

        "missing_or_unavailable_count":
            len(missing_rows),

        "textual_or_non_scalar_count":
            len(textual_rows),

        "numeric_parse_disagreements":
            len(parse_disagreements),

        "missing_flag_disagreements":
            len(missing_flag_disagreements),

        "numeric_value_disagreements":
            len(numeric_value_disagreements),

        "duplicate_source_observations":
            duplicate_source_observations,

        "explicit_review_evidence_rows":
            len(review_rows),

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
                "validated_ready_for_freeze"
                if not hard_failures
                else "validation_failed"
            ),

        "scope":
            (
                "Validation of the structured Group 3 PDF-only package. "
                "Checks cover counts, ID integrity, PDF provenance, family "
                "accounting, independent numeric parsing, missing-value flags, "
                "duplicate source observations, report/case coverage, and "
                "inherited extraction checks. Textual event states are preserved "
                "as explicit review evidence. No OCR, re-extraction, semantic "
                "normalization, unit conversion, fuzzy event linking, or source "
                "mutation is performed."
            ),
    }

    print()
    print(json.dumps(validation_metadata, indent=2, ensure_ascii=False))

    if hard_failures:
        raise SystemExit(
            "GROUP 3 PDF VALIDATION FAILED. Package was not frozen."
        )

    # Freeze
    if out.exists():
        shutil.rmtree(out)

    out.mkdir(parents=True, exist_ok=True)

    core_files = [
        "condition_registry.csv",
        "condition_values.csv",
        "extraction_failures.csv",
        "family_summary.csv",
        "validation_checks.csv",
        "metadata.json",
    ]

    for filename in core_files:
        shutil.copy2(src / filename, out / filename)

    write_csv(
        out / "explicit_review_evidence.csv",
        review_rows,
        [
            "group3_condition_id",
            "report_id",
            "case_id",
            "vehicle_number",
            "pdf_page",
            "pdf_line_number",
            "family",
            "field_label_raw",
            "field_value_raw",
            "review_reason",
        ],
    )

    write_csv(
        out / "freeze_validation_checks.csv",
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
        out / "freeze_validation_metadata.json"
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
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 3 - Event conditions, deployment, and status information",

        "source_package":
            str(src),

        "freeze_status":
            "frozen_validated_with_explicit_review_evidence",

        "condition_registry_count":
            len(registry),

        "condition_values_count":
            len(values),

        "report_count":
            len(reports),

        "case_count":
            len(cases),

        "numeric_value_count":
            len(numeric_rows),

        "missing_or_unavailable_count":
            len(missing_rows),

        "textual_or_non_scalar_count":
            len(textual_rows),

        "explicit_review_evidence_rows":
            len(review_rows),

        "hard_validation_failures":
            len(hard_failures),

        "warning_validation_failures":
            len(warning_failures),

        "immutable_intent":
            (
                "This package is the frozen validated Group 3 PDF-only source "
                "package. Do not modify unless a concrete validation or "
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
    print(json.dumps(freeze_manifest, indent=2, ensure_ascii=False))
    print()
    print(f"Frozen package: {out}")
    print()
    print("GROUP 3 PDF VALIDATION AND FREEZE COMPLETE.")


if __name__ == "__main__":
    main()
