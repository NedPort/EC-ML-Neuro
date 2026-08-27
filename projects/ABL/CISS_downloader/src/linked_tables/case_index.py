"""
Build the canonical CISS case-level index.

One row represents one audited crash case.

Sources:
- data/processed/<case_id>/audit/case_audit.json
- data/raw/<case_id>/metadata.json
- data/raw/<case_id>/export.xlsx, CRASH sheet
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


class CaseIndexBuilder:
    """Create one provenance-preserving row per audited CISS case."""

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)

    def build(
        self,
        case_ids: Iterable[int] | None = None,
        output_directory: str | Path | None = None,
    ) -> OutputPaths:
        audit_paths = self._resolve_audit_paths(case_ids)

        rows = [
            self._row_from_audit(audit_path)
            for audit_path in audit_paths
        ]

        self._validate_rows(rows)

        output_dir = Path(
            output_directory
            or self.data_root / "processed" / "linked_tables"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = OutputPaths(
            parquet=output_dir / "case_index.parquet",
            metadata=output_dir / "case_index_metadata.json",
        )

        frame = pd.DataFrame(rows).sort_values("case_id")
        frame.to_parquet(paths.parquet, index=False, engine="pyarrow")

        metadata = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_name": "case_index",
            "unit_of_analysis": "one audited CISS crash case",
            "primary_key": "case_id",
            "row_count": len(frame),
            "source_audit_files": [
                str(path) for path in audit_paths
            ],
            "source_policy": {
                "raw_values_preserved": True,
                "missing_values_imputed": False,
                "source_conflicts_silently_resolved": False,
                "crash_sheet_role": (
                    "primary raw case-level source"
                ),
                "metadata_role": (
                    "companion source for provenance "
                    "and cross-checking"
                ),
                "audit_role": (
                    "quality, availability, integrity, "
                    "and readiness source"
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

    def _row_from_audit(
        self,
        audit_path: Path,
    ) -> dict[str, Any]:
        with audit_path.open("r", encoding="utf-8") as file:
            audit = json.load(file)

        case_id = int(audit["case_id"])

        raw_case_dir = (
            self.data_root / "raw" / str(case_id)
        )

        metadata_path = raw_case_dir / "metadata.json"
        workbook_path = raw_case_dir / "export.xlsx"

        metadata = self._read_json(metadata_path)
        crash_record = self._read_crash_record(workbook_path)

        crash_summary = metadata.get("crashSummary") or {}
        assets = audit.get("asset_inventory", {})
        entities = audit.get("entities", {})
        collision_context = audit.get("collision_context", {})
        availability = audit.get("domain_availability", {})
        audit_summary = audit.get("audit_summary", {})
        contradictions = audit.get(
            "cross_source_contradictions",
            {},
        )
        manifest = audit.get("package_manifest", {})

        excel_case_id = self._positive_int(
            crash_record.get("CASEID")
        )
        metadata_case_id = self._positive_int(
            crash_summary.get("caseId")
        )

        source_case_ids = [
            value
            for value in [
                excel_case_id,
                metadata_case_id,
            ]
            if value is not None
        ]

        if not source_case_ids:
            source_case_id_agreement = "not_available"
        elif all(value == case_id for value in source_case_ids):
            source_case_id_agreement = "matched"
        else:
            source_case_id_agreement = "mismatch"

        asset_types = assets.get("assets_by_type", {})

        return {
            # Identity and provenance
            "case_id": case_id,
            "audit_status": audit.get("status"),
            "case_index_version": SCHEMA_VERSION,
            "source_audit_file": str(audit_path),
            "metadata_source_path": str(metadata_path),
            "excel_source_path": str(workbook_path),
            "metadata_available": metadata_path.is_file(),
            "excel_available": workbook_path.is_file(),
            "excel_case_id": excel_case_id,
            "metadata_case_id": metadata_case_id,
            "source_case_id_agreement": (
                source_case_id_agreement
            ),

            # Primary raw CRASH-sheet values
            "case_number": crash_record.get("CASENUMBER"),
            "case_number_raw": crash_record.get("CASENO"),
            "psu": crash_record.get("PSU"),
            "domain": crash_record.get("CATEGORY"),
            "crash_year": crash_record.get("CRASHYEAR"),
            "crash_month": crash_record.get("CRASHMONTH"),
            "crash_month_text": crash_record.get(
                "CRASHMONTHTEXT"
            ),
            "day_of_week": crash_record.get(
                "DAYOFWEEKTEXT"
            ),
            "day_of_week_code": crash_record.get(
                "DAYOFWEEK"
            ),
            "case_number_raw": crash_record.get("CASENO"),
            "crash_time_raw": crash_record.get("CRASHTIME"),
            "crash_configuration_code": crash_record.get(
                "CONFIG"
            ),
            "crash_configuration_text": crash_record.get(
                "CONFIGTEXT"
            ),
            "crash_summary": crash_record.get("SUMMARY"),
            "crash_event_count_raw": crash_record.get(
                "EVENTS"
            ),
            "vehicle_count_raw": crash_record.get(
                "VEHICLES"
            ),
            "manner_of_collision_raw": crash_record.get(
                "MANCOLL"
            ),
            "manner_of_collision_text": crash_record.get(
                "MANCOLLTEXT"
            ),
            # Case-level outcome/context fields; retained as raw values.
            "case_ais_raw": crash_record.get("CAIS"),
            "case_ais_text": crash_record.get("CAISTEXT"),
            "case_iss_raw": crash_record.get("CISS"),
            "case_injured_raw": crash_record.get("CINJURED"),
            "case_injury_severity_raw": crash_record.get(
                "CINJSEV"
            ),
            "case_treatment_raw": crash_record.get("CTREAT"),
            "case_treatment_text": crash_record.get(
                "CTREATTEXT"
            ),
            "alcohol_involvement_raw": crash_record.get(
                "ALCINV"
            ),
            "drug_involvement_raw": crash_record.get(
                "DRGINV"
            ),
            "case_weight": crash_record.get("CASEWGT"),
            "psu_stratum": crash_record.get("PSUSTRAT"),
            "source_version": crash_record.get("VERSION"),

            # metadata.json companion values
            "metadata_case_number": crash_summary.get(
                "caseNumber"
            ),
            "metadata_psu": crash_summary.get("psu"),
            "metadata_domain": crash_summary.get("domain"),
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

            # Audit counts and data-quality context
            "case_vehicle_count": collision_context.get(
                "case_vehicle_count"
            ),
            "case_crash_event_count": entities.get(
                "crash_events"
            ),
            "case_occupant_count": entities.get("occupants"),
            "case_injury_record_count": entities.get(
                "injuries"
            ),
            "edr_summary_count": entities.get("edr_summaries"),
            "edr_event_count": entities.get("edr_events"),
            "image_count": asset_types.get("image", 0),
            "sketch_count": asset_types.get("sketch", 0),
            "document_count": asset_types.get("document", 0),
            "asset_count": assets.get("total_assets", 0),
            "audit_warning_count": audit_summary.get(
                "warning_count",
                0,
            ),
            "audit_error_count": audit_summary.get(
                "error_count",
                0,
            ),
            "cross_source_contradiction_count": (
                contradictions.get("contradiction_count", 0)
            ),
            "package_status": manifest.get("status"),
            "package_validation_passed": manifest.get(
                "validation_passed"
            ),
            "crash_domain_status": availability.get(
                "crash",
                {},
            ).get("status"),
            "vehicle_domain_status": availability.get(
                "vehicle",
                {},
            ).get("status"),
            "edr_domain_status": availability.get(
                "edr",
                {},
            ).get("status"),
            "visual_assets_domain_status": availability.get(
                "visual_assets",
                {},
            ).get("status"),
        }

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _read_crash_record(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}

        frame = pd.read_excel(path, sheet_name="CRASH")

        if len(frame) != 1:
            raise RuntimeError(
                "CRASH sheet must contain exactly one row. "
                f"Found {len(frame)} rows in {path}."
            )

        record: dict[str, Any] = {}

        for key, value in frame.iloc[0].to_dict().items():
            record[key] = (
                None if pd.isna(value) else value
            )

        return record

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if value is None or pd.isna(value):
            return None

        try:
            candidate = int(value)
        except (TypeError, ValueError):
            return None

        return candidate if candidate > 0 else None

    @staticmethod
    def _validate_rows(rows: list[dict[str, Any]]) -> None:
        case_ids = [row["case_id"] for row in rows]

        if len(case_ids) != len(set(case_ids)):
            raise RuntimeError(
                "Duplicate case_id values found in case_index."
            )

        mismatched_cases = [
            str(row["case_id"])
            for row in rows
            if row["source_case_id_agreement"] == "mismatch"
        ]

        if mismatched_cases:
            raise RuntimeError(
                "Source case ID mismatch for case(s): "
                + ", ".join(mismatched_cases)
            )