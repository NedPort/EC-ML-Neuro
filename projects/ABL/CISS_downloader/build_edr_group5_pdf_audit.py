"""
Audit Group 5 PDF-only discovery candidates.

Input
-----
data/processed/edr/group5_pdf_discovery_v1/
    group5_pdf_candidate_fields.csv
    group5_pdf_review_fields.csv
    group5_pdf_report_coverage.csv

Output
------
data/processed/edr/group5_pdf_audit_v1/

    accepted_group5_pdf_fields.csv
    excluded_pdf_parse_artifacts.csv
    remaining_review_fields.csv
    audit_all_fields.csv
    family_summary.csv
    label_summary.csv
    report_summary.csv
    validation_checks.csv
    metadata.json

Purpose
-------
Audit the 619 PDF discovery candidates before structural extraction.

Key policy
----------
- Preserve numeric, N/A/SNA, and explicit "No" values exactly as reported.
- "Clipping Time ... = No" is retained as source-reported Group 5 evidence.
  It is not converted to zero or interpreted semantically.
- Exclude clear PDF line-splitting artifacts such as:
      Maximum Delta-V, Lateral Left to | Right
  where "Right" is part of the label phrase "Left to Right", not a value.
- Preserve page, line, section, event hint, source line, and PDF provenance.
- Do not normalize values, convert units, or infer event identity.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").strip(),
    )


def is_numeric(value):
    text = norm(value).replace(",", "")

    if not text:
        return False

    return bool(
        re.fullmatch(
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?",
            text,
        )
    )


def classify_candidate(row):
    label = norm(row.get("field_label_raw", ""))
    value = norm(row.get("field_value_raw", ""))
    source_line = norm(row.get("source_line_raw", ""))

    # Clear PDF parsing artifact:
    # source phrase is "Maximum Delta-V, Lateral Left to Right"
    # but generic label/value splitting interpreted "Right" as the value.
    if (
        re.search(
            r"\bmaximum delta[- ]?v,\s*lateral left to$",
            label,
            re.I,
        )
        and value.casefold() == "right"
        and re.search(
            r"\bmaximum delta[- ]?v,\s*lateral left to right\b",
            source_line,
            re.I,
        )
    ):
        return (
            "exclude",
            "pdf_label_split_artifact",
            "Right is part of the directional label phrase Left to Right.",
        )

    # All discovered Group 5 candidates otherwise remain accepted.
    # Explicit No/SNA values are valid source-reported values and are
    # intentionally preserved rather than forced to numeric.
    return (
        "accept",
        "accepted_group5_pdf_candidate",
        "Discovery rule and source-line audit support Group 5 membership.",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--discovery-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group5_pdf_discovery_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group5_pdf_audit_v1"
        ),
    )

    args = parser.parse_args()

    cand_path = (
        args.discovery_directory
        / "group5_pdf_candidate_fields.csv"
    )
    review_path = (
        args.discovery_directory
        / "group5_pdf_review_fields.csv"
    )
    coverage_path = (
        args.discovery_directory
        / "group5_pdf_report_coverage.csv"
    )

    for path in [
        cand_path,
        review_path,
        coverage_path,
    ]:
        if not path.exists():
            raise FileNotFoundError(path)

    candidates = read_csv(cand_path)
    discovery_review = read_csv(review_path)
    coverage = read_csv(coverage_path)

    audited = []

    for row in candidates:
        decision, status, reason = classify_candidate(row)

        audited.append({
            **row,
            "audit_decision": decision,
            "audit_status": status,
            "audit_reason": reason,
        })

    # There were zero discovery review fields in the current package,
    # but preserve the mechanism in case of reruns.
    for row in discovery_review:
        audited.append({
            **row,
            "audit_decision": "review",
            "audit_status": "remaining_review",
            "audit_reason": "Retained from PDF discovery review population.",
        })

    accepted = [
        row
        for row in audited
        if row["audit_decision"] == "accept"
    ]

    excluded = [
        row
        for row in audited
        if row["audit_decision"] == "exclude"
    ]

    remaining_review = [
        row
        for row in audited
        if row["audit_decision"] == "review"
    ]

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

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

    check(
        "input_candidate_count",
        len(candidates) == 619,
        len(candidates),
        619,
        severity="warning",
    )

    check(
        "discovery_review_count",
        len(discovery_review) == 0,
        len(discovery_review),
        0,
        severity="warning",
    )

    check(
        "all_candidate_rows_accounted_for",
        (
            len(accepted)
            + len(excluded)
            + len(remaining_review)
            == len(candidates)
            + len(discovery_review)
        ),
        (
            len(accepted)
            + len(excluded)
            + len(remaining_review)
        ),
        (
            len(candidates)
            + len(discovery_review)
        ),
    )

    ids = [
        norm(row.get("group5_pdf_candidate_id", ""))
        for row in accepted
    ]

    check(
        "accepted_candidate_ids_unique",
        len(ids) == len(set(ids)),
        len(ids) - len(set(ids)),
        0,
    )

    blank_labels = sum(
        1
        for row in accepted
        if not norm(row.get("field_label_raw", ""))
    )

    blank_values = sum(
        1
        for row in accepted
        if not norm(row.get("field_value_raw", ""))
    )

    check(
        "blank_accepted_labels",
        blank_labels == 0,
        blank_labels,
        0,
    )

    check(
        "blank_accepted_values",
        blank_values == 0,
        blank_values,
        0,
    )

    provenance_missing = sum(
        1
        for row in accepted
        if (
            not norm(row.get("source_path", ""))
            or not norm(row.get("source_page_number", ""))
            or not norm(row.get("source_line_number_on_page", ""))
            or not norm(row.get("source_line_raw", ""))
        )
    )

    check(
        "accepted_provenance_complete",
        provenance_missing == 0,
        provenance_missing,
        0,
    )

    # The only expected clear parse artifacts in this current discovery
    # are the two "Left to Right" rows.
    left_to_right_artifacts = sum(
        1
        for row in excluded
        if row["audit_status"]
        == "pdf_label_split_artifact"
    )

    check(
        "expected_left_to_right_parse_artifacts",
        left_to_right_artifacts == 2,
        left_to_right_artifacts,
        2,
        severity="warning",
    )

    # --------------------------------------------------------
    # Summaries
    # --------------------------------------------------------

    family_counter = Counter(
        row.get("candidate_family", "")
        for row in accepted
    )

    label_counter = Counter(
        norm(row.get("field_label_raw", ""))
        for row in accepted
    )

    report_counter = Counter(
        row.get("report_id", "")
        for row in accepted
    )

    family_summary = [
        {
            "candidate_family": family,
            "accepted_field_count": count,
            "report_count": len({
                row.get("report_id", "")
                for row in accepted
                if row.get("candidate_family", "") == family
            }),
        }
        for family, count
        in family_counter.most_common()
    ]

    label_summary = [
        {
            "field_label_raw": label,
            "accepted_field_count": count,
        }
        for label, count
        in label_counter.most_common()
    ]

    coverage_by_report = {
        row.get("report_id", ""): row
        for row in coverage
    }

    report_summary = []

    for report_id, count in report_counter.items():
        c = coverage_by_report.get(
            report_id,
            {},
        )

        report_summary.append({
            "report_id": report_id,
            "case_id": c.get("case_id", ""),
            "vehicle_number": c.get("vehicle_number", ""),
            "export_basename": c.get("export_basename", ""),
            "accepted_group5_pdf_fields": count,
        })

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)

    columns = list(audited[0].keys()) if audited else []

    write_csv(
        out / "accepted_group5_pdf_fields.csv",
        accepted,
        columns,
    )

    write_csv(
        out / "excluded_pdf_parse_artifacts.csv",
        excluded,
        columns,
    )

    write_csv(
        out / "remaining_review_fields.csv",
        remaining_review,
        columns,
    )

    write_csv(
        out / "audit_all_fields.csv",
        audited,
        columns,
    )

    write_csv(
        out / "family_summary.csv",
        family_summary,
        [
            "candidate_family",
            "accepted_field_count",
            "report_count",
        ],
    )

    write_csv(
        out / "label_summary.csv",
        label_summary,
        [
            "field_label_raw",
            "accepted_field_count",
        ],
    )

    write_csv(
        out / "report_summary.csv",
        report_summary,
        [
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "accepted_group5_pdf_fields",
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

    explicit_no_count = sum(
        1
        for row in accepted
        if norm(
            row.get("field_value_raw", "")
        ).casefold() == "no"
    )

    sna_count = sum(
        1
        for row in accepted
        if norm(
            row.get("field_value_raw", "")
        ).casefold() == "sna"
    )

    numeric_count = sum(
        1
        for row in accepted
        if is_numeric(
            row.get("field_value_raw", "")
        )
    )

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "PDF-only candidate audit",

        "input_candidate_fields":
            len(candidates),

        "input_review_fields":
            len(discovery_review),

        "accepted_group5_pdf_fields":
            len(accepted),

        "excluded_pdf_parse_artifacts":
            len(excluded),

        "remaining_review_fields":
            len(remaining_review),

        "reports_with_accepted_group5_pdf_fields":
            len(report_counter),

        "accepted_family_counts":
            dict(family_counter),

        "numeric_raw_value_count":
            numeric_count,

        "explicit_no_value_count":
            explicit_no_count,

        "sna_value_count":
            sna_count,

        "validation_checks":
            len(checks),

        "hard_validation_failures":
            len(hard_failures),

        "warning_validation_failures":
            len(warning_failures),

        "scope":
            (
                "Audit of Group 5 PDF-only discovery candidates. "
                "Clear PDF line-splitting artifacts are excluded. "
                "Explicit No and SNA values in clipping-time fields are "
                "preserved exactly as source-reported evidence rather than "
                "converted or semantically interpreted. Page/line/source "
                "provenance remains intact. No unit conversion, semantic "
                "normalization, OCR, fuzzy event linking, or final "
                "structural extraction is performed."
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
    print(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(f"Outputs: {out}")

    if hard_failures:
        print()
        print(
            "GROUP 5 PDF AUDIT HAS HARD VALIDATION FAILURES."
        )
        raise SystemExit(1)

    print()
    print(
        "GROUP 5 PDF AUDIT COMPLETE."
    )


if __name__ == "__main__":
    main()
