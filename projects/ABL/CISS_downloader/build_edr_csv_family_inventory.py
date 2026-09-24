from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


CSV_PROFILE_FILE = Path(
    "data/processed/edr/edr_csv_profile.csv"
)

OUTPUT_DIRECTORY = Path("data/processed/edr")

FAMILY_DETAIL_FILE = OUTPUT_DIRECTORY / (
    "edr_csv_report_family_candidates.csv"
)

FAMILY_SUMMARY_FILE = OUTPUT_DIRECTORY / (
    "edr_csv_report_family_summary.csv"
)

FAMILY_METADATA_FILE = OUTPUT_DIRECTORY / (
    "edr_csv_report_family_metadata.json"
)

TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def read_csv_rows(csv_path: Path) -> list[list[str]]:
    for encoding in TEXT_ENCODINGS:
        try:
            text = csv_path.read_text(
                encoding=encoding,
                errors="strict",
            )
            break
        except UnicodeDecodeError:
            continue
    else:
        text = csv_path.read_text(
            encoding="latin-1",
            errors="replace",
        )

    return [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO(text))
    ]


def normalize_text(value: str) -> str:
    value = value.upper().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def normalized_section_name(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(
        r"\(EVENT RECORD\s+\d+\)",
        "(EVENT RECORD #)",
        value,
    )
    value = value.replace(
        "(MOST RECENT EVENT)",
        "(EVENT)",
    )
    return value


def first_value_after_label(row: list[str]) -> str:
    for cell in row[1:]:
        if cell.strip():
            return cell.strip()

    return ""


def get_metadata_value(
    rows: list[list[str]],
    label_fragment: str,
) -> str:
    target = normalize_text(label_fragment)

    for row in rows:
        if not row:
            continue

        label = normalize_text(row[0])

        if target in label:
            return first_value_after_label(row)

    return ""


def get_system_name(rows: list[list[str]]) -> str:
    for row in rows[:20]:
        if not row:
            continue

        first_cell = row[0].strip()

        if first_cell.upper().startswith("SYSTEM:"):
            return first_cell.split(
                ":",
                maxsplit=1,
            )[1].strip()

    return ""


def classify_section(first_cell: str) -> str:
    value = normalize_text(first_cell)

    if value.startswith("SYSTEM STATUS AT EVENT"):
        return "system_status_at_event"

    if value.startswith("DEPLOYMENT COMMAND DATA"):
        return "deployment_command_data"

    if value.startswith("EVENT DATA"):
        return "event_data"

    if value.startswith("DTCS PRESENT"):
        return "dtc_table"

    if value.startswith("LONGITUDINAL CRASH PULSE"):
        return "longitudinal_crash_pulse"

    if value.startswith("LATERAL CRASH PULSE"):
        return "lateral_crash_pulse"

    if value.startswith("ROLLOVER CRASH PULSE"):
        return "rollover_crash_pulse"

    if value.startswith("VERTICAL CRASH PULSE"):
        return "vertical_crash_pulse"

    if value.startswith("PRE-CRASH DATA"):
        return "precrash_data"

    if value.startswith("PRE_CRASH DATA"):
        return "precrash_data"

    if value.startswith("DELTA-V, LONGITUDINAL"):
        return "longitudinal_delta_v_table"

    if value.startswith("DELTA-V, LATERAL"):
        return "lateral_delta_v_table"

    return ""


def extract_sections(rows: list[list[str]]) -> list[str]:
    sections: list[str] = []

    for row in rows:
        if not row:
            continue

        first_cell = row[0].strip()

        if not first_cell:
            continue

        category = classify_section(first_cell)

        if category:
            sections.append(
                f"{category}: {normalized_section_name(first_cell)}"
            )

    return sections


def make_family_key(
    system_name: str,
    device_type: str,
    section_categories: list[str],
) -> str:
    system_key = normalize_text(system_name) or "NO_SYSTEM_LABEL"
    device_key = normalize_text(device_type) or "NO_DEVICE_LABEL"
    sections_key = "|".join(section_categories)

    return (
        f"system={system_key}; "
        f"device={device_key}; "
        f"sections={sections_key}"
    )


def write_csv(
    output_path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> None:
    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not CSV_PROFILE_FILE.is_file():
        raise FileNotFoundError(
            "Run build_edr_export_inventory.py first."
        )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    with CSV_PROFILE_FILE.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        profile_rows = list(csv.DictReader(file))

    detail_rows: list[dict[str, str]] = []
    grouped_rows: dict[str, list[dict[str, str]]] = defaultdict(list)

    for profile_row in profile_rows:
        csv_path = Path(profile_row["csv_export_path"])

        if not csv_path.is_file():
            continue

        rows = read_csv_rows(csv_path)

        system_name = get_system_name(rows)
        device_type = get_metadata_value(
            rows,
            "EDR Device Type",
        )
        recovered_events = get_metadata_value(
            rows,
            "Event(s) recovered",
        )

        section_entries = extract_sections(rows)

        section_categories = [
            entry.split(":", maxsplit=1)[0]
            for entry in section_entries
        ]

        unique_section_categories = list(
            dict.fromkeys(section_categories)
        )

        family_key = make_family_key(
            system_name=system_name,
            device_type=device_type,
            section_categories=unique_section_categories,
        )

        detail_row = {
            "case_id": profile_row["case_id"],
            "vehicle_number": profile_row["vehicle_number"],
            "export_basename": profile_row["export_basename"],
            "cdrx_source_path": profile_row["cdrx_source_path"],
            "csv_export_path": str(csv_path.resolve()),
            "system_name": system_name,
            "edr_device_type": device_type,
            "events_recovered": recovered_events,
            "csv_row_count": profile_row["csv_row_count"],
            "csv_maximum_column_count": (
                profile_row["csv_maximum_column_count"]
            ),
            "section_categories": "|".join(
                unique_section_categories
            ),
            "section_headings_json": json.dumps(
                section_entries,
                ensure_ascii=False,
            ),
            "provisional_family_key": family_key,
        }

        detail_rows.append(detail_row)
        grouped_rows[family_key].append(detail_row)

    summary_rows: list[dict[str, str]] = []

    for family_number, (
        family_key,
        rows_in_family,
    ) in enumerate(
        sorted(
            grouped_rows.items(),
            key=lambda item: (
                -len(item[1]),
                item[0],
            ),
        ),
        start=1,
    ):
        representative = rows_in_family[0]

        summary_rows.append(
            {
                "provisional_family_id": (
                    f"family_{family_number:02d}"
                ),
                "report_count": str(len(rows_in_family)),
                "system_name": representative["system_name"],
                "edr_device_type": (
                    representative["edr_device_type"]
                ),
                "section_categories": (
                    representative["section_categories"]
                ),
                "representative_case_id": (
                    representative["case_id"]
                ),
                "representative_vehicle_number": (
                    representative["vehicle_number"]
                ),
                "representative_csv_path": (
                    representative["csv_export_path"]
                ),
                "provisional_family_key": family_key,
            }
        )

    detail_fieldnames = [
        "case_id",
        "vehicle_number",
        "export_basename",
        "cdrx_source_path",
        "csv_export_path",
        "system_name",
        "edr_device_type",
        "events_recovered",
        "csv_row_count",
        "csv_maximum_column_count",
        "section_categories",
        "section_headings_json",
        "provisional_family_key",
    ]

    summary_fieldnames = [
        "provisional_family_id",
        "report_count",
        "system_name",
        "edr_device_type",
        "section_categories",
        "representative_case_id",
        "representative_vehicle_number",
        "representative_csv_path",
        "provisional_family_key",
    ]

    write_csv(
        output_path=FAMILY_DETAIL_FILE,
        rows=detail_rows,
        fieldnames=detail_fieldnames,
    )

    write_csv(
        output_path=FAMILY_SUMMARY_FILE,
        rows=summary_rows,
        fieldnames=summary_fieldnames,
    )

    metadata = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "csv_reports_scanned": len(detail_rows),
        "provisional_family_count": len(summary_rows),
        "outputs": {
            "family_candidates": str(FAMILY_DETAIL_FILE),
            "family_summary": str(FAMILY_SUMMARY_FILE),
        },
        "notes": [
            "Families are provisional structure-based groups.",
            "A parser is created only after inspecting a representative report.",
            "Different event counts can occur within one report family.",
            "EDR values are not yet linked to CISS vehicle-events.",
        ],
    }

    FAMILY_METADATA_FILE.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("EDR CSV family discovery completed.")
    print(f"CSV reports scanned: {len(detail_rows)}")
    print(
        f"Provisional parser families: {len(summary_rows)}"
    )
    print(f"Family summary: {FAMILY_SUMMARY_FILE}")
    print(f"Family details: {FAMILY_DETAIL_FILE}")
    print(f"Metadata: {FAMILY_METADATA_FILE}")


if __name__ == "__main__":
    main()