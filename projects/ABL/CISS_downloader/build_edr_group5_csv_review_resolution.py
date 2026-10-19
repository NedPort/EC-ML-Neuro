"""
Resolve the remaining Group 5 CSV audit review fields and correct one
targeted family-classification issue.

Inputs
------
data/processed/edr/group5_csv_audit_v1/
    accepted_group5_fields.csv
    companion_group5_context.csv
    excluded_non_group5_fields.csv
    remaining_review_fields.csv

Outputs
-------
data/processed/edr/group5_csv_resolved_v1/

    accepted_group5_fields.csv
    companion_group5_context.csv
    excluded_non_group5_fields.csv
    remaining_review_fields.csv
    resolution_all_fields.csv
    family_summary.csv
    resolution_summary.csv
    metadata.json

Targeted corrections
--------------------
1. Reclassify scalar component values such as:
       Longitudinal ... Velocity Change at time of Maximum ...
       Lateral ... Velocity Change at time of Maximum ...
   from delta_v_timing to delta_v_component_at_maximum.

2. Resolve the 575 remaining review fields conservatively:
   - Saved on -> Group 1/report metadata
   - High Voltage Disable Notification Sent -> Group 3/status
   - Power loss detected during Event -> Group 3/event condition
   - Supplier ID, ACM -> Group 6/technical
   - Production Date, ACM -> Group 6/technical
   - Most Recent Event / Nth Prior Event -> Group 2/event structure

No accepted Group 5 value is changed, normalized, converted, or event-linked.
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


def union_columns(*row_sets):
    seen = set()
    columns = []

    preferred = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "group5_candidate_id",
        "field_label_raw",
        "field_value_raw",
        "audited_family",
        "audit_decision",
        "audit_status",
        "audit_reason",
        "resolution_decision",
        "resolution_status",
        "resolution_reason",
    ]

    for column in preferred:
        if column not in seen:
            seen.add(column)
            columns.append(column)

    for rows in row_sets:
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    columns.append(key)

    return columns


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


def reclassify_accepted(row):
    label = norm(
        row.get(
            "field_label_raw",
            ""
        )
    )

    family = norm(
        row.get(
            "audited_family",
            ""
        )
    )

    if (
        family == "delta_v_timing"
        and re.search(
            r"\b(?:longitudinal|lateral)\b",
            label,
            re.I,
        )
        and re.search(
            r"\bvelocity change\b",
            label,
            re.I,
        )
        and re.search(
            r"\bat time of maximum\b",
            label,
            re.I,
        )
        and not re.search(
            r"^\s*time\b",
            label,
            re.I,
        )
    ):
        row = dict(row)
        row["audited_family"] = (
            "delta_v_component_at_maximum"
        )
        row["audit_reason"] = (
            "scalar_component_value_at_resultant_maximum"
        )
        row["family_resolution_note"] = (
            "reclassified_from_delta_v_timing"
        )
        return row, True

    row = dict(row)
    row["family_resolution_note"] = ""
    return row, False


def resolve_review(row):
    label = norm(
        row.get(
            "field_label_raw",
            ""
        )
    )

    lower = label.casefold()

    if lower == "saved on":
        destination = "group1_report_metadata"
        reason = "report_saved_timestamp"

    elif lower == (
        "high voltage disable notification sent"
    ):
        destination = "group3_event_condition_status"
        reason = "event_related_high_voltage_status"

    elif lower == (
        "power loss detected during event"
    ):
        destination = "group3_event_condition_status"
        reason = "power_loss_event_condition"

    elif lower == "supplier id, acm":
        destination = "group6_technical"
        reason = "module_supplier_identifier"

    elif lower == "production date, acm":
        destination = "group6_technical"
        reason = "module_production_metadata"

    elif re.fullmatch(
        r"(?:"
        r"most recent event|"
        r"\d+(?:st|nd|rd|th) prior event"
        r")",
        lower,
        re.I,
    ):
        destination = "group2_event_structure"
        reason = "event_record_label"

    else:
        return {
            **row,
            "resolution_decision":
                "review",
            "resolution_status":
                "remaining_review",
            "resolution_reason":
                "no_safe_resolution_rule",
            "resolution_destination":
                "",
        }

    return {
        **row,
        "resolution_decision":
            "exclude",
        "resolution_status":
            "resolved_non_group5",
        "resolution_reason":
            reason,
        "resolution_destination":
            destination,
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--audit-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_audit_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_resolved_v1"
        ),
    )

    args = parser.parse_args()

    required = {
        "accepted":
            args.audit_directory
            / "accepted_group5_fields.csv",

        "companions":
            args.audit_directory
            / "companion_group5_context.csv",

        "excluded":
            args.audit_directory
            / "excluded_non_group5_fields.csv",

        "review":
            args.audit_directory
            / "remaining_review_fields.csv",
    }

    for name, path in required.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {name}: {path}"
            )

    accepted_input = read_csv(
        required["accepted"]
    )

    companions = read_csv(
        required["companions"]
    )

    excluded_existing = read_csv(
        required["excluded"]
    )

    review_input = read_csv(
        required["review"]
    )

    accepted = []
    reclassified_count = 0

    for row in accepted_input:
        resolved, changed = (
            reclassify_accepted(row)
        )
        accepted.append(resolved)

        if changed:
            reclassified_count += 1

    resolved_review = [
        resolve_review(row)
        for row in review_input
    ]

    resolved_non_group5 = [
        row
        for row in resolved_review
        if row[
            "resolution_decision"
        ] == "exclude"
    ]

    remaining_review = [
        row
        for row in resolved_review
        if row[
            "resolution_decision"
        ] == "review"
    ]

    final_excluded = (
        list(excluded_existing)
        + resolved_non_group5
    )

    input_total = (
        len(accepted_input)
        + len(companions)
        + len(excluded_existing)
        + len(review_input)
    )

    output_total = (
        len(accepted)
        + len(companions)
        + len(final_excluded)
        + len(remaining_review)
    )

    if input_total != output_total:
        raise RuntimeError(
            "Resolution accounting mismatch: "
            f"{input_total} != {output_total}"
        )

    family_counts = Counter(
        row.get(
            "audited_family",
            ""
        )
        for row in accepted
    )

    resolution_counts = Counter(
        row[
            "resolution_destination"
        ]
        for row in resolved_non_group5
    )

    out = args.output_directory
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_columns = union_columns(
        accepted,
        companions,
        final_excluded,
        remaining_review,
    )

    write_csv(
        out
        / "accepted_group5_fields.csv",
        accepted,
        all_columns,
    )

    write_csv(
        out
        / "companion_group5_context.csv",
        companions,
        all_columns,
    )

    write_csv(
        out
        / "excluded_non_group5_fields.csv",
        final_excluded,
        all_columns,
    )

    write_csv(
        out
        / "remaining_review_fields.csv",
        remaining_review,
        all_columns,
    )

    write_csv(
        out
        / "resolution_all_fields.csv",
        resolved_review,
        all_columns,
    )

    family_summary = [
        {
            "audited_family":
                family,
            "field_count":
                count,
        }
        for family, count
        in family_counts.most_common()
    ]

    write_csv(
        out
        / "family_summary.csv",
        family_summary,
        [
            "audited_family",
            "field_count",
        ],
    )

    resolution_summary = [
        {
            "resolution_destination":
                destination,
            "field_count":
                count,
        }
        for destination, count
        in resolution_counts.most_common()
    ]

    write_csv(
        out
        / "resolution_summary.csv",
        resolution_summary,
        [
            "resolution_destination",
            "field_count",
        ],
    )

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "CSV residual review resolution",

        "input_accepted_group5_fields":
            len(accepted_input),

        "reclassified_accepted_fields":
            reclassified_count,

        "input_remaining_review_fields":
            len(review_input),

        "resolved_non_group5_fields":
            len(resolved_non_group5),

        "remaining_review_fields":
            len(remaining_review),

        "final_accepted_group5_fields":
            len(accepted),

        "final_companion_group5_context_fields":
            len(companions),

        "final_excluded_non_group5_fields":
            len(final_excluded),

        "accepted_family_counts":
            dict(family_counts),

        "resolution_destination_counts":
            dict(resolution_counts),

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
                "Targeted resolution of the Group 5 CSV audit residual "
                "population plus one family-classification correction. "
                "Component velocity-change values reported at the time "
                "of maximum resultant velocity change are reclassified "
                "as scalar component measurements rather than timing "
                "fields. The residual review population is routed to "
                "Group 1, Group 2, Group 3, or Group 6 based only on "
                "explicit labels. No Group 5 values are normalized or "
                "converted, and no fuzzy event identity inference is "
                "performed."
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

    print()
    print(
        "GROUP 5 CSV REVIEW RESOLUTION COMPLETE."
    )


if __name__ == "__main__":
    main()
