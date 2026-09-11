from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Model1ContextViewPaths:
    parquet: Path
    metadata: Path
    feature_list: Path


class Model1ContextViewBuilder:
    """
    Build the first non-duplicated, context-only Model 1 dataset.

    One row remains one vehicle-event. This builder does not alter the
    provenance-rich flat table and does not use labels as predictors.
    """

    VERSION = "1.0"

    KEY_COLUMNS = [
        "case_id",
        "vehicle_id",
        "vehicle_number",
        "event_number",
        "vehicle_event_id",
    ]

    # Retained for target-specific eligibility filtering, never predictors.
    TARGET_AND_QUALITY_COLUMNS = [
        "total_delta_v_kmh",
        "longitudinal_delta_v_kmh",
        "lateral_delta_v_kmh",
        "pdof_degrees",
        "delta_v_training_usable",
        "delta_v_event_linked",
        "delta_v_exclusion_reason",
        "pdof_training_usable",
        "pdof_event_linked",
        "pdof_exclusion_reason",
    ]

    # One preferred representation for each subject-vehicle concept.
    SUBJECT_VEHICLE_FEATURES = [
        "metadata_model_year",
        "metadata_body_category",
        "metadata_vehicle_class",
        "metadata_special_use",
        "metadata_transport_status",
        "metadata_has_trailer",
        "excel_gv_curb_weight_raw",
        "excel_gv_cargo_weight_raw",
        "excel_vehspec_wheelbase_raw",
        "excel_vehspec_overall_length_raw",
        "excel_vehspec_max_width_raw",
        "excel_vehspec_track_width_raw",
        "excel_vehspec_front_overhang_raw",
        "excel_vehspec_rear_overhang_raw",
        "excel_vehspec_undeformed_end_width_raw",
        "excel_vehspec_engine_cylinders",
        "excel_vehspec_engine_displacement_raw",
        "excel_vehspec_transmission",
        "excel_vehspec_drive_wheels",
        "excel_vehspec_altered_vehicle",
        "excel_vehspec_suspension_modifications",
    ]

    COLLISION_CONFIGURATION_FEATURES = [
        "crash_configuration_text",
        "collision_partner_class",
    ]

    # Counts are retained instead of their directly derived Boolean copies.
    EVENT_SEQUENCE_FEATURES = [
        "linked_vehicle_count",
        "case_crash_event_count",
        "event_sequence_position",
        "prior_event_count",
    ]

    ROADWAY_AND_PREIMPACT_FEATURES = [
        "excel_gv_speed_limit_raw",
        "excel_gv_traffic_flow",
        "excel_gv_road_lane_count",
        "excel_gv_initial_lane",
        "excel_gv_surface_type",
        "excel_gv_surface_condition",
        "excel_gv_alignment",
        "excel_gv_profile",
        "excel_gv_light_condition",
        "excel_gv_weather",
        "excel_gv_traffic_device",
        "excel_gv_precrash_heading",
        "excel_gv_precrash_movement",
    ]

    NUMERIC_FEATURES = {
        "metadata_model_year",
        "excel_gv_curb_weight_raw",
        "excel_gv_cargo_weight_raw",
        "excel_vehspec_wheelbase_raw",
        "excel_vehspec_overall_length_raw",
        "excel_vehspec_max_width_raw",
        "excel_vehspec_track_width_raw",
        "excel_vehspec_front_overhang_raw",
        "excel_vehspec_rear_overhang_raw",
        "excel_vehspec_undeformed_end_width_raw",
        "excel_vehspec_engine_cylinders",
        "excel_vehspec_engine_displacement_raw",
        "linked_vehicle_count",
        "case_crash_event_count",
        "event_sequence_position",
        "prior_event_count",
        "excel_gv_speed_limit_raw",
        "excel_gv_road_lane_count",
    }

    FEATURE_GROUPS = {
        "subject_vehicle_information": SUBJECT_VEHICLE_FEATURES,
        "collision_configuration": COLLISION_CONFIGURATION_FEATURES,
        "event_sequence_and_complexity": EVENT_SEQUENCE_FEATURES,
        "roadway_and_preimpact_context": ROADWAY_AND_PREIMPACT_FEATURES,
    }

    def __init__(self, flat_table_path: Path) -> None:
        self.flat_table_path = flat_table_path

    def build(
        self,
        output_directory: Path,
    ) -> Model1ContextViewPaths:
        source = pd.read_parquet(self.flat_table_path)

        self._validate_source(source)

        feature_columns = [
            column
            for columns in self.FEATURE_GROUPS.values()
            for column in columns
        ]

        output_columns = (
            self.KEY_COLUMNS
            + self.TARGET_AND_QUALITY_COLUMNS
            + feature_columns
        )

        frame = source[output_columns].copy()

        if frame["vehicle_event_id"].duplicated().any():
            duplicates = frame.loc[
                frame["vehicle_event_id"].duplicated(keep=False),
                "vehicle_event_id",
            ].tolist()

            raise ValueError(
                "vehicle_event_id must be unique. "
                f"Duplicate IDs found: {duplicates[:10]}"
            )

        for column in self.NUMERIC_FEATURES:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="coerce",
            )

        categorical_columns = [
            column
            for column in feature_columns
            if column not in self.NUMERIC_FEATURES
        ]

        for column in categorical_columns:
            frame[column] = frame[column].astype("string")

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        parquet_path = (
            output_directory
            / "model1_context_candidate_v1.parquet"
        )

        metadata_path = (
            output_directory
            / "model1_context_candidate_v1_metadata.json"
        )

        feature_list_path = (
            output_directory
            / "model1_context_candidate_v1_feature_list.csv"
        )

        frame.to_parquet(
            parquet_path,
            index=False,
        )

        feature_list = self._build_feature_list(
            frame=frame,
            feature_columns=feature_columns,
        )

        feature_list.to_csv(
            feature_list_path,
            index=False,
        )

        metadata_path.write_text(
            json.dumps(
                self._build_metadata(
                    frame=frame,
                    feature_columns=feature_columns,
                ),
                indent=2,
            ),
            encoding="utf-8",
        )

        return Model1ContextViewPaths(
            parquet=parquet_path,
            metadata=metadata_path,
            feature_list=feature_list_path,
        )

    def _validate_source(
        self,
        source: pd.DataFrame,
    ) -> None:
        required_columns = (
            self.KEY_COLUMNS
            + self.TARGET_AND_QUALITY_COLUMNS
            + [
                column
                for columns in self.FEATURE_GROUPS.values()
                for column in columns
            ]
        )

        missing = [
            column
            for column in required_columns
            if column not in source.columns
        ]

        if missing:
            raise ValueError(
                "The Model 1 flat table is missing required columns: "
                f"{missing}"
            )

    def _build_feature_list(
        self,
        frame: pd.DataFrame,
        feature_columns: list[str],
    ) -> pd.DataFrame:
        group_by_column = {
            column: group
            for group, columns in self.FEATURE_GROUPS.items()
            for column in columns
        }

        rows: list[dict[str, Any]] = []

        for column in feature_columns:
            present = self._is_present(frame[column])

            rows.append(
                {
                    "column_name": column,
                    "feature_group": group_by_column[column],
                    "data_type": str(frame[column].dtype),
                    "non_null_count": int(present.sum()),
                    "missing_count": int(len(frame) - present.sum()),
                    "coverage_percent": round(
                        100 * present.mean(),
                        2,
                    ),
                    "model1_decision": "include_context",
                    "duplicate_policy": (
                        "canonical_predictor"
                    ),
                }
            )

        return pd.DataFrame(rows).sort_values(
            ["feature_group", "column_name"]
        )

    def _build_metadata(
        self,
        frame: pd.DataFrame,
        feature_columns: list[str],
    ) -> dict[str, Any]:
        return {
            "table_name": "model1_context_candidate_v1",
            "version": self.VERSION,
            "row_unit": (
                "One row per vehicle-event. Rows are retained even "
                "when one or more target labels are unavailable."
            ),
            "source_table": str(self.flat_table_path),
            "row_count": int(len(frame)),
            "case_count": int(frame["case_id"].nunique()),
            "vehicle_count": int(frame["vehicle_id"].nunique()),
            "vehicle_event_count": int(
                frame["vehicle_event_id"].nunique()
            ),
            "predictor_feature_count": len(feature_columns),
            "predictor_groups": {
                group: len(columns)
                for group, columns in self.FEATURE_GROUPS.items()
            },
            "excluded_from_predictors": {
                "labels": [
                    "total_delta_v_kmh",
                    "longitudinal_delta_v_kmh",
                    "lateral_delta_v_kmh",
                    "pdof_degrees",
                ],
                "direct_reconstruction_fields": (
                    "CDC Delta-V values, CDC heading angle, and all "
                    "Delta-V/PDOF provenance fields are excluded."
                ),
                "not_in_context_model": (
                    "Damage/crush evidence, injury outcomes, EDR/CDR "
                    "availability, VLM evidence, narrative text, "
                    "identifiers, paths, and audit status fields."
                ),
            },
            "target_eligibility": {
                "delta_v_event_linked_usable_rows": int(
                    (
                        frame["delta_v_training_usable"].fillna(False)
                        & frame["delta_v_event_linked"].fillna(False)
                    ).sum()
                ),
                "pdof_event_linked_usable_rows": int(
                    (
                        frame["pdof_training_usable"].fillna(False)
                        & frame["pdof_event_linked"].fillna(False)
                    ).sum()
                ),
            },
            "feature_list_file": (
                "model1_context_candidate_v1_feature_list.csv"
            ),
        }

    @staticmethod
    def _is_present(series: pd.Series) -> pd.Series:
        return (
            series.notna()
            & series.astype("string").str.strip().ne("")
        )