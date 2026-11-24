"""
Run the CISS Stage-2 audit for all downloaded numeric case folders.

Examples
--------
python audit_all.py
python audit_all.py --limit 5
python audit_all.py --data-root data
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.audit.case_auditor import CaseAuditor


def build_parser() -> argparse.ArgumentParser:
    """Create command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create or refresh Stage-2 audits for all downloaded "
            "CISS cases."
        )
    )

    parser.add_argument(
        "--data-root",
        default="data",
        help="Root data directory; default: data",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Audit only the first N numeric case folders. "
            "Useful for testing."
        ),
    )

    return parser


def find_case_ids(data_root: Path) -> list[int]:
    """Find numeric case directories under data/raw."""
    raw_directory = data_root / "raw"

    if not raw_directory.is_dir():
        raise RuntimeError(
            f"Raw CISS directory does not exist: {raw_directory}"
        )

    case_ids = sorted(
        int(directory.name)
        for directory in raw_directory.iterdir()
        if directory.is_dir() and directory.name.isdigit()
    )

    if not case_ids:
        raise RuntimeError(
            "No numeric CISS case folders were found under "
            f"{raw_directory}"
        )

    return case_ids


def _summary_by_message(
    results: list[dict[str, Any]],
    message_key: str,
    summary_key: str,
) -> list[dict[str, Any]]:
    """
    Summarize repeated warnings or errors across completed cases.

    Parameters
    ----------
    results:
        One result record per requested case.
    message_key:
        Either 'warnings' or 'errors'.
    summary_key:
        Either 'warning' or 'error'.
    """
    message_to_case_ids: dict[str, list[int]] = {}

    for result in results:
        if result.get("run_status") != "completed":
            continue

        case_id = int(result["case_id"])

        for message in result.get(message_key, []):
            text = str(message)

            message_to_case_ids.setdefault(
                text,
                [],
            ).append(case_id)

    return [
        {
            summary_key: message,
            "case_count": len(case_ids),
            "case_ids": sorted(case_ids),
        }
        for message, case_ids in sorted(
            message_to_case_ids.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]


def _collision_context_summary(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Summarize collision-partner categories and preserve the exact
    CISS contact details for fixed-object and unknown events.
    """
    completed = [
        result
        for result in results
        if result.get("run_status") == "completed"
    ]

    multi_vehicle_case_ids: list[int] = []
    category_to_case_ids: dict[str, set[int]] = {}
    category_event_counts: dict[str, int] = {}

    fixed_object_events: list[dict[str, Any]] = []
    unknown_collision_events: list[dict[str, Any]] = []

    for result in completed:
        case_id = int(result["case_id"])

        vehicle_count = result.get("case_vehicle_count")

        if vehicle_count is not None and int(vehicle_count) > 1:
            multi_vehicle_case_ids.append(case_id)

        for event in result.get("collision_events", []):
            partner_class = str(
                event.get("collision_partner_class")
                or "unknown"
            )

            category_event_counts[partner_class] = (
                category_event_counts.get(partner_class, 0) + 1
            )

            category_to_case_ids.setdefault(
                partner_class,
                set(),
            ).add(case_id)

            event_detail = {
                "case_id": case_id,
                "vehicle_number": event.get(
                    "vehicle_number"
                ),
                "event_number": event.get(
                    "event_number"
                ),
                "collision_partner_class": partner_class,
                "collision_partner_text": event.get(
                    "collision_partner_text"
                ),
                "collision_partner_raw_code": event.get(
                    "collision_partner_raw_code"
                ),
                "collision_context_source": event.get(
                    "collision_context_source"
                ),
                "collision_context_status": event.get(
                    "collision_context_status"
                ),
            }

            if partner_class == "fixed_object":
                fixed_object_events.append(event_detail)

            if partner_class == "unknown":
                unknown_collision_events.append(event_detail)

    category_summary = [
        {
            "collision_partner_class": partner_class,
            "event_count": category_event_counts[
                partner_class
            ],
            "case_count": len(
                category_to_case_ids[partner_class]
            ),
            "case_ids": sorted(
                category_to_case_ids[partner_class]
            ),
        }
        for partner_class in sorted(category_event_counts)
    ]

    return {
        "cases_with_more_than_one_vehicle": len(
            multi_vehicle_case_ids
        ),
        "multi_vehicle_case_ids": sorted(
            multi_vehicle_case_ids
        ),
        "collision_partner_category_summary": (
            category_summary
        ),
        "vehicle_to_vehicle_event_count": (
            category_event_counts.get("vehicle", 0)
        ),
        "fixed_object_event_count": len(
            fixed_object_events
        ),
        "fixed_object_events": fixed_object_events,
        "unknown_collision_event_count": len(
            unknown_collision_events
        ),
        "unknown_collision_events": (
            unknown_collision_events
        ),
    }


def save_batch_summary(
    data_root: Path,
    results: list[dict[str, Any]],
) -> Path:
    """Save cohort-level audit outcomes and recurring findings."""
    output_directory = data_root / "processed"
    output_directory.mkdir(parents=True, exist_ok=True)

    output_path = output_directory / "audit_batch_summary.json"

    successful = [
        result
        for result in results
        if result["run_status"] == "completed"
    ]

    failed = [
        result
        for result in results
        if result["run_status"] == "failed"
    ]

    audit_statuses = sorted(
        {
            result.get("audit_status")
            for result in successful
            if result.get("audit_status") is not None
        }
    )

    summary = {
        "schema_version": "1.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operation": "batch_case_audit",
        "case_count_requested": len(results),
        "case_count_completed": len(successful),
        "case_count_failed": len(failed),
        "audit_status_counts": {
            status: sum(
                result.get("audit_status") == status
                for result in successful
            )
            for status in audit_statuses
        },

        "collision_context_summary": (
            _collision_context_summary(
                results
            )
        ),        
        "warning_summary": _summary_by_message(
            results=results,
            message_key="warnings",
            summary_key="warning",
        ),
        "error_summary": _summary_by_message(
            results=results,
            message_key="errors",
            summary_key="error",
        ),
        "results": results,
    }

    output_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    return output_path


def main() -> None:
    """Audit all downloaded CISS cases."""
    arguments = build_parser().parse_args()

    data_root = Path(arguments.data_root)
    case_ids = find_case_ids(data_root)

    if arguments.limit is not None:
        if arguments.limit < 1:
            raise SystemExit(
                "--limit must be a positive integer."
            )

        case_ids = case_ids[:arguments.limit]

    auditor = CaseAuditor(data_root=data_root)
    results: list[dict[str, Any]] = []

    print("=" * 60)
    print(f"CISS batch audit started: {len(case_ids)} case(s)")
    print("=" * 60)

    for index, case_id in enumerate(case_ids, start=1):
        print()
        print(
            f"[{index}/{len(case_ids)}] "
            f"Auditing CISS case {case_id}"
        )

        try:
            audit = auditor.audit_case(case_id)

            audit_summary = audit.get(
                "audit_summary",
                {},
            )
            collision_context = audit.get(
                "collision_context",
                {},
            )

            partner_class_counts = collision_context.get(
                "partner_class_counts",
                {},
            )
            result = {
                "case_id": case_id,
                "run_status": "completed",
                "audit_status": audit.get("status"),
                "error_count": audit_summary.get(
                    "error_count",
                    0,
                ),
                "warning_count": audit_summary.get(
                    "warning_count",
                    0,
                ),

                "case_vehicle_count": collision_context.get(
                    "case_vehicle_count"
                ),
                "collision_context_available": bool(
                    collision_context
                ),

                "collision_events": collision_context.get(
                    "vehicle_events",
                    [],
                ),


                "vehicle_to_vehicle_event_count": (
                    partner_class_counts.get(
                        "vehicle",
                        0,
                    )
                ),
                "fixed_object_event_count": (
                    partner_class_counts.get(
                        "fixed_object",
                        0,
                    )
                ),
                "unknown_collision_event_count": (
                    partner_class_counts.get(
                        "unknown",
                        0,
                    )
                ),

                "errors": audit_summary.get(
                    "errors",
                    [],
                ),
                "warnings": audit_summary.get(
                    "warnings",
                    [],
                ),
            }

            print(
                "Completed: "
                f"{result['audit_status']} | "
                f"errors={result['error_count']} | "
                f"warnings={result['warning_count']}"
            )

        except Exception as error:
            result = {
                "case_id": case_id,
                "run_status": "failed",
                "error": str(error),
            }

            print(f"Failed: {error}")

        results.append(result)

    summary_path = save_batch_summary(
        data_root=data_root,
        results=results,
    )

    completed_count = sum(
        result["run_status"] == "completed"
        for result in results
    )

    failed_count = sum(
        result["run_status"] == "failed"
        for result in results
    )

    print()
    print("=" * 60)
    print("CISS batch audit finished")
    print(f"Completed: {completed_count}")
    print(f"Failed: {failed_count}")
    print(f"Summary: {summary_path}")
    print("=" * 60)

    if failed_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()