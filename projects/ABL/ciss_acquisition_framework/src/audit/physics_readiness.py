"""Evaluate physics-input readiness for CISS vehicle-occupant pairs."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.audit.audit_rules import PHYSICS_READINESS_REGISTRY_VERSION


class PhysicsReadinessBuilder:
    """Describe supported physics capabilities without running simulations."""

    def build(
        self,
        case_id: int,
        sheets: dict[str, dict[str, Any]],
        entity_registry: dict[str, Any],
        research_labels: dict[str, Any],
        occupant_age_audit: dict[str, Any],
        edr_audit: dict[str, Any],
    ) -> dict[str, Any]:
        """Return readiness metadata for every registered occupant."""

        case_id = int(case_id)
        labels = research_labels.get("labels", [])
        usable_labels = [
            item
            for item in labels
            if isinstance(item, dict) and item.get("training_usable")
        ]
        age_index = self._age_index(occupant_age_audit)
        occupant_records = self._record_index(sheets, "OCC", ("VEHNO", "OCCNO"))
        vehicle_records = self._record_index(sheets, "GV", ("VEHNO",))
        seat_records = self._record_index(sheets, "SEAT", ("VEHNO", "SEATLOC"))
        registered_ids = {
            item.get("entity_id")
            for item in entity_registry.get("entities", [])
            if isinstance(item, dict)
        }

        pairs: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        occupants = [
            item
            for item in entity_registry.get("entities", [])
            if isinstance(item, dict) and item.get("entity_type") == "occupant"
        ]

        for occupant in occupants:
            entity_id = occupant.get("entity_id")
            natural_key = occupant.get("natural_key", {})
            vehicle_number = self._positive_int(natural_key.get("VEHNO"))
            occupant_number = self._positive_int(natural_key.get("OCCNO"))
            vehicle_id = f"{case_id}-V{vehicle_number}" if vehicle_number else None

            if (
                not entity_id
                or vehicle_number is None
                or occupant_number is None
                or vehicle_id not in registered_ids
            ):
                unresolved.append(
                    {
                        "occupant_entity_id": entity_id,
                        "reason": "occupant_or_parent_vehicle_not_resolved",
                    }
                )
                continue

            occ = occupant_records.get((vehicle_number, occupant_number), {})
            vehicle = vehicle_records.get((vehicle_number,), {})
            seat_location = self._positive_int(occ.get("SEATLOC"))
            seat = seat_records.get((vehicle_number, seat_location), {})

            delta_v = self._preferred_label(
                usable_labels,
                vehicle_id=vehicle_id,
                source_priority=(
                    "EDREVENT.MAXDVLONG",
                    "CDC.DVTOTAL",
                    "GV.DVTOTAL",
                ),
            )
            pdof = self._preferred_label(
                usable_labels,
                vehicle_id=vehicle_id,
                source_priority=("CDC.PDOF",),
            )

            age = self._age_input(
                age_index.get((vehicle_number, occupant_number))
            )
            height = self._numeric_input(
                occ.get("HEIGHT"),
                sentinel_values={999},
                unit="cm",
                missing_assumption="occupant_height_distribution",
            )
            weight = self._numeric_input(
                occ.get("WEIGHT"),
                sentinel_values={999},
                unit="kg",
                missing_assumption="occupant_mass_distribution",
            )
            seat_position = self._coded_input(
                occ.get("SEATLOC"),
                occ.get("SEATLOCTEXT"),
                source="OCC.SEATLOC",
            )
            belt_use = self._coded_input(
                occ.get("BELTUSE"),
                occ.get("BELTUSETEXT"),
                source="OCC.BELTUSE",
            )
            airbag = self._coded_input(
                occ.get("PARAIRBAG"),
                occ.get("PARAIRBAGTEXT"),
                source="OCC.PARAIRBAG",
            )
            model_year = self._numeric_input(
                vehicle.get("MODELYR"),
                sentinel_values={9999},
                unit="year",
            )
            curb_weight = self._numeric_input(
                vehicle.get("CURBWT"),
                sentinel_values={9999, 99999},
                unit="kg",
                missing_assumption="vehicle_mass_distribution",
            )

            belt_inspection = self._coded_input(
                seat.get("BELTUSEINSP"),
                seat.get("BELTUSEINSPTEXT"),
                source="SEAT.BELTUSEINSP",
            )
            pretensioner = self._coded_input(
                seat.get("BELTPRETENSIONINSP"),
                seat.get("BELTPRETENSIONINSPTEXT"),
                source="SEAT.BELTPRETENSIONINSP",
            )

            pulse_candidate = bool(edr_audit.get("pulse_candidate_available"))
            pulse_ready = bool(edr_audit.get("pulse_ready_for_simulation"))
            unit_validation_required = bool(
                edr_audit.get("unit_validation_required")
            )
            pulse = {
                "status": (
                    "observed_requires_unit_validation"
                    if pulse_candidate and unit_validation_required
                    else "observed"
                    if pulse_ready
                    else "unavailable"
                ),
                "candidate_available": pulse_candidate,
                "unit_validation_required": unit_validation_required,
                "simulation_ready": pulse_ready,
                "applicable_event_number": edr_audit.get(
                    "applicable_event_number"
                ),
            }
            pulse_duration = self._pulse_duration_input(edr_audit)

            delta_v_available = delta_v is not None
            pdof_available = pdof is not None
            parameter_ready = delta_v_available and pdof_available
            anthropometry_usable = age["status"] in {
                "observed",
                "requires_standardization",
            }
            restraint_observed = belt_use["status"] == "observed"
            seat_observed = seat_position["status"] == "observed"

            analytical_ready = (
                parameter_ready
                and anthropometry_usable
                and restraint_observed
                and seat_observed
            )
            requires_uncertainty = analytical_ready and any(
                item["status"] == "requires_distribution"
                for item in (height, weight, curb_weight, pulse_duration)
            )

            capabilities = {
                "delta_v_modeling": delta_v_available,
                "pdof_modeling": pdof_available,
                "stage4_parameter_construction": parameter_ready,
                "simplified_occupant_model": analytical_ready,
                "simplified_model_requires_uncertainty": requires_uncertainty,
                "pulse_based_occupant_model": pulse_ready and analytical_ready,
                "crash_pulse_duration_derivable": (
                    pulse_duration["status"] == "derivable_after_validation"
                ),
                "crash_pulse_duration_model_input_ready": (
                    pulse_duration["status"] == "derived"
                ),
                "multibody_simulation": False,
                "finite_element_simulation": False,
            }

            blockers: list[str] = []
            if not delta_v_available:
                blockers.append("usable_delta_v_unavailable")
            if not pdof_available:
                blockers.append("usable_pdof_unavailable")
            if not pulse_candidate:
                blockers.append("crash_pulse_unavailable")
            elif unit_validation_required:
                blockers.append("crash_pulse_unit_not_validated")
            if pulse_duration["status"] == "derivable_after_validation":
                blockers.extend(
                    [
                        "crash_pulse_time_unit_not_validated",
                        "crash_pulse_boundary_method_not_defined",
                    ]
                )
            elif pulse_duration["status"] == "requires_distribution":
                blockers.extend(
                    [
                        "crash_pulse_duration_requires_distribution",
                        "crash_pulse_shape_requires_distribution",
                    ]
                )
            if weight["status"] != "observed":
                blockers.append("occupant_mass_requires_distribution")
            if height["status"] != "observed":
                blockers.append("occupant_height_requires_distribution")
            blockers.extend(
                [
                    "seat_stiffness_requires_external_model_or_distribution",
                    "seat_damping_requires_external_model_or_distribution",
                    "belt_stiffness_and_slack_require_external_model_or_distribution",
                ]
            )

            if capabilities["pulse_based_occupant_model"]:
                readiness_level = "simulation_ready_with_uncertainty"
            elif analytical_ready:
                readiness_level = "analytical_ready_with_assumptions"
            elif parameter_ready:
                readiness_level = "parameter_ready"
            else:
                readiness_level = "not_ready"

            pairs.append(
                {
                    "occupant_entity_id": entity_id,
                    "vehicle_entity_id": vehicle_id,
                    "readiness_level": readiness_level,
                    "inputs": {
                        "crash_mechanics": {
                            "delta_v": self._label_input(delta_v),
                            "pdof": self._label_input(pdof),
                            "crash_pulse": pulse,
                            "crash_pulse_duration": pulse_duration,
                        },
                        "occupant": {
                            "age": age,
                            "height": height,
                            "weight": weight,
                            "seat_position": seat_position,
                        },
                        "restraint_system": {
                            "belt_use": belt_use,
                            "belt_inspection": belt_inspection,
                            "pretensioner": pretensioner,
                            "airbag": airbag,
                        },
                        "vehicle": {
                            "model_year": model_year,
                            "curb_weight": curb_weight,
                        },
                    },
                    "capabilities": capabilities,
                    "blocking_reasons": sorted(set(blockers)),
                    "assumption_policy": {
                        "single_arbitrary_imputation_allowed": False,
                        "parameter_distributions_required": requires_uncertainty,
                        "uncertainty_propagation_required": requires_uncertainty,
                        "pulse_duration_distribution_required": (
                            pulse_duration["status"] == "requires_distribution"
                        ),
                        "pulse_shape_distribution_required": not pulse_ready,
                    },
                }
            )

        level_counts = Counter(item["readiness_level"] for item in pairs)
        capability_counts = Counter()
        for item in pairs:
            for name, available in item["capabilities"].items():
                if available:
                    capability_counts[name] += 1

        return {
            "registry_version": PHYSICS_READINESS_REGISTRY_VERSION,
            "case_id": case_id,
            "assessment_scope": "vehicle_occupant_pairs",
            "policy": {
                "simulation_executed": False,
                "raw_values_modified": False,
                "readiness_is_not_biomechanical_validity": True,
                "uncertain_parameters_require_distributions": True,
            },
            "summary": {
                "pair_count": len(pairs),
                "readiness_levels": dict(sorted(level_counts.items())),
                "capability_pair_counts": dict(sorted(capability_counts.items())),
                "unresolved_entity_count": len(unresolved),
            },
            "occupant_vehicle_pairs": pairs,
            "unresolved_entities": unresolved,
        }

    @staticmethod
    def _record_index(
        sheets: dict[str, dict[str, Any]],
        worksheet: str,
        keys: tuple[str, ...],
    ) -> dict[tuple[Any, ...], dict[str, Any]]:
        records = sheets.get(worksheet, {}).get("records", [])
        return {
            tuple(record.get(key) for key in keys): record
            for record in records
            if isinstance(record, dict)
        }

    @staticmethod
    def _age_index(audit: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
        result = {}
        for record in audit.get("records", []):
            vehicle = PhysicsReadinessBuilder._positive_int(
                record.get("vehicle_number")
            )
            occupant = PhysicsReadinessBuilder._positive_int(
                record.get("occupant_number")
            )
            if vehicle is not None and occupant is not None:
                result[(vehicle, occupant)] = record
        return result

    @staticmethod
    def _preferred_label(
        labels: list[dict[str, Any]],
        vehicle_id: str,
        source_priority: tuple[str, ...],
    ) -> dict[str, Any] | None:
        for source in source_priority:
            candidates = [
                item
                for item in labels
                if item.get("source_variable") == source
                and (
                    item.get("entity_id") == vehicle_id
                    or str(item.get("entity_id", "")).startswith(
                        f"{vehicle_id}-EDR-"
                    )
                )
            ]
            if candidates:
                return candidates[0]
        return None

    @staticmethod
    def _label_input(label: dict[str, Any] | None) -> dict[str, Any]:
        if label is None:
            return {"status": "unavailable", "value": None}
        return {
            "status": "observed",
            "value": label.get("training_value"),
            "unit": label.get("unit"),
            "source_variable": label.get("source_variable"),
            "label_id": label.get("label_id"),
        }

    @staticmethod
    def _pulse_duration_input(edr_audit: dict[str, Any]) -> dict[str, Any]:
        """Describe whether pulse duration is observed, derivable, or assumed."""

        signal = next(
            (
                item
                for item in edr_audit.get("applicable_event_signals", [])
                if isinstance(item, dict)
                and item.get("delta_v_history")
                and item.get("signal_type") == "longitudinal_delta_v"
            ),
            None,
        )
        if signal is None:
            return {
                "status": "requires_distribution",
                "value": None,
                "unit": "second",
                "assumption": "crash_pulse_duration_distribution",
                "reason": "validated_time_indexed_crash_pulse_unavailable",
            }

        time_start = signal.get("time_min")
        time_end = signal.get("time_max")
        recorded_span = None
        if isinstance(time_start, (int, float)) and isinstance(
            time_end, (int, float)
        ):
            recorded_span = time_end - time_start

        return {
            "status": "derivable_after_validation",
            "value": None,
            "unit": "second",
            "symbol": "delta_t_pulse",
            "recorded_time_start": time_start,
            "recorded_time_end": time_end,
            "recorded_time_span": recorded_span,
            "recorded_time_unit": None,
            "candidate_duration_seconds": None,
            "recorded_span_is_physical_pulse_duration": False,
            "blocking_reasons": [
                "time_unit_not_explicitly_validated",
                "pulse_boundary_method_not_defined",
            ],
        }

    @staticmethod
    def _age_input(record: dict[str, Any] | None) -> dict[str, Any]:
        if not record:
            return {
                "status": "requires_distribution",
                "value": None,
                "unit": "year",
                "assumption": "occupant_age_distribution",
            }
        candidate = record.get("canonical_age_years_candidate")
        if candidate is None:
            return {
                "status": "requires_distribution",
                "value": None,
                "unit": "year",
                "assumption": "occupant_age_distribution",
            }
        return {
            "status": "requires_standardization",
            "raw_value": record.get("raw_excel_age"),
            "canonical_candidate": candidate,
            "unit": "year",
            "apply_in_stage": 3,
            "transformation": record.get("normalization_candidate"),
        }

    @staticmethod
    def _numeric_input(
        value: Any,
        sentinel_values: set[Any],
        unit: str,
        missing_assumption: str | None = None,
    ) -> dict[str, Any]:
        if value is None or value == "" or value in sentinel_values:
            if missing_assumption:
                return {
                    "status": "requires_distribution",
                    "value": None,
                    "unit": unit,
                    "assumption": missing_assumption,
                }
            return {"status": "unavailable", "value": None, "unit": unit}
        return {"status": "observed", "value": value, "unit": unit}

    @staticmethod
    def _coded_input(value: Any, text: Any, source: str) -> dict[str, Any]:
        normalized_text = str(text or "").strip().lower()
        unavailable = (
            value is None
            or value == ""
            or "unknown" in normalized_text
            or "not reported" in normalized_text
        )
        if unavailable:
            return {
                "status": "unavailable",
                "value": None,
                "text": text,
                "source_variable": source,
            }
        return {
            "status": "observed",
            "value": value,
            "text": text,
            "source_variable": source,
        }

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            converted = int(value)
        except (TypeError, ValueError):
            return None
        return converted if converted > 0 else None
