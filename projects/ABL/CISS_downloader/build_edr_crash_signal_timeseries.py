"""
Create a canonical, source-traceable long table for Bosch crash signals.

This script reconstructs time/value samples from the raw table-value layer.
It preserves source wording, units, and row references. It does not calculate
derived metrics and does not alter the reported sign convention.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROCESSED_EDR_DIRECTORY = Path("data/processed/edr")

CANONICAL_EVENT_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_event_canonical.csv"
)

RAW_TABLE_VALUE_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_csv_raw_table_value_long.csv"
)

OUTPUT_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_crash_signal_timeseries_long.csv"
)

AUDIT_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_crash_signal_parse_audit.csv"
)

METADATA_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_crash_signal_timeseries_metadata.json"
)


def normalize_text(value: str | None) -> str:
    """Normalize text for matching while retaining raw values elsewhere."""
    return " ".join((value or "").upper().split())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV, allowing a UTF-8 BOM."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Required input file was not found: {path}"
        )

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as input_file:
        return list(csv.DictReader(input_file))


def parse_float(value: str | None) -> float | None:
    """
    Convert an explicitly numeric source value when possible.

    The raw source string remains in the output even when conversion fails.
    """
    if value is None:
        return None

    cleaned = value.strip()

    if not cleaned:
        return None

    cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned)
    except ValueError:
        return None


def is_reported_event(
    event_scope_by_id: dict[str, str],
    edr_event_id: str,
) -> bool:
    """Keep only actual Bosch-reported event rows."""
    return (
        event_scope_by_id.get(edr_event_id)
        == "reported_event"
    )


def is_crash_signal_section(
    section_category: str,
    source_heading: str,
) -> bool:
    """
    Select candidate crash-signal tables conservatively.

    Raw data remain available in edr_csv_raw_table_value_long.csv even if a
    table is not selected here.
    """
    category = normalize_text(section_category)
    heading = normalize_text(source_heading)

    category_terms = (
        "LONGITUDINAL_DELTA_V_TABLE",
        "LATERAL_DELTA_V_TABLE",
        "LONGITUDINAL_CRASH_PULSE",
        "LATERAL_CRASH_PULSE",
        "ROLLOVER_CRASH_PULSE",
    )

    if any(term in category for term in category_terms):
        return True

    if "CRASH PULSE" in heading:
        return True

    if (
        "DELTA-V" in heading
        or "DELTA V" in heading
    ):
        return True

    return False


def detect_section_axis(
    section_category: str,
    source_heading: str,
) -> str:
    """
    Determine axis only when clearly indicated by source category or heading.
    """
    source_text = " ".join(
        (
            normalize_text(section_category),
            normalize_text(source_heading),
        )
    )

    has_longitudinal = "LONGITUDINAL" in source_text
    has_lateral = "LATERAL" in source_text
    has_rollover = "ROLLOVER" in source_text

    axis_count = sum(
        (
            has_longitudinal,
            has_lateral,
            has_rollover,
        )
    )

    if axis_count != 1:
        return ""

    if has_longitudinal:
        return "longitudinal"

    if has_lateral:
        return "lateral"

    return "rollover"


def detect_column_axis(
    source_column_name: str,
) -> str:
    """Determine axis from the original table-column heading."""
    column_name = normalize_text(source_column_name)

    if "LONGITUDINAL" in column_name:
        return "longitudinal"

    if "LATERAL" in column_name:
        return "lateral"

    if "ROLLOVER" in column_name:
        return "rollover"

    return ""


def is_time_column(source_column_name: str) -> bool:
    """Identify source columns that represent time."""
    column_name = normalize_text(source_column_name)

    return "TIME" in column_name


def looks_like_value_column(
    source_column_name: str,
) -> bool:
    """
    Identify a possible numeric signal-value column.

    This function intentionally does not require a known unit, because some
    Bosch tables label the value column only as 'km/h'.
    """
    column_name = normalize_text(source_column_name)

    if not column_name:
        return False

    if is_time_column(column_name):
        return False

    excluded_terms = (
        "STATUS",
        "EVENT RECORDER",
        "RECORD STATUS",
        "COMPLETE",
    )

    return not any(
        term in column_name
        for term in excluded_terms
    )


def extract_unit(source_column_name: str) -> str:
    """Recognize explicit units without treating descriptions as units."""
    aliases = {
        "KM/H": "km/h",
        "KPH": "km/h",
        "MPH": "mph",
        "M/S": "m/s",
        "M/S2": "m/s2",
        "M/S^2": "m/s2",
        "M/S²": "m/s2",
        "G": "g",
        "DEG": "deg",
        "DEGREES": "deg",
        "DEG/S": "deg/s",
        "DEG/SEC": "deg/s",
        "DEGREES/SECOND": "deg/s",
    }

    parenthetical_parts = re.findall(
        r"\(([^()]*)\)",
        source_column_name,
    )

    for part in reversed(parenthetical_parts):
        normalized = normalize_text(part)
        if normalized in aliases:
            return aliases[normalized]

    return aliases.get(
        normalize_text(source_column_name),
        "",
    )

def classify_source_measure(
    source_heading: str,
    source_column_name: str,
) -> str:
    """
    Classify only what is explicitly indicated by the source labels.

    'crash_pulse_unspecified_measure' means the report calls it a crash pulse
    but the parser does not claim whether it represents Delta-V, acceleration,
    or another module-specific measurement.
    """
    source_text = " ".join(
        (
            normalize_text(source_heading),
            normalize_text(source_column_name),
        )
    )

def classify_source_measure(
    source_heading: str,
    source_column_name: str,
) -> str:
    """Prefer the measurement explicitly named in the value column."""
    column = normalize_text(source_column_name)
    heading = normalize_text(source_heading)

    if "ACCELERATION" in column:
        return "acceleration"

    if "DELTA-V" in column or "DELTA V" in column:
        return "delta_v"

    if "ANGULAR" in column and (
        "RATE" in column or "VELOCITY" in column
    ):
        return "angular_velocity"

    if "ROLL" in column and "RATE" in column:
        return "angular_velocity"

    if "ANGLE" in column:
        return "angle"

    if "DELTA-V" in heading or "DELTA V" in heading:
        return "delta_v"

    return "crash_pulse_unspecified_measure"


def main() -> None:
    canonical_event_rows = read_csv_rows(
        CANONICAL_EVENT_PATH
    )

    event_scope_by_id = {
        row["edr_event_id"]: row["event_scope"]
        for row in canonical_event_rows
        if row.get("edr_event_id")
    }

    event_metadata_by_id = {
        row["edr_event_id"]: row
        for row in canonical_event_rows
        if row.get("edr_event_id")
    }

    # Key:
    # (event, section category, source heading, source data row)
    # Value:
    # all cells originally present in that Bosch table row.
    source_rows: dict[
        tuple[str, str, str, str],
        list[dict[str, str]],
    ] = defaultdict(list)

    scanned_table_value_rows = 0
    selected_candidate_cells = 0

    if not RAW_TABLE_VALUE_PATH.is_file():
        raise FileNotFoundError(
            f"Required input file was not found: "
            f"{RAW_TABLE_VALUE_PATH}"
        )

    with RAW_TABLE_VALUE_PATH.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as input_file:
        reader = csv.DictReader(input_file)

        for row in reader:
            scanned_table_value_rows += 1

            edr_event_id = row.get(
                "edr_event_id",
                "",
            )

            if not is_reported_event(
                event_scope_by_id,
                edr_event_id,
            ):
                continue

            if not is_crash_signal_section(
                row.get("section_category", ""),
                row.get("source_heading", ""),
            ):
                continue

            grouping_key = (
                edr_event_id,
                row.get("section_category", ""),
                row.get("source_heading", ""),
                row.get("source_row_number", ""),
            )

            source_rows[grouping_key].append(row)
            selected_candidate_cells += 1

    output_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []

    audit_reason_counts: Counter[str] = Counter()
    axis_counts: Counter[str] = Counter()
    measure_counts: Counter[str] = Counter()

    for grouping_key, cells in source_rows.items():
        (
            edr_event_id,
            section_category,
            source_heading,
            original_csv_row_number,
        ) = grouping_key

        source_data_row_number = cells[0].get(
            "source_data_row_number",
            "",
        )

        event_metadata = event_metadata_by_id[
            edr_event_id
        ]

        sorted_cells = sorted(
            cells,
            key=lambda row: int(
                row.get("source_column_index", "0")
                or 0
            ),
        )

        time_cells = [
            row
            for row in sorted_cells
            if is_time_column(
                row.get("source_column_name", "")
            )
        ]

        if len(time_cells) != 1:
            reason = (
                "missing_time_column"
                if len(time_cells) == 0
                else "ambiguous_time_columns"
            )

            audit_reason_counts[reason] += 1

            audit_rows.append(
                {
                    "edr_event_id": edr_event_id,
                    "case_id": event_metadata.get(
                        "case_id",
                        "",
                    ),
                    "vehicle_number": event_metadata.get(
                        "vehicle_number",
                        "",
                    ),
                    "section_category": section_category,
                    "source_heading": source_heading,
                    "source_data_row_number": (
                        source_data_row_number
                    ),
                    "audit_status": "not_emitted",
                    "reason": reason,
                    "source_columns_json": json.dumps(
                        [
                            row.get(
                                "source_column_name",
                                "",
                            )
                            for row in sorted_cells
                        ],
                        ensure_ascii=False,
                    ),
                }
            )

            continue

        time_cell = time_cells[0]
        time_raw_value = time_cell.get(
            "source_value",
            "",
        )
        time_ms = parse_float(time_raw_value)

        if time_ms is None:
            reason = "non_numeric_time_value"

            audit_reason_counts[reason] += 1

            audit_rows.append(
                {
                    "edr_event_id": edr_event_id,
                    "case_id": event_metadata.get(
                        "case_id",
                        "",
                    ),
                    "vehicle_number": event_metadata.get(
                        "vehicle_number",
                        "",
                    ),
                    "section_category": section_category,
                    "source_heading": source_heading,
                    "source_data_row_number": (
                        source_data_row_number
                    ),
                    "audit_status": "not_emitted",
                    "reason": reason,
                    "source_columns_json": json.dumps(
                        [
                            row.get(
                                "source_column_name",
                                "",
                            )
                            for row in sorted_cells
                        ],
                        ensure_ascii=False,
                    ),
                }
            )

            continue

        section_axis = detect_section_axis(
            section_category,
            source_heading,
        )

        emitted_rows_for_source_row = 0

        for value_cell in sorted_cells:
            source_column_name = value_cell.get(
                "source_column_name",
                "",
            )

            if is_time_column(source_column_name):
                continue

            if not looks_like_value_column(
                source_column_name
            ):
                continue

            source_value_raw = value_cell.get(
                "source_value",
                "",
            )
            numeric_value = parse_float(
                source_value_raw
            )

            if numeric_value is None:
                continue

            column_axis = detect_column_axis(
                source_column_name
            )

            # Use a table-wide axis only if the section is unambiguous.
            signal_axis = column_axis or section_axis

            if not signal_axis:
                continue

            source_measure = classify_source_measure(
                source_heading,
                source_column_name,
            )

            source_row_number = value_cell.get(
                "source_row_number",
                "",
            )

            output_rows.append(
                {
                    "edr_event_id": edr_event_id,
                    "edr_file_id": event_metadata.get(
                        "edr_file_id",
                        "",
                    ),
                    "case_id": event_metadata.get(
                        "case_id",
                        "",
                    ),
                    "vehicle_number": event_metadata.get(
                        "vehicle_number",
                        "",
                    ),
                    "export_basename": event_metadata.get(
                        "export_basename",
                        "",
                    ),
                    "provisional_family_ids_json": (
                        event_metadata.get(
                            "provisional_family_ids_json",
                            "[]",
                        )
                    ),
                    "source_event_label": (
                        event_metadata.get(
                            "source_event_label",
                            "",
                        )
                    ),
                    "section_category": section_category,
                    "source_heading": source_heading,
                    "source_data_row_number": (
                        source_data_row_number
                    ),
                    "source_row_number": source_row_number,
                    "signal_axis": signal_axis,
                    "source_measure": source_measure,
                    "time_ms": time_ms,
                    "time_raw_value": time_raw_value,
                    "time_source_column_name": (
                        time_cell.get(
                            "source_column_name",
                            "",
                        )
                    ),
                    "value": numeric_value,
                    "value_raw": source_value_raw,
                    "value_unit": extract_unit(
                        source_column_name
                    ),
                    "value_source_column_name": (
                        source_column_name
                    ),
                    "source_csv_path": value_cell.get(
                        "csv_export_path",
                        "",
                    ),
                }
            )

            emitted_rows_for_source_row += 1
            axis_counts[signal_axis] += 1
            measure_counts[source_measure] += 1

        if emitted_rows_for_source_row == 0:
            reason = (
                "no_numeric_axis_value_with_"
                "unambiguous_axis"
            )

            audit_reason_counts[reason] += 1

            audit_rows.append(
                {
                    "edr_event_id": edr_event_id,
                    "case_id": event_metadata.get(
                        "case_id",
                        "",
                    ),
                    "vehicle_number": event_metadata.get(
                        "vehicle_number",
                        "",
                    ),
                    "section_category": section_category,
                    "source_heading": source_heading,
                    "source_data_row_number": (
                        source_data_row_number
                    ),
                    "audit_status": "not_emitted",
                    "reason": reason,
                    "source_columns_json": json.dumps(
                        [
                            row.get(
                                "source_column_name",
                                "",
                            )
                            for row in sorted_cells
                        ],
                        ensure_ascii=False,
                    ),
                }
            )

    output_rows.sort(
        key=lambda row: (
            int(row["case_id"]),
            int(row["vehicle_number"]),
            str(row["edr_event_id"]),
            str(row["signal_axis"]),
            float(row["time_ms"]),
            int(row["source_row_number"] or 0),
        )
    )

    audit_rows.sort(
        key=lambda row: (
            int(row["case_id"]),
            int(row["vehicle_number"]),
            str(row["edr_event_id"]),
            int(row["source_data_row_number"] or 0),
        )
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_fieldnames = [
        "edr_event_id",
        "edr_file_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "provisional_family_ids_json",
        "source_event_label",
        "section_category",
        "source_heading",
        "source_data_row_number",
        "source_row_number",
        "signal_axis",
        "source_measure",
        "time_ms",
        "time_raw_value",
        "time_source_column_name",
        "value",
        "value_raw",
        "value_unit",
        "value_source_column_name",
        "source_csv_path",
    ]

    with OUTPUT_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=output_fieldnames,
        )
        writer.writeheader()
        writer.writerows(output_rows)

    audit_fieldnames = [
        "edr_event_id",
        "case_id",
        "vehicle_number",
        "section_category",
        "source_heading",
        "source_data_row_number",
        "audit_status",
        "reason",
        "source_columns_json",
    ]

    with AUDIT_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as audit_file:
        writer = csv.DictWriter(
            audit_file,
            fieldnames=audit_fieldnames,
        )
        writer.writeheader()
        writer.writerows(audit_rows)

    metadata = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "purpose": (
            "Create source-traceable crash-signal time-series rows "
            "from raw Bosch table values. No sign normalization, "
            "event selection, or derived feature calculation is applied."
        ),
        "input_canonical_event_index": str(
            CANONICAL_EVENT_PATH
        ),
        "input_raw_table_values": str(
            RAW_TABLE_VALUE_PATH
        ),
        "raw_table_value_rows_scanned": (
            scanned_table_value_rows
        ),
        "candidate_source_cells_selected": (
            selected_candidate_cells
        ),
        "candidate_source_table_rows": len(
            source_rows
        ),
        "emitted_signal_samples": len(
            output_rows
        ),
        "not_emitted_source_table_rows": len(
            audit_rows
        ),
        "signal_axis_counts": dict(axis_counts),
        "source_measure_counts": dict(
            measure_counts
        ),
        "not_emitted_reason_counts": dict(
            audit_reason_counts
        ),
        "output_timeseries_csv": str(OUTPUT_PATH),
        "output_audit_csv": str(AUDIT_PATH),
    }

    with METADATA_PATH.open(
        "w",
        encoding="utf-8",
    ) as metadata_file:
        json.dump(
            metadata,
            metadata_file,
            indent=2,
            ensure_ascii=False,
        )

    print("Canonical EDR crash-signal time series completed.")
    print(
        f"Raw table-value rows scanned: "
        f"{scanned_table_value_rows}"
    )
    print(
        f"Candidate source table rows: "
        f"{len(source_rows)}"
    )
    print(
        f"Signal samples emitted: "
        f"{len(output_rows)}"
    )
    print(
        f"Source table rows not emitted: "
        f"{len(audit_rows)}"
    )
    print(f"Time series: {OUTPUT_PATH}")
    print(f"Audit: {AUDIT_PATH}")
    print(f"Metadata: {METADATA_PATH}")
    print()
    print("Signal-axis sample counts:")

    for axis, count in sorted(axis_counts.items()):
        print(f"  {axis}: {count}")

    print()
    print("Source-measure counts:")

    for measure, count in sorted(
        measure_counts.items()
    ):
        print(f"  {measure}: {count}")

    if audit_reason_counts:
        print()
        print("Not-emitted source table-row reasons:")

        for reason, count in sorted(
            audit_reason_counts.items()
        ):
            print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()