"""
Audit Group 3 CSV discovery results.

Inputs
------
data/processed/edr/group3_csv_discovery_v1/
    group3_candidate_fields.csv
    group3_review_fields.csv

Outputs
-------
data/processed/edr/group3_csv_audit_v1/

    accepted_group3_fields.csv
    companion_group3_context.csv
    excluded_non_group3_fields.csv
    remaining_review_fields.csv
    audit_all_fields.csv
    family_summary.csv
    decision_summary.csv
    label_decision_summary.csv
    validation_checks.csv
    metadata.json

Purpose
-------
Refine Group 3 before structured extraction.

Main corrections
----------------
1. Separate deployment STATUS from deployment TIMING.
2. Separate pretensioner STATUS from pretensioner TIMING.
3. Separate restraint state from restraint activation/deployment timing.
4. Recover clear Group 3 fields from the discovery review population,
   including:
      - seat-track status
      - safing/discriminating deployment state
      - knee-bolster/load-limiter/head-restraint deployment fields
      - algorithm wake-up/reset/start timing
      - crash-sensor fault state at algorithm wake-up
      - battery/energy-reserve state at algorithm wake-up
5. Exclude clear overlaps:
      - Group 2 record/recording/counter fields
      - Group 5 crash-measurement companion context
      - Group 6 readout/technical/investigation fields
6. Preserve ambiguous fields for explicit later review.

No semantic value normalization, unit conversion, or fuzzy event linking is
performed.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
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


def union_columns(rows):
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
    ]

    for column in preferred:
        if column not in seen:
            seen.add(column)
            columns.append(column)

    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)

    return columns


# ============================================================
# Helpers
# ============================================================

def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").strip(),
    )


def has(text, pattern):
    return bool(
        re.search(
            pattern,
            norm(text),
            re.I,
        )
    )


# ============================================================
# Family refinement for discovery candidates
# ============================================================

def refine_candidate_family(label, old_family):
    text = norm(label)

    # --------------------------------------------------------
    # Group 5 companion overlap: keep outside Group 3
    # --------------------------------------------------------

    if has(
        text,
        r"\bpower supply status\b.*\bmax(?:imum)?\.?\s*(?:delta[- ]?v|velocity change)\b",
    ):
        return (
            "exclude",
            "group5_measurement_context",
            "excluded_non_group3",
            "power_status_is_context_for_group5_maximum_delta_v",
        )

    # --------------------------------------------------------
    # Record structure overlap
    # --------------------------------------------------------

    if has(
        text,
        r"\brecording status\b",
    ):
        return (
            "exclude",
            "group2_record_structure",
            "excluded_non_group3",
            "recording_status_belongs_to_group2",
        )

    # --------------------------------------------------------
    # Technical/readout overlap
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"power[- ]on cycle at reading|"
        r"ignition cycles? at investigation|"
        r"supplier id|production date|"
        r"serial number|part number|"
        r"software version"
        r")\b",
    ):
        return (
            "exclude",
            "group6_technical",
            "excluded_non_group3",
            "technical_or_readout_metadata",
        )

    # --------------------------------------------------------
    # Pretensioner timing before generic pretensioner status
    # --------------------------------------------------------

    if (
        has(text, r"\bpretensioner\b")
        and has(
            text,
            r"\b(?:time|time to|time from|fire|deployment loop command criteria met)\b",
        )
    ):
        return (
            "accept",
            "pretensioner_timing",
            "accepted_group3_candidate",
            "pretensioner_activation_or_deployment_timing",
        )

    # --------------------------------------------------------
    # Other restraint-device timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:"
            r"belt[- ]load limiter|"
            r"adaptive load limiter|"
            r"active head ?rest(?:raint)?|"
            r"inflatable knee bolster|"
            r"knee bolster|"
            r"inflatable seatbelt|"
            r"adaptive steering column|"
            r"can(?:n)?ister vent|"
            r"battery disconnect|"
            r"rollover protection system"
            r")\b",
        )
        and has(
            text,
            r"\b(?:time|time to|time from|fire|deploy|deployment)\b",
        )
    ):
        return (
            "accept",
            "restraint_deployment_timing",
            "accepted_group3_candidate",
            "restraint_or_protection_device_activation_timing",
        )

    # --------------------------------------------------------
    # General deployment timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:deployment|deploy|air ?bag)\b",
        )
        and has(
            text,
            r"\b(?:"
            r"time|time to|time from|"
            r"criteria met|1st stage time|2nd stage time"
            r")\b",
        )
    ):
        return (
            "accept",
            "deployment_timing",
            "accepted_group3_candidate",
            "deployment_command_or_stage_timing",
        )

    # Event-severity timing should not remain generic severity status.
    if (
        has(
            text,
            r"\bevent severity\b",
        )
        and has(
            text,
            r"\btime\b",
        )
    ):
        return (
            "accept",
            "event_severity_timing",
            "accepted_group3_candidate",
            "event_severity_threshold_timing",
        )

    # Warning lamp timing/history remains Group 3, but distinguish it.
    if (
        has(
            text,
            r"\bwarning lamp\b|\bmalfunction indicator lamp\b|\bMIL\b",
        )
        and has(
            text,
            r"\b(?:time|minutes?|seconds?|cycles?)\b",
        )
    ):
        return (
            "accept",
            "warning_lamp_history",
            "accepted_group3_candidate",
            "warning_lamp_time_or_cycle_history",
        )

    # Configuration of restraint hardware is not event state.
    if has(
        text,
        r"\bconfigured\b.*\b(?:belt|restraint|head restraint|pretensioner)\b",
    ):
        return (
            "exclude",
            "group6_configuration",
            "excluded_non_group3",
            "hardware_configuration_not_event_state",
        )

    # Default: preserve discovery family.
    return (
        "accept",
        norm(old_family) or "other_event_condition",
        "accepted_group3_candidate",
        "strong_group3_discovery_pattern",
    )


# ============================================================
# Review recovery
# ============================================================

def classify_review(label):
    text = norm(label)

    # --------------------------------------------------------
    # Group 2 exclusions
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"complete status of event data record|"
        r"recording status|"
        r"deployment command counter|"
        r"event counter|"
        r"record complete|"
        r"recording complete"
        r")\b",
    ):
        return (
            "exclude",
            "group2_record_structure",
            "excluded_non_group3",
            "record_or_counter_structure",
        )

    # --------------------------------------------------------
    # Group 6 exclusions
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"power[- ]on cycle at reading|"
        r"lifetime operating timer|"
        r"production date|supplier id|"
        r"part number|serial number|"
        r"software version"
        r")\b",
    ):
        return (
            "exclude",
            "group6_technical",
            "excluded_non_group3",
            "technical_or_readout_metadata",
        )

    # --------------------------------------------------------
    # Seat-track status
    # --------------------------------------------------------

    if has(
        text,
        r"\bseat track\b.*\b(?:position|forward|foremost|status|fault)\b",
    ):
        return (
            "accept",
            "seat_track_status",
            "recovered_group3_measurement",
            "seat_track_event_state",
        )

    # --------------------------------------------------------
    # Sensor deployment discrimination/safing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:"
            r"discriminating deployment|"
            r"safing deployment"
            r")\b",
        )
    ):
        return (
            "accept",
            "deployment_sensor_status",
            "recovered_group3_measurement",
            "sensor_discriminating_or_safing_deployment_state",
        )

    # --------------------------------------------------------
    # Device deployment/status/timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:"
            r"belt[- ]load limiter|"
            r"adaptive load limiter|"
            r"active head ?rest(?:raint)?|"
            r"inflatable knee bolster|"
            r"knee bolster|"
            r"inflatable seatbelt|"
            r"adaptive steering column|"
            r"battery disconnect|"
            r"rollover protection system|"
            r"can(?:n)?ister vent|"
            r"side seat airbag|"
            r"active glove box"
            r")\b",
        )
    ):
        if has(
            text,
            r"\b(?:time|fire|deploy|deployment)\b",
        ):
            return (
                "accept",
                "restraint_deployment_timing",
                "recovered_group3_measurement",
                "protection_device_activation_or_deployment",
            )

        return (
            "accept",
            "restraint_activation_status",
            "recovered_group3_measurement",
            "protection_device_activation_state",
        )

    # --------------------------------------------------------
    # Algorithm timing/status
    # --------------------------------------------------------

    if has(
        text,
        r"\btime\b.*\balgorithm\b.*\b(?:reset|wake[- ]?up|start)\b",
    ):
        return (
            "accept",
            "algorithm_timing",
            "recovered_group3_measurement",
            "algorithm_event_timing",
        )

    # --------------------------------------------------------
    # Sensor faults/state at algorithm wake-up
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:sensor|seat track)\b.*\bfault\b.*\balgorithm wake[- ]?up\b",
        )
    ):
        return (
            "accept",
            "sensor_fault_status",
            "recovered_group3_measurement",
            "sensor_fault_state_at_algorithm_wakeup",
        )

    # --------------------------------------------------------
    # Event electrical state at algorithm wake-up
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"key on timer|"
        r"battery voltage|"
        r"energy reserve voltage"
        r")\b.*\balgorithm wake[- ]?up\b",
    ):
        return (
            "accept",
            "algorithm_wakeup_condition",
            "recovered_group3_measurement",
            "event_electrical_state_at_algorithm_wakeup",
        )

    # --------------------------------------------------------
    # Explicit seat/restraint/occupant status
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"seat track position switch|"
        r"occupancy status|"
        r"occupant classification|"
        r"passenger classification|"
        r"belt switch|safety belt"
        r")\b",
    ):
        return (
            "accept",
            "occupant_restraint_status",
            "recovered_group3_measurement",
            "occupant_or_restraint_event_state",
        )

    # --------------------------------------------------------
    # Warning/brake status
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:warning status|warning lamp|brake system warning)\b",
    ):
        return (
            "accept",
            "warning_lamp_status",
            "recovered_group3_measurement",
            "warning_state",
        )

    # --------------------------------------------------------
    # Fuel cutoff event decision timing
    # --------------------------------------------------------

    if has(
        text,
        r"\bfuel cutoff algorithm decision time\b",
    ):
        return (
            "accept",
            "algorithm_timing",
            "recovered_group3_measurement",
            "fuel_cutoff_algorithm_event_timing",
        )

    # --------------------------------------------------------
    # Freeze signal factors are potentially meaningful event conditions
    # but model-specific; preserve for explicit review.
    # --------------------------------------------------------

    if has(
        text,
        r"\bfreeze signal factor\b",
    ):
        return (
            "review",
            "other_event_condition",
            "remaining_review",
            "manufacturer_specific_freeze_signal_factor",
        )

    return (
        "review",
        "unresolved_review",
        "remaining_review",
        "no_safe_group3_resolution_rule",
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
            "data/processed/edr/group3_csv_discovery_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_csv_audit_v1"
        ),
    )

    args = parser.parse_args()

    candidate_path = (
        args.discovery_directory
        / "group3_candidate_fields.csv"
    )

    review_path = (
        args.discovery_directory
        / "group3_review_fields.csv"
    )

    if not candidate_path.exists():
        raise FileNotFoundError(candidate_path)

    if not review_path.exists():
        raise FileNotFoundError(review_path)

    candidates = read_csv(candidate_path)
    reviews = read_csv(review_path)

    audited = []

    for row in candidates:
        (
            decision,
            family,
            status,
            reason,
        ) = refine_candidate_family(
            row.get("field_label_raw", ""),
            row.get("candidate_family", ""),
        )

        audited.append({
            **row,
            "audited_family": family,
            "audit_decision": decision,
            "audit_status": status,
            "audit_reason": reason,
            "audit_origin": "discovery_candidate",
        })

    for row in reviews:
        (
            decision,
            family,
            status,
            reason,
        ) = classify_review(
            row.get("field_label_raw", "")
        )

        audited.append({
            **row,
            "audited_family": family,
            "audit_decision": decision,
            "audit_status": status,
            "audit_reason": reason,
            "audit_origin": "discovery_review",
        })

    accepted = [
        row
        for row in audited
        if row["audit_decision"] == "accept"
    ]

    companions = [
        row
        for row in audited
        if row["audit_decision"] == "companion"
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

    input_total = (
        len(candidates)
        + len(reviews)
    )

    output_total = (
        len(accepted)
        + len(companions)
        + len(excluded)
        + len(remaining_review)
    )

    if input_total != output_total:
        raise RuntimeError(
            "Audit accounting mismatch: "
            f"{input_total} != {output_total}"
        )

    # ========================================================
    # Summaries
    # ========================================================

    family_counts = Counter(
        row["audited_family"]
        for row in accepted
    )

    decision_counts = Counter(
        row["audit_decision"]
        for row in audited
    )

    promoted_from_review = sum(
        1
        for row in accepted
        if row["audit_origin"]
        == "discovery_review"
    )

    reports_with_accepted = {
        row.get("report_id", "")
        for row in accepted
        if row.get("report_id", "")
    }

    label_grouped = defaultdict(Counter)

    for row in audited:
        label_grouped[
            norm(
                row.get(
                    "field_label_raw",
                    "",
                )
            )
        ][
            row["audit_decision"]
        ] += 1

    label_decision_summary = []

    for label, counts in sorted(
        label_grouped.items(),
        key=lambda item: (
            -sum(item[1].values()),
            item[0].casefold(),
        ),
    ):
        label_decision_summary.append({
            "field_label_raw":
                label,
            "total_count":
                sum(counts.values()),
            "accept_count":
                counts.get("accept", 0),
            "companion_count":
                counts.get("companion", 0),
            "exclude_count":
                counts.get("exclude", 0),
            "review_count":
                counts.get("review", 0),
        })

    family_summary = [
        {
            "audited_family":
                family,
            "field_count":
                count,
            "report_count":
                len({
                    row.get("report_id", "")
                    for row in accepted
                    if (
                        row["audited_family"]
                        == family
                        and row.get(
                            "report_id",
                            "",
                        )
                    )
                }),
            "promoted_from_review_count":
                sum(
                    1
                    for row in accepted
                    if (
                        row["audited_family"]
                        == family
                        and row["audit_origin"]
                        == "discovery_review"
                    )
                ),
        }
        for family, count
        in family_counts.most_common()
    ]

    origin_decisions = Counter(
        (
            row["audit_origin"],
            row["audit_decision"],
        )
        for row in audited
    )

    decision_summary = [
        {
            "audit_origin": origin,
            "audit_decision": decision,
            "field_count": count,
        }
        for (
            origin,
            decision,
        ), count
        in sorted(
            origin_decisions.items()
        )
    ]

    # ========================================================
    # Validation checks
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
            "status":
                "PASS"
                if condition
                else "FAIL",
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

    ids = [
        row.get("group3_candidate_id", "")
        for row in audited
        if row.get("group3_candidate_id", "")
    ]

    duplicate_ids = (
        len(ids) - len(set(ids))
    )

    check(
        "duplicate_candidate_ids",
        duplicate_ids == 0,
        duplicate_ids,
        0,
    )

    blank_accepted_labels = sum(
        1
        for row in accepted
        if not norm(
            row.get(
                "field_label_raw",
                "",
            )
        )
    )

    check(
        "blank_accepted_labels",
        blank_accepted_labels == 0,
        blank_accepted_labels,
        0,
    )

    # ========================================================
    # Write
    # ========================================================

    out = args.output_directory
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    columns = union_columns(audited)

    write_csv(
        out
        / "accepted_group3_fields.csv",
        accepted,
        columns,
    )

    write_csv(
        out
        / "companion_group3_context.csv",
        companions,
        columns,
    )

    write_csv(
        out
        / "excluded_non_group3_fields.csv",
        excluded,
        columns,
    )

    write_csv(
        out
        / "remaining_review_fields.csv",
        remaining_review,
        columns,
    )

    write_csv(
        out
        / "audit_all_fields.csv",
        audited,
        columns,
    )

    write_csv(
        out
        / "family_summary.csv",
        family_summary,
        [
            "audited_family",
            "field_count",
            "report_count",
            "promoted_from_review_count",
        ],
    )

    write_csv(
        out
        / "decision_summary.csv",
        decision_summary,
        [
            "audit_origin",
            "audit_decision",
            "field_count",
        ],
    )

    write_csv(
        out
        / "label_decision_summary.csv",
        label_decision_summary,
        [
            "field_label_raw",
            "total_count",
            "accept_count",
            "companion_count",
            "exclude_count",
            "review_count",
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

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 3 - Event conditions, deployment, and status information",

        "stage":
            "CSV candidate audit",

        "input_discovery_candidates":
            len(candidates),

        "input_discovery_review_fields":
            len(reviews),

        "total_fields_audited":
            len(audited),

        "accepted_group3_fields":
            len(accepted),

        "companion_group3_context_fields":
            len(companions),

        "excluded_non_group3_fields":
            len(excluded),

        "remaining_review_fields":
            len(remaining_review),

        "reports_with_accepted_group3_fields":
            len(reports_with_accepted),

        "promoted_from_discovery_review":
            promoted_from_review,

        "accepted_family_counts":
            dict(family_counts),

        "decision_counts":
            dict(decision_counts),

        "input_accounting_total":
            input_total,

        "output_accounting_total":
            output_total,

        "all_fields_accounted_for":
            input_total == output_total,

        "validation_checks":
            len(checks),

        "hard_validation_failures":
            len(hard_failures),

        "warning_validation_failures":
            len(warning_failures),

        "scope":
            (
                "Audit of Group 3 CSV discovery candidates and review fields. "
                "Deployment status is separated from deployment timing; "
                "pretensioner status from pretensioner timing; restraint state "
                "from restraint-device deployment timing; and warning-lamp "
                "state from warning-lamp history. Clear Group 2 record "
                "structure, Group 5 measurement-context, and Group 6 technical "
                "fields are excluded. Clear event-state fields from the review "
                "population are recovered. Manufacturer-specific or ambiguous "
                "fields remain explicit review evidence. No semantic value "
                "normalization, unit conversion, fuzzy event linking, PDF "
                "processing, or final extraction is performed."
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

    tmp.replace(
        out / "metadata.json"
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
            "GROUP 3 CSV AUDIT HAS HARD VALIDATION FAILURES."
        )
        raise SystemExit(1)

    print()
    print(
        "GROUP 3 CSV CANDIDATE AUDIT COMPLETE."
    )


if __name__ == "__main__":
    main()
