# """
# Build the Stage 3 standardized CISS vehicle--event index.

# One row represents one audited vehicle involved in one crash event.
# The table is a provenance-preserving canonical dataset. It is not yet
# the ML training table: Delta-V and PDOF targets are retained here but
# must be excluded from the corresponding model input features.
# """

# from __future__ import annotations

# import json
# from dataclasses import dataclass
# from datetime import datetime, timezone
# from pathlib import Path
# from typing import Any, Iterable


# SCHEMA_VERSION = "1.2"


# @dataclass(frozen=True)
# class OutputPaths:
#     """Locations of the vehicle--event output artifacts."""

#     parquet: Path
#     metadata: Path


# class VehicleEventIndexBuilder:
#     """Build one canonical row per audited CISS vehicle--event."""

#     def __init__(self, data_root: str | Path = "data") -> None:
#         self.data_root = Path(data_root)

#     def build(
#         self,
#         case_ids: Iterable[int] | None = None,
#         output_directory: str | Path | None = None,
#     ) -> OutputPaths:
#         """Build the vehicle--event Parquet table from Stage 2 audit files."""
#         audit_paths = self._resolve_audit_paths(case_ids)

#         rows = [
#             row
#             for audit_path in audit_paths
#             for row in self._rows_from_audit(audit_path)
#         ]

#         self._validate_rows(rows)

#         output_dir = Path(
#             output_directory
#             or self.data_root / "processed" / "linked_tables"
#         )
#         output_dir.mkdir(parents=True, exist_ok=True)

#         paths = OutputPaths(
#             parquet=output_dir / "vehicle_event_index.parquet",
#             metadata=output_dir / "vehicle_event_index_metadata.json",
#         )

#         self._write_parquet(rows, paths.parquet)
#         self._write_metadata(rows, audit_paths, paths.metadata)

#         return paths

#     def _resolve_audit_paths(
#         self,
#         case_ids: Iterable[int] | None,
#     ) -> list[Path]:
#         """Resolve requested case audit files."""
#         if case_ids is None:
#             paths = sorted(
#                 (self.data_root / "processed").glob(
#                     "*/audit/case_audit.json"
#                 )
#             )
#         else:
#             paths = [
#                 self.data_root
#                 / "processed"
#                 / str(case_id)
#                 / "audit"
#                 / "case_audit.json"
#                 for case_id in case_ids
#             ]

#         missing = [
#             str(path)
#             for path in paths
#             if not path.is_file()
#         ]

#         if missing:
#             raise RuntimeError(
#                 "Missing Stage 2 audit file(s): "
#                 + "; ".join(missing)
#             )

#         if not paths:
#             raise RuntimeError(
#                 "No Stage 2 case_audit.json files were found."
#             )

#         return paths

#     def _rows_from_audit(
#         self,
#         audit_path: Path,
#     ) -> list[dict[str, Any]]:
#         """Create canonical vehicle--event rows from one audit file."""
#         with audit_path.open("r", encoding="utf-8") as file:
#             audit = json.load(file)

#         case_id = int(audit["case_id"])

#         reconstruction_entities = (
#             audit.get("crash_mechanics_sources", {})
#             .get("reconstruction", {})
#             .get("entities", [])
#         )

#         edr_observations = (
#             audit.get("crash_mechanics_sources", {})
#             .get("edr", {})
#             .get("applicable_event_observations", [])
#         )

#         pdof_labels = self._pdof_labels_by_vehicle(
#             audit.get("research_labels", {})
#         )

#         collision_context_by_vehicle_event = (
#             self._collision_context_by_vehicle_event(
#                 audit.get("collision_context", {})
#             )
#         )

#         reconstruction_by_vehicle_event = {
#             (
#                 int(entity["vehicle_number"]),
#                 int(entity["event_number"]),
#             ): entity
#             for entity in reconstruction_entities
#             if entity.get("vehicle_number") is not None
#             and entity.get("event_number") is not None
#         }

#         # Collision context is the canonical base.
#         # This retains events even when Delta-V and EDR are unavailable.
#         event_keys = set(collision_context_by_vehicle_event)
#         event_keys.update(reconstruction_by_vehicle_event)

#         # Retain an applicable EDR-only event if it has no collision-context row.
#         for edr in edr_observations:
#             vehicle_number = edr.get("vehicle_number")
#             event_number = edr.get("edr_event_number")

#             if vehicle_number is not None and event_number is not None:
#                 event_keys.add(
#                     (
#                         int(vehicle_number),
#                         int(event_number),
#                     )
#                 )

#         rows: list[dict[str, Any]] = []

#         for vehicle_number, event_number in sorted(event_keys):
#             reconstruction = reconstruction_by_vehicle_event.get(
#                 (
#                     vehicle_number,
#                     event_number,
#                 )
#             )

#             selected_observation = (
#                 reconstruction.get("selected_observation", {})
#                 if reconstruction
#                 else {}
#             )

#             applicable_edr_event = self._find_edr_event(
#                 edr_observations,
#                 vehicle_number,
#                 event_number,
#             )

#             # Prefer a reconstruction observation when it exists.
#             # Otherwise keep EDR evidence, or an empty record.
#             # Never create or infer a Delta-V value.
#             delta_v_observation = (
#                 selected_observation
#                 or applicable_edr_event
#                 or {}
#             )

#             delta_v_source = (
#                 selected_observation.get("source")
#                 if selected_observation
#                 else (
#                     "EDREVENT"
#                     if applicable_edr_event
#                     else None
#                 )
#             )

#             rows.append(
#                 self._build_row(
#                     audit=audit,
#                     audit_path=audit_path,
#                     case_id=case_id,
#                     vehicle_number=vehicle_number,
#                     event_number=event_number,
#                     delta_v_observation=delta_v_observation,
#                     delta_v_source=delta_v_source,
#                     delta_v_internally_consistent=(
#                         reconstruction.get("internally_consistent")
#                         if reconstruction
#                         else None
#                     ),
#                     collision_context=(
#                         collision_context_by_vehicle_event.get(
#                             (
#                                 vehicle_number,
#                                 event_number,
#                             )
#                         )
#                     ),
#                     pdof_label=pdof_labels.get(
#                         (
#                             vehicle_number,
#                             event_number,
#                         )
#                     ),
#                     applicable_edr_event=applicable_edr_event,
#                 )
#             )

#         return rows

#     def _build_row(
#         self,
#         *,
#         audit: dict[str, Any],
#         audit_path: Path,
#         case_id: int,
#         vehicle_number: int,
#         event_number: int,
#         delta_v_observation: dict[str, Any],
#         delta_v_source: str | None,
#         delta_v_internally_consistent: bool | None,
#         pdof_label: dict[str, Any] | None,
#         applicable_edr_event: dict[str, Any] | None,
#         collision_context: dict[str, Any] | None,
#     ) -> dict[str, Any]:
#         """Build one fully provenance-preserving vehicle-event record."""
#         vehicle_id = f"{case_id}-V{vehicle_number}"
#         vehicle_event_id = (
#             f"{case_id}-V{vehicle_number}-E{event_number}"
#         )

#         assets = audit.get("asset_inventory", {})
#         asset_types = assets.get("assets_by_type", {})

#         physics_readiness = audit.get("physics_readiness", {})
#         pulse_status = self._pulse_status_for_vehicle(
#             physics_readiness,
#             vehicle_id,
#         )

#         total_delta_v = delta_v_observation.get("total_delta_v")
#         longitudinal_delta_v = delta_v_observation.get(
#             "longitudinal_delta_v"
#         )
#         lateral_delta_v = delta_v_observation.get(
#             "lateral_delta_v"
#         )
#         delta_v_scope = self._delta_v_scope(
#             delta_v_source
#         )

#         warning_count = len(
#             audit.get(
#                 "audit_summary",
#                 {},
#             ).get(
#                 "warnings",
#                 [],
#             )
#         )

#         contradiction_count = audit.get(
#             "cross_source_contradictions",
#             {},
#         ).get(
#             "contradiction_count",
#             0,
#         )

#         case_event_count = audit.get(
#             "entities",
#             {},
#         ).get(
#             "crash_events",
#         )
#         pdof_value = None
#         pdof_unit = None
#         pdof_source_variable = None
#         pdof_training_usable = False
#         pdof_exclusion_reason = "no_audited_pdof_label"

#         if pdof_label is not None:
#             pdof_value = pdof_label.get("training_value")
#             pdof_unit = pdof_label.get("unit")
#             pdof_source_variable = pdof_label.get(
#                 "source_variable"
#             )
#             pdof_training_usable = bool(
#                 pdof_label.get("training_usable")
#             )
#             pdof_exclusion_reason = pdof_label.get(
#                 "exclusion_reason"
#             )

#         return {
#             # Identity and provenance
#             "case_id": case_id,
#             "vehicle_id": vehicle_id,
#             "vehicle_number": vehicle_number,
#             "event_number": event_number,
#             "vehicle_event_id": vehicle_event_id,
#             "audit_status": audit.get("status"),
#             "source_audit_file": str(audit_path),
#             "standardization_version": SCHEMA_VERSION,

#             # Delta-V target records
#             "total_delta_v_kmh": total_delta_v,
#             "longitudinal_delta_v_kmh": longitudinal_delta_v,
#             "lateral_delta_v_kmh": lateral_delta_v,
#             "delta_v_unit": "km/h",
#             "delta_v_source": delta_v_source,
#             "delta_v_source_priority": self._source_priority(
#                 delta_v_source
#             ),
#             "delta_v_internal_consistency": (
#                 delta_v_internally_consistent
#             ),
#             "delta_v_training_usable": self._delta_v_is_usable(
#                 total_delta_v,
#                 longitudinal_delta_v,
#                 lateral_delta_v,
#             ),

#             "delta_v_exclusion_reason": self._delta_v_exclusion_reason(
#                 total_delta_v,
#                 longitudinal_delta_v,
#                 lateral_delta_v,
#             ),
#             "delta_v_scope": delta_v_scope,
#             "delta_v_event_linked": (
#                 delta_v_scope == "event_specific"
#             ),

#             # PDOF target record
#             "pdof_degrees": pdof_value,
#             "pdof_unit": pdof_unit,
#             "pdof_source_variable": pdof_source_variable,
#             "pdof_training_usable": pdof_training_usable,
#             "pdof_exclusion_reason": pdof_exclusion_reason,
#             "pdof_event_linked": pdof_label is not None,
#             # Collision configuration and partner evidence.
#             "case_vehicle_count": (
#                 audit.get(
#                     "collision_context",
#                     {},
#                 ).get("case_vehicle_count")
#             ),
#             "case_crash_event_count": case_event_count,
#             "is_multi_vehicle_case": (
#                 (
#                     audit.get(
#                         "collision_context",
#                         {},
#                     ).get(
#                         "case_vehicle_count",
#                     )
#                     or 0
#                 )
#                 > 1
#             ),
#             "is_multi_event_case": bool(
#                 case_event_count
#                 and case_event_count > 1
#             ),
#             "event_sequence_position": event_number,
#             "prior_event_count": max(
#                 event_number - 1,
#                 0,
#             ),
#             "crash_configuration_code": (
#                 audit.get(
#                     "collision_context",
#                     {},
#                 ).get("crash_configuration_code")
#             ),
#             "crash_configuration_text": (
#                 audit.get(
#                     "collision_context",
#                     {},
#                 ).get("crash_configuration_text")
#             ),
#             "collision_partner_class": (
#                 collision_context.get(
#                     "collision_partner_class"
#                 )
#                 if collision_context
#                 else "unknown"
#             ),
#             "collision_partner_vehicle_number": (
#                 collision_context.get(
#                     "collision_partner_vehicle_number"
#                 )
#                 if collision_context
#                 else None
#             ),
#             "collision_partner_raw_code": (
#                 collision_context.get(
#                     "collision_partner_raw_code"
#                 )
#                 if collision_context
#                 else None
#             ),
#             "collision_partner_text": (
#                 collision_context.get(
#                     "collision_partner_text"
#                 )
#                 if collision_context
#                 else None
#             ),
#             "collision_context_source": (
#                 collision_context.get(
#                     "collision_context_source"
#                 )
#                 if collision_context
#                 else None
#             ),
#             "collision_context_status": (
#                 collision_context.get(
#                     "collision_context_status"
#                 )
#                 if collision_context
#                 else "not_audited"
#             ),
#             "event_focal_damage_area": (
#                 collision_context.get(
#                     "event_focal_damage_area"
#                 )
#                 if collision_context
#                 else None
#             ),
#             "event_partner_class_text": (
#                 collision_context.get(
#                     "event_partner_class_text"
#                 )
#                 if collision_context
#                 else None
#             ),
#             "event_partner_damage_area": (
#                 collision_context.get(
#                     "event_partner_damage_area"
#                 )
#                 if collision_context
#                 else None
#             ),
#             "analysis_cohort": self._analysis_cohort(
#                 collision_context
#             ),
            
#             # EDR and crash-pulse availability
#             "edr_available": applicable_edr_event is not None,
#             "edr_event_number": (
#                 applicable_edr_event.get("edr_event_number")
#                 if applicable_edr_event
#                 else None
#             ),
#             "edr_event_description": (
#                 applicable_edr_event.get("event_description")
#                 if applicable_edr_event
#                 else None
#             ),
#             "edr_related_to_investigated_crash": (
#                 applicable_edr_event.get(
#                     "related_to_investigated_crash"
#                 )
#                 if applicable_edr_event
#                 else None
#             ),
#             "crash_pulse_status": pulse_status.get("status"),
#             "crash_pulse_candidate_available": pulse_status.get(
#                 "candidate_available"
#             ),
#             "crash_pulse_unit_validation_required": pulse_status.get(
#                 "unit_validation_required"
#             ),

#             # Evidence availability, safe to include later as features.
#             "image_count": asset_types.get("image", 0),
#             "document_count": asset_types.get("document", 0),
#             "sketch_count": asset_types.get("sketch", 0),
#             "has_vehicle_damage_images": (
#                 asset_types.get("image", 0) > 0
#             ),
#             "has_sketches": asset_types.get("sketch", 0) > 0,
#             "visual_semantics_available": False,

#             # Explicit future integration fields; remain null for now.
#             "vlm_damage_location": None,
#             "vlm_damage_severity": None,
#             "vlm_vehicle_orientation": None,
#             "vlm_intrusion_evidence": None,
#             "vlm_collision_partner_evidence": None,
#             "vlm_scene_geometry": None,
#             "vlm_semantic_version": None,
#             "audit_warning_count": warning_count,
#             "cross_source_contradiction_count": (
#                 contradiction_count
#             ),
#         }



#     @staticmethod
#     def _collision_context_by_vehicle_event(
#         collision_context: dict[str, Any],
#     ) -> dict[tuple[int, int], dict[str, Any]]:
#         """Index audited collision context by vehicle and event."""
#         indexed: dict[
#             tuple[int, int],
#             dict[str, Any],
#         ] = {}

#         for item in collision_context.get(
#             "vehicle_events",
#             [],
#         ):
#             vehicle_number = item.get("vehicle_number")
#             event_number = item.get("event_number")

#             if vehicle_number is None or event_number is None:
#                 continue

#             indexed[
#                 (int(vehicle_number), int(event_number))
#             ] = item

#         return indexed

#     @staticmethod
#     def _analysis_cohort(
#         collision_context: dict[str, Any] | None,
#     ) -> str:
#         """
#         Assign a descriptive cohort without excluding any record.

#         This is not an ML eligibility decision yet.
#         """
#         if collision_context is None:
#             return "collision_context_not_available"

#         partner_class = collision_context.get(
#             "collision_partner_class"
#         )

#         cohorts = {
#             "vehicle": "vehicle_to_vehicle",
#             "fixed_object": "vehicle_to_fixed_object",
#             "pedestrian_or_cyclist": (
#                 "vehicle_to_pedestrian_or_cyclist"
#             ),
#             "animal": "vehicle_to_animal",
#             "non_motor_vehicle": "vehicle_to_non_motor_vehicle",
#         }

#         return cohorts.get(
#             partner_class,
#             "collision_partner_unknown",
#         )


#     @staticmethod
#     def _pdof_labels_by_vehicle(
#         research_labels: dict[str, Any],
#     ) -> dict[tuple[int, int], dict[str, Any]]:
#         """Index usable PDOF labels by vehicle and event."""
#         result: dict[tuple[int, int], dict[str, Any]] = {}

#         for label in research_labels.get("labels", []):
#             if (
#                 label.get("canonical_name")
#                 != "principal_direction_of_force"
#             ):
#                 continue

#             if label.get("entity_type") != "vehicle":
#                 continue

#             vehicle_number = VehicleEventIndexBuilder._number_from_id(
#                 label.get("entity_id"),
#                 "V",
#             )

#             event_number = VehicleEventIndexBuilder._event_from_label(
#                 label
#             )

#             if vehicle_number is None or event_number is None:
#                 continue

#             key = (vehicle_number, event_number)

#             current = result.get(key)

#             if current is None or (
#                 label.get("training_usable")
#                 and not current.get("training_usable")
#             ):
#                 result[key] = label

#         return result

#     @staticmethod
#     def _event_from_label(
#         label: dict[str, Any],
#     ) -> int | None:
#         """Read EVENT<number> from a source key such as EVENT1."""
#         source_key = (
#             label.get("source", {})
#             .get("source_record_key", "")
#         )

#         if not source_key.startswith("EVENT"):
#             return None

#         suffix = source_key.replace("EVENT", "", 1)

#         return int(suffix) if suffix.isdigit() else None

#     @staticmethod
#     def _number_from_id(
#         entity_id: str | None,
#         prefix: str,
#     ) -> int | None:
#         """Extract a numeric segment such as V1 from an entity ID."""
#         if not entity_id:
#             return None

#         for token in entity_id.split("-"):
#             if token.startswith(prefix) and token[1:].isdigit():
#                 return int(token[1:])

#         return None

#     @staticmethod
#     def _sole_pdof_label_for_vehicle(
#         pdof_labels: dict[tuple[int, int], dict[str, Any]],
#         vehicle_number: int,
#     ) -> dict[str, Any] | None:
#         """Use PDOF only when one unambiguous label exists for the vehicle."""
#         matches = [
#             label
#             for (vehicle, _event), label in pdof_labels.items()
#             if vehicle == vehicle_number
#         ]

#         return matches[0] if len(matches) == 1 else None

#     @staticmethod
#     def _find_edr_event(
#         edr_observations: list[dict[str, Any]],
#         vehicle_number: int,
#         event_number: int,
#     ) -> dict[str, Any] | None:
#         """Find one applicable EDR record for this vehicle and event."""
#         for observation in edr_observations:
#             if (
#                 observation.get("vehicle_number") == vehicle_number
#                 and observation.get("edr_event_number")
#                 == event_number
#             ):
#                 return observation

#         return None

#     @staticmethod
#     def _pulse_status_for_vehicle(
#         physics_readiness: dict[str, Any],
#         vehicle_id: str,
#     ) -> dict[str, Any]:
#         """Read the audit's pulse readiness record without interpreting it."""
#         for pair in physics_readiness.get(
#             "occupant_vehicle_pairs",
#             [],
#         ):
#             if pair.get("vehicle_entity_id") != vehicle_id:
#                 continue

#             crash_mechanics = (
#                 pair.get("inputs", {})
#                 .get("crash_mechanics", {})
#             )

#             crash_pulse = crash_mechanics.get(
#                 "crash_pulse",
#                 {},
#             )

#             if crash_pulse:
#                 return crash_pulse

#         return {
#             "status": "not_available",
#             "candidate_available": False,
#             "unit_validation_required": False,
#         }

#     @staticmethod
#     def _source_priority(
#         source: str | None,
#     ) -> int | None:
#         """Record source hierarchy without modifying any source values."""
#         priorities = {
#             "EDREVENT": 1,
#             "CDC": 2,
#             "GV": 3,
#         }

#         return priorities.get(source)
#     @staticmethod
#     def _delta_v_scope(
#         source: str | None,
#     ) -> str:
#         """
#         State whether the selected Delta-V source
#         is specifically linked to one collision event.
#         """
#         if source in {
#             "CDC",
#             "EDREVENT",
#         }:
#             return "event_specific"

#         if source == "GV":
#             return "vehicle_total"

#         return "unavailable_or_unresolved"
#     @staticmethod
#     def _delta_v_is_usable(
#         total_delta_v: Any,
#         longitudinal_delta_v: Any,
#         lateral_delta_v: Any,
#     ) -> bool:
#         """A row is useful when at least one audited Delta-V value exists."""
#         return any(
#             value is not None
#             for value in (
#                 total_delta_v,
#                 longitudinal_delta_v,
#                 lateral_delta_v,
#             )
#         )

#     @staticmethod
#     def _delta_v_exclusion_reason(
#         total_delta_v: Any,
#         longitudinal_delta_v: Any,
#         lateral_delta_v: Any,
#     ) -> str | None:
#         """Explain unavailable Delta-V instead of imputing it."""
#         if VehicleEventIndexBuilder._delta_v_is_usable(
#             total_delta_v,
#             longitudinal_delta_v,
#             lateral_delta_v,
#         ):
#             return None

#         return "no_audited_delta_v_value"

#     @staticmethod
#     def _validate_rows(
#         rows: list[dict[str, Any]],
#     ) -> None:
#         """Validate the canonical primary key."""
#         if not rows:
#             raise RuntimeError(
#                 "No vehicle--event rows were found in selected audits."
#             )

#         identifiers = [
#             row["vehicle_event_id"]
#             for row in rows
#         ]

#         duplicates = sorted(
#             {
#                 identifier
#                 for identifier in identifiers
#                 if identifiers.count(identifier) > 1
#             }
#         )

#         if duplicates:
#             raise RuntimeError(
#                 "Duplicate vehicle-event IDs found: "
#                 + ", ".join(duplicates)
#             )

#     @staticmethod
#     def _write_parquet(
#         rows: list[dict[str, Any]],
#         path: Path,
#     ) -> None:
#         """Write the canonical index as Parquet."""
#         try:
#             import pandas as pd
#             import pyarrow  # noqa: F401
#         except ImportError as error:
#             raise RuntimeError(
#                 "Parquet support is missing. Run: "
#                 "uv pip install pandas pyarrow"
#             ) from error

#         frame = (
#             pd.DataFrame(rows)
#             .sort_values(
#                 ["case_id", "vehicle_number", "event_number"]
#             )
#             .reset_index(drop=True)
#         )

#         frame.to_parquet(
#             path,
#             index=False,
#             engine="pyarrow",
#         )
#     @staticmethod
#     def _canonical_coverage(
#         rows: list[dict[str, Any]],
#     ) -> dict[str, Any]:
#         """
#         Summarize canonical event coverage and initial
#         leakage-safe baseline-model eligibility.
#         """
#         partner_classes = [
#             row.get(
#                 "collision_partner_class",
#                 "unknown",
#             )
#             or "unknown"
#             for row in rows
#         ]

#         unique_case_ids = sorted(
#             {
#                 row["case_id"]
#                 for row in rows
#             }
#         )

#         multi_vehicle_case_ids = sorted(
#             {
#                 row["case_id"]
#                 for row in rows
#                 if row.get("is_multi_vehicle_case")
#             }
#         )

#         multi_event_case_ids = sorted(
#             {
#                 row["case_id"]
#                 for row in rows
#                 if row.get("is_multi_event_case")
#             }
#         )

#         vehicle_to_vehicle_rows = [
#             row
#             for row in rows
#             if row.get("collision_partner_class")
#             == "vehicle"
#         ]

#         fixed_object_rows = [
#             row
#             for row in rows
#             if row.get("collision_partner_class")
#             == "fixed_object"
#         ]

#         unknown_partner_rows = [
#             row
#             for row in rows
#             if row.get("collision_partner_class")
#             in {
#                 None,
#                 "unknown",
#             }
#         ]

#         event_linked_delta_v_rows = [
#             row
#             for row in rows
#             if row.get("delta_v_training_usable")
#             and row.get("delta_v_event_linked")
#         ]

#         event_linked_pdof_rows = [
#             row
#             for row in rows
#             if row.get("pdof_training_usable")
#             and row.get("pdof_event_linked")
#         ]

#         rows_with_both_targets = [
#             row
#             for row in rows
#             if row.get("delta_v_training_usable")
#             and row.get("delta_v_event_linked")
#             and row.get("pdof_training_usable")
#             and row.get("pdof_event_linked")
#         ]

#         initial_baseline_rows = [
#             row
#             for row in rows
#             if row.get("collision_partner_class")
#             == "vehicle"
#             and not row.get("is_multi_event_case")
#             and row.get("delta_v_training_usable")
#             and row.get("delta_v_event_linked")
#             and row.get("pdof_training_usable")
#             and row.get("pdof_event_linked")
#             and row.get(
#                 "cross_source_contradiction_count",
#                 0,
#             ) == 0
#         ]

#         return {
#             "canonical_case_count": len(
#                 unique_case_ids
#             ),
#             "canonical_vehicle_event_count": len(
#                 rows
#             ),
#             "cases_with_more_than_one_vehicle": len(
#                 multi_vehicle_case_ids
#             ),
#             "multi_vehicle_case_ids": multi_vehicle_case_ids,
#             "cases_with_multiple_events": len(
#                 multi_event_case_ids
#             ),
#             "multi_event_case_ids": multi_event_case_ids,
#             "collision_partner_event_counts": {
#                 "vehicle": len(vehicle_to_vehicle_rows),
#                 "fixed_object": len(fixed_object_rows),
#                 "unknown": len(unknown_partner_rows),
#             },
#             "event_linked_target_availability": {
#                 "delta_v": len(
#                     event_linked_delta_v_rows
#                 ),
#                 "pdof": len(
#                     event_linked_pdof_rows
#                 ),
#                 "delta_v_and_pdof": len(
#                     rows_with_both_targets
#                 ),
#             },
#             "initial_baseline_candidate_count": len(
#                 initial_baseline_rows
#             ),
#             "initial_baseline_definition": (
#                 "vehicle-to-vehicle, not a multi-event "
#                 "case, event-linked usable Delta-V, "
#                 "event-linked usable PDOF, and no "
#                 "cross-source contradiction"
#             ),
#         }
#     @staticmethod
#     def _write_metadata(
#         rows: list[dict[str, Any]],
#         audit_paths: list[Path],
#         path: Path,
#     ) -> None:
#         """Write schema, provenance, and target availability summary."""
#         metadata = {
#             "schema_version": SCHEMA_VERSION,
#             "created_at": datetime.now(timezone.utc).isoformat(),
#             "table_name": "vehicle_event_index",
#             "unit_of_analysis": (
#                 "one audited CISS vehicle involved in one crash event"
#             ),
#             "row_count": len(rows),
#             "case_count": len(
#                 {
#                     row["case_id"]
#                     for row in rows
#                 }
#             ),
#             "primary_key": "vehicle_event_id",
#             "source_audit_files": [
#                 str(audit_path)
#                 for audit_path in audit_paths
#             ],
#             "canonical_coverage": (
#                 VehicleEventIndexBuilder._canonical_coverage(
#                     rows
#                 )
#             ),
#             "target_availability": {
#                 "rows_with_any_delta_v": sum(
#                     bool(row["delta_v_training_usable"])
#                     for row in rows
#                 ),
#                 "rows_with_total_delta_v": sum(
#                     row["total_delta_v_kmh"] is not None
#                     for row in rows
#                 ),
#                 "rows_with_pdof": sum(
#                     bool(row["pdof_training_usable"])
#                     for row in rows
#                 ),
#             },
#             "standardization_policy": {
#                 "raw_values_preserved": True,
#                 "missing_values_imputed": False,
#                 "target_fields_are_not_model_inputs": True,
#                 "edr_priority_note": (
#                     "Applicable EDR records are retained, but total "
#                     "Delta-V and crash-pulse duration are not inferred "
#                     "when unavailable or unvalidated."
#                 ),
#                 "visual_features_note": (
#                     "Only evidence availability is included now. "
#                     "VLM semantic fields remain null until validated "
#                     "semantic extraction is integrated."
#                 ),
#             },
#             "columns": list(rows[0].keys()),
#         }

#         path.write_text(
#             json.dumps(metadata, indent=2),
#             encoding="utf-8",
#         )