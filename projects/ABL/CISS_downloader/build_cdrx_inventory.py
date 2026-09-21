from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DATA_TEMP_ROOT = Path("data/temp")
OUTPUT_DIRECTORY = Path("data/processed/edr")

VEHICLE_DIRECTORY_PATTERN = re.compile(
    r"^Vehicle\s+(\d+)$",
    re.IGNORECASE,
)


def relative_path(path: Path) -> str:
    """Return a readable project-relative path when possible."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def export_status(
    pdf_exists: bool,
    csv_exists: bool,
) -> str:
    if pdf_exists and csv_exists:
        return "pdf_and_csv_available"

    if pdf_exists:
        return "pdf_only_available"

    if csv_exists:
        return "csv_only_available"

    return "needs_cdr_export"


def main() -> None:
    if not DATA_TEMP_ROOT.is_dir():
        raise FileNotFoundError(
            f"Downloaded-case directory not found: {DATA_TEMP_ROOT}"
        )

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []

    for case_directory in sorted(DATA_TEMP_ROOT.iterdir()):
        if not case_directory.is_dir():
            continue

        if not case_directory.name.isdigit():
            continue

        case_id = int(case_directory.name)

        docs_directory = (
            case_directory
            / "extracted"
            / "Docs"
        )

        if not docs_directory.is_dir():
            continue

        for vehicle_directory in sorted(docs_directory.iterdir()):
            if not vehicle_directory.is_dir():
                continue

            match = VEHICLE_DIRECTORY_PATTERN.match(
                vehicle_directory.name
            )

            if match is None:
                continue

            vehicle_number = int(match.group(1))

            cdrx_files = sorted(
                path
                for path in vehicle_directory.rglob("*")
                if path.is_file()
                and path.suffix.lower() == ".cdrx"
            )

            for cdrx_file in cdrx_files:
                export_directory = (
                    cdrx_file.parent
                    / "cdr_exports"
                )

                pdf_file = (
                    export_directory
                    / f"{cdrx_file.stem}_report.pdf"
                )

                csv_file = (
                    export_directory
                    / f"{cdrx_file.stem}_report.csv"
                )

                pdf_exists = pdf_file.is_file()
                csv_exists = csv_file.is_file()

                rows.append(
                    {
                        "case_id": case_id,
                        "vehicle_number": vehicle_number,
                        "vehicle_id": (
                            f"{case_id}-V{vehicle_number}"
                        ),
                        "cdrx_filename": cdrx_file.name,
                        "cdrx_source_path": relative_path(
                            cdrx_file
                        ),
                        "vehicle_directory": relative_path(
                            vehicle_directory
                        ),
                        "planned_export_directory": relative_path(
                            export_directory
                        ),
                        "planned_pdf_path": relative_path(
                            pdf_file
                        ),
                        "planned_csv_path": relative_path(
                            csv_file
                        ),
                        "pdf_exists": pdf_exists,
                        "csv_exists": csv_exists,
                        "cdr_export_status": export_status(
                            pdf_exists=pdf_exists,
                            csv_exists=csv_exists,
                        ),
                    }
                )

    csv_path = (
        OUTPUT_DIRECTORY
        / "cdrx_file_inventory.csv"
    )

    fieldnames = [
        "case_id",
        "vehicle_number",
        "vehicle_id",
        "cdrx_filename",
        "cdrx_source_path",
        "vehicle_directory",
        "planned_export_directory",
        "planned_pdf_path",
        "planned_csv_path",
        "pdf_exists",
        "csv_exists",
        "cdr_export_status",
    ]

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    status_counts = Counter(
        row["cdr_export_status"]
        for row in rows
    )

    case_ids_with_cdrx = sorted(
        {
            row["case_id"]
            for row in rows
        }
    )

    metadata = {
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "inventory_name": "cdrx_file_inventory",
        "source_root": str(DATA_TEMP_ROOT),
        "scan_rule": (
            "Scan data/temp/<case_id>/extracted/"
            "Docs/Vehicle */ recursively for .cdrx files."
        ),
        "cdrx_file_count": len(rows),
        "case_count_with_cdrx": len(
            case_ids_with_cdrx
        ),
        "case_ids_with_cdrx": case_ids_with_cdrx,
        "export_status_counts": dict(
            status_counts
        ),
        "csv_inventory": str(csv_path),
    }

    json_path = (
        OUTPUT_DIRECTORY
        / "cdrx_file_inventory_metadata.json"
    )

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2,
        )

    print("CDRX inventory completed.")
    print(f"CDRX files: {len(rows)}")
    print(
        "Cases containing CDRX files: "
        f"{len(case_ids_with_cdrx)}"
    )
    print(f"CSV: {csv_path}")
    print(f"Metadata: {json_path}")
    print("Status counts:")

    for status, count in sorted(
        status_counts.items()
    ):
        print(f"  {status}: {count}")


if __name__ == "__main__":
    main()