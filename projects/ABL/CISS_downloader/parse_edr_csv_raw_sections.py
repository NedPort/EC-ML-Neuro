from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from contextlib import ExitStack
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
        "cdr_file_information",
        re.compile(r"^CDR FILE INFORMATION$", re.IGNORECASE),
    ),
    (
        "system_status_at_retrieval",
        re.compile(
            r"^SYSTEM STATUS AT RETRIEVAL",
            re.IGNORECASE,
        ),
    ),
    (
        "system_status_at_event",
        re.compile(
            r"^SYSTEM STATUS AT EVENT",
            re.IGNORECASE,
        ),
    ),
    (
        "faults_present_at_event",
        re.compile(
            r"^FAULTS PRESENT AT START OF EVENT",
            re.IGNORECASE,
        ),
    ),
    (
        "deployment_command_data",
        re.compile(
            r"^DEPLOYMENT COMMAND DATA",
            re.IGNORECASE,
        ),
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
    return clean_cell(row[0]) if row else ""


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def read_csv_rows(
    csv_path: Path,
) -> tuple[list[list[str]], str]:
    encodings = (
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "utf-16",
    )

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
        f"Could not read {csv_path}. Last error: {last_error}"
    )


def generic_section_category(
    heading: str,
) -> str | None:
    """
    Preserve uppercase, one-cell Bosch section headings that
    are not yet part of the known section vocabulary.
    """

    normalized = heading.strip()

    if (
        len(normalized) < 8
        or normalized != normalized.upper()
        or " " not in normalized
    ):
        return None

    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        normalized.lower(),
    ).strip("_")

    return f"unclassified_{slug}"


def classify_section_heading(
    row: list[str],
) -> str | None:
    heading = first_cell(row)

    if not heading:
        return None

    nonempty_cell_count = sum(
        bool(clean_cell(value))
        for value in row
    )

    if nonempty_cell_count != 1:
        return None

    for category, pattern in SECTION_PATTERNS:
        if pattern.match(heading):
            return category

    return generic_section_category(heading)


def find_sections(
    rows: list[list[str]],
) -> list[dict[str, object]]:
    starts: list[tuple[int, str, str]] = []

    for row_number, row in enumerate(rows):
        category = classify_section_heading(row)

        if category is None:
            continue

        starts.append(
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
    ) in enumerate(starts):
        end_row = (
            starts[index + 1][0]
            if index + 1 < len(starts)
            else len(rows)
        )

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
) -> list[tuple[int, list[str]]]:
    content: list[tuple[int, list[str]]] = []

    for row_number in range(start_row + 1, end_row):
        row = rows[row_number]

        if has_content(row):
            content.append((row_number, row))

    return content


def get_availability(
    content_rows: list[tuple[int, list[str]]],
) -> str:
    if not content_rows:
        return "empty_section"

    first_content = first_cell(
        content_rows[0][1]
    ).lower()

    if "contains no recorded data" in first_content:
        return "no_recorded_data"

    return "recorded"


def extract_event_label(
    source_heading: str,
) -> str:
    """
    Return a logical Bosch event label.

    Table fragments such as 'TABLE 1 OF 2' are merged into
    their parent event. The original full source heading remains
    preserved elsewhere in the raw output.
    """

    match = re.search(
        r"\(([^)]*(?:event|record)[^)]*)\)",
        source_heading,
        flags=re.IGNORECASE,
    )

    if match is None:
        return "file_level_or_unspecified_event"

    event_label = re.sub(
        r"\s+",
        " ",
        match.group(1).strip(),
    )

    event_label = re.sub(
        r"\s*-\s*TABLE\s+\d+\s+OF\s+\d+\s*$",
        "",
        event_label,
        flags=re.IGNORECASE,
    )

    event_label = re.sub(
        r"\s*-\s*(?:NON-)?DEPLOYMENT\s*$",
        "",
        event_label,
        flags=re.IGNORECASE,
    )

    event_label = re.sub(
        r"^\[\d+\s+SAMPLES/SEC\]\s*",
        "",
        event_label,
        flags=re.IGNORECASE,
    )

    return event_label.upper()


def make_file_id(
    case_id: str,
    vehicle_number: str,
    export_basename: str,
) -> str:
    return (
        f"{case_id}-V{vehicle_number}-"
        f"{export_basename}"
    )


def make_event_id(
    file_id: str,
    event_label: str,
) -> str:
    safe_label = re.sub(
        r"[^A-Z0-9]+",
        "_",
        event_label.upper(),
    ).strip("_")

    return f"{file_id}-E-{safe_label}"


def write_header(
    writer: csv.DictWriter,
) -> None:
    writer.writeheader()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parse Bosch CDR CSV files into provenance-preserving "
            "raw section, field, and table-value outputs."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Optional number of CSV reports to parse for a "
            "small validation run."
        ),
    )

    arguments = parser.parse_args()

    if arguments.limit is not None and arguments.limit < 1:
        raise SystemExit("--limit must be at least 1.")

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
        row["provisional_family_key"]:
        row["provisional_family_id"]
        for row in family_summary_rows
    }

    with FAMILY_CANDIDATES_FILE.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        candidate_rows = list(
            csv.DictReader(file)
        )

    if arguments.limit is not None:
        candidate_rows = candidate_rows[:arguments.limit]

    output_paths = {
        "file_index": (
            OUTPUT_DIRECTORY
            / "edr_csv_raw_file_index.csv"
        ),
        "event_index": (
            OUTPUT_DIRECTORY
            / "edr_csv_raw_event_index.csv"
        ),
        "section_index": (
            OUTPUT_DIRECTORY
            / "edr_csv_raw_section_index.csv"
        ),
        "key_values": (
            OUTPUT_DIRECTORY
            / "edr_csv_raw_key_value_long.csv"
        ),
        "table_values": (
            OUTPUT_DIRECTORY
            / "edr_csv_raw_table_value_long.csv"
        ),
        "failures": (
            OUTPUT_DIRECTORY
            / "edr_csv_raw_parse_failures.csv"
        ),
    }

    temporary_paths = {
        name: output_path.with_suffix(
            output_path.suffix + ".part"
        )
        for name, output_path in output_paths.items()
    }

    event_records: dict[str, dict[str, object]] = {}

    reports_parsed = 0
    key_value_count = 0
    table_value_count = 0
    section_counts: Counter[str] = Counter()
    availability_counts: Counter[str] = Counter()
    failure_count = 0

    with ExitStack() as stack:
        files = {
            name: stack.enter_context(
                temporary_path.open(
                    "w",
                    newline="",
                    encoding="utf-8",
                )
            )
            for name, temporary_path
            in temporary_paths.items()
        }

        file_writer = csv.DictWriter(
            files["file_index"],
            fieldnames=[
                "edr_file_id",
                "case_id",
                "vehicle_number",
                "export_basename",
                "provisional_family_id",
                "provisional_family_key",
                "system_name",
                "edr_device_type",
                "events_recovered",
                "cdrx_source_path",
                "csv_export_path",
                "csv_encoding_used",
                "parse_status",
            ],
        )

        event_writer = csv.DictWriter(
            files["event_index"],
            fieldnames=[
                "edr_event_id",
                "edr_file_id",
                "case_id",
                "vehicle_number",
                "export_basename",
                "event_label",
                "section_categories_json",
                "source_headings_json",
                "availability_counts_json",
            ],
        )

        section_writer = csv.DictWriter(
            files["section_index"],
            fieldnames=[
                "edr_file_id",
                "edr_event_id",
                "case_id",
                "vehicle_number",
                "export_basename",
                "provisional_family_id",
                "csv_export_path",
                "section_category",
                "source_heading",
                "event_label",
                "section_start_row_number",
                "section_end_row_number",
                "availability",
                "layout_type",
                "table_header_json",
                "content_row_count",
            ],
        )

        key_value_writer = csv.DictWriter(
            files["key_values"],
            fieldnames=[
                "edr_file_id",
                "edr_event_id",
                "case_id",
                "vehicle_number",
                "export_basename",
                "provisional_family_id",
                "csv_export_path",
                "section_category",
                "source_heading",
                "event_label",
                "source_row_number",
                "source_field_name",
                "source_value",
                "source_value_cells_json",
            ],
        )

        table_value_writer = csv.DictWriter(
            files["table_values"],
            fieldnames=[
                "edr_file_id",
                "edr_event_id",
                "case_id",
                "vehicle_number",
                "export_basename",
                "provisional_family_id",
                "csv_export_path",
                "section_category",
                "source_heading",
                "event_label",
                "source_row_number",
                "source_data_row_number",
                "source_column_index",
                "source_column_name",
                "source_value",
            ],
        )

        failure_writer = csv.DictWriter(
            files["failures"],
            fieldnames=[
                "case_id",
                "vehicle_number",
                "export_basename",
                "csv_export_path",
                "error",
            ],
        )

        for writer in (
            file_writer,
            event_writer,
            section_writer,
            key_value_writer,
            table_value_writer,
            failure_writer,
        ):
            write_header(writer)

        for index, candidate in enumerate(
            candidate_rows,
            start=1,
        ):
            case_id = candidate["case_id"]
            vehicle_number = candidate["vehicle_number"]
            export_basename = candidate[
                "export_basename"
            ]
            csv_path = Path(candidate["csv_export_path"])
            family_key = candidate[
                "provisional_family_key"
            ]
            family_id = family_id_by_key.get(
                family_key,
                "unmapped_family",
            )

            file_id = make_file_id(
                case_id=case_id,
                vehicle_number=vehicle_number,
                export_basename=export_basename,
            )

            try:
                rows, encoding = read_csv_rows(csv_path)

            except Exception as error:
                failure_count += 1

                file_writer.writerow(
                    {
                        "edr_file_id": file_id,
                        "case_id": case_id,
                        "vehicle_number": vehicle_number,
                        "export_basename": export_basename,
                        "provisional_family_id": family_id,
                        "provisional_family_key": family_key,
                        "system_name": candidate["system_name"],
                        "edr_device_type": candidate[
                            "edr_device_type"
                        ],
                        "events_recovered": candidate[
                            "events_recovered"
                        ],
                        "cdrx_source_path": candidate[
                            "cdrx_source_path"
                        ],
                        "csv_export_path": str(csv_path),
                        "csv_encoding_used": "",
                        "parse_status": "failed",
                    }
                )

                failure_writer.writerow(
                    {
                        "case_id": case_id,
                        "vehicle_number": vehicle_number,
                        "export_basename": export_basename,
                        "csv_export_path": str(csv_path),
                        "error": (
                            f"{type(error).__name__}: {error}"
                        ),
                    }
                )

                continue

            reports_parsed += 1

            file_writer.writerow(
                {
                    "edr_file_id": file_id,
                    "case_id": case_id,
                    "vehicle_number": vehicle_number,
                    "export_basename": export_basename,
                    "provisional_family_id": family_id,
                    "provisional_family_key": family_key,
                    "system_name": candidate["system_name"],
                    "edr_device_type": candidate[
                        "edr_device_type"
                    ],
                    "events_recovered": candidate[
                        "events_recovered"
                    ],
                    "cdrx_source_path": candidate[
                        "cdrx_source_path"
                    ],
                    "csv_export_path": str(csv_path),
                    "csv_encoding_used": encoding,
                    "parse_status": "parsed",
                }
            )

            for section in find_sections(rows):
                start_row = int(section["start_row"])
                end_row = int(section["end_row"])
                category = str(
                    section["section_category"]
                )
                source_heading = str(
                    section["source_heading"]
                )

                event_label = extract_event_label(
                    source_heading
                )

                event_id = make_event_id(
                    file_id=file_id,
                    event_label=event_label,
                )

                content = get_section_content(
                    rows=rows,
                    start_row=start_row,
                    end_row=end_row,
                )

                availability = get_availability(content)

                layout_type = (
                    "tabular"
                    if category in TABULAR_SECTION_CATEGORIES
                    else "key_value"
                )

                table_header: list[str] = []

                if (
                    availability == "recorded"
                    and layout_type == "tabular"
                    and content
                ):
                    table_header = clean_row(
                        content[0][1]
                    )

                section_writer.writerow(
                    {
                        "edr_file_id": file_id,
                        "edr_event_id": event_id,
                        "case_id": case_id,
                        "vehicle_number": vehicle_number,
                        "export_basename": export_basename,
                        "provisional_family_id": family_id,
                        "csv_export_path": str(csv_path),
                        "section_category": category,
                        "source_heading": source_heading,
                        "event_label": event_label,
                        "section_start_row_number": (
                            start_row + 1
                        ),
                        "section_end_row_number": end_row,
                        "availability": availability,
                        "layout_type": layout_type,
                        "table_header_json": json_text(
                            table_header
                        ),
                        "content_row_count": len(content),
                    }
                )

                section_counts[category] += 1
                availability_counts[availability] += 1

                event_record = event_records.setdefault(
                    event_id,
                    {
                        "edr_event_id": event_id,
                        "edr_file_id": file_id,
                        "case_id": case_id,
                        "vehicle_number": vehicle_number,
                        "export_basename": export_basename,
                        "event_label": event_label,
                        "section_categories": set(),
                        "source_headings": set(),
                        "availability_counts": Counter(),
                    },
                )

                event_record["section_categories"].add(
                    category
                )
                event_record["source_headings"].add(
                    source_heading
                )
                event_record["availability_counts"][
                    availability
                ] += 1

                if availability != "recorded":
                    continue

                if layout_type == "key_value":
                    for row_number, row in content:
                        field_name = first_cell(row)

                        if not field_name:
                            continue

                        value_cells = row[1:]
                        source_value = (
                            value_cells[0]
                            if value_cells
                            else ""
                        )

                        key_value_writer.writerow(
                            {
                                "edr_file_id": file_id,
                                "edr_event_id": event_id,
                                "case_id": case_id,
                                "vehicle_number": (
                                    vehicle_number
                                ),
                                "export_basename": export_basename,
                                "provisional_family_id": family_id,
                                "csv_export_path": str(csv_path),
                                "section_category": category,
                                "source_heading": source_heading,
                                "event_label": event_label,
                                "source_row_number": (
                                    row_number + 1
                                ),
                                "source_field_name": field_name,
                                "source_value": source_value,
                                "source_value_cells_json": (
                                    json_text(value_cells)
                                ),
                            }
                        )

                        key_value_count += 1

                else:
                    if not content:
                        continue

                    header_row_number, header = content[0]
                    data_rows = content[1:]

                    for source_row_number, data_row in data_rows:
                        max_columns = max(
                            len(header),
                            len(data_row),
                        )

                        for column_index in range(max_columns):
                            source_column_name = (
                                header[column_index]
                                if column_index < len(header)
                                else (
                                    "unlabeled_column_"
                                    f"{column_index + 1}"
                                )
                            )

                            source_value = (
                                data_row[column_index]
                                if column_index < len(data_row)
                                else ""
                            )

                            table_value_writer.writerow(
                                {
                                    "edr_file_id": file_id,
                                    "edr_event_id": event_id,
                                    "case_id": case_id,
                                    "vehicle_number": (
                                        vehicle_number
                                    ),
                                    "export_basename": (
                                        export_basename
                                    ),
                                    "provisional_family_id": (
                                        family_id
                                    ),
                                    "csv_export_path": (
                                        str(csv_path)
                                    ),
                                    "section_category": category,
                                    "source_heading": source_heading,
                                    "event_label": event_label,
                                    "source_row_number": (
                                        source_row_number + 1
                                    ),
                                    "source_data_row_number": (
                                        source_row_number
                                        - header_row_number
                                    ),
                                    "source_column_index": (
                                        column_index + 1
                                    ),
                                    "source_column_name": (
                                        source_column_name
                                    ),
                                    "source_value": source_value,
                                }
                            )

                            table_value_count += 1

            if index % 50 == 0:
                print(
                    f"Parsed {index}/{len(candidate_rows)} "
                    "CSV reports..."
                )

        for event_record in event_records.values():
            event_writer.writerow(
                {
                    "edr_event_id": event_record[
                        "edr_event_id"
                    ],
                    "edr_file_id": event_record[
                        "edr_file_id"
                    ],
                    "case_id": event_record["case_id"],
                    "vehicle_number": event_record[
                        "vehicle_number"
                    ],
                    "export_basename": event_record[
                        "export_basename"
                    ],
                    "event_label": event_record[
                        "event_label"
                    ],
                    "section_categories_json": json_text(
                        sorted(
                            event_record[
                                "section_categories"
                            ]
                        )
                    ),
                    "source_headings_json": json_text(
                        sorted(
                            event_record[
                                "source_headings"
                            ]
                        )
                    ),
                    "availability_counts_json": json_text(
                        dict(
                            sorted(
                                event_record[
                                    "availability_counts"
                                ].items()
                            )
                        )
                    ),
                }
            )

    for name, temporary_path in temporary_paths.items():
        temporary_path.replace(output_paths[name])

    metadata_path = (
        OUTPUT_DIRECTORY
        / "edr_csv_raw_parse_metadata.json"
    )

    metadata = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "requested_limit": arguments.limit,
        "candidate_csv_report_count": len(candidate_rows),
        "reports_parsed": reports_parsed,
        "failed_report_count": failure_count,
        "event_count": len(event_records),
        "section_occurrence_count": sum(
            section_counts.values()
        ),
        "key_value_row_count": key_value_count,
        "table_value_row_count": table_value_count,
        "section_category_counts": dict(
            sorted(section_counts.items())
        ),
        "availability_counts": dict(
            sorted(availability_counts.items())
        ),
        "outputs": {
            name: str(path)
            for name, path in output_paths.items()
        },
    }

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2,
        )

    print("EDR CSV raw-section parsing completed.")
    print(f"CSV reports parsed: {reports_parsed}")
    print(f"CSV reports failed: {failure_count}")
    print(f"EDR events indexed: {len(event_records)}")
    print(
        "Section occurrences: "
        f"{sum(section_counts.values())}"
    )
    print(f"Key-value rows: {key_value_count}")
    print(f"Table-value rows: {table_value_count}")

    print("\nOutputs:")
    for name, path in output_paths.items():
        print(f"  {name}: {path}")

    print(f"  metadata: {metadata_path}")


if __name__ == "__main__":
    main()