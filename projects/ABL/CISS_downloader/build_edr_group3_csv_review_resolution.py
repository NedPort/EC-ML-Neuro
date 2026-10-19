"""
Resolve the remaining Group 3 CSV audit review fields.

Input
-----
data/processed/edr/group3_csv_audit_v1/
    accepted_group3_fields.csv
    companion_group3_context.csv
    excluded_non_group3_fields.csv
    remaining_review_fields.csv

Output
------
data/processed/edr/group3_csv_resolved_v1/
    accepted_group3_fields.csv
    companion_group3_context.csv
    excluded_non_group3_fields.csv
    resolved_review_fields.csv
    remaining_review_fields.csv
    family_summary.csv
    resolution_summary.csv
    validation_checks.csv
    metadata.json

The 121 residual review rows were inspected explicitly. They consist of 12
distinct labels, all of which are structurally consistent with Group 3 event
conditions/status/timing and can be resolved without fuzzy inference.

No value normalization, unit conversion, or event-link inference is performed.
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


def union_columns(*rowsets):
    seen = set()
    columns = []

    preferred = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "group3_candidate_id",
        "source_format",
        "source_path",
        "source_record_index",
        "source_section_heading",
        "event_hint",
        "field_label_raw",
        "field_value_raw",
        "candidate_family",
        "audited_family",
        "audit_decision",
        "audit_status",
        "audit_reason",
        "resolution_family",
        "resolution_decision",
        "resolution_reason",
    ]

    for col in preferred:
        if col not in seen:
            seen.add(col)
            columns.append(col)

    for rows in rowsets:
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)

    return columns


# ============================================================
# Explicit resolution rules for the 12 residual labels
# ============================================================

def resolve_row(row):
    label = norm(row.get("field_label_raw", ""))

    # Direct deployment-state fields.
    if re.fullmatch(
        r"Side Seat Airbags Deployment, (?:Left|Right)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_status",
            "explicit_side_airbag_deployment_state",
        )

    # Manufacturer-specific freeze-signal factors are event-state variables.
    # They are tied to deployment discriminators/CSA logic and appear under
    # SYSTEM STATUS AT EVENT. Preserve the raw OFF value exactly.
    if re.fullmatch(
        r"Freeze Signal Factor, Side CSA Deployment, "
        r"(?:Left|Right) Side",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_sensor_status",
            "deployment_freeze_signal_factor_at_event",
        )

    if re.fullmatch(
        r"Freeze Signal Factor, Rollover CSA Deployment",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_sensor_status",
            "rollover_deployment_freeze_signal_factor_at_event",
        )

    # High-voltage battery deactivation command is event/deployment behavior.
    # Even when raw value is "Not Deployed", preserve it as a timing/status
    # observation rather than forcing a numeric value.
    if re.fullmatch(
        r"High-Voltage Battery Deactivation, Time to Deployment \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "high_voltage_deactivation_timing",
            "high_voltage_battery_deactivation_deployment_timing",
        )

    if re.fullmatch(
        r"Belt tensioner deployment, time to 1st stage, driver \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "pretensioner_timing",
            "belt_tensioner_first_stage_deployment_timing",
        )

    if re.fullmatch(
        r"Driver Center Inboard Time From Time Zero to "
        r"Deployment Loop Command Criteria Met \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_timing",
            "deployment_loop_command_criteria_timing",
        )

    if re.fullmatch(
        r"Time From Time Zero to Deployment \(Rollover\) \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_timing",
            "rollover_deployment_timing",
        )

    if re.fullmatch(
        r"Active Head-Rest, Time to Deployment, "
        r"Front (?:Passenger|Driver) \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "restraint_deployment_timing",
            "active_head_restraint_deployment_timing",
        )

    if re.fullmatch(
        r"Tire Pressure Monitoring System Warning Light Status",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "warning_lamp_status",
            "event_warning_light_state",
        )

    return (
        "review",
        "unresolved_review",
        "no_explicit_resolution_rule",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--audit-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_csv_audit_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_csv_resolved_v1"
        ),
    )

    args = parser.parse_args()

    src = args.audit_directory
    out = args.output_directory

    paths = {
        "accepted": src / "accepted_group3_fields.csv",
        "companion": src / "companion_group3_context.csv",
        "excluded": src / "excluded_non_group3_fields.csv",
        "review": src / "remaining_review_fields.csv",
    }

    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {name}: {path}")

    accepted_prior = read_csv(paths["accepted"])
    companion = read_csv(paths["companion"])
    excluded = read_csv(paths["excluded"])
    review = read_csv(paths["review"])

    resolved = []
    unresolved = []

    for row in review:
        decision, family, reason = resolve_row(row)

        updated = {
            **row,
            "resolution_family": family,
            "resolution_decision": decision,
            "resolution_reason": reason,
        }

        if decision == "accept":
            # Promote the final resolved family into audited_family so the
            # downstream extractor needs only one canonical family column.
            updated["audited_family"] = family
            updated["audit_decision"] = "accept"
            updated["audit_status"] = "resolved_group3_measurement"
            updated["audit_reason"] = reason
            resolved.append(updated)
        else:
            unresolved.append(updated)

    accepted_final = accepted_prior + resolved

    # ========================================================
    # Validation
    # ========================================================

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

    check(
        "input_review_count",
        len(review) == 121,
        len(review),
        121,
    )

    check(
        "all_review_rows_accounted_for",
        len(resolved) + len(unresolved) == len(review),
        len(resolved) + len(unresolved),
        len(review),
    )

    check(
        "remaining_review_zero",
        len(unresolved) == 0,
        len(unresolved),
        0,
    )

    check(
        "final_accepted_count",
        len(accepted_final) == 37065,
        len(accepted_final),
        37065,
    )

    ids = [
        norm(row.get("group3_candidate_id", ""))
        for row in accepted_final
        if norm(row.get("group3_candidate_id", ""))
    ]

    duplicate_ids = len(ids) - len(set(ids))

    check(
        "duplicate_accepted_candidate_ids",
        duplicate_ids == 0,
        duplicate_ids,
        0,
    )

    blank_labels = sum(
        1
        for row in accepted_final
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
        norm(row.get("audited_family", ""))
        for row in accepted_final
    )

    resolution_counts = Counter(
        (
            row.get("resolution_decision", ""),
            row.get("resolution_family", ""),
        )
        for row in resolved + unresolved
    )

    family_summary = [
        {
            "audited_family": family,
            "field_count": count,
        }
        for family, count
        in family_counts.most_common()
    ]

    resolution_summary = [
        {
            "resolution_decision": decision,
            "resolution_family": family,
            "field_count": count,
        }
        for (decision, family), count
        in sorted(resolution_counts.items())
    ]

    # ========================================================
    # Write
    # ========================================================

    out.mkdir(parents=True, exist_ok=True)

    columns = union_columns(
        accepted_final,
        companion,
        excluded,
        resolved,
        unresolved,
    )

    write_csv(
        out / "accepted_group3_fields.csv",
        accepted_final,
        columns,
    )

    write_csv(
        out / "companion_group3_context.csv",
        companion,
        columns,
    )

    write_csv(
        out / "excluded_non_group3_fields.csv",
        excluded,
        columns,
    )

    write_csv(
        out / "resolved_review_fields.csv",
        resolved,
        columns,
    )

    write_csv(
        out / "remaining_review_fields.csv",
        unresolved,
        columns,
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
        out / "resolution_summary.csv",
        resolution_summary,
        [
            "resolution_decision",
            "resolution_family",
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
            "CSV residual review resolution",

        "input_prior_accepted":
            len(accepted_prior),

        "input_remaining_review":
            len(review),

        "resolved_as_group3":
            len(resolved),

        "remaining_review":
            len(unresolved),

        "final_accepted_group3_fields":
            len(accepted_final),

        "companion_group3_context_fields":
            len(companion),

        "excluded_non_group3_fields":
            len(excluded),

        "final_family_counts":
            dict(family_counts),

        "validation_checks":
            len(checks),

        "hard_validation_failures":
            hard_failures,

        "warning_validation_failures":
            warning_failures,

        "scope":
            (
                "Explicit resolution of the 121 residual Group 3 CSV review "
                "fields. Twelve distinct residual labels were inspected. "
                "Side-airbag deployment states, deployment freeze-signal "
                "factors, high-voltage battery deactivation timing, belt "
                "tensioner timing, deployment-loop criteria timing, rollover "
                "deployment timing, active-head-rest deployment timing, and "
                "TPMS warning-light status are retained as Group 3. Raw "
                "values and provenance are preserved. No semantic value "
                "normalization, unit conversion, fuzzy event linking, or "
                "source modification is performed."
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
        print("GROUP 3 CSV REVIEW RESOLUTION HAS HARD FAILURES.")
        raise SystemExit(1)

    print()
    print("GROUP 3 CSV REVIEW RESOLUTION COMPLETE.")


if __name__ == "__main__":
    main()
