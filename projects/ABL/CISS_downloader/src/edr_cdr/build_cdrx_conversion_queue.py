"""
Find CDRX files for selected CISS cases and create a controlled
CDR conversion queue.

This script does not modify, open, or convert any CDRX file.
It creates an inventory first, so every later CDR export is
traceable to its original source file.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CASE_IDS = [6892, 7009, 7051, 7155, 7252]


def infer_vehicle_number(filename: str) -> int | None:
    """Infer V<number> from a CDRX filename when present."""

    match = re.search(r"(?:^|[_\-\s])V(\d+)(?:[_\-\s.]|$)", filename, re.I)

    return int(match.group(1)) if match else None


def build_queue(
    data_root: Path,
    output_directory: Path,
    case_ids: list[int],
) -> tuple[Path, Path]:
    """Create CSV and JSON manifests for CDRX conversion."""

    rows: list[dict[str, Any]] = []

    for case_id in case_ids:
        candidate_directories = [
            data_root / "raw" / str(case_id),
            data_root / "temp" / str(case_id) / "extracted",
            data_root / "temp" / str(case_id),
        ]

        case_directory = next(
            (
                directory
                for directory in candidate_directories
                if directory.exists()
            ),
            None,
        )

        if case_directory is None:
            rows.append(
                {
                    "case_id": case_id,
                    "vehicle_number": None,
                    "cdrx_source_path": None,
                    "csv_export_path": None,
                    "pdf_export_path": None,
                    "cdrx_file_found": False,
                    "conversion_status": "case_directory_not_found",
                    "notes": (
                        "No raw or temporary extracted case "
                        "directory was found."
                    ),
                }
            )
            continue

        cdrx_files = sorted(
            path
            for path in case_directory.rglob("*")
            if path.is_file() and path.suffix.lower() == ".cdrx"
        )

        if not cdrx_files:
            rows.append(
                {
                    "case_id": case_id,
                    "vehicle_number": None,
                    "cdrx_source_path": None,
                    "csv_export_path": None,
                    "pdf_export_path": None,
                    "cdrx_file_found": False,
                    "conversion_status": "no_cdrx_file_found",
                    "notes": (
                        "No .cdrx file was found under: "
                        f"{case_directory}"
                    ),
                }
            )
            continue

        for cdrx_path in cdrx_files:
            csv_path = cdrx_path.with_suffix(".csv")
            pdf_path = cdrx_path.with_suffix(".pdf")

            rows.append(
                {
                    "case_id": case_id,
                    "vehicle_number": infer_vehicle_number(
                        cdrx_path.name
                    ),
                    "cdrx_source_path": str(cdrx_path),
                    "csv_export_path": str(csv_path),
                    "pdf_export_path": str(pdf_path),
                    "cdrx_file_found": True,
                    "conversion_status": (
                        "already_exported"
                        if csv_path.exists()
                        else "pending_manual_cdr_export"
                    ),
                    "notes": (
                        "CSV already exists beside the CDRX file."
                        if csv_path.exists()
                        else (
                            "Open in Bosch CDR and export the "
                            "CDR report as CSV text file."
                        )
                    ),
                }
            )

    output_directory.mkdir(parents=True, exist_ok=True)

    csv_path = output_directory / "cdrx_conversion_queue_first5.csv"
    json_path = output_directory / "cdrx_conversion_queue_first5.json"

    fieldnames = [
        "case_id",
        "vehicle_number",
        "cdrx_source_path",
        "csv_export_path",
        "pdf_export_path",
        "cdrx_file_found",
        "conversion_status",
        "notes",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_ids_requested": case_ids,
        "case_count_requested": len(case_ids),
        "cdrx_file_count": sum(
            row["cdrx_file_found"]
            for row in rows
        ),
        "cases_with_cdrx": len(
            {
                row["case_id"]
                for row in rows
                if row["cdrx_file_found"]
            }
        ),
        "conversion_status_counts": {
            status: sum(
                row["conversion_status"] == status
                for row in rows
            )
            for status in sorted(
                {
                    row["conversion_status"]
                    for row in rows
                }
            )
        },
        "files": rows,
    }

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    return csv_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        default="data",
        help="Directory containing raw/<case_id> folders.",
    )
    parser.add_argument(
        "--output-directory",
        default="data/processed/edr_cdr",
        help="Directory for the conversion queue.",
    )
    parser.add_argument(
        "--case-ids",
        nargs="+",
        type=int,
        default=DEFAULT_CASE_IDS,
        help="Case IDs to scan.",
    )
    arguments = parser.parse_args()

    csv_path, json_path = build_queue(
        data_root=Path(arguments.data_root),
        output_directory=Path(arguments.output_directory),
        case_ids=arguments.case_ids,
    )

    print("CDRX conversion queue created.")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()