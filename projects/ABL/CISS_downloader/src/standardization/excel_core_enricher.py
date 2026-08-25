"""
Enrich a metadata-enriched CISS vehicle-event table from export.xlsx.

The output remains one row per:
    case_id × vehicle_number × event_number

This module uses only safe joins:
- Vehicle sheets: VEHNO
- Event sheets: VEHNO + EVENTNO or VEHNUM + EVENTNO
- Pre-crash sheet: VEHNO, aggregated per vehicle
- EDR collection/summary: VEHNO

EDREVENT is intentionally excluded here because EDR event numbers must
be validated before they are linked to CISS crash events.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ExcelCoreEnrichmentPaths:
    """Paths created by ExcelCoreEnricher."""

    parquet: Path
    metadata: Path


class ExcelCoreEnricher:
    """Add selected, safely joined Excel fields to vehicle-event rows."""

    SCHEMA_VERSION = "1.0"

    REQUIRED_SHEETS = {
        "GV",
        "VEHSPEC",
        "VEH_MEAS",
        "EVENT",
        "CDC",
        "PRE_FHE",
        "EDRCOLLECT",
        "EDRSUMM",
    }

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)
        self._workbook_cache: dict[
            int,
            dict[str, pd.DataFrame]
        ] = {}

    def build(
        self,
        *,
        input_parquet: str | Path | None = None,
        output_directory: str | Path | None = None,
    ) -> ExcelCoreEnrichmentPaths:
        """Create the Excel-enriched core vehicle-event table."""
        input_path = (
            Path(input_parquet)
            if input_parquet is not None
            else (
                self.data_root
                / "processed"
                / "standardized"
                / "vehicle_event_metadata_enriched.parquet"
            )
        )

        if not input_path.exists():
            raise FileNotFoundError(
                "Metadata-enriched input was not found:\n"
                f"{input_path}"
            )

        destination = (
            Path(output_directory)
            if output_directory is not None
            else input_path.parent
        )
        destination.mkdir(parents=True, exist_ok=True)

        output_parquet = (
            destination / "vehicle_event_rich_core.parquet"
        )
        output_metadata = (
            destination
            / "vehicle_event_rich_core_metadata.json"
        )

        input_frame = pd.read_parquet(input_path)
        self._validate_input(input_frame)

        rows = [
            self._enrich_row(row.to_dict())
            for _, row in input_frame.iterrows()
        ]

        output_frame = pd.DataFrame(rows)

        self._validate_output(
            input_frame=input_frame,
            output_frame=output_frame,
        )

        output_frame = self._prepare_for_parquet(
            output_frame
        )

        output_frame.to_parquet(
            output_parquet,
            index=False,
        )

        report = self._build_report(
            input_path=input_path,
            output_path=output_parquet,
            frame=output_frame,
        )

        with output_metadata.open("w", encoding="utf-8") as file:
            json.dump(
                report,
                file,
                indent=2,
                ensure_ascii=False,
            )

        print("Excel core enrichment completed.")
        print(f"Input rows: {len(input_frame)}")
        print(f"Output rows: {len(output_frame)}")
        print(f"Parquet: {output_parquet}")
        print(f"Coverage report: {output_metadata}")

        return ExcelCoreEnrichmentPaths(
            parquet=output_parquet,
            metadata=output_metadata,
        )

    def _enrich_row(
        self,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        """Add Excel fields to one existing vehicle-event row."""
        case_id = self._to_int(row.get("case_id"))
        vehicle_number = self._to_int(
            row.get("vehicle_number")
        )
        event_number = self._to_int(
            row.get("event_number")
        )

        workbook_path = (
            self.data_root
            / "raw"
            / str(case_id)
            / "export.xlsx"
        )

        enrichment = self._empty_enrichment(workbook_path)

        if not workbook_path.exists():
            return {**row, **enrichment}

        try:
            sheets = self._load_workbook(case_id, workbook_path)

        except Exception as error:
            enrichment["excel_read_error"] = str(error)
            return {**row, **enrichment}

        enrichment["excel_available"] = True

        gv, gv_status = self._find_unique(
            sheets.get("GV"),
            {"VEHNO": vehicle_number},
        )

        vehicle_spec, vehicle_spec_status = self._find_unique(
            sheets.get("VEHSPEC"),
            {"VEHNO": vehicle_number},
        )

        vehicle_measurements, measurement_status = (
            self._find_unique(
                sheets.get("VEH_MEAS"),
                {"VEHNO": vehicle_number},
            )
        )

        cdc, cdc_status = self._find_unique(
            sheets.get("CDC"),
            {
                "VEHNO": vehicle_number,
                "EVENTNO": event_number,
            },
        )

        event, event_status = self._find_unique(
            sheets.get("EVENT"),
            {
                "VEHNUM": vehicle_number,
                "EVENTNO": event_number,
            },
        )

        edr_collect, edr_collect_status = self._find_unique(
            sheets.get("EDRCOLLECT"),
            {"VEHNO": vehicle_number},
        )

        edr_summary, edr_summary_status = self._find_unique(
            sheets.get("EDRSUMM"),
            {"VEHNO": vehicle_number},
        )

        precrash_records = self._find_all(
            sheets.get("PRE_FHE"),
            {"VEHNO": vehicle_number},
        )

        enrichment.update(
            {
                "excel_gv_match_status": gv_status,
                "excel_vehicle_spec_match_status": (
                    vehicle_spec_status
                ),
                "excel_vehicle_measurement_match_status": (
                    measurement_status
                ),
                "excel_cdc_match_status": cdc_status,
                "excel_event_match_status": event_status,
                "excel_edr_collect_match_status": (
                    edr_collect_status
                ),
                "excel_edr_summary_match_status": (
                    edr_summary_status
                ),
                "excel_precrash_record_count": len(
                    precrash_records
                ),
            }
        )

        enrichment.update(self._gv_fields(gv))
        enrichment.update(
            self._vehicle_specification_fields(vehicle_spec)
        )
        enrichment.update(
            self._vehicle_measurement_fields(
                vehicle_measurements
            )
        )
        enrichment.update(self._event_fields(event))
        enrichment.update(self._cdc_fields(cdc))
        enrichment.update(
            self._precrash_fields(precrash_records)
        )
        enrichment.update(
            self._edr_collection_fields(edr_collect)
        )
        enrichment.update(
            self._edr_summary_fields(edr_summary)
        )

        return {**row, **enrichment}

    def _load_workbook(
        self,
        case_id: int | None,
        workbook_path: Path,
    ) -> dict[str, pd.DataFrame]:
        """Load only the Excel sheets used by this core enrichment."""
        if case_id is None:
            raise ValueError("case_id is required.")

        if case_id in self._workbook_cache:
            return self._workbook_cache[case_id]

        excel_file = pd.ExcelFile(workbook_path)

        available_sheets = set(excel_file.sheet_names)
        sheets: dict[str, pd.DataFrame] = {}

        for sheet_name in self.REQUIRED_SHEETS:
            if sheet_name not in available_sheets:
                sheets[sheet_name] = pd.DataFrame()
                continue

            frame = pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
            )

            frame.columns = [
                str(column).strip().upper()
                for column in frame.columns
            ]

            sheets[sheet_name] = frame

        self._workbook_cache[case_id] = sheets
        return sheets

    @staticmethod
    def _empty_enrichment(
        workbook_path: Path,
    ) -> dict[str, Any]:
        """Return all Excel columns with safe empty defaults."""
        return {
            "excel_available": False,
            "excel_read_error": None,
            "excel_source_path": str(workbook_path),
            "excel_gv_match_status": "not_attempted",
            "excel_vehicle_spec_match_status": "not_attempted",
            "excel_vehicle_measurement_match_status": (
                "not_attempted"
            ),
            "excel_cdc_match_status": "not_attempted",
            "excel_event_match_status": "not_attempted",
            "excel_edr_collect_match_status": "not_attempted",
            "excel_edr_summary_match_status": "not_attempted",
            "excel_precrash_record_count": 0,
            # GV: vehicle, roadway, environment, pre-crash context.
            "excel_gv_vehicle_class": None,
            "excel_gv_body_type": None,
            "excel_gv_body_category": None,
            "excel_gv_special_use": None,
            "excel_gv_transport_status": None,
            "excel_gv_inspection_type": None,
            "excel_gv_tow_status": None,
            "excel_gv_curb_weight_raw": None,
            "excel_gv_curb_weight_text": None,
            "excel_gv_cargo_weight_raw": None,
            "excel_gv_cargo_weight_text": None,
            "excel_gv_speed_limit_raw": None,
            "excel_gv_speed_limit_text": None,
            "excel_gv_traffic_flow": None,
            "excel_gv_road_lane_count": None,
            "excel_gv_initial_lane": None,
            "excel_gv_surface_type": None,
            "excel_gv_surface_condition": None,
            "excel_gv_alignment": None,
            "excel_gv_profile": None,
            "excel_gv_light_condition": None,
            "excel_gv_weather": None,
            "excel_gv_traffic_device": None,
            "excel_gv_precrash_heading": None,
            "excel_gv_precrash_movement": None,
            # VEHSPEC.
            "excel_vehspec_wheelbase_raw": None,
            "excel_vehspec_overall_length_raw": None,
            "excel_vehspec_max_width_raw": None,
            "excel_vehspec_curb_weight_raw": None,
            "excel_vehspec_track_width_raw": None,
            "excel_vehspec_front_overhang_raw": None,
            "excel_vehspec_rear_overhang_raw": None,
            "excel_vehspec_undeformed_end_width_raw": None,
            "excel_vehspec_engine_cylinders": None,
            "excel_vehspec_engine_displacement_raw": None,
            "excel_vehspec_transmission": None,
            "excel_vehspec_drive_wheels": None,
            "excel_vehspec_altered_vehicle": None,
            "excel_vehspec_suspension_modifications": None,
            # VEH_MEAS.
            "excel_measure_front_bumper_raw": None,
            "excel_measure_rear_bumper_raw": None,
            "excel_measure_front_track_raw": None,
            "excel_measure_rear_track_raw": None,
            "excel_measure_front_hood_raw": None,
            "excel_measure_side_door_raw": None,
            # EVENT.
            "excel_event_class_1": None,
            "excel_event_class_1_text": None,
            "excel_event_general_area_damage_1": None,
            "excel_event_general_area_damage_1_text": None,
            "excel_event_object_contact": None,
            "excel_event_object_contact_text": None,
            "excel_event_class_2": None,
            "excel_event_class_2_text": None,
            "excel_event_general_area_damage_2": None,
            "excel_event_general_area_damage_2_text": None,
            # CDC: raw evidence only; never overwrites labels.
            "excel_cdc_code": None,
            "excel_cdc_plane": None,
            "excel_cdc_plane_text": None,
            "excel_cdc_extent": None,
            "excel_cdc_extent_text": None,
            "excel_cdc_end_shift": None,
            "excel_cdc_end_shift_text": None,
            "excel_cdc_overlap_under_ride": None,
            "excel_cdc_heading_angle": None,
            "excel_cdc_max_crush_raw": None,
            "excel_cdc_total_delta_v_raw": None,
            "excel_cdc_longitudinal_delta_v_raw": None,
            "excel_cdc_lateral_delta_v_raw": None,
            "excel_cdc_delta_v_basis": None,
            "excel_cdc_delta_v_basis_text": None,
            "excel_cdc_delta_v_estimate": None,
            "excel_cdc_delta_v_rank": None,
            # PRE_FHE aggregated by vehicle.
            "excel_precrash_sequences": None,
            "excel_precrash_events": None,
            "excel_precrash_event_texts": None,
            # EDR collection and summary, vehicle-level only.
            "excel_edr_obtained": None,
            "excel_edr_obtained_text": None,
            "excel_edr_method": None,
            "excel_edr_method_text": None,
            "excel_edr_summary_number": None,
            "excel_edr_number_of_events": None,
            "excel_edr_cdr_version_collected": None,
            "excel_edr_cdr_version_reported": None,
            "excel_edr_module_type": None,
            "excel_edr_module_type_text": None,
            "excel_edr_ignition_cycle_download": None,
        }

    @staticmethod
    def _gv_fields(record: dict[str, Any] | None) -> dict[str, Any]:
        record = record or {}

        return {
            "excel_gv_vehicle_class": record.get(
                "VEHCLASSTEXT"
            ),
            "excel_gv_body_type": record.get("BODYTYPETEXT"),
            "excel_gv_body_category": record.get(
                "BODYCATTEXT"
            ),
            "excel_gv_special_use": record.get("SPECUSETEXT"),
            "excel_gv_transport_status": record.get(
                "TRANSTATTEXT"
            ),
            "excel_gv_inspection_type": record.get(
                "INSPTYPETEXT"
            ),
            "excel_gv_tow_status": record.get("TOWSTATTEXT"),
            "excel_gv_curb_weight_raw": record.get("CURBWT"),
            "excel_gv_curb_weight_text": record.get(
                "CURBWTTEXT"
            ),
            "excel_gv_cargo_weight_raw": record.get("CARGOWT"),
            "excel_gv_cargo_weight_text": record.get(
                "CARGOWTTEXT"
            ),
            "excel_gv_speed_limit_raw": record.get(
                "SPEEDLIMIT"
            ),
            "excel_gv_speed_limit_text": record.get(
                "SPEEDLIMITTEXT"
            ),
            "excel_gv_traffic_flow": record.get("TRAFFLOWTEXT"),
            "excel_gv_road_lane_count": record.get("RDLANESTEXT"),
            "excel_gv_initial_lane": record.get("INITLANETEXT"),
            "excel_gv_surface_type": record.get("SURFTYPETEXT"),
            "excel_gv_surface_condition": record.get(
                "SURFCONDTEXT"
            ),
            "excel_gv_alignment": record.get("ALIGNMENTTEXT"),
            "excel_gv_profile": record.get("PROFILETEXT"),
            "excel_gv_light_condition": record.get(
                "LIGHTCONDTEXT"
            ),
            "excel_gv_weather": record.get("WEATHERTEXT"),
            "excel_gv_traffic_device": record.get("TRAFDEVTEXT"),
            "excel_gv_precrash_heading": record.get(
                "PREFHETEXT"
            ),
            "excel_gv_precrash_movement": record.get(
                "PREMOVETEXT"
            ),
        }

    @staticmethod
    def _vehicle_specification_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "excel_vehspec_wheelbase_raw": record.get(
                "WHEELBASE"
            ),
            "excel_vehspec_overall_length_raw": record.get("OAL"),
            "excel_vehspec_max_width_raw": record.get(
                "MAXWIDTH"
            ),
            "excel_vehspec_curb_weight_raw": record.get("CURBWT"),
            "excel_vehspec_track_width_raw": record.get(
                "TRACKWIDTH"
            ),
            "excel_vehspec_front_overhang_raw": record.get(
                "OVERHANG_FRT"
            ),
            "excel_vehspec_rear_overhang_raw": record.get(
                "OVERHANG_REAR"
            ),
            "excel_vehspec_undeformed_end_width_raw": record.get(
                "UEW"
            ),
            "excel_vehspec_engine_cylinders": record.get(
                "ENG_CYL"
            ),
            "excel_vehspec_engine_displacement_raw": record.get(
                "ENG_DISP"
            ),
            "excel_vehspec_transmission": record.get(
                "TRANSMISSIONTEXT"
            ),
            "excel_vehspec_drive_wheels": record.get(
                "DRVWHEELSTEXT"
            ),
            "excel_vehspec_altered_vehicle": record.get(
                "ALTVEHTEXT"
            ),
            "excel_vehspec_suspension_modifications": record.get(
                "SUSPMODSTEXT"
            ),
        }

    @staticmethod
    def _vehicle_measurement_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "excel_measure_front_bumper_raw": record.get(
                "FRNTBUMP"
            ),
            "excel_measure_rear_bumper_raw": record.get(
                "REARBUMP"
            ),
            "excel_measure_front_track_raw": record.get(
                "FRNTTRACK"
            ),
            "excel_measure_rear_track_raw": record.get(
                "REARTRACK"
            ),
            "excel_measure_front_hood_raw": record.get(
                "FRNTHOOD"
            ),
            "excel_measure_side_door_raw": record.get(
                "SIDEDOOR"
            ),
        }

    @staticmethod
    def _event_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "excel_event_class_1": record.get("CLASS1"),
            "excel_event_class_1_text": record.get("CLASS1TEXT"),
            "excel_event_general_area_damage_1": record.get("GAD1"),
            "excel_event_general_area_damage_1_text": record.get(
                "GAD1TEXT"
            ),
            "excel_event_object_contact": record.get("OBJCONT"),
            "excel_event_object_contact_text": record.get(
                "OBJCONTTEXT"
            ),
            "excel_event_class_2": record.get("CLASS2"),
            "excel_event_class_2_text": record.get("CLASS2TEXT"),
            "excel_event_general_area_damage_2": record.get("GAD2"),
            "excel_event_general_area_damage_2_text": record.get(
                "GAD2TEXT"
            ),
        }

    @staticmethod
    def _cdc_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "excel_cdc_code": record.get("CDC"),
            "excel_cdc_plane": record.get("CDCPLANE"),
            "excel_cdc_plane_text": record.get("CDCPLANETEXT"),
            "excel_cdc_extent": record.get("CDCEXTENT"),
            "excel_cdc_extent_text": record.get(
                "CDCEXTENTTEXT"
            ),
            "excel_cdc_end_shift": record.get("ENDSHIFT"),
            "excel_cdc_end_shift_text": record.get(
                "ENDSHIFTTEXT"
            ),
            "excel_cdc_overlap_under_ride": record.get(
                "OVERUNDER"
            ),
            "excel_cdc_heading_angle": record.get(
                "HEADINGANG"
            ),
            "excel_cdc_max_crush_raw": record.get("CMAX"),
            "excel_cdc_total_delta_v_raw": record.get(
                "DVTOTAL"
            ),
            "excel_cdc_longitudinal_delta_v_raw": record.get(
                "DVLONG"
            ),
            "excel_cdc_lateral_delta_v_raw": record.get(
                "DVLAT"
            ),
            "excel_cdc_delta_v_basis": record.get("DVBASIS"),
            "excel_cdc_delta_v_basis_text": record.get(
                "DVBASISTEXT"
            ),
            "excel_cdc_delta_v_estimate": record.get(
                "DVESTIMATE"
            ),
            "excel_cdc_delta_v_rank": record.get("DVRANK"),
        }

    @staticmethod
    def _precrash_fields(
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ordered_records = sorted(
            records,
            key=lambda item: (
                ExcelCoreEnricher._to_int(
                    item.get("SEQUENCE")
                )
                or 0
            ),
        )

        sequences = [
            str(record["SEQUENCE"])
            for record in ordered_records
            if ExcelCoreEnricher._present(
                record.get("SEQUENCE")
            )
        ]

        events = [
            str(record["PREEVENT"])
            for record in ordered_records
            if ExcelCoreEnricher._present(
                record.get("PREEVENT")
            )
        ]

        event_texts = [
            str(record["PREEVENTTEXT"])
            for record in ordered_records
            if ExcelCoreEnricher._present(
                record.get("PREEVENTTEXT")
            )
        ]

        return {
            "excel_precrash_sequences": (
                " | ".join(sequences)
                if sequences
                else None
            ),
            "excel_precrash_events": (
                " | ".join(events)
                if events
                else None
            ),
            "excel_precrash_event_texts": (
                " | ".join(event_texts)
                if event_texts
                else None
            ),
        }

    @staticmethod
    def _edr_collection_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "excel_edr_obtained": record.get("EDROBTAINED"),
            "excel_edr_obtained_text": record.get(
                "EDROBTAINEDTEXT"
            ),
            "excel_edr_method": record.get("EDRMETHOD"),
            "excel_edr_method_text": record.get(
                "EDRMETHODTEXT"
            ),
        }

    @staticmethod
    def _edr_summary_fields(
        record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record = record or {}

        return {
            "excel_edr_summary_number": record.get(
                "EDRSUMMNO"
            ),
            "excel_edr_number_of_events": record.get(
                "NUMEVENTS"
            ),
            "excel_edr_cdr_version_collected": record.get(
                "CDRVERCOLL"
            ),
            "excel_edr_cdr_version_reported": record.get(
                "CDRVERREPT"
            ),
            "excel_edr_module_type": record.get("MODTYPE"),
            "excel_edr_module_type_text": record.get(
                "MODTYPETEXT"
            ),
            "excel_edr_ignition_cycle_download": record.get(
                "IGCYCDOWN"
            ),
        }

    @staticmethod
    def _find_unique(
        frame: pd.DataFrame | None,
        criteria: dict[str, int | None],
    ) -> tuple[dict[str, Any] | None, str]:
        """Return one exact Excel match; never silently choose duplicates."""
        if frame is None or frame.empty:
            return None, "sheet_empty_or_missing"

        filtered = frame.copy()

        for column, expected_value in criteria.items():
            if expected_value is None:
                return None, "missing_join_key"

            if column not in filtered.columns:
                return None, f"missing_column_{column.lower()}"

            filtered = filtered.loc[
                filtered[column].apply(
                    ExcelCoreEnricher._to_int
                )
                == expected_value
            ]

        if len(filtered) == 0:
            return None, "not_found"

        if len(filtered) > 1:
            return None, "duplicate_records"

        return (
            ExcelCoreEnricher._clean_record(
                filtered.iloc[0].to_dict()
            ),
            "matched",
        )

    @staticmethod
    def _find_all(
        frame: pd.DataFrame | None,
        criteria: dict[str, int | None],
    ) -> list[dict[str, Any]]:
        """Return all matching records for a valid one-to-many join."""
        if frame is None or frame.empty:
            return []

        filtered = frame.copy()

        for column, expected_value in criteria.items():
            if expected_value is None or column not in filtered.columns:
                return []

            filtered = filtered.loc[
                filtered[column].apply(
                    ExcelCoreEnricher._to_int
                )
                == expected_value
            ]

        return [
            ExcelCoreEnricher._clean_record(
                record.to_dict()
            )
            for _, record in filtered.iterrows()
        ]

    @staticmethod
    def _clean_record(
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert pandas missing values into normal Python None."""
        return {
            key: (
                None
                if not ExcelCoreEnricher._present(value)
                else value
            )
            for key, value in record.items()
        }

    @staticmethod
    def _present(value: Any) -> bool:
        """Safely identify nonmissing scalar values."""
        if value is None:
            return False

        try:
            return not bool(pd.isna(value))

        except (TypeError, ValueError):
            return True

    @staticmethod
    def _to_int(value: Any) -> int | None:
        """Convert Excel identifiers safely."""
        if not ExcelCoreEnricher._present(value):
            return None

        try:
            return int(float(value))

        except (TypeError, ValueError):
            return None
    @staticmethod
    def _prepare_for_parquet(
        frame: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Make mixed object columns safe for Parquet.

        CISS exports sometimes represent the same descriptive field
        as text in one case and a number in another case. Numeric
        columns remain numeric when already consistently typed.
        """
        prepared = frame.copy()

        for column in prepared.columns:
            if not pd.api.types.is_object_dtype(
                prepared[column]
            ):
                continue

            nonmissing = prepared[column].dropna()

            if nonmissing.empty:
                continue

            value_types = {
                type(value)
                for value in nonmissing
            }

            if len(value_types) > 1:
                prepared[column] = prepared[column].astype(
                    "string"
                )

        return prepared
    @staticmethod
    def _validate_input(
        frame: pd.DataFrame,
    ) -> None:
        required_columns = {
            "case_id",
            "vehicle_number",
            "event_number",
            "vehicle_event_id",
        }

        missing = required_columns.difference(frame.columns)

        if missing:
            raise ValueError(
                "Input table is missing required columns: "
                f"{sorted(missing)}"
            )

        if frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "Input table contains duplicate "
                "vehicle_event_id values."
            )

    @staticmethod
    def _validate_output(
        *,
        input_frame: pd.DataFrame,
        output_frame: pd.DataFrame,
    ) -> None:
        """Confirm row identity remains unchanged."""
        if len(input_frame) != len(output_frame):
            raise ValueError(
                "Excel enrichment changed the row count."
            )

        if (
            input_frame["vehicle_event_id"].tolist()
            != output_frame["vehicle_event_id"].tolist()
        ):
            raise ValueError(
                "Excel enrichment changed row identity/order."
            )

        if output_frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "Output contains duplicate vehicle_event_id values."
            )

    def _build_report(
        self,
        *,
        input_path: Path,
        output_path: Path,
        frame: pd.DataFrame,
    ) -> dict[str, Any]:
        """Create coverage information for manual verification."""
        status_columns = [
            "excel_gv_match_status",
            "excel_vehicle_spec_match_status",
            "excel_vehicle_measurement_match_status",
            "excel_cdc_match_status",
            "excel_event_match_status",
            "excel_edr_collect_match_status",
            "excel_edr_summary_match_status",
        ]

        match_counts = {
            column: {
                str(key): int(value)
                for key, value in frame[column]
                .value_counts(dropna=False)
                .to_dict()
                .items()
            }
            for column in status_columns
        }

        excel_columns = [
            column
            for column in frame.columns
            if column.startswith("excel_")
        ]

        return {
            "schema_version": self.SCHEMA_VERSION,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "table_name": "vehicle_event_rich_core",
            "unit_of_analysis": (
                "one audited CISS vehicle involved "
                "in one crash event"
            ),
            "primary_key": "vehicle_event_id",
            "input_parquet": str(input_path),
            "output_parquet": str(output_path),
            "row_count": len(frame),
            "case_count": int(frame["case_id"].nunique()),
            "enrichment_policy": {
                "original_rows_preserved": True,
                "missing_values_imputed": False,
                "cdc_targets_do_not_overwrite_standardized_labels": (
                    True
                ),
                "edr_event_sheet_not_joined_without_validation": (
                    True
                ),
            },
            "match_counts": match_counts,
            "excel_columns_added": excel_columns,
            "column_nonmissing_counts": {
                column: int(frame[column].notna().sum())
                for column in excel_columns
            },
        }