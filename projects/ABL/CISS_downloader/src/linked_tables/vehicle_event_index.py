"""
Create the linked vehicle-event index from the existing rich evidence table.

One row represents one CISS:
    case_id × vehicle_number × event_number

The existing rich extraction is preserved. This builder validates links to
case_index and vehicle_index, then adds reconciled case-level vehicle counts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class VehicleEventIndexPaths:
    """Paths created by LinkedVehicleEventIndexBuilder."""

    parquet: Path
    metadata: Path


class LinkedVehicleEventIndexBuilder:
    """Create a validated linked vehicle-event master table."""

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)

    def build(
        self,
        *,
        output_directory: str | Path | None = None,
        rich_event_input: str | Path | None = None,
    ) -> VehicleEventIndexPaths:
        """Validate and link the existing rich vehicle-event evidence table."""

        output_dir = Path(
            output_directory
            or self.data_root / "processed" / "linked_tables"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        rich_event_path = Path(
            rich_event_input
            or self.data_root
            / "processed"
            / "standardized"
            / "vehicle_event_rich_evidence.parquet"
        )

        case_index_path = output_dir / "case_index.parquet"
        vehicle_index_path = output_dir / "vehicle_index.parquet"

        output_parquet = output_dir / "vehicle_event_index.parquet"
        output_metadata = (
            output_dir / "vehicle_event_index_metadata.json"
        )

        required_paths = [
            rich_event_path,
            case_index_path,
            vehicle_index_path,
        ]

        missing_paths = [
            str(path)
            for path in required_paths
            if not path.is_file()
        ]

        if missing_paths:
            raise FileNotFoundError(
                "Required linked-table input file(s) are missing:\n"
                + "\n".join(missing_paths)
            )

        rich_frame = pd.read_parquet(rich_event_path)
        case_frame = pd.read_parquet(case_index_path)
        vehicle_frame = pd.read_parquet(vehicle_index_path)

        self._validate_inputs(
            rich_frame=rich_frame,
            case_frame=case_frame,
            vehicle_frame=vehicle_frame,
        )

        linked_frame = self._link(
            rich_frame=rich_frame,
            case_frame=case_frame,
            vehicle_frame=vehicle_frame,
        )

        self._validate_output(linked_frame)

        linked_frame.to_parquet(output_parquet, index=False)

        metadata = self._build_metadata(
            rich_event_path=rich_event_path,
            case_index_path=case_index_path,
            vehicle_index_path=vehicle_index_path,
            frame=linked_frame,
        )

        output_metadata.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        print("Linked vehicle-event index completed.")
        print(f"Rows: {len(linked_frame)}")
        print(f"Cases: {linked_frame['case_id'].nunique()}")
        print(f"Parquet: {output_parquet}")
        print(f"Metadata: {output_metadata}")

        return VehicleEventIndexPaths(
            parquet=output_parquet,
            metadata=output_metadata,
        )

    @staticmethod
    def _validate_inputs(
        *,
        rich_frame: pd.DataFrame,
        case_frame: pd.DataFrame,
        vehicle_frame: pd.DataFrame,
    ) -> None:
        required_rich_columns = {
            "case_id",
            "vehicle_id",
            "vehicle_number",
            "event_number",
            "vehicle_event_id",
        }

        required_case_columns = {
            "case_id",
            "linked_vehicle_count",
            "vehicle_count_reconciliation_status",
        }

        required_vehicle_columns = {
            "case_id",
            "vehicle_id",
            "vehicle_number",
        }

        missing_rich = required_rich_columns - set(rich_frame.columns)
        missing_case = required_case_columns - set(case_frame.columns)
        missing_vehicle = (
            required_vehicle_columns - set(vehicle_frame.columns)
        )

        if missing_rich:
            raise ValueError(
                f"Rich event table is missing: {sorted(missing_rich)}"
            )

        if missing_case:
            raise ValueError(
                f"Case index is missing: {sorted(missing_case)}"
            )

        if missing_vehicle:
            raise ValueError(
                f"Vehicle index is missing: {sorted(missing_vehicle)}"
            )

        if rich_frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "Rich event table contains duplicate vehicle_event_id values."
            )

        if case_frame["case_id"].duplicated().any():
            raise ValueError(
                "Case index contains duplicate case_id values."
            )

        if vehicle_frame["vehicle_id"].duplicated().any():
            raise ValueError(
                "Vehicle index contains duplicate vehicle_id values."
            )

    @staticmethod
    def _link(
        *,
        rich_frame: pd.DataFrame,
        case_frame: pd.DataFrame,
        vehicle_frame: pd.DataFrame,
    ) -> pd.DataFrame:
        """Validate vehicle links and append reconciled case fields."""

        frame = rich_frame.copy()

        # Preserve the prior audit-derived event-table count under an
        # unambiguous name before appending the reconciled case fields.
        if "case_vehicle_count" in frame.columns:
            frame = frame.rename(
                columns={
                    "case_vehicle_count": (
                        "event_audit_case_vehicle_count"
                    )
                }
            )

        valid_vehicle_ids = set(vehicle_frame["vehicle_id"])

        unknown_vehicle_ids = sorted(
            set(frame["vehicle_id"]) - valid_vehicle_ids
        )

        if unknown_vehicle_ids:
            raise ValueError(
                "Event rows reference vehicle_id values absent from "
                "vehicle_index: "
                + ", ".join(unknown_vehicle_ids[:20])
            )

        case_fields = [
            "case_id",
            "vehicle_count_raw",
            "case_vehicle_count",
            "linked_vehicle_count",
            "vehicle_count_reconciliation_status",
        ]

        available_case_fields = [
            column
            for column in case_fields
            if column in case_frame.columns
        ]

        frame = frame.merge(
            case_frame[available_case_fields],
            on="case_id",
            how="left",
            validate="many_to_one",
        )

        if frame["linked_vehicle_count"].isna().any():
            missing_case_ids = sorted(
                frame.loc[
                    frame["linked_vehicle_count"].isna(),
                    "case_id",
                ]
                .dropna()
                .astype(int)
                .unique()
                .tolist()
            )

            raise ValueError(
                "Event rows reference case_id values absent from "
                "case_index: "
                + ", ".join(map(str, missing_case_ids[:20]))
            )

        frame["vehicle_event_index_version"] = SCHEMA_VERSION

        return (
            frame.sort_values(
                ["case_id", "vehicle_number", "event_number"]
            )
            .reset_index(drop=True)
        )

    @staticmethod
    def _validate_output(frame: pd.DataFrame) -> None:
        """Validate linked-table keys and reconciliation fields."""

        if frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "Linked output contains duplicate vehicle_event_id values."
            )

        if frame["vehicle_id"].isna().any():
            raise ValueError(
                "Linked output contains missing vehicle_id values."
            )

        if frame["linked_vehicle_count"].isna().any():
            raise ValueError(
                "Linked output contains missing linked_vehicle_count values."
            )

    @staticmethod
    def _build_metadata(
        *,
        rich_event_path: Path,
        case_index_path: Path,
        vehicle_index_path: Path,
        frame: pd.DataFrame,
    ) -> dict[str, object]:
        """Create provenance and coverage metadata."""

        status_counts = (
            frame["vehicle_count_reconciliation_status"]
            .value_counts(dropna=False)
            .to_dict()
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_name": "vehicle_event_index",
            "unit_of_analysis": (
                "one audited CISS vehicle involved in one crash event"
            ),
            "primary_key": "vehicle_event_id",
            "row_count": int(len(frame)),
            "case_count": int(frame["case_id"].nunique()),
            "vehicle_count": int(frame["vehicle_id"].nunique()),
            "source_tables": {
                "rich_event_evidence": str(rich_event_path),
                "case_index": str(case_index_path),
                "vehicle_index": str(vehicle_index_path),
            },
            "vehicle_count_reconciliation_status_counts": (
                status_counts
            ),
            "policy": {
                "rich_event_fields_preserved": True,
                "event_audit_case_vehicle_count_preserved": True,
                "linked_vehicle_count_added": True,
                "all_vehicle_links_validated": True,
                "missing_values_imputed": False,
                "target_fields_are_not_model_inputs": True,
            },
            "columns": frame.columns.tolist(),
        }