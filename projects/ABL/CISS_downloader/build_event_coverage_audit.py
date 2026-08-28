import json
from pathlib import Path

import pandas as pd


VEHICLE_INPUT = Path(
    "data/processed/linked_tables/vehicle_index.parquet"
)

EVENT_INPUT = Path(
    "data/processed/linked_tables/vehicle_event_index.parquet"
)

OUTPUT_PATH = Path(
    "data/processed/linked_tables/event_coverage_audit.csv"
)


def event_numbers_from_excel(
    excel_path: Path,
    sheet_name: str,
    vehicle_column: str,
    vehicle_number: int,
) -> list[int]:
    """Return raw event numbers for one vehicle from one Excel sheet."""

    if not excel_path.exists():
        return []

    frame = pd.read_excel(excel_path, sheet_name=sheet_name)
    frame.columns = (
        frame.columns.astype(str).str.strip().str.upper()
    )

    if not {vehicle_column, "EVENTNO"}.issubset(frame.columns):
        return []

    values = pd.to_numeric(
        frame.loc[
            pd.to_numeric(
                frame[vehicle_column],
                errors="coerce",
            ) == vehicle_number,
            "EVENTNO",
        ],
        errors="coerce",
    )

    return sorted(values.dropna().astype(int).unique().tolist())


def main() -> None:
    vehicle_df = pd.read_parquet(VEHICLE_INPUT)
    event_df = pd.read_parquet(EVENT_INPUT)

    vehicles_with_events = set(event_df["vehicle_id"])

    rows = []

    for vehicle in vehicle_df.to_dict(orient="records"):
        case_id = int(vehicle["case_id"])
        vehicle_number = int(vehicle["vehicle_number"])
        vehicle_id = vehicle["vehicle_id"]

        metadata_path = Path(
            f"data/raw/{case_id}/metadata.json"
        )
        excel_path = Path(
            f"data/raw/{case_id}/export.xlsx"
        )

        metadata_event_numbers = []

        if metadata_path.exists():
            with metadata_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                metadata = json.load(file)

            metadata_event_numbers = sorted(
                {
                    int(event["eventNumber"])
                    for event in metadata.get("events", [])
                    if str(event.get("vehNum")) == str(vehicle_number)
                    and event.get("eventNumber") is not None
                }
            )

        excel_event_numbers = event_numbers_from_excel(
            excel_path=excel_path,
            sheet_name="EVENT",
            vehicle_column="VEHNUM",
            vehicle_number=vehicle_number,
        )

        excel_cdc_event_numbers = event_numbers_from_excel(
            excel_path=excel_path,
            sheet_name="CDC",
            vehicle_column="VEHNO",
            vehicle_number=vehicle_number,
        )

        indexed_event_numbers = sorted(
            pd.to_numeric(
                event_df.loc[
                    event_df["vehicle_id"] == vehicle_id,
                    "event_number",
                ],
                errors="coerce",
            )
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        raw_event_exists = bool(
            metadata_event_numbers
            or excel_event_numbers
            or excel_cdc_event_numbers
        )

        rows.append(
            {
                "case_id": case_id,
                "vehicle_id": vehicle_id,
                "vehicle_number": vehicle_number,
                "indexed_event_numbers": indexed_event_numbers,
                "metadata_event_numbers": metadata_event_numbers,
                "excel_event_numbers": excel_event_numbers,
                "excel_cdc_event_numbers": excel_cdc_event_numbers,
                "raw_event_exists": raw_event_exists,
                "event_coverage_status": (
                    "indexed_event_record_available"
                    if vehicle_id in vehicles_with_events
                    else (
                        "raw_event_exists_missing_from_index"
                        if raw_event_exists
                        else "no_raw_event_record_found"
                    )
                ),
            }
        )

    coverage_df = pd.DataFrame(rows)

    coverage_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Created: {OUTPUT_PATH}")
    print()
    print(
        coverage_df["event_coverage_status"]
        .value_counts()
        .to_string()
    )


if __name__ == "__main__":
    main()