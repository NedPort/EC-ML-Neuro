"""
Audit Group 6 CSV discovery results.

Inputs
------
data/processed/edr/group6_csv_discovery_v1/
    group6_candidate_fields.csv

Output
------
data/processed/edr/group6_csv_audit_v1/

    accepted_group6_fields.csv
    excluded_non_group6_fields.csv
    remaining_review_fields.csv
    audit_all_fields.csv
    family_summary.csv
    routing_summary.csv
    validation_checks.csv
    metadata.json

Audit decisions
---------------
The Group 6 candidate labels were inspected explicitly.

Refinements inside Group 6:
- software/calibration/version identifiers are separated from generic
  part/serial identifiers
- module supplier information gets its own family
- VIN values read from PCM/ACM are retained as technical vehicle identifiers
- module voltage at retrieval is kept as readout voltage
- adapter detection during download is kept as readout-tool status
- SDM primary key definitions are kept as module-key definitions
- PCM calibration filenames are kept under software/calibration/version

Cross-group exclusions:
- OnStar SDM Recorded Vehicle Velocity Change Data Sent -> Group 3
- ACM/Supply/System Voltage at Event -> Group 3 power/event condition

No semantic normalization, unit conversion, fuzzy inference, or source
modification is performed.
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

    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
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


def union_columns(rows):
    seen = set()
    cols = []

    preferred = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "group6_candidate_id",
        "source_format",
        "source_path",
        "source_record_index",
        "source_section_heading",
        "field_label_raw",
        "field_value_raw",
        "candidate_family",
        "audited_family",
        "audit_decision",
        "audit_route",
        "audit_reason",
    ]

    for col in preferred:
        if col not in seen:
            seen.add(col)
            cols.append(col)

    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                cols.append(key)

    return cols


def audit_candidate(row):
    label = norm(row.get("field_label_raw", ""))
    family = norm(row.get("candidate_family", ""))

    # --------------------------------------------------------
    # Group 3 overlap: event-related status/condition
    # --------------------------------------------------------

    if label.casefold() == (
        "OnStar SDM Recorded Vehicle Velocity Change Data Sent"
    ).casefold():
        return (
            "exclude",
            "group3_event_condition",
            "group3",
            "event_data_transmission_status",
        )

    if re.fullmatch(
        r"(?:"
        r"Supply Voltage at Event, ACM \(V\)|"
        r"ACM System Voltage at Event \(V\)|"
        r"ACM Supply Voltage at Event \(V\)"
        r")",
        label,
        flags=re.I,
    ):
        return (
            "exclude",
            "group3_power_event_condition",
            "group3",
            "module_voltage_at_event_is_event_condition",
        )

    # --------------------------------------------------------
    # Group 6 family refinements
    # --------------------------------------------------------

    if re.search(
        r"\b(?:"
        r"software|calibration|firmware|application version|"
        r"hardware version|software strategy"
        r")\b",
        label,
        re.I,
    ):
        return (
            "accept",
            "software_calibration_version",
            "group6",
            "software_calibration_or_version_identifier",
        )

    if re.search(
        r"\b(?:Current VIN|Vehicle Identification Number)\b",
        label,
        re.I,
    ):
        return (
            "accept",
            "vehicle_identifier_technical",
            "group6",
            "technical_vehicle_identifier_from_module",
        )

    if re.search(
        r"\b(?:ACM Supplier|Airbag Control Module Supplier)\b",
        label,
        re.I,
    ):
        return (
            "accept",
            "module_supplier",
            "group6",
            "module_supplier_information",
        )

    if re.search(
        r"\bACM Supply Voltage at Time of Retrieval\b",
        label,
        re.I,
    ):
        return (
            "accept",
            "readout_voltage",
            "group6",
            "retrieval_time_module_voltage",
        )

    if re.search(
        r"\bACM Adapter Detected During Download\b",
        label,
        re.I,
    ):
        return (
            "accept",
            "readout_tool_status",
            "group6",
            "download_adapter_detection_status",
        )

    if re.search(
        r"\bSDM Primary Key Definition\b",
        label,
        re.I,
    ):
        return (
            "accept",
            "module_key_definition",
            "group6",
            "module_primary_key_definition",
        )

    if re.search(
        r"\bPCM File Name \(calibration level\)\b",
        label,
        re.I,
    ):
        return (
            "accept",
            "software_calibration_version",
            "group6",
            "pcm_calibration_filename",
        )

    return (
        "accept",
        family or "other_structured_technical",
        "group6",
        "valid_group6_candidate",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--discovery-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group6_csv_discovery_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group6_csv_audit_v1"
        ),
    )

    args = parser.parse_args()

    src = args.discovery_directory
    out = args.output_directory

    candidate_path = src / "group6_candidate_fields.csv"

    if not candidate_path.exists():
        raise FileNotFoundError(candidate_path)

    candidates = read_csv(candidate_path)

    audited = []

    for row in candidates:
        decision, family, route, reason = audit_candidate(row)

        audited.append({
            **row,
            "audited_family": family,
            "audit_decision": decision,
            "audit_route": route,
            "audit_reason": reason,
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
            "check": name,
            "status": "PASS" if condition else "FAIL",
            "severity": severity,
            "observed": str(observed),
            "expected": str(expected),
            "note": note,
        })

    check(
        "input_candidate_count",
        len(candidates) == 13575,
        len(candidates),
        13575,
    )

    check(
        "all_candidates_accounted_for",
        (
            len(accepted)
            + len(excluded)
            + len(remaining_review)
        ) == len(candidates),
        len(accepted) + len(excluded) + len(remaining_review),
        len(candidates),
    )

    check(
        "expected_accepted_count",
        len(accepted) == 13202,
        len(accepted),
        13202,
    )

    check(
        "expected_excluded_count",
        len(excluded) == 373,
        len(excluded),
        373,
    )

    check(
        "remaining_review_zero",
        len(remaining_review) == 0,
        len(remaining_review),
        0,
    )

    ids = [
        norm(row.get("group6_candidate_id", ""))
        for row in audited
        if norm(row.get("group6_candidate_id", ""))
    ]

    duplicate_ids = len(ids) - len(set(ids))

    check(
        "duplicate_candidate_ids",
        duplicate_ids == 0,
        duplicate_ids,
        0,
    )

    blank_labels = sum(
        1
        for row in accepted
        if not norm(row.get("field_label_raw", ""))
    )

    check(
        "blank_accepted_labels",
        blank_labels == 0,
        blank_labels,
        0,
    )

    # ========================================================
    # Summaries
    # ========================================================

    family_counts = Counter(
        row["audited_family"]
        for row in accepted
    )

    route_counts = Counter(
        row["audit_route"]
        for row in excluded
    )

    reports = {
        row.get("report_id", "")
        for row in accepted
        if row.get("report_id", "")
    }

    cases = {
        row.get("case_id", "")
        for row in accepted
        if row.get("case_id", "")
    }

    family_summary = [
        {
            "audited_family": family,
            "field_count": count,
        }
        for family, count
        in family_counts.most_common()
    ]

    routing_summary = [
        {
            "audit_route": route,
            "field_count": count,
        }
        for route, count
        in route_counts.most_common()
    ]

    # ========================================================
    # Write
    # ========================================================

    out.mkdir(parents=True, exist_ok=True)
    cols = union_columns(audited)

    write_csv(
        out / "accepted_group6_fields.csv",
        accepted,
        cols,
    )

    write_csv(
        out / "excluded_non_group6_fields.csv",
        excluded,
        cols,
    )

    write_csv(
        out / "remaining_review_fields.csv",
        remaining_review,
        cols,
    )

    write_csv(
        out / "audit_all_fields.csv",
        audited,
        cols,
    )

    write_csv(
        out / "family_summary.csv",
        family_summary,
        [
            "audited_family",
            "field_count",
        ],
    )

    write_csv(
        out / "routing_summary.csv",
        routing_summary,
        [
            "audit_route",
            "field_count",
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

    hard_failures = sum(
        1
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"] == "hard"
        )
    )

    warning_failures = sum(
        1
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"] == "warning"
        )
    )

    metadata = {
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 6 - Other structured technical and investigation information",

        "stage":
            "CSV candidate audit",

        "input_candidates":
            len(candidates),

        "accepted_group6_fields":
            len(accepted),

        "excluded_non_group6_fields":
            len(excluded),

        "remaining_review_fields":
            len(remaining_review),

        "reports_with_accepted_group6_fields":
            len(reports),

        "cases_with_accepted_group6_fields":
            len(cases),

        "accepted_family_counts":
            dict(family_counts),

        "excluded_route_counts":
            dict(route_counts),

        "validation_checks":
            len(checks),

        "hard_validation_failures":
            hard_failures,

        "warning_validation_failures":
            warning_failures,

        "scope":
            (
                "Audit of Group 6 CSV discovery. Software/calibration/version "
                "identifiers, technical vehicle identifiers, module suppliers, "
                "retrieval-time voltage, adapter/download status, and module "
                "key definitions are refined into explicit Group 6 families. "
                "OnStar event-data transmission status and ACM/system voltage "
                "at the event are routed to Group 3 because they represent "
                "event-state information rather than technical/readout metadata. "
                "No semantic normalization, unit conversion, fuzzy inference, "
                "PDF processing, or source mutation is performed."
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
        print("GROUP 6 CSV AUDIT HAS HARD VALIDATION FAILURES.")
        raise SystemExit(1)

    print()
    print("GROUP 6 CSV AUDIT COMPLETE.")


if __name__ == "__main__":
    main()
