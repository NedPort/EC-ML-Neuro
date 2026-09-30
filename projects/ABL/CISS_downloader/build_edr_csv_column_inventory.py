from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


FAMILY_SUMMARY_FILE = Path(
    "data/processed/edr/edr_csv_report_family_summary.csv"
)

FAMILY_CANDIDATES_FILE = Path(
    "data/processed/edr/edr_csv_report_family_candidates.csv"
)

OUTPUT_DIRECTORY = Path("data/processed/edr")


SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "system_status_at_event",
        re.compile(r"^SYSTEM STATUS AT EVENT", re.IGNORECASE),
    ),
    (
        "deployment_command_data",
        re.compile(r"^DEPLOYMENT COMMAND DATA", re.IGNORECASE),
    ),
    (
        "dtc_table",
        re.compile(
            r"^(DTC|DTCS) PRESENT AT START OF EVENT",
            re.IGNORECASE,
        ),
    ),
    (
        "longitudinal_crash_pulse",
        re.compile(
            r"^LONGITUDINAL CRASH PULSE",
            re.IGNORECASE,
        ),
    ),
    (
        "lateral_crash_pulse",
        re.compile(
            r"^LATERAL CRASH PULSE",
            re.IGNORECASE,
        ),
    ),
    (
        "rollover_crash_pulse",
        re.compile(
            r"^ROLLOVER CRASH PULSE",
            re.IGNORECASE,
        ),
    ),
    (
        "longitudinal_delta_v_table",
        re.compile(
            r"^DELTA-V,\s*LONGITUDINAL",
            re.IGNORECASE,
        ),
    ),
    (
        "lateral_delta_v_table",
        re.compile(
            r"^DELTA-V,\s*LATERAL",
            re.IGNORECASE,
        ),
    ),
    (
        "precrash_data",
        re.compile(
            r"^PRE[_ -]CRASH DATA",
            re.IGNORECASE,
        ),
    ),
]


TABULAR_SECTION_CATEGORIES = {
    "dtc_table",
    "longitudinal_crash_pulse",
    "lateral_crash_pulse",
    "rollover_crash_pulse",
    "longitudinal_delta_v_table",
    "lateral_delta_v_table",
    "precrash_data",
}


def clean_cell(value: str) -> str:
    return value.replace("\ufeff", "").strip()


def clean_row(row: list[str]) -> list[str]:
    cleaned = [clean_cell(value) for value in row]

    while cleaned and not cleaned[-1]:
        cleaned.pop()

    return cleaned


def has_content(row: list[str]) -> bool:
    return any(clean_cell(value) for value in row)


def first_cell(row: list[str]) -> str:
    if not row:
        return ""

    return clean_cell(row[0])


def read_csv_rows(csv_path: Path) -> tuple[list[list[str]], str]:
    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "utf-16",
    ]

    last_error: Exception | None = None

    for encoding in encodings:
        try:
            with csv_path.open(
                "r",
                newline="",
                encoding=encoding,
            ) as file:
                rows = [
                    clean_row(row)
                    for row in csv.reader(file)
                ]

            return rows, encoding

        except UnicodeError as error:
            last_error = error

    raise RuntimeError(
        f"Could not read CSV with supported encodings: "
        f"{csv_path}. Last error: {last_error}"
    )


def classify_section_heading(row: list[str]) -> str | None:
    heading = first_cell(row)

    if not heading:
        return None

    for category, pattern in SECTION_PATTERNS:
        if pattern.match(heading):
            return category

    return None


def find_sections(
    rows: list[list[str]],
) -> list[dict[str, object]]:
    section_starts: list[tuple[int, str, str]] = []

    for row_number, row in enumerate(rows):
        category = classify_section_heading(row)

        if category is None:
            continue

        section_starts.append(
            (
                row_number,
                category,
                first_cell(row),
            )
        )

    sections: list[dict[str, object]] = []

    for index, (
        start_row,
        category,
        source_heading,
    ) in enumerate(section_starts):
        if index + 1 < len(section_starts):
            end_row = section_starts[index + 1][0]
        else:
            end_row = len(rows)

        sections.append(
            {
                "start_row": start_row,
                "end_row": end_row,
                "section_category": category,
                "source_heading": source_heading,
            }
        )

    return sections


def get_section_content(
    rows: list[list[str]],
    start_row: int,
    end_row: int,
) -> list[list[str]]:
    return [
        row
        for row in rows[start_row + 1 : end_row]
        if has_content(row)
    ]


def section_availability(
    content_rows: list[list[str]],
) -> str:
    if not content_rows:
        return "empty_section"

    first_content = first_cell(content_rows[0]).lower()

    if "contains no recorded data" in first_content:
        return "no_recorded_data"

    return "recorded"


def split_column_name_and_unit(
    column_name: str,
) -> tuple[str, str]:
    column_name = clean_cell(column_name)

    match = re.match(
        r"^(.*?)(?:\s*\(([^()]*)\))$",
        column_name,
    )

    if match is None:
        return column_name, ""

    return match.group(1).strip(), match.group(2).strip()


def json_text(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
    )


def limited_examples(
    examples: set[str],
    limit: int = 3,
) -> str:
    return json_text(sorted(examples)[:limit])


def write_csv(
    output_path: Path,
    rows: list[dict[str, object]],
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
    if not FAMILY_SUMMARY_FILE.is_file():
        raise FileNotFoundError(
            f"Family summary not found: {FAMILY_SUMMARY_FILE}"
        )

    if not FAMILY_CANDIDATES_FILE.is_file():
        raise FileNotFoundError(
            f"Family candidates not found: "
            f"{FAMILY_CANDIDATES_FILE}"
        )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    with FAMILY_SUMMARY_FILE.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        family_summary_rows = list(
            csv.DictReader(file)
        )

    family_id_by_key = {
        row["provisional_family_key"]: row[
            "provisional_family_id"
        ]
        for row in family_summary_rows
    }

    with FAMILY_CANDIDATES_FILE.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        candidate_rows = list(
            csv.DictReader(file)
        )

    section_rows: list[dict[str, object]] = []

    column_counts: Counter[tuple[str, ...]] = Counter()
    column_examples: defaultdict[
        tuple[str, ...],
        set[str],
    ] = defaultdict(set)

    key_field_counts: Counter[tuple[str, ...]] = Counter()
    key_field_examples: defaultdict[
        tuple[str, ...],
        set[str],
    ] = defaultdict(set)

    unreadable_files: list[dict[str, str]] = []
    reports_scanned = 0

    for candidate in candidate_rows:
        csv_path = Path(candidate["csv_export_path"])

        if not csv_path.is_file():
            unreadable_files.append(
                {
                    "csv_export_path": str(csv_path),
                    "error": "CSV file does not exist.",
                }
            )
            continue

        family_key = candidate[
            "provisional_family_key"
        ]

        family_id = family_id_by_key.get(
            family_key,
            "unmapped_family",
        )

        try:
            rows, encoding = read_csv_rows(csv_path)

        except Exception as error:
            unreadable_files.append(
                {
                    "csv_export_path": str(csv_path),
                    "error": (
                        f"{type(error).__name__}: {error}"
                    ),
                }
            )
            continue

        reports_scanned += 1

        for section in find_sections(rows):
            start_row = int(section["start_row"])
            end_row = int(section["end_row"])
            category = str(
                section["section_category"]
            )
            source_heading = str(
                section["source_heading"]
            )

            content_rows = get_section_content(
                rows=rows,
                start_row=start_row,
                end_row=end_row,
            )

            availability = section_availability(
                content_rows
            )

            layout_type = (
                "tabular"
                if category in TABULAR_SECTION_CATEGORIES
                else "key_value"
            )

            table_header: list[str] = []
            sample_data_rows: list[list[str]] = []
            key_fields: list[str] = []

            if availability == "recorded":
                if layout_type == "tabular":
                    table_header = clean_row(
                        content_rows[0]
                    )

                    sample_data_rows = [
                        clean_row(row)
                        for row in content_rows[1:4]
                    ]

                    for column_index, column_name in enumerate(
                        table_header,
                        start=1,
                    ):
                        if not column_name:
                            continue

                        normalized_name, unit = (
                            split_column_name_and_unit(
                                column_name
                            )
                        )

                        column_key = (
                            family_id,
                            category,
                            source_heading,
                            str(column_index),
                            column_name,
                            normalized_name,
                            unit,
                        )

                        column_counts[column_key] += 1

                        for sample_row in sample_data_rows:
                            if (
                                column_index - 1
                                < len(sample_row)
                            ):
                                sample_value = sample_row[
                                    column_index - 1
                                ]

                                if sample_value:
                                    column_examples[
                                        column_key
                                    ].add(sample_value)

                else:
                    for row in content_rows:
                        field_name = first_cell(row)

                        if not field_name:
                            continue

                        key_fields.append(field_name)

                        key_field_key = (
                            family_id,
                            category,
                            source_heading,
                            field_name,
                        )

                        key_field_counts[
                            key_field_key
                        ] += 1

                        if len(row) > 1 and row[1]:
                            key_field_examples[
                                key_field_key
                            ].add(row[1])

                    sample_data_rows = [
                        clean_row(row)
                        for row in content_rows[:3]
                    ]

            section_rows.append(
                {
                    "case_id": candidate["case_id"],
                    "vehicle_number": (
                        candidate["vehicle_number"]
                    ),
                    "export_basename": (
                        candidate["export_basename"]
                    ),
                    "provisional_family_id": family_id,
                    "provisional_family_key": family_key,
                    "csv_export_path": str(csv_path),
                    "csv_encoding_used": encoding,
                    "section_category": category,
                    "source_heading": source_heading,
                    "section_start_row_number": (
                        start_row + 1
                    ),
                    "availability": availability,
                    "layout_type": layout_type,
                    "table_header_json": json_text(
                        table_header
                    ),
                    "key_fields_json": json_text(
                        key_fields
                    ),
                    "sample_data_rows_json": json_text(
                        sample_data_rows
                    ),
                }
            )

    column_rows: list[dict[str, object]] = []

    for key, occurrence_count in sorted(
        column_counts.items()
    ):
        (
            family_id,
            category,
            source_heading,
            column_index,
            source_column_name,
            normalized_column_name,
            unit,
        ) = key

        column_rows.append(
            {
                "provisional_family_id": family_id,
                "section_category": category,
                "source_heading": source_heading,
                "column_index": column_index,
                "source_column_name": source_column_name,
                "normalized_column_name": (
                    normalized_column_name
                ),
                "unit_from_header": unit,
                "section_occurrence_count": (
                    occurrence_count
                ),
                "sample_values_json": limited_examples(
                    column_examples[key]
                ),
            }
        )

    key_field_rows: list[dict[str, object]] = []

    for key, occurrence_count in sorted(
        key_field_counts.items()
    ):
        (
            family_id,
            category,
            source_heading,
            source_field_name,
        ) = key

        key_field_rows.append(
            {
                "provisional_family_id": family_id,
                "section_category": category,
                "source_heading": source_heading,
                "source_field_name": source_field_name,
                "section_occurrence_count": (
                    occurrence_count
                ),
                "sample_values_json": limited_examples(
                    key_field_examples[key]
                ),
            }
        )

    section_output = (
        OUTPUT_DIRECTORY
        / "edr_csv_section_inventory.csv"
    )

    column_output = (
        OUTPUT_DIRECTORY
        / "edr_csv_column_inventory.csv"
    )

    key_field_output = (
        OUTPUT_DIRECTORY
        / "edr_csv_key_field_inventory.csv"
    )

    unreadable_output = (
        OUTPUT_DIRECTORY
        / "edr_csv_unreadable_files.csv"
    )

    metadata_output = (
        OUTPUT_DIRECTORY
        / "edr_csv_column_inventory_metadata.json"
    )

    write_csv(
        output_path=section_output,
        rows=section_rows,
        fieldnames=[
            "case_id",
            "vehicle_number",
            "export_basename",
            "provisional_family_id",
            "provisional_family_key",
            "csv_export_path",
            "csv_encoding_used",
            "section_category",
            "source_heading",
            "section_start_row_number",
            "availability",
            "layout_type",
            "table_header_json",
            "key_fields_json",
            "sample_data_rows_json",
        ],
    )

    write_csv(
        output_path=column_output,
        rows=column_rows,
        fieldnames=[
            "provisional_family_id",
            "section_category",
            "source_heading",
            "column_index",
            "source_column_name",
            "normalized_column_name",
            "unit_from_header",
            "section_occurrence_count",
            "sample_values_json",
        ],
    )

    write_csv(
        output_path=key_field_output,
        rows=key_field_rows,
        fieldnames=[
            "provisional_family_id",
            "section_category",
            "source_heading",
            "source_field_name",
            "section_occurrence_count",
            "sample_values_json",
        ],
    )

    write_csv(
        output_path=unreadable_output,
        rows=unreadable_files,
        fieldnames=[
            "csv_export_path",
            "error",
        ],
    )

    availability_counts = Counter(
        row["availability"]
        for row in section_rows
    )

    metadata = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "input_csv_reports": len(candidate_rows),
        "reports_scanned": reports_scanned,
        "unreadable_report_count": len(
            unreadable_files
        ),
        "section_occurrence_count": len(
            section_rows
        ),
        "distinct_table_column_rows": len(
            column_rows
        ),
        "distinct_key_value_field_rows": len(
            key_field_rows
        ),
        "section_availability_counts": dict(
            sorted(availability_counts.items())
        ),
        "outputs": {
            "section_inventory": str(section_output),
            "column_inventory": str(column_output),
            "key_field_inventory": str(
                key_field_output
            ),
            "unreadable_files": str(
                unreadable_output
            ),
        },
    }

    with metadata_output.open(
        "w",
        encoding="utf-8-sig",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2,
        )

    print("EDR CSV column inventory completed.")
    print(f"CSV reports scanned: {reports_scanned}")
    print(
        f"Unreadable or missing CSV reports: "
        f"{len(unreadable_files)}"
    )
    print(
        f"Section occurrences: {len(section_rows)}"
    )
    print(
        f"Distinct table-column rows: {len(column_rows)}"
    )
    print(
        f"Distinct key-value field rows: "
        f"{len(key_field_rows)}"
    )
    print(f"Section inventory: {section_output}")
    print(f"Column inventory: {column_output}")
    print(
        f"Key-value field inventory: "
        f"{key_field_output}"
    )
    print(f"Metadata: {metadata_output}")

    print("\nSection availability:")

    for availability, count in sorted(
        availability_counts.items()
    ):
        print(f"  {availability}: {count}")


if __name__ == "__main__":
    main()