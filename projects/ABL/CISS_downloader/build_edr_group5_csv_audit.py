"""
Audit Group 5 CSV discovery results.

Inputs
------
data/processed/edr/group5_csv_discovery_v1/
    group5_candidate_fields.csv
    group5_review_fields.csv

Outputs
-------
data/processed/edr/group5_csv_audit_v1/

    accepted_group5_fields.csv
    companion_group5_context.csv
    excluded_non_group5_fields.csv
    remaining_review_fields.csv
    audit_all_fields.csv
    family_summary.csv
    decision_summary.csv
    label_decision_summary.csv
    metadata.json

Purpose
-------
Refine Group 5 discovery before structured extraction.

Key corrections
---------------
1. Split true Delta-V / velocity-change scalar values from timing fields.
2. Split peak acceleration values from time-of-peak acceleration.
3. Keep clipping/range-exceeded timing as Group 5 measurement-quality timing.
4. Recover selected Group 5 measurements from the first-stage review set.
5. Route scalar context/status that describes a Group 5 measurement to
   companion metadata rather than treating it as a core measurement.
6. Keep unrelated restraint/deployment/status/record/configuration fields
   outside Group 5.

This is still an audit stage:
- no semantic normalization of values
- no unit conversion
- no fuzzy event identity inference
- no PDF processing
- original raw labels/values/provenance are preserved
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


def write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".part"
    )

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
        "group5_candidate_id",
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
        for key in row.keys():
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
        str(
            value
            if value is not None
            else ""
        ).strip(),
    )


def norm_key(value):
    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            norm(value).casefold(),
        )
    )


def matches(text, pattern):
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
    # Measurement-quality timing first
    # --------------------------------------------------------

    if matches(
        text,
        r"\b(?:"
        r"clipping time|"
        r"accelerometer range exceeded|"
        r"sensor design range (?:was )?exceeded|"
        r"reached maximum sensor range"
        r")\b",
    ):
        return "range_clipping_timing"

    # --------------------------------------------------------
    # Acceleration peak/timing
    # --------------------------------------------------------

    if (
        matches(
            text,
            r"\btime\b",
        )
        and matches(
            text,
            r"\bmaximum acceleration\b",
        )
    ):
        return "acceleration_peak_timing"

    if matches(
        text,
        r"\bmaximum acceleration\b",
    ):
        return "acceleration_peak"

    # --------------------------------------------------------
    # Delta-V timing
    # --------------------------------------------------------

    if (
        matches(
            text,
            r"\b(?:"
            r"time|"
            r"time to|"
            r"time from"
            r")\b",
        )
        and matches(
            text,
            r"\b(?:"
            r"delta[- ]?v|"
            r"velocity change|"
            r"synthesis delta[- ]?v"
            r")\b",
        )
        and matches(
            text,
            r"\b(?:"
            r"maximum|max(?:imum)?|"
            r"recorded"
            r")\b",
        )
    ):
        return "delta_v_timing"

    # --------------------------------------------------------
    # Delta-V time-zero offsets
    # --------------------------------------------------------

    if matches(
        text,
        r"\bdelta[- ]?v\b.*\btime zero offset\b",
    ):
        return "delta_v_time_zero_offset"

    # --------------------------------------------------------
    # Delta-V duration / integration
    # --------------------------------------------------------

    if matches(
        text,
        r"\blength of delta[- ]?v\b",
    ):
        return "delta_v_duration"

    if matches(
        text,
        r"\bintegration time\b.*\bdelta[- ]?v\b",
    ):
        return "delta_v_integration_time"

    # --------------------------------------------------------
    # Delta-V component / maximum summaries
    # --------------------------------------------------------

    if matches(
        text,
        r"\b(?:"
        r"maximum|max\.?|max"
        r")\b.*\b(?:"
        r"delta[- ]?v|"
        r"velocity change"
        r")\b",
    ):
        return "delta_v_summary"

    if matches(
        text,
        r"\b(?:"
        r"longitudinal|lateral"
        r")\b.*\bvelocity change\b.*\btime of maximum\b",
    ):
        return "delta_v_component_at_maximum"

    if matches(
        text,
        r"\b(?:resultant|synthesis)\b.*\bdelta[- ]?v\b",
    ):
        return "delta_v_summary"

    # --------------------------------------------------------
    # Roll / direction
    # --------------------------------------------------------

    if matches(
        text,
        r"\broll ?angle peak\b|\brollangle peak\b",
    ):
        return "roll_peak"

    if matches(
        text,
        r"\b(?:"
        r"recorded side|"
        r"pdof|"
        r"principal direction"
        r")\b",
    ):
        return "direction_summary"

    # --------------------------------------------------------
    # Trigger timing
    # --------------------------------------------------------

    if matches(
        text,
        r"\btime from time zero to trg\b",
    ):
        return "trigger_relative_timing"

    return (
        norm(old_family)
        or "other_crash_measurement"
    )


# ============================================================
# Review recovery
# ============================================================

def classify_review_label(label):
    """
    Return:
        decision, family, status, reason

    Decisions:
        accept
        companion
        exclude
        review
    """

    text = norm(label)

    # --------------------------------------------------------
    # Recover definite Group 5 scalar measurements
    # --------------------------------------------------------

    if matches(
        text,
        r"^roll angle at the time of trg\b",
    ):
        return (
            "accept",
            "roll_at_trigger",
            "recovered_group5_measurement",
            "scalar_roll_angle_at_trigger",
        )

    if matches(
        text,
        r"\broll angle time zero offset\b",
    ):
        return (
            "accept",
            "roll_time_zero_offset",
            "recovered_group5_measurement",
            "scalar_roll_time_alignment_measurement",
        )

    if matches(
        text,
        r"\bsensor design range exceeded time\b.*\bacceleration\b",
    ):
        return (
            "accept",
            "range_clipping_timing",
            "recovered_group5_measurement",
            "sensor_range_exceeded_timing",
        )

    if matches(
        text,
        r"\bintegration time\b.*\bdelta[- ]?v\b",
    ):
        return (
            "accept",
            "delta_v_integration_time",
            "recovered_group5_measurement",
            "scalar_delta_v_integration_time",
        )

    if matches(
        text,
        r"\btime yaw rate lost\b",
    ):
        return (
            "accept",
            "sensor_loss_timing",
            "recovered_group5_measurement",
            "scalar_yaw_rate_loss_timing",
        )

    if matches(
        text,
        r"\btime from last speed data sample\b.*\btime zero\b",
    ):
        return (
            "accept",
            "precrash_time_alignment",
            "recovered_group5_measurement",
            "precrash_sample_to_event_time_alignment",
        )

    # --------------------------------------------------------
    # Group 5 companion/context fields
    # --------------------------------------------------------

    if matches(
        text,
        r"\bpower supply status\b.*\bmax\.?\s*delta[- ]?v\b",
    ):
        return (
            "companion",
            "measurement_context",
            "group5_companion_context",
            "status_at_delta_v_summary",
        )

    if matches(
        text,
        r"\bclipping flag\b",
    ):
        return (
            "companion",
            "measurement_quality_context",
            "group5_companion_context",
            "clipping_flag_context",
        )

    if matches(
        text,
        r"\btime from pre[- ]?crash to trg\b",
    ):
        return (
            "companion",
            "temporal_alignment_context",
            "group5_companion_context",
            "precrash_to_trigger_alignment_context",
        )

    if matches(
        text,
        r"\btime from trg to next sample\b",
    ):
        return (
            "companion",
            "temporal_alignment_context",
            "group5_companion_context",
            "trigger_to_next_sample_alignment_context",
        )

    # --------------------------------------------------------
    # Explicit non-Group-5 routing
    # --------------------------------------------------------

    # Group 2: event/record structure
    if matches(
        text,
        r"\b(?:"
        r"event\(s\) recovered|"
        r"recording status|"
        r"complete file recorded|"
        r"previous crash type|"
        r"event record type|"
        r"event type|"
        r"multi[- ]?event|"
        r"concurrent event|"
        r"time from event \d+ to \d+|"
        r"time from previous event|"
        r"time from initial event|"
        r"time from previous trg|"
        r"trg count|"
        r"trip count"
        r")\b",
    ):
        return (
            "exclude",
            "group2_or_record_structure",
            "excluded_non_group5",
            "record_or_event_structure",
        )

    # Group 3: restraint/deployment/status
    if matches(
        text,
        r"\b(?:"
        r"safety belt|"
        r"seat track|"
        r"passenger seat occupancy|"
        r"deployment|"
        r"event severity status|"
        r"algorithm active|"
        r"rsca disable|"
        r"onstar .* data sent|"
        r"onstar deployment|"
        r"knee deployment|"
        r"warning lamp|"
        r"occupant|"
        r"restraint"
        r")\b",
    ):
        return (
            "exclude",
            "group3_status",
            "excluded_non_group5",
            "deployment_restraint_or_event_status",
        )

    # Group 6 / technical context
    if matches(
        text,
        r"\b(?:"
        r"odometer|"
        r"vehicle mileage|"
        r"operating time|"
        r"freeze signal|"
        r"location of .*sensor|"
        r"supply voltage|"
        r"vehicle clock|"
        r"event establishment factor|"
        r"trg establishment factor|"
        r"time count input system|"
        r"time count"
        r")\b",
    ):
        return (
            "exclude",
            "group6_technical",
            "excluded_non_group5",
            "technical_or_investigation_context",
        )

    # Timing of algorithm start/reset is status/control context,
    # not a physical summary measurement for this group.
    if matches(
        text,
        r"\btime from time zero to algorithm (?:start|reset)\b",
    ):
        return (
            "exclude",
            "group3_algorithm_status",
            "excluded_non_group5",
            "algorithm_state_timing",
        )

    # Rollover deployment angle belongs with deployment status,
    # not generic crash scalar measurements.
    if matches(
        text,
        r"\broll angle\b.*\bdeployment\b",
    ):
        return (
            "exclude",
            "group3_deployment_status",
            "excluded_non_group5",
            "deployment_related_roll_angle",
        )

    return (
        "review",
        "unresolved_review",
        "remaining_review",
        "no_safe_group5_resolution_rule",
    )


# ============================================================
# Audit record
# ============================================================

def audit_candidate(row):
    family = refine_candidate_family(
        row.get(
            "field_label_raw",
            "",
        ),
        row.get(
            "candidate_family",
            "",
        ),
    )

    return {
        **row,

        "audited_family":
            family,

        "audit_decision":
            "accept",

        "audit_status":
            "accepted_group5_candidate",

        "audit_reason":
            "strong_scalar_crash_measurement_pattern",

        "audit_origin":
            "discovery_candidate",
    }


def audit_review(row):
    (
        decision,
        family,
        status,
        reason,
    ) = classify_review_label(
        row.get(
            "field_label_raw",
            "",
        )
    )

    return {
        **row,

        "audited_family":
            family,

        "audit_decision":
            decision,

        "audit_status":
            status,

        "audit_reason":
            reason,

        "audit_origin":
            "discovery_review",
    }


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--discovery-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_discovery_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_audit_v1"
        ),
    )

    args = parser.parse_args()

    candidate_path = (
        args.discovery_directory
        / "group5_candidate_fields.csv"
    )

    review_path = (
        args.discovery_directory
        / "group5_review_fields.csv"
    )

    if not candidate_path.exists():
        raise FileNotFoundError(
            candidate_path
        )

    if not review_path.exists():
        raise FileNotFoundError(
            review_path
        )

    candidates = read_csv(
        candidate_path
    )

    reviews = read_csv(
        review_path
    )

    audited = []

    for row in candidates:
        audited.append(
            audit_candidate(row)
        )

    for row in reviews:
        audited.append(
            audit_review(row)
        )

    accepted = [
        row
        for row in audited
        if row[
            "audit_decision"
        ] == "accept"
    ]

    companions = [
        row
        for row in audited
        if row[
            "audit_decision"
        ] == "companion"
    ]

    excluded = [
        row
        for row in audited
        if row[
            "audit_decision"
        ] == "exclude"
    ]

    remaining_review = [
        row
        for row in audited
        if row[
            "audit_decision"
        ] == "review"
    ]

    # ========================================================
    # Summaries
    # ========================================================

    family_counts = Counter(
        row[
            "audited_family"
        ]
        for row in accepted
    )

    decision_counts = Counter(
        row[
            "audit_decision"
        ]
        for row in audited
    )

    origin_decisions = Counter(
        (
            row[
                "audit_origin"
            ],
            row[
                "audit_decision"
            ],
        )
        for row in audited
    )

    reports_with_accepted = {
        row.get(
            "report_id",
            ""
        )
        for row in accepted
        if row.get(
            "report_id",
            ""
        )
    }

    promoted_from_review = [
        row
        for row in accepted
        if row[
            "audit_origin"
        ] == "discovery_review"
    ]

    # Family summary
    family_summary = [
        {
            "audited_family":
                family,

            "field_count":
                count,

            "report_count":
                len(
                    {
                        row.get(
                            "report_id",
                            ""
                        )
                        for row in accepted
                        if row[
                            "audited_family"
                        ] == family
                        and row.get(
                            "report_id",
                            ""
                        )
                    }
                ),

            "promoted_from_review_count":
                sum(
                    1
                    for row in accepted
                    if (
                        row[
                            "audited_family"
                        ] == family
                        and row[
                            "audit_origin"
                        ] == "discovery_review"
                    )
                ),
        }
        for family, count
        in family_counts.most_common()
    ]

    decision_summary = [
        {
            "audit_origin":
                origin,

            "audit_decision":
                decision,

            "field_count":
                count,
        }
        for (
            origin,
            decision,
        ), count
        in sorted(
            origin_decisions.items()
        )
    ]

    # Label-decision summary
    label_grouped = defaultdict(
        Counter
    )

    for row in audited:
        label = norm(
            row.get(
                "field_label_raw",
                ""
            )
        )

        label_grouped[
            label
        ][
            row[
                "audit_decision"
            ]
        ] += 1

    label_decision_summary = []

    for label, counts in sorted(
        label_grouped.items(),
        key=lambda item: (
            -sum(
                item[1].values()
            ),
            item[0].casefold(),
        ),
    ):
        label_decision_summary.append({
            "field_label_raw":
                label,

            "total_count":
                sum(
                    counts.values()
                ),

            "accept_count":
                counts.get(
                    "accept",
                    0,
                ),

            "companion_count":
                counts.get(
                    "companion",
                    0,
                ),

            "exclude_count":
                counts.get(
                    "exclude",
                    0,
                ),

            "review_count":
                counts.get(
                    "review",
                    0,
                ),
        })

    # ========================================================
    # Validation
    # ========================================================

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

    duplicate_ids = sum(
        1
        for count
        in Counter(
            row.get(
                "group5_candidate_id",
                ""
            )
            for row in audited
            if row.get(
                "group5_candidate_id",
                ""
            )
        ).values()
        if count > 1
    )

    if input_total != output_total:
        raise RuntimeError(
            "Audit accounting mismatch: "
            f"{input_total} != {output_total}"
        )

    # ========================================================
    # Write
    # ========================================================

    out = args.output_directory
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    columns = union_columns(
        audited
    )

    write_csv(
        out
        / "audit_all_fields.csv",
        audited,
        columns,
    )

    write_csv(
        out
        / "accepted_group5_fields.csv",
        accepted,
        columns,
    )

    write_csv(
        out
        / "companion_group5_context.csv",
        companions,
        columns,
    )

    write_csv(
        out
        / "excluded_non_group5_fields.csv",
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

    # ========================================================
    # Metadata
    # ========================================================

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "CSV candidate audit",

        "input_discovery_candidates":
            len(
                candidates
            ),

        "input_discovery_review_fields":
            len(
                reviews
            ),

        "total_fields_audited":
            len(
                audited
            ),

        "accepted_group5_fields":
            len(
                accepted
            ),

        "companion_group5_context_fields":
            len(
                companions
            ),

        "excluded_non_group5_fields":
            len(
                excluded
            ),

        "remaining_review_fields":
            len(
                remaining_review
            ),

        "reports_with_accepted_group5_fields":
            len(
                reports_with_accepted
            ),

        "promoted_from_discovery_review":
            len(
                promoted_from_review
            ),

        "accepted_family_counts":
            dict(
                family_counts
            ),

        "decision_counts":
            dict(
                decision_counts
            ),

        "duplicate_candidate_ids":
            duplicate_ids,

        "input_accounting_total":
            input_total,

        "output_accounting_total":
            output_total,

        "all_fields_accounted_for":
            (
                input_total
                == output_total
            ),

        "scope":
            (
                "Audit of Group 5 CSV discovery candidates and review "
                "fields. Delta-V scalar summaries are separated from "
                "time-of-maximum fields; peak acceleration values are "
                "separated from peak timing; clipping/range-exceeded "
                "timing remains a Group 5 measurement-quality family. "
                "Selected scalar measurements are recovered from the "
                "review population, while direct measurement context is "
                "preserved separately as Group 5 companion metadata. "
                "Unrelated record structure, restraint/deployment/status, "
                "and technical/investigation fields are excluded. "
                "No semantic value normalization, unit conversion, fuzzy "
                "event linking, PDF processing, or final extraction is "
                "performed."
            ),
    }

    tmp = (
        out
        / "metadata.json.part"
    )

    tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        out
        / "metadata.json"
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

    print()
    print(
        "GROUP 5 CSV CANDIDATE AUDIT COMPLETE."
    )


if __name__ == "__main__":
    main()
