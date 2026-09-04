from pathlib import Path

import pandas as pd


INPUT_PATH = Path(
    "data/processed/modeling/"
    "model1_delta_v_pdof_candidate_flat.parquet"
)

OUTPUT_PATH = Path(
    "data/processed/modeling/"
    "model1_delta_v_pdof_candidate_flat_data_dictionary.csv"
)


LEAKAGE_COLUMNS = {
    "total_delta_v_kmh",
    "longitudinal_delta_v_kmh",
    "lateral_delta_v_kmh",
    "pdof_degrees",
    "excel_cdc_total_delta_v_raw",
    "excel_cdc_longitudinal_delta_v_raw",
    "excel_cdc_lateral_delta_v_raw",
    "excel_cdc_heading_angle",
}


TARGET_COLUMNS = {
    "total_delta_v_kmh",
    "longitudinal_delta_v_kmh",
    "lateral_delta_v_kmh",
    "pdof_degrees",
}


IDENTIFIER_COLUMNS = {
    "case_id",
    "vehicle_id",
    "vehicle_number",
    "event_number",
    "vehicle_event_id",
}


def feature_group(column: str) -> str:
    if column in IDENTIFIER_COLUMNS:
        return "identity_and_split_keys"

    if column in TARGET_COLUMNS or column.startswith(
        ("delta_v_", "pdof_")
    ):
        return "targets_and_target_provenance"

    if column.startswith(
        ("collision_partner_", "event_partner_", "analysis_cohort")
    ):
        return "collision_partner_information"

    if column.startswith(
        ("event_sequence_", "prior_event_", "is_multi_", "case_crash_event")
    ):
        return "event_sequence_and_crash_complexity"

    if column.startswith(
        ("excel_gv_speed", "excel_gv_traffic", "excel_gv_road",
         "excel_gv_initial", "excel_gv_surface", "excel_gv_alignment",
         "excel_gv_profile", "excel_gv_light", "excel_gv_weather",
         "excel_gv_precrash", "excel_precrash_")
    ):
        return "preimpact_motion_and_roadway_context"

    if column.startswith(
        ("metadata_damage_", "metadata_event_area_damage",
         "event_focal_damage", "excel_measure_", "excel_cdc_",
         "excel_event_general_area_damage")
    ):
        return "postcrash_damage_and_crush_evidence"

    if column.startswith(
        ("edr_", "metadata_edr_", "excel_edr_", "crash_pulse_",
         "asset_", "tree_", "vlm_", "image_count", "document_count",
         "sketch_count", "has_vehicle_damage_images", "has_sketches")
    ):
        return "edr_scene_image_and_sketch_evidence"

    if column.startswith(("metadata_", "excel_gv_", "excel_vehspec_")):
        return "subject_vehicle_information"

    if column.startswith(("audit_", "source_", "metadata_read_",
                          "excel_read_", "linked_vehicle_count",
                          "vehicle_count_reconciliation")):
        return "provenance_and_quality"

    return "other_or_review_required"


def source_table(column: str) -> str:
    if column.startswith(("metadata_", "excel_", "audit_", "asset_", "tree_")):
        return "vehicle_event_index"

    if column.startswith(("case_", "linked_vehicle_count",
                          "vehicle_count_reconciliation")):
        return "case_index"

    if column.startswith("vehicle_index_"):
        return "vehicle_index"

    return "linked-table build"


def model1_status(column: str) -> str:
    if column in IDENTIFIER_COLUMNS:
        return "join_or_split_key_not_model_input"

    if column in TARGET_COLUMNS:
        return "target_only_not_model_input"

    if column in LEAKAGE_COLUMNS:
        return "exclude_leakage"

    if (
        column.startswith(("delta_v_", "pdof_"))
        or column.endswith("_training_usable")
        or column.endswith("_exclusion_reason")
    ):
        return "target_provenance_not_model_input"

    if column.startswith(("vlm_", "asset_", "tree_")):
        return "candidate_feature_or_availability_flag"

    if column.startswith(("audit_", "source_")):
        return "provenance_or_quality_control"

    return "candidate_feature_review_required"


def main() -> None:
    df = pd.read_parquet(INPUT_PATH)

    rows = []

    for column in df.columns:
        non_null = int(df[column].notna().sum())

        rows.append(
            {
                "column_name": column,
                "feature_group": feature_group(column),
                "source_table": source_table(column),
                "data_type": str(df[column].dtype),
                "model1_feature_status": model1_status(column),
                "non_null_count": non_null,
                "missing_count": int(len(df) - non_null),
                "coverage_percent": round(
                    100 * non_null / len(df),
                    2,
                ),
                "review_notes": "",
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