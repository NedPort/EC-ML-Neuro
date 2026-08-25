"""
Enrich the standardized CISS vehicle-event index with metadata.json.

One output row remains one CISS case × vehicle × crash event.
The original vehicle_event_index.parquet is never modified.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class MetadataEnrichmentPaths:
    """Paths created by MetadataEnricher."""

    parquet: Path
    metadata: Path


class MetadataEnricher:
    """
    Add safely joinable metadata.json fields to vehicle-event rows.

    Join levels:
    - case: copied to every vehicle-event row in the case
    - vehicle: joined by vehicleNumber
    - event: joined by vehNum + eventNumber
    - EDR/CDR: joined or aggregated by vehicleNumber
    """

    SCHEMA_VERSION = "1.0"

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)

    def build(
        self,
        *,
        input_parquet: str | Path | None = None,
        output_directory: str | Path | None = None,
    ) -> MetadataEnrichmentPaths:
        """Read the index, enrich it from metadata.json, and save outputs."""
        index_path = (
            Path(input_parquet)
            if input_parquet is not None
            else (
                self.data_root
                / "processed"
                / "standardized"
                / "vehicle_event_index.parquet"
            )
        )

        if not index_path.exists():
            raise FileNotFoundError(
                "Vehicle-event index was not found:\n"
                f"{index_path}"
            )

        destination = (
            Path(output_directory)
            if output_directory is not None
            else index_path.parent
        )
        destination.mkdir(parents=True, exist_ok=True)

        output_parquet = (
            destination
            / "vehicle_event_metadata_enriched.parquet"
        )
        output_metadata = (
            destination
            / "vehicle_event_metadata_enriched_metadata.json"
        )

        index_frame = pd.read_parquet(index_path)

        self._validate_index(index_frame)

        enriched_rows = [
            self._enrich_row(row.to_dict())
            for _, row in index_frame.iterrows()
        ]

        enriched_frame = pd.DataFrame(enriched_rows)

        self._validate_output(
            original_frame=index_frame,
            enriched_frame=enriched_frame,
        )

        enriched_frame.to_parquet(
            output_parquet,
            index=False,
        )

        report = self._build_report(
            index_path=index_path,
            output_parquet=output_parquet,
            original_frame=index_frame,
            enriched_frame=enriched_frame,
        )

        with output_metadata.open("w", encoding="utf-8") as file:
            json.dump(
                report,
                file,
                indent=2,
                ensure_ascii=False,
            )

        print("Metadata enrichment completed.")
        print(f"Input rows: {len(index_frame)}")
        print(f"Output rows: {len(enriched_frame)}")
        print(f"Parquet: {output_parquet}")
        print(f"Metadata report: {output_metadata}")

        return MetadataEnrichmentPaths(
            parquet=output_parquet,
            metadata=output_metadata,
        )

    def _enrich_row(
        self,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        """Enrich one existing vehicle-event row from its metadata file."""
        case_id = self._to_int(row.get("case_id"))
        vehicle_number = self._to_int(row.get("vehicle_number"))
        event_number = self._to_int(row.get("event_number"))

        metadata_path = (
            self.data_root
            / "raw"
            / str(case_id)
            / "metadata.json"
        )

        enrichment = self._empty_enrichment(
            metadata_path=metadata_path,
        )

        if not metadata_path.exists():
            return {**row, **enrichment}

        try:
            with metadata_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                metadata = json.load(file)

        except (OSError, json.JSONDecodeError) as error:
            enrichment["metadata_read_error"] = str(error)
            return {**row, **enrichment}

        enrichment["metadata_available"] = True

        crash_summary = metadata.get("crashSummary") or {}
        enrichment.update(
            self._case_fields(crash_summary)
        )

        vehicle_summary = self._find_by_number(
            records=metadata.get(
                "crashSummaryVehicles"
            ),
            number_field="vehicleNumber",
            number=vehicle_number,
        )

        general_vehicle = self._find_by_number(
            records=metadata.get(
                "generalVehicleVehicles"
            ),
            number_field="vehicleNumber",
            number=vehicle_number,
        )

        vehicle_specifications = self._find_by_number(
            records=metadata.get(
                "generalVehicleSpecifications"
            ),
            number_field="vehicleNumber",
            number=vehicle_number,
        )

        event = self._find_event(
            records=metadata.get("events"),
            vehicle_number=vehicle_number,
            event_number=event_number,
        )

        edr_summary = self._find_by_number(
            records=metadata.get("edrSummaries"),
            number_field="vehicleNumber",
            number=vehicle_number,
        )

        cdr_records = self._records_for_vehicle(
            records=metadata.get("edrCdrs"),
            vehicle_number=vehicle_number,
        )

        enrichment["metadata_vehicle_match_status"] = (
            "matched"
            if any(
                [
                    vehicle_summary,
                    general_vehicle,
                    vehicle_specifications,
                ]
            )
            else "not_found"
        )

        enrichment["metadata_event_match_status"] = (
            "matched"
            if event
            else "not_found"
        )

        enrichment["metadata_edr_match_status"] = (
            "matched"
            if edr_summary
            else "not_found"
        )

        enrichment.update(
            self._vehicle_summary_fields(
                vehicle_summary
            )
        )

        enrichment.update(
            self._general_vehicle_fields(
                general_vehicle
            )
        )

        enrichment.update(
            self._vehicle_specification_fields(
                vehicle_specifications
            )
        )

        enrichment.update(
            self._event_fields(event)
        )

        enrichment.update(
            self._edr_summary_fields(edr_summary)
        )

        enrichment.update(
            self._cdr_file_fields(cdr_records)
        )

        return {**row, **enrichment}

    @staticmethod
    def _empty_enrichment(
        *,
        metadata_path: Path,
    ) -> dict[str, Any]:
        """Return every metadata-enrichment column with safe defaults."""
        return {
            "metadata_available": False,
            "metadata_read_error": None,
            "metadata_source_path": str(metadata_path),
            "metadata_case_id": None,
            "metadata_psu": None,
            "metadata_domain": None,
            "metadata_case_number": None,
            "metadata_crash_date_raw": None,
            "metadata_crash_time_raw": None,
            "metadata_crash_year": None,
            "metadata_day_of_week": None,
            "metadata_crash_summary": None,
            "metadata_crash_configuration": None,
            "metadata_vehicle_match_status": "not_attempted",
            "metadata_event_match_status": "not_attempted",
            "metadata_edr_match_status": "not_attempted",
            "metadata_model_year": None,
            "metadata_make": None,
            "metadata_model": None,
            "metadata_damage_plane": None,
            "metadata_damage_severity": None,
            "metadata_vin_masked": None,
            "metadata_body_category": None,
            "metadata_body_type": None,
            "metadata_vehicle_class": None,
            "metadata_special_use": None,
            "metadata_transport_status": None,
            "metadata_has_trailer": None,
            "metadata_inspection_status": None,
            "metadata_curb_weight_raw": None,
            "metadata_curb_weight_source": None,
            "metadata_cargo_weight_raw": None,
            "metadata_cargo_weight_source": None,
            "metadata_wheelbase_raw": None,
            "metadata_overall_length_raw": None,
            "metadata_maximum_width_raw": None,
            "metadata_curb_weight_spec_raw": None,
            "metadata_average_track_width_raw": None,
            "metadata_front_overhang_raw": None,
            "metadata_rear_overhang_raw": None,
            "metadata_undeformed_end_width_raw": None,
            "metadata_engine_cylinders": None,
            "metadata_engine_displacement_raw": None,
            "metadata_transmission_type": None,
            "metadata_drive_wheels": None,
            "metadata_modification_status": None,
            "metadata_event_description": None,
            "metadata_event_area_damage_code": None,
            "metadata_event_area_damage_description": None,
            "metadata_event_vehicle_class": None,
            "metadata_event_vehicle_class_description": None,
            "metadata_event_object_contact_class": None,
            "metadata_event_object_contact_class_description": None,
            "metadata_event_object_contact_code": None,
            "metadata_event_object_contact_description": None,
            "metadata_event_vehicle_contact_class": None,
            "metadata_event_vehicle_contact_class_description": None,
            "metadata_event_vehicle_contact_damage": None,
            "metadata_event_vehicle_contact_damage_description": None,
            "metadata_edr_obtained": None,
            "metadata_edr_imaging_method": None,
            "metadata_edr_event_total": None,
            "metadata_edr_module_type": None,
            "metadata_edr_ignition_cycle_download": None,
            "metadata_cdr_version_collected": None,
            "metadata_cdr_version_reported": None,
            "metadata_cdr_file_count": 0,
            "metadata_cdr_file_available": False,
            "metadata_cdr_file_names": None,
            "metadata_cdr_file_descriptions": None,
            "metadata_cdr_object_ids": None,
        }

    @staticmethod
    def _case_fields(
        crash_summary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "metadata_case_id": crash_summary.get("caseId"),
            "metadata_psu": crash_summary.get("psu"),
            "metadata_domain": crash_summary.get("domain"),
            "metadata_case_number": crash_summary.get(
                "caseNumber"
            ),
            "metadata_crash_date_raw": crash_summary.get(
                "crashDate"
            ),
            "metadata_crash_time_raw": crash_summary.get(
                "crashTime"
            ),
            "metadata_crash_year": crash_summary.get(
                "crashYear"
            ),
            "metadata_day_of_week": crash_summary.get(
                "dayOfWeek"
            ),
            "metadata_crash_summary": crash_summary.get(
                "summary"
            ),
            "metadata_crash_configuration": crash_summary.get(
                "crashConfiguration"
            ),
        }

    @staticmethod
    def _vehicle_summary_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "metadata_model_year": record.get(
                "modelYearDescription"
            ),
            "metadata_make": record.get(
                "makeDescription"
            ),
            "metadata_model": record.get(
                "modelDescription"
            ),
            "metadata_damage_plane": record.get(
                "damagePlaneDescription"
            ),
            "metadata_damage_severity": record.get(
                "severityDescription"
            ),
        }

    @staticmethod
    def _general_vehicle_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "metadata_vin_masked": record.get("vin"),
            "metadata_body_category": record.get(
                "bodyCategory"
            ),
            "metadata_body_type": record.get(
                "ncsaBodyType"
            ),
            "metadata_vehicle_class": record.get(
                "vehicleClassDescription"
            ),
            "metadata_special_use": record.get(
                "specialUseDescription"
            ),
            "metadata_transport_status": record.get(
                "vehicleTransport"
            ),
            "metadata_has_trailer": record.get(
                "hasTrailer"
            ),
            "metadata_inspection_status": record.get(
                "inspection"
            ),
            "metadata_curb_weight_raw": record.get(
                "curbWeight"
            ),
            "metadata_curb_weight_source": record.get(
                "curbSource"
            ),
            "metadata_cargo_weight_raw": record.get(
                "cargoWeight"
            ),
            "metadata_cargo_weight_source": record.get(
                "cargoSource"
            ),
        }

    @staticmethod
    def _vehicle_specification_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "metadata_wheelbase_raw": record.get("wheelbase"),
            "metadata_overall_length_raw": record.get(
                "overallLength"
            ),
            "metadata_maximum_width_raw": record.get(
                "maximumWidth"
            ),
            "metadata_curb_weight_spec_raw": record.get(
                "curbWeightVehSpec"
            ),
            "metadata_average_track_width_raw": record.get(
                "averageTrackWidth"
            ),
            "metadata_front_overhang_raw": record.get(
                "frontOverhang"
            ),
            "metadata_rear_overhang_raw": record.get(
                "rearOverhang"
            ),
            "metadata_undeformed_end_width_raw": record.get(
                "undeformedEndWidth"
            ),
            "metadata_engine_cylinders": record.get(
                "engineCylinders"
            ),
            "metadata_engine_displacement_raw": record.get(
                "engineDisplacement"
            ),
            "metadata_transmission_type": record.get(
                "typeOfTransmissionDescription"
            ),
            "metadata_drive_wheels": record.get(
                "driveWheelsDescription"
            ),
            "metadata_modification_status": record.get(
                "multistageOrAlteredVehicleDescription"
            ),
        }

    @staticmethod
    def _event_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "metadata_event_description": record.get(
                "eventDesc"
            ),
            "metadata_event_area_damage_code": record.get(
                "areaDamage"
            ),
            "metadata_event_area_damage_description": record.get(
                "areaDamageDesc"
            ),
            "metadata_event_vehicle_class": record.get(
                "vehClass"
            ),
            "metadata_event_vehicle_class_description": record.get(
                "vehClassDesc"
            ),
            "metadata_event_object_contact_class": record.get(
                "objectContactClass"
            ),
            "metadata_event_object_contact_class_description": (
                record.get("objectContactClassDesc")
            ),
            "metadata_event_object_contact_code": record.get(
                "objectContact"
            ),
            "metadata_event_object_contact_description": record.get(
                "objectContactDesc"
            ),
            "metadata_event_vehicle_contact_class": record.get(
                "vehContactClass"
            ),
            "metadata_event_vehicle_contact_class_description": (
                record.get("vehContactClassDesc")
            ),
            "metadata_event_vehicle_contact_damage": record.get(
                "vehContactDamage"
            ),
            "metadata_event_vehicle_contact_damage_description": (
                record.get("vehContactDamageDesc")
            ),
        }

    @staticmethod
    def _edr_summary_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "metadata_edr_obtained": record.get("obtained"),
            "metadata_edr_imaging_method": record.get(
                "imagingMethod"
            ),
            "metadata_edr_event_total": record.get(
                "eventTotal"
            ),
            "metadata_edr_module_type": record.get(
                "moduleType"
            ),
            "metadata_edr_ignition_cycle_download": record.get(
                "ignitionCycleDownload"
            ),
            "metadata_cdr_version_collected": record.get(
                "cdrVersionCollected"
            ),
            "metadata_cdr_version_reported": record.get(
                "cdrVersionReported"
            ),
        }

    @staticmethod
    def _cdr_file_fields(
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        file_names = [
            record.get("fileName")
            for record in records
            if record.get("fileName")
        ]

        descriptions = [
            record.get("fileDescription")
            for record in records
            if record.get("fileDescription")
        ]

        object_ids = [
            record.get("objectId")
            for record in records
            if record.get("objectId")
        ]

        return {
            "metadata_cdr_file_count": len(records),
            "metadata_cdr_file_available": bool(records),
            "metadata_cdr_file_names": (
                " | ".join(file_names)
                if file_names
                else None
            ),
            "metadata_cdr_file_descriptions": (
                " | ".join(descriptions)
                if descriptions
                else None
            ),
            "metadata_cdr_object_ids": (
                " | ".join(object_ids)
                if object_ids
                else None
            ),
        }

    @staticmethod
    def _find_by_number(
        *,
        records: Any,
        number_field: str,
        number: int | None,
    ) -> dict[str, Any] | None:
        """Find the first metadata record for one vehicle."""
        if number is None or not isinstance(records, list):
            return None

        for record in records:
            if not isinstance(record, dict):
                continue

            if (
                MetadataEnricher._to_int(
                    record.get(number_field)
                )
                == number
            ):
                return record

        return None

    @staticmethod
    def _find_event(
        *,
        records: Any,
        vehicle_number: int | None,
        event_number: int | None,
    ) -> dict[str, Any] | None:
        """Find one metadata event by vehicle number and event number."""
        if (
            vehicle_number is None
            or event_number is None
            or not isinstance(records, list)
        ):
            return None

        for record in records:
            if not isinstance(record, dict):
                continue

            record_vehicle = MetadataEnricher._to_int(
                record.get("vehNum")
            )
            record_event = MetadataEnricher._to_int(
                record.get("eventNumber")
            )

            if (
                record_vehicle == vehicle_number
                and record_event == event_number
            ):
                return record

        return None

    @staticmethod
    def _records_for_vehicle(
        *,
        records: Any,
        vehicle_number: int | None,
    ) -> list[dict[str, Any]]:
        """Return every metadata record associated with one vehicle."""
        if vehicle_number is None or not isinstance(records, list):
            return []

        return [
            record
            for record in records
            if isinstance(record, dict)
            and MetadataEnricher._to_int(
                record.get("vehicleNumber")
            )
            == vehicle_number
        ]

    @staticmethod
    def _to_int(value: Any) -> int | None:
        """Convert an identifier-like value to int when possible."""
        if value is None:
            return None

        try:
            return int(float(value))

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _validate_index(
        frame: pd.DataFrame,
    ) -> None:
        required_columns = {
            "case_id",
            "vehicle_number",
            "event_number",
            "vehicle_event_id",
        }

        missing_columns = required_columns.difference(
            frame.columns
        )

        if missing_columns:
            raise ValueError(
                "The input index is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        if frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "The input index contains duplicate "
                "vehicle_event_id values."
            )

    @staticmethod
    def _validate_output(
        *,
        original_frame: pd.DataFrame,
        enriched_frame: pd.DataFrame,
    ) -> None:
        """Confirm enrichment did not change the row contract."""
        if len(original_frame) != len(enriched_frame):
            raise ValueError(
                "Metadata enrichment changed the number of rows."
            )

        original_ids = original_frame["vehicle_event_id"].tolist()
        enriched_ids = enriched_frame["vehicle_event_id"].tolist()

        if original_ids != enriched_ids:
            raise ValueError(
                "Metadata enrichment changed row identity/order."
            )

        if enriched_frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "The enriched output contains duplicate "
                "vehicle_event_id values."
            )

    def _build_report(
        self,
        *,
        index_path: Path,
        output_parquet: Path,
        original_frame: pd.DataFrame,
        enriched_frame: pd.DataFrame,
    ) -> dict[str, Any]:
        """Create a transparent coverage report for manual review."""
        def count_true(column: str) -> int:
            if column not in enriched_frame.columns:
                return 0

            return int(
                enriched_frame[column]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        def count_value(column: str, value: str) -> int:
            if column not in enriched_frame.columns:
                return 0

            return int(
                (enriched_frame[column] == value).sum()
            )

        metadata_columns = [
            column
            for column in enriched_frame.columns
            if column.startswith("metadata_")
        ]

        column_coverage = {
            column: int(enriched_frame[column].notna().sum())
            for column in metadata_columns
        }

        return {
            "schema_version": self.SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_name": "vehicle_event_metadata_enriched",
            "unit_of_analysis": (
                "one audited CISS vehicle involved "
                "in one crash event"
            ),
            "input_parquet": str(index_path),
            "output_parquet": str(output_parquet),
            "row_count": len(enriched_frame),
            "case_count": int(
                enriched_frame["case_id"].nunique()
            ),
            "primary_key": "vehicle_event_id",
            "enrichment_policy": {
                "raw_metadata_preserved": True,
                "original_index_preserved": True,
                "row_count_preserved": True,
                "metadata_overwrites_existing_targets": False,
                "missing_values_imputed": False,
            },
            "match_coverage": {
                "rows_with_metadata_file": count_true(
                    "metadata_available"
                ),
                "rows_with_vehicle_match": count_value(
                    "metadata_vehicle_match_status",
                    "matched",
                ),
                "rows_with_event_match": count_value(
                    "metadata_event_match_status",
                    "matched",
                ),
                "rows_with_edr_summary_match": count_value(
                    "metadata_edr_match_status",
                    "matched",
                ),
                "rows_with_cdr_file": count_true(
                    "metadata_cdr_file_available"
                ),
            },
            "metadata_column_coverage": column_coverage,
            "metadata_columns_added": metadata_columns,
        }