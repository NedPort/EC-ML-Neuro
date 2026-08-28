"""
Build the canonical CISS vehicle-level index.

One row represents one audited vehicle within one crash case.

Sources:
- data/processed/<case_id>/audit/case_audit.json
- data/raw/<case_id>/metadata.json
- data/raw/<case_id>/export.xlsx, GV and VEHSPEC sheets
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class OutputPaths:
    parquet: Path
    metadata: Path


METADATA_GENERAL_FIELDS = {
    "metadata_model_year": "modelYearText",
    "metadata_make": "ncsaMake",
    "metadata_model": "ncsaModel",
    "metadata_body_category": "bodyCategory",
    "metadata_body_type": "ncsaBodyType",
    "metadata_vehicle_class": "vehicleClassDescription",
    "metadata_special_use": "specialUseDescription",
    "metadata_transport_status": "vehicleTransport",
    "metadata_has_trailer": "hasTrailer",
    "metadata_curb_weight_raw": "curbWeight",
    "metadata_curb_weight_source": "curbSource",
    "metadata_cargo_weight_raw": "cargoWeight",
    "metadata_cargo_weight_source": "cargoSource",
}

METADATA_SPECIFICATION_FIELDS = {
    "metadata_wheelbase_raw": "wheelbase",
    "metadata_overall_length_raw": "overallLength",
    "metadata_maximum_width_raw": "maximumWidth",
    "metadata_curb_weight_spec_raw": "curbWeightVehSpec",
    "metadata_average_track_width_raw": "averageTrackWidth",
    "metadata_front_overhang_raw": "frontOverhang",
    "metadata_rear_overhang_raw": "rearOverhang",
    "metadata_undeformed_end_width_raw": "undeformedEndWidth",
    "metadata_engine_cylinders": "engineCylinders",
    "metadata_engine_displacement_raw": "engineDisplacement",
    "metadata_transmission_type": "typeOfTransmissionDescription",
    "metadata_drive_wheels": "driveWheelsDescription",
    "metadata_modification_status": (
        "multistageOrAlteredVehicleDescription"
    ),
}

EXCEL_GV_FIELDS = {
    "excel_gv_vehicle_class": "VEHCLASSTEXT",
    "excel_gv_body_type": "BODYTYPETEXT",
    "excel_gv_body_category": "BODYCATTEXT",
    "excel_gv_special_use": "SPECUSETEXT",
    "excel_gv_transport_status": "TRANSTATTEXT",
    "excel_gv_towed_status": "TOWSTATTEXT",
    "excel_gv_curb_weight_raw": "CURBWT",
    "excel_gv_curb_weight_text": "CURBWTTEXT",
    "excel_gv_cargo_weight_raw": "CARGOWT",
    "excel_gv_cargo_weight_text": "CARGOWTTEXT",
}

EXCEL_VEHSPEC_FIELDS = {
    "excel_vehspec_wheelbase_raw": "WHEELBASE",
    "excel_vehspec_overall_length_raw": "OAL",
    "excel_vehspec_max_width_raw": "MAXWIDTH",
    "excel_vehspec_curb_weight_raw": "CURBWT",
    "excel_vehspec_track_width_raw": "TRACKWIDTH",
    "excel_vehspec_front_overhang_raw": "OVERHANG_FRT",
    "excel_vehspec_rear_overhang_raw": "OVERHANG_REAR",
    "excel_vehspec_undeformed_end_width_raw": "UEW",
    "excel_vehspec_engine_cylinders": "ENG_CYL",
    "excel_vehspec_engine_displacement_raw": "ENG_DISP",
    "excel_vehspec_transmission": "TRANSMISSIONTEXT",
    "excel_vehspec_drive_wheels": "DRVWHEELSTEXT",
    "excel_vehspec_altered_vehicle": "ALTVEHTEXT",
    "excel_vehspec_suspension_modifications": "SUSPMODSTEXT",
}


class VehicleIndexBuilder:
    """Create one provenance-preserving vehicle row per audited case."""

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)

    def build(
        self,
        case_ids: Iterable[int] | None = None,
        output_directory: str | Path | None = None,
    ) -> OutputPaths:
        audit_paths = self._resolve_audit_paths(case_ids)

        rows = [
            row
            for audit_path in audit_paths
            for row in self._rows_from_audit(audit_path)
        ]

        self._validate_rows(rows)

        output_dir = Path(
            output_directory
            or self.data_root / "processed" / "linked_tables"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = OutputPaths(
            parquet=output_dir / "vehicle_index.parquet",
            metadata=output_dir / "vehicle_index_metadata.json",
        )

        frame = pd.DataFrame(rows).sort_values(
            ["case_id", "vehicle_number"]
        )
        # Excel “text” fields may be read as numbers in some cases and
        # strings in others. Store them consistently as nullable text
        # without changing missing values.
        text_columns = [
            column
            for column in frame.columns
            if column.endswith("_text")
        ]

        for column in text_columns:
            frame[column] = frame[column].astype("string")
        frame.to_parquet(
            paths.parquet,
            index=False,
            engine="pyarrow",
        )

        metadata = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_name": "vehicle_index",
            "unit_of_analysis": (
                "one audited CISS vehicle within one crash case"
            ),
            "primary_key": "vehicle_id",
            "row_count": len(frame),
            "case_count": int(frame["case_id"].nunique()),
            "source_audit_files": [
                str(path) for path in audit_paths
            ],
            "source_policy": {
                "raw_values_preserved": True,
                "missing_values_imputed": False,
                "source_conflicts_silently_resolved": False,
                "metadata_role": (
                    "CISS API companion source for vehicle details"
                ),
                "excel_gv_role": (
                    "primary Excel General Vehicle source"
                ),
                "excel_vehspec_role": (
                    "primary Excel Vehicle Specifications source"
                ),
                "audit_role": (
                    "vehicle identity and quality-control source"
                ),
            },
            "columns": frame.columns.tolist(),
        }

        paths.metadata.write_text(
            json.dumps(metadata, indent=2, default=str),
            encoding="utf-8",
        )

        return paths

    def _resolve_audit_paths(
        self,
        case_ids: Iterable[int] | None,
    ) -> list[Path]:
        if case_ids is None:
            paths = sorted(
                (self.data_root / "processed").glob(
                    "*/audit/case_audit.json"
                )
            )
        else:
            paths = [
                self.data_root
                / "processed"
                / str(case_id)
                / "audit"
                / "case_audit.json"
                for case_id in case_ids
            ]

        if not paths:
            raise RuntimeError(
                "No Stage 2 case_audit.json files were found."
            )

        missing = [
            str(path)
            for path in paths
            if not path.is_file()
        ]

        if missing:
            raise RuntimeError(
                "Missing Stage 2 audit file(s): "
                + "; ".join(missing)
            )

        return paths

    def _rows_from_audit(
        self,
        audit_path: Path,
    ) -> list[dict[str, Any]]:
        with audit_path.open("r", encoding="utf-8") as file:
            audit = json.load(file)

        case_id = int(audit["case_id"])

        raw_case_dir = (
            self.data_root / "raw" / str(case_id)
        )

        metadata_path = raw_case_dir / "metadata.json"
        workbook_path = raw_case_dir / "export.xlsx"

        metadata = self._read_json(metadata_path)
        sheets = self._read_vehicle_sheets(workbook_path)

        vehicle_numbers = self._vehicle_numbers_from_audit(audit)

        if not vehicle_numbers:
            vehicle_numbers = self._vehicle_numbers_from_gv(
                sheets.get("GV")
            )

        return [
            self._build_row(
                audit=audit,
                audit_path=audit_path,
                case_id=case_id,
                vehicle_number=vehicle_number,
                metadata=metadata,
                sheets=sheets,
                metadata_path=metadata_path,
                workbook_path=workbook_path,
            )
            for vehicle_number in vehicle_numbers
        ]

    def _build_row(
        self,
        *,
        audit: dict[str, Any],
        audit_path: Path,
        case_id: int,
        vehicle_number: int,
        metadata: dict[str, Any],
        sheets: dict[str, pd.DataFrame],
        metadata_path: Path,
        workbook_path: Path,
    ) -> dict[str, Any]:
        vehicle_id = f"{case_id}-V{vehicle_number}"

        crash_summary_vehicle = self._find_metadata_record(
            metadata.get("crashSummaryVehicles"),
            vehicle_number,
        )

        general_vehicle = self._find_metadata_record(
            metadata.get("generalVehicleVehicles"),
            vehicle_number,
        )

        vehicle_specifications = self._find_metadata_record(
            metadata.get("generalVehicleSpecifications"),
            vehicle_number,
        )

        gv_record, gv_match_status = self._find_excel_record(
            sheets.get("GV"),
            "VEHNO",
            vehicle_number,
        )

        vehspec_record, vehspec_match_status = (
            self._find_excel_record(
                sheets.get("VEHSPEC"),
                "VEHNO",
                vehicle_number,
            )
        )

        metadata_vehicle_present = any(
            [
                crash_summary_vehicle,
                general_vehicle,
                vehicle_specifications,
            ]
        )

        metadata_vehicle_match_status = (
            "matched"
            if metadata_vehicle_present
            else "not_found"
        )

        metadata_case_id = self._positive_int(
            (metadata.get("crashSummary") or {}).get("caseId")
        )

        if metadata_case_id is None:
            source_case_id_agreement = "not_available"
        elif metadata_case_id == case_id:
            source_case_id_agreement = "matched"
        else:
            source_case_id_agreement = "mismatch"

        row = {
            # Identity and provenance
            "case_id": case_id,
            "vehicle_id": vehicle_id,
            "vehicle_number": vehicle_number,
            "audit_status": audit.get("status"),
            "vehicle_index_version": SCHEMA_VERSION,
            "source_audit_file": str(audit_path),
            "metadata_source_path": str(metadata_path),
            "excel_source_path": str(workbook_path),
            "metadata_available": metadata_path.is_file(),
            "excel_available": workbook_path.is_file(),
            "metadata_case_id": metadata_case_id,
            "source_case_id_agreement": (
                source_case_id_agreement
            ),
            "metadata_vehicle_match_status": (
                metadata_vehicle_match_status
            ),
            "excel_gv_match_status": gv_match_status,
            "excel_vehspec_match_status": vehspec_match_status,

            # Vehicle-summary companion fields
            "metadata_summary_model_year": (
                crash_summary_vehicle.get(
                    "modelYearDescription"
                )
                if crash_summary_vehicle
                else None
            ),
            "metadata_summary_make": (
                crash_summary_vehicle.get(
                    "makeDescription"
                )
                if crash_summary_vehicle
                else None
            ),
            "metadata_summary_model": (
                crash_summary_vehicle.get(
                    "modelDescription"
                )
                if crash_summary_vehicle
                else None
            ),
        }

        row.update(
            self._mapped_values(
                general_vehicle,
                METADATA_GENERAL_FIELDS,
            )
        )

        row.update(
            self._mapped_values(
                vehicle_specifications,
                METADATA_SPECIFICATION_FIELDS,
            )
        )

        row.update(
            self._mapped_values(
                gv_record,
                EXCEL_GV_FIELDS,
            )
        )

        row.update(
            self._mapped_values(
                vehspec_record,
                EXCEL_VEHSPEC_FIELDS,
            )
        )

        return row

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _read_vehicle_sheets(
        workbook_path: Path,
    ) -> dict[str, pd.DataFrame]:
        if not workbook_path.is_file():
            return {}

        return {
            "GV": pd.read_excel(
                workbook_path,
                sheet_name="GV",
            ),
            "VEHSPEC": pd.read_excel(
                workbook_path,
                sheet_name="VEHSPEC",
            ),
        }

    @staticmethod
    def _vehicle_numbers_from_audit(
        audit: dict[str, Any],
    ) -> list[int]:
        registry = audit.get("entity_registry", {})
        entities = registry.get("entities", [])

        vehicle_numbers: set[int] = set()

        for entity in entities:
            if entity.get("entity_type") != "vehicle":
                continue

            natural_key = entity.get("natural_key", {})
            vehicle_number = natural_key.get("VEHNO")

            if vehicle_number is not None:
                vehicle_numbers.add(int(vehicle_number))

        return sorted(vehicle_numbers)

    @staticmethod
    def _vehicle_numbers_from_gv(
        gv_frame: pd.DataFrame | None,
    ) -> list[int]:
        if gv_frame is None or "VEHNO" not in gv_frame.columns:
            return []

        values = gv_frame["VEHNO"].dropna().tolist()

        return sorted({int(value) for value in values})

    @staticmethod
    def _find_metadata_record(
        records: Any,
        vehicle_number: int,
    ) -> dict[str, Any]:
        if not isinstance(records, list):
            return {}

        for record in records:
            if not isinstance(record, dict):
                continue

            if record.get("vehicleNumber") == vehicle_number:
                return record

        return {}

    @staticmethod
    def _find_excel_record(
        frame: pd.DataFrame | None,
        key_column: str,
        vehicle_number: int,
    ) -> tuple[dict[str, Any], str]:
        if frame is None or key_column not in frame.columns:
            return {}, "sheet_or_key_not_available"

        matches = frame[
            frame[key_column] == vehicle_number
        ]

        if len(matches) == 0:
            return {}, "not_found"

        if len(matches) > 1:
            return {}, "duplicate_match"

        record = {}

        for key, value in matches.iloc[0].to_dict().items():
            record[key] = None if pd.isna(value) else value

        return record, "matched"

    @staticmethod
    def _mapped_values(
        record: dict[str, Any],
        mapping: dict[str, str],
    ) -> dict[str, Any]:
        return {
            output_column: record.get(source_column)
            for output_column, source_column in mapping.items()
        }

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if value is None:
            return None

        try:
            candidate = int(value)
        except (TypeError, ValueError):
            return None

        return candidate if candidate > 0 else None

    @staticmethod
    def _validate_rows(rows: list[dict[str, Any]]) -> None:
        if not rows:
            raise RuntimeError(
                "No vehicle rows were found in the selected audits."
            )

        vehicle_ids = [row["vehicle_id"] for row in rows]

        if len(vehicle_ids) != len(set(vehicle_ids)):
            raise RuntimeError(
                "Duplicate vehicle_id values found in vehicle_index."
            )

        mismatched_cases = [
            str(row["case_id"])
            for row in rows
            if row["source_case_id_agreement"] == "mismatch"
        ]

        if mismatched_cases:
            raise RuntimeError(
                "Source case ID mismatch for case(s): "
                + ", ".join(sorted(set(mismatched_cases)))
            )
