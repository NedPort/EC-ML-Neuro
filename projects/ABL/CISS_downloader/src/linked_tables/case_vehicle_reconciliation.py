"""
Reconcile case-level vehicle counts with the linked vehicle index.

Original CISS/audit counts are preserved. The derived linked_vehicle_count
is based on the actual rows in vehicle_index and is the count used for
linked-table analysis.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class CaseVehicleCountReconciler:
    """Add transparent vehicle-count reconciliation fields to case_index."""

    def __init__(
        self,
        output_directory: Path | None = None,
    ) -> None:
        self.output_directory = (
            Path(output_directory)
            if output_directory is not None
            else Path("data/processed/linked_tables")
        )
    def build(self) -> dict[str, Path]:
        case_index_path = self.output_directory / "case_index.parquet"
        vehicle_index_path = self.output_directory / "vehicle_index.parquet"
        metadata_path = (
            self.output_directory
            / "case_vehicle_count_reconciliation_metadata.json"
        )

        case_frame = pd.read_parquet(case_index_path)
        vehicle_frame = pd.read_parquet(vehicle_index_path)

        if case_frame["case_id"].duplicated().any():
            raise ValueError("case_index contains duplicate case_id values.")

        if vehicle_frame["vehicle_id"].duplicated().any():
            raise ValueError("vehicle_index contains duplicate vehicle_id values.")

        linked_counts = (
            vehicle_frame.groupby("case_id")
            .size()
            .rename("linked_vehicle_count")
        )

        case_frame["linked_vehicle_count"] = (
            case_frame["case_id"]
            .map(linked_counts)
            .fillna(0)
            .astype("Int64")
        )

        audit_counts = pd.to_numeric(
            case_frame["case_vehicle_count"],
            errors="coerce",
        )

        case_frame["vehicle_count_reconciliation_status"] = "audit_count_missing"

        case_frame.loc[
            audit_counts == case_frame["linked_vehicle_count"],
            "vehicle_count_reconciliation_status",
        ] = "matched"

        case_frame.loc[
            audit_counts < case_frame["linked_vehicle_count"],
            "vehicle_count_reconciliation_status",
        ] = "audit_undercount"

        case_frame.loc[
            audit_counts > case_frame["linked_vehicle_count"],
            "vehicle_count_reconciliation_status",
        ] = "audit_overcount"

        case_frame["case_vehicle_reconciliation_version"] = "1.0"

        case_frame.to_parquet(case_index_path, index=False)

        status_counts = (
            case_frame["vehicle_count_reconciliation_status"]
            .value_counts(dropna=False)
            .to_dict()
        )

        metadata = {
            "table_updated": "case_index.parquet",
            "reconciliation_version": "1.0",
            "original_counts_preserved": [
                "vehicle_count_raw",
                "case_vehicle_count",
            ],
            "derived_analysis_count": "linked_vehicle_count",
            "status_field": "vehicle_count_reconciliation_status",
            "linked_count_source": (
                "Number of distinct vehicle_index rows for each case_id."
            ),
            "case_count": int(len(case_frame)),
            "linked_vehicle_row_count": int(len(vehicle_frame)),
            "reconciliation_status_counts": status_counts,
        }

        metadata_path.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        return {
            "case_index": case_index_path,
            "metadata": metadata_path,
        }