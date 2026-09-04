"""
Build the broad candidate flat table for Model 1:
Delta-V and PDOF prediction.

This is not the final training matrix. It preserves candidate features,
labels, and provenance so feature specification can be done transparently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Model1FlatTablePaths:
    parquet: Path
    metadata: Path


class Model1FlatTableBuilder:
    """Create one flat candidate row per verified vehicle-event."""

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)

    def build(
        self,
        output_directory: str | Path | None = None,
    ) -> Model1FlatTablePaths:
        linked_directory = (
            self.data_root / "processed" / "linked_tables"
        )

        output_dir = Path(
            output_directory
            or self.data_root / "processed" / "modeling"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        case_path = linked_directory / "case_index.parquet"
        vehicle_path = linked_directory / "vehicle_index.parquet"
        event_path = (
            linked_directory / "vehicle_event_index.parquet"
        )

        output_parquet = (
            output_dir / "model1_delta_v_pdof_candidate_flat.parquet"
        )
        output_metadata = (
            output_dir
            / "model1_delta_v_pdof_candidate_flat_metadata.json"
        )

        for path in [case_path, vehicle_path, event_path]:
            if not path.is_file():
                raise FileNotFoundError(
                    f"Required input table is missing: {path}"
                )

        case_df = pd.read_parquet(case_path)
        vehicle_df = pd.read_parquet(vehicle_path)
        event_df = pd.read_parquet(event_path)

        self._validate_inputs(
            case_df=case_df,
            vehicle_df=vehicle_df,
            event_df=event_df,
        )

        flat_df, added_case_columns, added_vehicle_columns = (
            self._build_flat_table(
                case_df=case_df,
                vehicle_df=vehicle_df,
                event_df=event_df,
            )
        )

        self._validate_output(flat_df)

        flat_df.to_parquet(output_parquet, index=False)

        metadata = self._build_metadata(
            case_path=case_path,
            vehicle_path=vehicle_path,
            event_path=event_path,
            frame=flat_df,
            added_case_columns=added_case_columns,
            added_vehicle_columns=added_vehicle_columns,
        )

        output_metadata.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        print("Model 1 candidate flat table completed.")
        print(f"Rows: {len(flat_df)}")
        print(f"Cases: {flat_df['case_id'].nunique()}")
        print(f"Columns: {len(flat_df.columns)}")
        print(f"Parquet: {output_parquet}")
        print(f"Metadata: {output_metadata}")

        return Model1FlatTablePaths(
            parquet=output_parquet,
            metadata=output_metadata,
        )

    @staticmethod
    def _validate_inputs(
        *,
        case_df: pd.DataFrame,
        vehicle_df: pd.DataFrame,
        event_df: pd.DataFrame,
    ) -> None:
        if case_df["case_id"].duplicated().any():
            raise ValueError("case_index contains duplicate case_id values.")

        if vehicle_df["vehicle_id"].duplicated().any():
            raise ValueError(
                "vehicle_index contains duplicate vehicle_id values."
            )

        if event_df["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "vehicle_event_index contains duplicate "
                "vehicle_event_id values."
            )

        unknown_case_ids = set(event_df["case_id"]) - set(
            case_df["case_id"]
        )
        if unknown_case_ids:
            raise ValueError(
                "Event table contains unknown case_id values: "
                + ", ".join(map(str, sorted(unknown_case_ids)))
            )

        unknown_vehicle_ids = set(event_df["vehicle_id"]) - set(
            vehicle_df["vehicle_id"]
        )
        if unknown_vehicle_ids:
            raise ValueError(
                "Event table contains unknown vehicle_id values: "
                + ", ".join(sorted(unknown_vehicle_ids))
            )

    @staticmethod
    def _build_flat_table(
        *,
        case_df: pd.DataFrame,
        vehicle_df: pd.DataFrame,
        event_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, list[str], list[str]]:
        """
        Start from event rows and add only non-duplicated fields from
        case_index and vehicle_index.

        Existing event-table fields are retained without overwrite because
        they already preserve their original metadata/Excel event context.
        """

        flat_df = event_df.copy()

        case_columns = [
            column
            for column in case_df.columns
            if column != "case_id" and column not in flat_df.columns
        ]

        flat_df = flat_df.merge(
            case_df[["case_id", *case_columns]],
            on="case_id",
            how="left",
            validate="many_to_one",
        )

        vehicle_columns = [
            column
            for column in vehicle_df.columns
            if column not in {
                "case_id",
                "vehicle_id",
                "vehicle_number",
            }
            and column not in flat_df.columns
        ]

        flat_df = flat_df.merge(
            vehicle_df[
                [
                    "case_id",
                    "vehicle_id",
                    "vehicle_number",
                    *vehicle_columns,
                ]
            ],
            on=["case_id", "vehicle_id", "vehicle_number"],
            how="left",
            validate="many_to_one",
        )

        flat_df["model1_candidate_flat_version"] = SCHEMA_VERSION

        return flat_df, case_columns, vehicle_columns

    @staticmethod
    def _validate_output(frame: pd.DataFrame) -> None:
        if frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "Flat table contains duplicate vehicle_event_id values."
            )

        if frame["case_id"].isna().any():
            raise ValueError("Flat table contains missing case_id values.")

        if frame["vehicle_id"].isna().any():
            raise ValueError(
                "Flat table contains missing vehicle_id values."
            )

    @staticmethod
    def _build_metadata(
        *,
        case_path: Path,
        vehicle_path: Path,
        event_path: Path,
        frame: pd.DataFrame,
        added_case_columns: list[str],
        added_vehicle_columns: list[str],
    ) -> dict[str, object]:
        leakage_fields = [
            "total_delta_v_kmh",
            "longitudinal_delta_v_kmh",
            "lateral_delta_v_kmh",
            "pdof_degrees",
            "excel_cdc_total_delta_v_raw",
            "excel_cdc_longitudinal_delta_v_raw",
            "excel_cdc_lateral_delta_v_raw",
            "excel_cdc_heading_angle",
        ]

        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_name": "model1_delta_v_pdof_candidate_flat",
            "unit_of_analysis": (
                "one verified CISS vehicle involved in one "
                "raw-evidenced crash event"
            ),
            "primary_key": "vehicle_event_id",
            "row_count": int(len(frame)),
            "case_count": int(frame["case_id"].nunique()),
            "column_count": int(len(frame.columns)),
            "source_tables": {
                "case_index": str(case_path),
                "vehicle_index": str(vehicle_path),
                "vehicle_event_index": str(event_path),
            },
            "columns_added_from_case_index": added_case_columns,
            "columns_added_from_vehicle_index": added_vehicle_columns,
            "target_fields_retained": [
                "total_delta_v_kmh",
                "longitudinal_delta_v_kmh",
                "lateral_delta_v_kmh",
                "pdof_degrees",
            ],
            "known_leakage_fields_excluded_from_future_model_inputs": (
                leakage_fields
            ),
            "policy": {
                "linked_master_tables_unchanged": True,
                "missing_values_imputed": False,
                "feature_selection_not_yet_applied": True,
                "case_level_split_required": True,
            },
            "columns": frame.columns.tolist(),
        }