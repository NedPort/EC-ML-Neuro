"""
Resolve all remaining Group 6 PDF review rows after exact-pattern audit.

Input
-----
data/processed/edr/group6_pdf_audit_v1/
    accepted_group6_pdf_fields.csv
    excluded_keyword_noise.csv
    remaining_review_fields.csv

Output
------
data/processed/edr/group6_pdf_resolved_v1/
    accepted_group6_pdf_fields.csv
    excluded_non_group6_fields.csv
    remaining_review_fields.csv
    review_resolution.csv
    family_summary.csv
    routing_summary.csv
    validation_checks.csv
    metadata.json

Resolution of the 771 review rows
---------------------------------
Accepted into Group 6:
- Ignition Cycle, Download (times) <value>
- Manufacturing Traceability Data, Serial/Lot/BatchNumber <value>
- Manufacturing Traceability Data, Year <value>
- Manufacturing Traceability Data, DayOfTheYear <value>

Routed to Group 3:
- Ignition Cycles At Deployment <value>
- Ignition Cycles At Non-Deployment <value>
- Ignition Cycle Key On Timer at Start of Frontal/Side Event ...

Excluded as documentation:
- software licensing header/footer text
- explanatory ignition-cycle prose
- CDR software/version narrative notices
- counter behavior documentation

No fuzzy inference is used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
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


def stable_id(*parts):
    text = "|".join(norm(x) for x in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def union_columns(*rowsets):
    seen = set()
    cols = []
    for rows in rowsets:
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    cols.append(key)
    return cols


def resolve_review(row):
    line = norm(row.get("source_line_raw", ""))

    m = re.fullmatch(
        r"(Ignition Cycle, Download \(times\))\s+(.+)",
        line,
        flags=re.I,
    )
    if m:
        return {
            "resolution": "accept",
            "route": "group6",
            "family": "ignition_cycle_readout",
            "label": norm(m.group(1)),
            "value": norm(m.group(2)),
            "reason": "download_ignition_cycle_count",
        }

    m = re.fullmatch(
        r"(Manufacturing Traceability Data, "
        r"(?:Serial/Lot/BatchNumber|Year|DayOfTheYear))\s+(.+)",
        line,
        flags=re.I,
    )
    if m:
        return {
            "resolution": "accept",
            "route": "group6",
            "family": "traceability_identifier",
            "label": norm(m.group(1)),
            "value": norm(m.group(2)),
            "reason": "manufacturing_traceability_field",
        }

    if re.fullmatch(
        r"Ignition Cycles At Deployment\s+.+",
        line,
        flags=re.I,
    ):
        return {
            "resolution": "exclude",
            "route": "group3",
            "family": "",
            "label": "",
            "value": "",
            "reason": "deployment_event_ignition_cycle",
        }

    if re.fullmatch(
        r"Ignition Cycles At Non-Deployment\s+.+",
        line,
        flags=re.I,
    ):
        return {
            "resolution": "exclude",
            "route": "group3",
            "family": "",
            "label": "",
            "value": "",
            "reason": "nondeployment_event_ignition_cycle",
        }

    if re.fullmatch(
        r"Ignition Cycle Key On Timer at Start of "
        r"(?:Frontal|Side) Event \(sec\)\s+.+",
        line,
        flags=re.I,
    ):
        return {
            "resolution": "exclude",
            "route": "group3",
            "family": "",
            "label": "",
            "value": "",
            "reason": "event_start_ignition_timer",
        }

    if re.match(
        r"^(?:Reported|Imaged) with Software Licensed to",
        line,
        flags=re.I,
    ):
        return {
            "resolution": "exclude",
            "route": "documentation",
            "family": "",
            "label": "",
            "value": "",
            "reason": "software_license_header",
        }

    if re.search(
        r"\b(?:ignition cycle|ignition cycles|ignition cycle counter)\b",
        line,
        flags=re.I,
    ):
        return {
            "resolution": "exclude",
            "route": "documentation",
            "family": "",
            "label": "",
            "value": "",
            "reason": "ignition_cycle_explanatory_text",
        }

    if re.search(r"\bsoftware\b", line, flags=re.I):
        return {
            "resolution": "exclude",
            "route": "documentation",
            "family": "",
            "label": "",
            "value": "",
            "reason": "software_documentation_text",
        }

    return {
        "resolution": "review",
        "route": "unresolved",
        "family": "",
        "label": "",
        "value": "",
        "reason": "no_exact_resolution_rule",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--audit-directory",
        type=Path,
        default=Path("data/processed/edr/group6_pdf_audit_v1"),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("data/processed/edr/group6_pdf_resolved_v1"),
    )

    args = parser.parse_args()

    src = args.audit_directory
    out = args.output_directory

    accepted_path = src / "accepted_group6_pdf_fields.csv"
    excluded_path = src / "excluded_keyword_noise.csv"
    review_path = src / "remaining_review_fields.csv"

    for path in [accepted_path, excluded_path, review_path]:
        if not path.exists():
            raise FileNotFoundError(path)

    prior_accepted = read_csv(accepted_path)
    prior_excluded = read_csv(excluded_path)
    review_rows = read_csv(review_path)

    if len(review_rows) != 771:
        raise RuntimeError(
            f"Expected 771 review rows, found {len(review_rows)}."
        )

    promoted = []
    newly_excluded = []
    unresolved = []
    resolution_log = []

    for row in review_rows:
        result = resolve_review(row)

        resolution_log.append({
            **row,
            "resolution": result["resolution"],
            "resolution_route": result["route"],
            "resolution_family": result["family"],
            "resolution_reason": result["reason"],
        })

        if result["resolution"] == "accept":
            candidate_id = (
                "g6pdf_"
                + stable_id(
                    row.get("report_id", ""),
                    row.get("pdf_page", ""),
                    row.get("pdf_line_number", ""),
                    result["label"],
                    result["value"],
                )
            )

            promoted.append({
                "report_id": row.get("report_id", ""),
                "case_id": row.get("case_id", ""),
                "vehicle_number": row.get("vehicle_number", ""),
                "export_basename": row.get("export_basename", ""),
                "group6_candidate_id": candidate_id,
                "source_format": "pdf",
                "source_path": row.get("source_path", ""),
                "pdf_page": row.get("pdf_page", ""),
                "pdf_line_number": row.get("pdf_line_number", ""),
                "source_line_raw": row.get("source_line_raw", ""),
                "field_label_raw": result["label"],
                "field_value_raw": result["value"],
                "audited_family": result["family"],
                "audit_decision": "accept",
                "audit_reason": result["reason"],
                "semantic_normalization_status": "not_normalized",
                "unit_conversion_status": "not_converted",
            })

        elif result["resolution"] == "exclude":
            newly_excluded.append({
                **row,
                "audit_decision": "exclude",
                "audit_route": result["route"],
                "audit_reason": result["reason"],
            })

        else:
            unresolved.append(row)

    final_accepted = prior_accepted + promoted

    normalized_prior_excluded = [
        {
            **row,
            "audit_route": (
                row.get("audit_route", "")
                or "previous_audit_exclusion"
            ),
        }
        for row in prior_excluded
    ]

    final_excluded = normalized_prior_excluded + newly_excluded

    family_counts = Counter(
        norm(row.get("audited_family", ""))
        for row in final_accepted
    )

    route_counts = Counter(
        norm(row.get("audit_route", ""))
        for row in final_excluded
    )

    resolution_counts = Counter(
        row["resolution"]
        for row in resolution_log
    )

    # Validation
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

    check("input_review_count", len(review_rows) == 771, len(review_rows), 771)
    check("promoted_group6_count", len(promoted) == 13, len(promoted), 13)
    check(
        "new_group3_exclusions",
        sum(1 for r in newly_excluded if r["audit_route"] == "group3") == 101,
        sum(1 for r in newly_excluded if r["audit_route"] == "group3"),
        101,
    )
    check(
        "new_documentation_exclusions",
        sum(
            1
            for r in newly_excluded
            if r["audit_route"] == "documentation"
        ) == 657,
        sum(
            1
            for r in newly_excluded
            if r["audit_route"] == "documentation"
        ),
        657,
    )
    check("remaining_review_zero", len(unresolved) == 0, len(unresolved), 0)
    check(
        "review_accounting_complete",
        len(promoted) + len(newly_excluded) + len(unresolved) == 771,
        len(promoted) + len(newly_excluded) + len(unresolved),
        771,
    )
    check(
        "final_accepted_count",
        len(final_accepted) == 416,
        len(final_accepted),
        416,
    )

    ids = [
        norm(row.get("group6_candidate_id", ""))
        for row in final_accepted
    ]
    check(
        "accepted_candidate_ids_unique",
        len(ids) == len(set(ids)),
        len(ids) - len(set(ids)),
        0,
    )

    hard_failures = sum(
        1
        for r in checks
        if r["status"] == "FAIL" and r["severity"] == "hard"
    )

    warning_failures = sum(
        1
        for r in checks
        if r["status"] == "FAIL" and r["severity"] == "warning"
    )

    out.mkdir(parents=True, exist_ok=True)

    accepted_cols = union_columns(final_accepted)
    excluded_cols = union_columns(final_excluded)
    resolution_cols = union_columns(resolution_log)

    write_csv(
        out / "accepted_group6_pdf_fields.csv",
        final_accepted,
        accepted_cols,
    )

    write_csv(
        out / "excluded_non_group6_fields.csv",
        final_excluded,
        excluded_cols,
    )

    write_csv(
        out / "remaining_review_fields.csv",
        unresolved,
        union_columns(review_rows),
    )

    write_csv(
        out / "review_resolution.csv",
        resolution_log,
        resolution_cols,
    )

    write_csv(
        out / "family_summary.csv",
        [
            {
                "audited_family": family,
                "field_count": count,
            }
            for family, count in family_counts.most_common()
        ],
        ["audited_family", "field_count"],
    )

    write_csv(
        out / "routing_summary.csv",
        [
            {
                "audit_route": route,
                "field_count": count,
            }
            for route, count in route_counts.most_common()
        ],
        ["audit_route", "field_count"],
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

    reports = {
        norm(r.get("report_id", ""))
        for r in final_accepted
        if norm(r.get("report_id", ""))
    }

    cases = {
        norm(r.get("case_id", ""))
        for r in final_accepted
        if norm(r.get("case_id", ""))
    }

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "group": "Group 6 - Other structured technical and investigation information",
        "stage": "PDF-only residual review resolution",
        "prior_accepted_fields": len(prior_accepted),
        "input_remaining_review_fields": len(review_rows),
        "promoted_to_group6": len(promoted),
        "newly_excluded_fields": len(newly_excluded),
        "remaining_review_fields": len(unresolved),
        "final_accepted_group6_fields": len(final_accepted),
        "reports_with_accepted_group6_fields": len(reports),
        "cases_with_accepted_group6_fields": len(cases),
        "resolution_counts": dict(resolution_counts),
        "accepted_family_counts": dict(family_counts),
        "new_exclusion_route_counts": dict(
            Counter(r["audit_route"] for r in newly_excluded)
        ),
        "validation_checks": len(checks),
        "hard_validation_failures": hard_failures,
        "warning_validation_failures": warning_failures,
        "scope": (
            "Exact resolution of every residual Group 6 PDF review row. "
            "Download-time ignition-cycle counts and manufacturing traceability "
            "fields are retained in Group 6. Deployment/non-deployment ignition "
            "cycle fields and event-start key-on timers are routed to Group 3. "
            "Software-license headers and explanatory ignition-cycle/software "
            "prose are excluded as documentation. No fuzzy inference, semantic "
            "normalization, unit conversion, OCR, or source mutation is used."
        ),
    }

    (out / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print()
    print(f"Outputs: {out}")

    if hard_failures:
        print()
        print("GROUP 6 PDF REVIEW RESOLUTION HAS HARD VALIDATION FAILURES.")
        raise SystemExit(1)

    print()
    print("GROUP 6 PDF REVIEW RESOLUTION COMPLETE.")


if __name__ == "__main__":
    main()
