from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Model1TargetCohortPaths:
    output_directory: Path
    metadata: Path


class Model1TargetCohortBuilder:
    """
    Create target-specific Model 1 datasets from the context-only view.

    Each output contains:
    - linkage keys;
    - one target column;
    - the same 40 context predictors.

    No target-derived field is retained as a predictor.
    """

    VERSION = "1.0"

    KEY_COLUMNS = [
        "case_id",
        "vehicle_id",
        "vehicle_number",
        "event_number",
        "vehicle_event_id",
    ]

    TARGET_CONFIGURATIONS = {
        "total_delta_v": {
            "target_column": "total_delta_v_kmh",
            "usable_column": "delta_v_training_usable",
            "linked_column": "delta_v_event_linked",
        },
        "longitudinal_delta_v": {
            "target_column": "longitudinal_delta_v_kmh",
            "usable_column": "delta_v_training_usable",
            "linked_column": "delta_v_event_linked",
        },
        "lateral_delta_v": {
            "target_column": "lateral_delta_v_kmh",
            "usable_column": "delta_v_training_usable",
            "linked_column": "delta_v_event_linked",
        },
        "pdof": {
            "target_column": "pdof_degrees",
            "usable_column": "pdof_training_usable",
            "linked_column": "pdof_event_linked",
        },
    }

    NON_PREDICTOR_COLUMNS = {
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
    }

    def __init__(self, context_table_path: Path) -> None:
        self.context_table_path = context_table_path

    def build(self, output_directory: Path) -> Model1TargetCohortPaths:
        source = pd.read_parquet(self.context_table_path)

        self._validate_source(source)

        predictor_columns = [
            column
            for column in source.columns
            if column not in self.KEY_COLUMNS
            and column not in self.NON_PREDICTOR_COLUMNS
        ]

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        cohort_summary = {}

        for cohort_name, config in self.TARGET_CONFIGURATIONS.items():
            target_column = config["target_column"]

            eligible = (
                self._as_bool(source[config["usable_column"]])
                & self._as_bool(source[config["linked_column"]])
                & source[target_column].notna()
            )

            cohort = source.loc[
                eligible,
                self.KEY_COLUMNS
                + [target_column]
                + predictor_columns,
            ].copy()

            if cohort["vehicle_event_id"].duplicated().any():
                raise ValueError(
                    f"{cohort_name} contains duplicate vehicle_event_id values."
                )

            output_path = (
                output_directory
                / f"model1_{cohort_name}_context_v1.parquet"
            )

            cohort.to_parquet(
                output_path,
                index=False,
            )

            cohort_summary[cohort_name] = {
                "file": str(output_path),
                "target_column": target_column,
                "row_count": int(len(cohort)),
                "case_count": int(cohort["case_id"].nunique()),
                "vehicle_count": int(cohort["vehicle_id"].nunique()),
                "predictor_feature_count": len(predictor_columns),
            }

        metadata_path = (
            output_directory
            / "model1_target_cohorts_context_v1_metadata.json"
        )

        metadata_path.write_text(
            json.dumps(
                {
                    "version": self.VERSION,
                    "source_context_table": str(
                        self.context_table_path
                    ),
                    "row_unit": "One eligible vehicle-event per target-specific cohort.",
                    "predictor_feature_count": len(
                        predictor_columns
                    ),
                    "case_split_rule": (
                        "Split train, validation, and test sets by case_id, "
                        "not by individual vehicle-event row."
                    ),
                    "cohorts": cohort_summary,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return Model1TargetCohortPaths(
            output_directory=output_directory,
            metadata=metadata_path,
        )

    def _validate_source(self, source: pd.DataFrame) -> None:
        required = (
            self.KEY_COLUMNS
            + list(self.NON_PREDICTOR_COLUMNS)
        )

        missing = [
            column
            for column in required
            if column not in source.columns
        ]

        if missing:
            raise ValueError(
                "Context table is missing required columns: "
                f"{missing}"
            )

    @staticmethod
    def _as_bool(series: pd.Series) -> pd.Series:
        return (
            series.fillna(False)
            .astype("string")
            .str.strip()
            .str.lower()
            .isin({"true", "1", "yes"})
        )