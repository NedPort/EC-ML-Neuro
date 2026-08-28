from pathlib import Path

import pandas as pd


INPUT_PATH = Path(
    "data/processed/linked_tables/vehicle_index.parquet"
)

OUTPUT_PATH = Path(
    "data/processed/linked_tables/vehicle_index_data_dictionary.csv"
)

COLUMN_DETAILS = {
    "case_id": (
        "CISS crash-case identifier.",
        "linked-table identifier",
        "primary_key",
    ),
    "vehicle_id": (
        "Unique linked-table vehicle identifier: <case_id>-V<vehicle_number>.",
        "linked-table identifier",
        "primary_key",
    ),
    "vehicle_number": (
        "CISS vehicle number within the crash case (VEHNO).",
        "audit entity registry / export.xlsx",
        "join_key",
    ),
    "audit_status": (
        "Overall validation outcome recorded by the case audit.",
        "case_audit.json",
        "quality_flag",
    ),
    "vehicle_index_version": (
        "Schema version of the vehicle-index builder.",
        "linked-table build",
        "provenance",
    ),
    "source_audit_file": (
        "Path to the case audit JSON used to construct this row.",
        "linked-table build",
        "provenance",
    ),
    "metadata_source_path": (
        "Path to the source metadata.json file.",
        "linked-table build",
        "provenance",
    ),
    "excel_source_path": (
        "Path to the source export.xlsx file.",
        "linked-table build",
        "provenance",
    ),
    "metadata_available": (
        "Whether metadata.json was available during vehicle-index construction.",
        "linked-table build: checks metadata.json",
        "availability_flag",
    ),
    "excel_available": (
        "Whether export.xlsx was available during vehicle-index construction.",
        "linked-table build: checks export.xlsx",
        "availability_flag",
    ),
    "metadata_case_id": (
        "Case identifier read from metadata.json for source verification.",
        "metadata.json",
        "quality_flag",
    ),
    "source_case_id_agreement": (
        "Whether source case identifiers agree with the linked-table case_id.",
        "linked-table build",
        "quality_flag",
    ),
    "metadata_vehicle_match_status": (
        "Whether a unique metadata vehicle record matched this vehicle number.",
        "metadata.json",
        "quality_flag",
    ),
    "excel_gv_match_status": (
        "Whether a unique General Vehicle worksheet record matched this vehicle number.",
        "export.xlsx: GV worksheet",
        "quality_flag",
    ),
    "excel_vehspec_match_status": (
        "Whether a unique Vehicle Specifications worksheet record matched this vehicle number.",
        "export.xlsx: VEHSPEC worksheet",
        "quality_flag",
    ),
}


def classify_column(column: str) -> tuple[str, str, str]:
    """Return entity level, source, and role."""

    if column in COLUMN_DETAILS:
        _, source, role = COLUMN_DETAILS[column]
        return "vehicle", source, role

    if column.startswith("metadata_summary_"):
        return "vehicle", "metadata.json: vehicle summary", "source_evidence"

    if column.startswith("metadata_"):
        return "vehicle", "metadata.json", "source_evidence"

    if column.startswith("excel_gv_"):
        return "vehicle", "export.xlsx: GV worksheet", "source_evidence"

    if column.startswith("excel_vehspec_"):
        return "vehicle", "export.xlsx: VEHSPEC worksheet", "source_evidence"

    return "vehicle", "linked-table build", "provenance"


def readable_name(column: str) -> str:
    """Return an accurate description for known build fields."""

    if column in COLUMN_DETAILS:
        meaning, _, _ = COLUMN_DETAILS[column]
        return meaning

    return (
        f"Source-preserved vehicle attribute: {column}. "
        "See its source and field name for exact interpretation."
    )

def main() -> None:
    df = pd.read_parquet(INPUT_PATH)

    rows = []

    for column in df.columns:
        entity_level, source, role = classify_column(column)

        non_null_count = int(df[column].notna().sum())
        missing_count = int(df[column].isna().sum())

        rows.append(
            {
                "column_name": column,
                "meaning": readable_name(column),
                "source": source,
                "entity_level": entity_level,
                "data_type": str(df[column].dtype),
                "role": role,
                "non_null_count": non_null_count,
                "missing_count": missing_count,
                "coverage_percent": round(
                    100 * non_null_count / len(df),
                    2,
                ),
            }
        )

    dictionary_df = pd.DataFrame(rows)

    dictionary_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Created: {OUTPUT_PATH}")
    print(f"Documented columns: {len(dictionary_df)}")


if __name__ == "__main__":
    main()