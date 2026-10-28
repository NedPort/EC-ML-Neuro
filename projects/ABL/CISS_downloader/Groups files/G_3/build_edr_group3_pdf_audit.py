"""
Audit Group 3 PDF-only discovery results.

Inputs
------
data/processed/edr/group3_pdf_discovery_v1/
    group3_pdf_candidates.csv
    group3_pdf_review.csv

Outputs
-------
data/processed/edr/group3_pdf_audit_v1/
    accepted_group3_pdf_fields.csv
    excluded_non_group3_pdf_fields.csv
    remaining_review_fields.csv
    audit_all_fields.csv
    family_summary.csv
    routing_summary.csv
    validation_checks.csv
    metadata.json

Audit logic
-----------
The discovery output was inspected explicitly.

Candidate corrections:
1. Exclude explanatory/documentation lines that were split as if they were
   field/value observations.
2. Exclude `Power Supply Status at the time of Max. Delta-V` from Group 3
   because it is context for a Group 5 scalar crash measurement.
3. Exclude truncated `Passenger Classification Status at Event Enable
   Classificati` / `on` parse artifacts.
4. Preserve valid restraint, occupant, deployment, algorithm, power,
   high-voltage, severity, and related event-condition fields.

Review resolution:
- Rollover Sensor Status Data = valid Group 3 sensor/status field.
- Time-series table headers = Group 4 overlap.
- Longitudinal velocity change during algorithm run time = Group 5 scalar
  crash/event measurement.
- Algorithm run time = Group 5 scalar crash/event measurement.
- explanatory `Data not Available` prose = documentation, not a measurement.

No OCR, semantic normalization, unit conversion, fuzzy event linking,
or source modification is performed.
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


def union_columns(rows):
    seen = set()
    cols = []

    preferred = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "group3_candidate_id",
        "source_format",
        "source_path",
        "pdf_page",
        "pdf_line_number",
        "source_section_heading",
        "event_hint",
        "source_line_raw",
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


# ============================================================
# Candidate audit
# ============================================================

EXPLANATORY_LABELS = {
    "-Driver's and Passenger's Belt Switch Circuit Status indicates the status of the seat belt switch circuit, except",
    "- Frontal Airbag Disable Indicator Status",
    "- Airbag Warning Lamp, Status",
    "- Safety Belt Status",
    "- Seat Track Position Switch",
    "- Occupant Size Classification, Front Passenger",
    "- Time to Deployment",
}


def audit_candidate(row):
    label = norm(row.get("field_label_raw", ""))
    value = norm(row.get("field_value_raw", ""))
    family = norm(row.get("candidate_family", ""))

    if label in EXPLANATORY_LABELS:
        return (
            "exclude",
            family or "documentation",
            "documentation",
            "explanatory_or_definition_line_misparsed_as_field",
        )

    if label.casefold() == (
        "power supply status at the time of max. delta-v"
    ).casefold():
        return (
            "exclude",
            "group5_measurement_context",
            "group5",
            "power_supply_status_is_context_for_maximum_delta_v",
        )

    if (
        label.casefold()
        == "passenger classification status at event enable classificati".casefold()
        and value.casefold() == "on"
    ):
        return (
            "exclude",
            "occupant_status",
            "parse_artifact",
            "terminal_on_split_from_word_classification",
        )

    return (
        "accept",
        family or "other_event_condition",
        "group3",
        "valid_group3_pdf_candidate",
    )


# ============================================================
# Review resolution
# ============================================================

def audit_review(row):
    label = norm(row.get("field_label_raw", ""))

    if label == "Rollover Sensor Status Data":
        return (
            "accept",
            "sensor_status",
            "group3",
            "rollover_sensor_status_is_event_status_information",
        )

    if label.startswith(
        "Time (sec) Status Status (Mpa) (m/s^2) (deg/s) (degrees) Shift Positi"
    ):
        return (
            "exclude",
            "group4_timeseries_header",
            "group4",
            "time_series_table_header_not_scalar_group3_field",
        )

    if label == "Longitudinal velocity change during algorithm run time (MPH)":
        return (
            "exclude",
            "group5_scalar_measurement",
            "group5",
            "scalar_velocity_change_measurement",
        )

    if label == "Algorithm run time (msec)":
        return (
            "exclude",
            "group5_scalar_measurement",
            "group5",
            "scalar_event_runtime_measurement",
        )

    if label.startswith(
        'The status "Data not Available" is reported if the ACM was unable to store the data element'
    ):
        return (
            "exclude",
            "documentation",
            "documentation",
            "explanatory_prose_not_structured_measurement",
        )

    return (
        "review",
        "unresolved_review",
        "review",
        "no_safe_resolution_rule",
    )


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--discovery-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_pdf_discovery_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_pdf_audit_v1"
        ),
    )

    args = parser.parse_args()

    src = args.discovery_directory
    out = args.output_directory

    candidate_path = src / "group3_pdf_candidates.csv"
    review_path = src / "group3_pdf_review.csv"

    if not candidate_path.exists():
        raise FileNotFoundError(candidate_path)

    if not review_path.exists():
        raise FileNotFoundError(review_path)

    candidates = read_csv(candidate_path)
    review = read_csv(review_path)

    audited = []

    for row in candidates:
        decision, family, route, reason = audit_candidate(row)

        audited.append({
            **row,
            "audited_family": family,
            "audit_decision": decision,
            "audit_route": route,
            "audit_reason": reason,
            "audit_origin": "discovery_candidate",
        })

    for row in review:
        decision, family, route, reason = audit_review(row)

        audited.append({
            **row,
            "audited_family": family,
            "audit_decision": decision,
            "audit_route": route,
            "audit_reason": reason,
            "audit_origin": "discovery_review",
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

    input_total = len(candidates) + len(review)
    output_total = (
        len(accepted)
        + len(excluded)
        + len(remaining_review)
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
            "check": name,
            "status": "PASS" if condition else "FAIL",
            "severity": severity,
            "observed": str(observed),
            "expected": str(expected),
            "note": note,
        })

    check(
        "all_input_fields_accounted_for",
        input_total == output_total,
        output_total,
        input_total,
    )

    check(
        "expected_candidate_input",
        len(candidates) == 599,
        len(candidates),
        599,
    )

    check(
        "expected_review_input",
        len(review) == 19,
        len(review),
        19,
    )

    check(
        "remaining_review_zero",
        len(remaining_review) == 0,
        len(remaining_review),
        0,
    )

    # Based on explicit inspection:
    # 599 candidates - 62 candidate exclusions = 537
    # + 1 accepted review row = 538
    check(
        "expected_accepted_count",
        len(accepted) == 538,
        len(accepted),
        538,
    )

    check(
        "expected_excluded_count",
        len(excluded) == 80,
        len(excluded),
        80,
    )

    ids = [
        norm(row.get("group3_candidate_id", ""))
        for row in audited
        if norm(row.get("group3_candidate_id", ""))
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
        out / "accepted_group3_pdf_fields.csv",
        accepted,
        cols,
    )

    write_csv(
        out / "excluded_non_group3_pdf_fields.csv",
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
        if row["status"] == "FAIL"
        and row["severity"] == "hard"
    )

    warning_failures = sum(
        1
        for row in checks
        if row["status"] == "FAIL"
        and row["severity"] == "warning"
    )

    metadata = {
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 3 - Event conditions, deployment, and status information",

        "stage":
            "PDF-only candidate audit",

        "input_candidates":
            len(candidates),

        "input_review_fields":
            len(review),

        "total_fields_audited":
            len(audited),

        "accepted_group3_pdf_fields":
            len(accepted),

        "excluded_non_group3_pdf_fields":
            len(excluded),

        "remaining_review_fields":
            len(remaining_review),

        "reports_with_accepted_group3_pdf_fields":
            len(reports),

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
                "Audit of Group 3 PDF-only discovery. Explanatory prose, "
                "definition lines, table headers, Group 5 scalar/event "
                "measurements, Group 5 maximum-Delta-V context, and PDF "
                "terminal-token split artifacts are excluded. Rollover "
                "sensor status is recovered as Group 3 event-status data. "
                "Original PDF text and provenance are preserved. No OCR, "
                "semantic normalization, unit conversion, fuzzy event "
                "linking, or source modification is performed."
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
        print("GROUP 3 PDF AUDIT HAS HARD VALIDATION FAILURES.")
        raise SystemExit(1)

    print()
    print("GROUP 3 PDF AUDIT COMPLETE.")


if __name__ == "__main__":
    main()
