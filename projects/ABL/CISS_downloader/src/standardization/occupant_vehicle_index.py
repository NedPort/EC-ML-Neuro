"""Build the first standardized CISS occupant--vehicle training table.

This module consumes Stage 2 ``case_audit.json`` files.  It deliberately does
not impute missing values or overwrite raw values.  Instead, it creates one
row per audited occupant--vehicle pair and retains the audit's availability,
readiness, and provenance decisions alongside standardized fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class OutputPaths:
    """Locations of Stage 3 output artifacts."""

    parquet: Path
    metadata: Path


class OccupantVehicleIndexBuilder:
    """Create a non-imputed, occupant-level standardized index from audits."""

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)

    def build(
        self,
        case_ids: Iterable[int] | None = None,
        output_directory: str | Path | None = None,
    ) -> OutputPaths:
        """Build and write the indexed Parquet table and provenance metadata.

        Args:
            case_ids: Optional CISS IDs.  When omitted, all audit files beneath
                ``data/processed/*/audit/case_audit.json`` are used.
            output_directory: Optional output folder.  Defaults to
                ``data/processed/standardized``.

        Raises:
            RuntimeError: If no audit files are found, identifiers are
                duplicated, or the Parquet dependency is not installed.
        """
        audit_paths = self._resolve_audit_paths(case_ids)
        rows = [row for path in audit_paths for row in self._rows_from_audit(path)]
        self._validate_rows(rows)

        output_dir = Path(output_directory or self.data_root / "processed" / "standardized")
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = OutputPaths(
            parquet=output_dir / "occupant_vehicle_index.parquet",
            metadata=output_dir / "occupant_vehicle_index_metadata.json",
        )

        self._write_parquet(rows, paths.parquet)
        self._write_metadata(rows, audit_paths, paths.metadata)
        return paths

    def _resolve_audit_paths(self, case_ids: Iterable[int] | None) -> list[Path]:
        if case_ids is None:
            paths = sorted((self.data_root / "processed").glob("*/audit/case_audit.json"))
        else:
            paths = [
                self.data_root / "processed" / str(case_id) / "audit" / "case_audit.json"
                for case_id in case_ids
            ]

        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise RuntimeError("Missing Stage 2 audit file(s): " + "; ".join(missing))
        if not paths:
            raise RuntimeError("No Stage 2 case_audit.json files were found.")
        return paths

    def _rows_from_audit(self, audit_path: Path) -> list[dict[str, Any]]:
        with audit_path.open("r", encoding="utf-8") as file:
            audit = json.load(file)

        case_id = int(audit["case_id"])
        label_map = self._labels_by_occupant(audit.get("research_labels", {}))
        pairs = audit.get("physics_readiness", {}).get("occupant_vehicle_pairs", [])
        rows: list[dict[str, Any]] = []

        for pair in pairs:
            inputs = pair.get("inputs", {})
            crash = inputs.get("crash_mechanics", {})
            occupant = inputs.get("occupant", {})
            restraint = inputs.get("restraint_system", {})
            vehicle = inputs.get("vehicle", {})
            occupant_id = pair.get("occupant_entity_id")
            vehicle_id = pair.get("vehicle_entity_id")

            if not occupant_id or not vehicle_id:
                continue

            age = occupant.get("age", {})
            labels = label_map.get(occupant_id, {})
            rows.append({
                "case_id": case_id,
                "occupant_id": occupant_id,
                "vehicle_id": vehicle_id,
                "vehicle_number": self._entity_number(vehicle_id, "V"),
                "occupant_number": self._entity_number(occupant_id, "O"),
                "audit_status": audit.get("status"),
                "physics_readiness_level": pair.get("readiness_level"),
                "stage4_parameter_construction_eligible": pair.get("capabilities", {}).get("stage4_parameter_construction"),
                "simplified_occupant_model_eligible": pair.get("capabilities", {}).get("simplified_occupant_model"),
                "delta_v_raw": crash.get("delta_v", {}).get("value"),
                "delta_v_unit": crash.get("delta_v", {}).get("unit"),
                "delta_v_status": crash.get("delta_v", {}).get("status"),
                "delta_v_source_variable": crash.get("delta_v", {}).get("source_variable"),
                "pdof_raw": crash.get("pdof", {}).get("value"),
                "pdof_unit": crash.get("pdof", {}).get("unit"),
                "pdof_status": crash.get("pdof", {}).get("status"),
                "pdof_source_variable": crash.get("pdof", {}).get("source_variable"),
                "crash_pulse_status": crash.get("crash_pulse", {}).get("status"),
                "crash_pulse_candidate_available": crash.get("crash_pulse", {}).get("candidate_available"),
                "crash_pulse_unit_validation_required": crash.get("crash_pulse", {}).get("unit_validation_required"),
                "age_raw": age.get("raw_value"),
                "age_years": self._confirmed_age_years(age),
                "age_status": age.get("status"),
                "age_transformation": self._as_json(age.get("transformation")),
                "height_raw": occupant.get("height", {}).get("value"),
                "height_unit": occupant.get("height", {}).get("unit"),
                "height_status": occupant.get("height", {}).get("status"),
                "weight_raw": occupant.get("weight", {}).get("value"),
                "weight_unit": occupant.get("weight", {}).get("unit"),
                "weight_status": occupant.get("weight", {}).get("status"),
                "seat_position_raw": occupant.get("seat_position", {}).get("value"),
                "seat_position_text": occupant.get("seat_position", {}).get("text"),
                "belt_use_raw": restraint.get("belt_use", {}).get("value"),
                "belt_use_text": restraint.get("belt_use", {}).get("text"),
                "airbag_raw": restraint.get("airbag", {}).get("value"),
                "airbag_text": restraint.get("airbag", {}).get("text"),
                "vehicle_model_year": vehicle.get("model_year", {}).get("value"),
                "vehicle_curb_weight_kg": vehicle.get("curb_weight", {}).get("value"),
                "reported_injury_count": labels.get("reported_injury_count"),
                "mais": labels.get("maximum_ais"),
                "injury_label_training_usable": labels.get("training_usable"),
                "physics_blocking_reasons": self._as_json(pair.get("blocking_reasons", [])),
                "source_audit_file": str(audit_path),
                "standardization_version": SCHEMA_VERSION,
            })
        return rows

    @staticmethod
    def _labels_by_occupant(research_labels: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for label in research_labels.get("labels", []):
            if label.get("entity_type") != "occupant":
                continue
            entity_id = label.get("entity_id")
            if not entity_id:
                continue
            entry = result.setdefault(entity_id, {"training_usable": False})
            if label.get("training_usable"):
                entry["training_usable"] = True
            if label.get("validity") == "available" and label.get("training_usable"):
                canonical_name = label.get("canonical_name")
                if canonical_name in {"reported_injury_count", "maximum_ais"}:
                    entry[canonical_name] = label.get("training_value")
        return result

    @staticmethod
    def _confirmed_age_years(age: dict[str, Any]) -> float | None:
        """Return only an audit-confirmed age candidate; never impute."""
        candidate = age.get("canonical_candidate")
        if candidate is None:
            return None
        if age.get("status") in {"observed", "requires_standardization", "reconciled"}:
            return float(candidate)
        return None

    @staticmethod
    def _entity_number(entity_id: str, prefix: str) -> int | None:
        for token in reversed(entity_id.split("-")):
            if token.startswith(prefix) and token[1:].isdigit():
                return int(token[1:])
        return None

    @staticmethod
    def _as_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, default=str)

    @staticmethod
    def _validate_rows(rows: list[dict[str, Any]]) -> None:
        if not rows:
            raise RuntimeError("No occupant--vehicle rows were found in the selected audits.")
        identifiers = [row["occupant_id"] for row in rows]
        duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
        if duplicates:
            raise RuntimeError("Duplicate occupant identifiers found: " + ", ".join(duplicates))

    @staticmethod
    def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
        try:
            import pandas as pd
        except ImportError as error:
            raise RuntimeError("Install pandas to create the Stage 3 table.") from error

        try:
            import pyarrow  # noqa: F401
        except ImportError as error:
            raise RuntimeError(
                "Parquet support is missing. Install it with: uv pip install pyarrow"
            ) from error

        frame = pd.DataFrame(rows).sort_values(["case_id", "vehicle_number", "occupant_number"])
        frame.to_parquet(path, index=False, engine="pyarrow")

    @staticmethod
    def _write_metadata(rows: list[dict[str, Any]], audit_paths: list[Path], path: Path) -> None:
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_name": "occupant_vehicle_index",
            "unit_of_analysis": "one audited occupant--vehicle pair",
            "row_count": len(rows),
            "case_count": len({row["case_id"] for row in rows}),
            "primary_key": "occupant_id",
            "source_audit_files": [str(item) for item in audit_paths],
            "standardization_policy": {
                "raw_values_preserved": True,
                "missing_values_imputed": False,
                "age_years_rule": "Only audit-confirmed canonical age candidates are standardized.",
                "unit_conversion_rule": "Units are preserved unless a later approved conversion rule is added.",
            },
            "columns": list(rows[0].keys()),
        }
        path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
