"""Build research supervision labels for one audited CISS case."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.audit.audit_rules import (
    NUMERIC_SENTINEL_VALUES,
    RESEARCH_LABEL_DEFINITIONS,
    RESEARCH_LABEL_REGISTRY_VERSION,
)


class ResearchLabelBuilder:
    """Register potential labels without imputing or standardizing raw data."""

    def build(
        self,
        case_id: int,
        sheets: dict[str, dict[str, Any]],
        entity_registry: dict[str, Any],
        final_label_readiness: dict[str, Any],
        edr_audit: dict[str, Any],
    ) -> dict[str, Any]:
        """Return row-level final and intermediate supervision metadata."""

        case_id = int(case_id)
        known_entities = {
            item.get("entity_id")
            for item in entity_registry.get("entities", [])
            if isinstance(item, dict)
        }
        occupant_readiness = self._occupant_readiness(final_label_readiness)
        selected_edr_event = self._selected_edr_event(edr_audit)
        labels: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        for source_variable, definition in RESEARCH_LABEL_DEFINITIONS.items():
            worksheet, column = source_variable.split(".", 1)
            for row_number, record in enumerate(
                self._records(sheets, worksheet), start=2
            ):
                if column not in record:
                    continue

                entity_id = self._entity_id(
                    case_id=case_id,
                    worksheet=worksheet,
                    record=record,
                )
                if entity_id is None or entity_id not in known_entities:
                    unresolved.append(
                        {
                            "source_variable": source_variable,
                            "worksheet_row": row_number,
                            "reason": "target_entity_not_found",
                            "expected_entity_id": entity_id,
                        }
                    )
                    continue

                raw_value = record.get(column)
                sentinel_reason = self._sentinel_reason(source_variable, raw_value)
                value_available = raw_value is not None
                role = definition["training_role"]
                validity = "available"
                exclusion_reason = None

                if not value_available:
                    validity = "missing"
                    exclusion_reason = "raw_value_missing"
                elif sentinel_reason is not None:
                    validity = "source_sentinel"
                    exclusion_reason = f"source_sentinel:{sentinel_reason}"

                if role == "final_label":
                    readiness = occupant_readiness.get(entity_id)
                    if not readiness or not readiness.get("training_eligible", False):
                        validity = "outcome_not_reliable"
                        exclusion_reason = (
                            readiness.get("exclusion_reason")
                            if readiness
                            else "occupant_label_readiness_missing"
                        )

                if worksheet == "EDREVENT":
                    event_number = self._positive_int(record.get("EDREVENTNO"))
                    vehicle_number = self._positive_int(record.get("VEHNO"))
                    event_key = (vehicle_number, event_number)
                    if selected_edr_event is None:
                        validity = "applicable_event_not_identified"
                        exclusion_reason = "applicable_edr_event_not_identified"
                    elif event_key != selected_edr_event:
                        validity = "not_applicable_event"
                        exclusion_reason = "edr_event_not_related_to_investigated_crash"

                training_usable = validity == "available"
                text_value = record.get(f"{column}TEXT")
                source_record_key = self._source_record_key(
                    worksheet=worksheet,
                    record=record,
                    row_number=row_number,
                )
                label_id = f"{entity_id}::{source_variable}::{source_record_key}"

                labels.append(
                    {
                        "label_id": label_id,
                        "entity_id": entity_id,
                        "entity_type": definition["entity_type"],
                        "source_variable": source_variable,
                        "canonical_name": definition["canonical_name"],
                        "label_family": definition["label_family"],
                        "training_role": role,
                        "raw_value": raw_value,
                        "raw_text": text_value,
                        "training_value": raw_value if training_usable else None,
                        "unit": definition["unit"],
                        "validity": validity,
                        "training_usable": training_usable,
                        "exclusion_reason": exclusion_reason,
                        "normalization_status": "not_applied_stage2",
                        "downstream_stages": list(definition["downstream_stages"]),
                        "source": {
                            "worksheet": worksheet,
                            "column": column,
                            "worksheet_row": row_number,
                            "source_record_key": source_record_key,
                        },
                    }
                )

        pulse_duration_candidate = self._pulse_duration_candidate(
            case_id=case_id,
            edr_audit=edr_audit,
            known_entities=known_entities,
        )
        if pulse_duration_candidate is not None:
            labels.append(pulse_duration_candidate)

        family_counts = Counter(item["label_family"] for item in labels)
        role_counts = Counter(item["training_role"] for item in labels)
        validity_counts = Counter(item["validity"] for item in labels)
        usable_by_role = Counter(
            item["training_role"] for item in labels if item["training_usable"]
        )

        return {
            "registry_version": RESEARCH_LABEL_REGISTRY_VERSION,
            "case_id": case_id,
            "stage2_policy": {
                "raw_values_preserved": True,
                "normalization_applied": False,
                "missing_injury_is_not_no_injury": True,
                "nonapplicable_edr_events_excluded": True,
            },
            "summary": {
                "total_label_records": len(labels),
                "training_usable_label_count": sum(
                    item["training_usable"] for item in labels
                ),
                "labels_by_family": dict(sorted(family_counts.items())),
                "labels_by_role": dict(sorted(role_counts.items())),
                "labels_by_validity": dict(sorted(validity_counts.items())),
                "training_usable_by_role": dict(sorted(usable_by_role.items())),
                "unresolved_label_count": len(unresolved),
            },
            "labels": labels,
            "unresolved_labels": unresolved,
        }

    @staticmethod
    def _pulse_duration_candidate(
        case_id: int,
        edr_audit: dict[str, Any],
        known_entities: set[Any],
    ) -> dict[str, Any] | None:
        """Register recorded pulse span without treating it as duration yet."""

        selected = edr_audit.get("event_selection", {}).get("event")
        if not isinstance(selected, dict):
            return None

        vehicle_number = ResearchLabelBuilder._positive_int(
            selected.get("vehicle_number")
        )
        event_number = ResearchLabelBuilder._positive_int(
            selected.get("edr_event_number")
        )
        if vehicle_number is None or event_number is None:
            return None

        entity_suffix = f"-E{event_number}"
        entity_prefix = f"{case_id}-V{vehicle_number}-EDR-S"
        matching_entities = sorted(
            str(entity_id)
            for entity_id in known_entities
            if str(entity_id).startswith(entity_prefix)
            and str(entity_id).endswith(entity_suffix)
        )
        if len(matching_entities) != 1:
            return None

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
            return None

        time_start = signal.get("time_min")
        time_end = signal.get("time_max")
        recorded_span = None
        if isinstance(time_start, (int, float)) and isinstance(
            time_end, (int, float)
        ):
            recorded_span = time_end - time_start

        entity_id = matching_entities[0]
        return {
            "label_id": (
                f"{entity_id}::DERIVED.CRASH_PULSE_DURATION::EDREVENT{event_number}"
            ),
            "entity_id": entity_id,
            "entity_type": "edr_event",
            "source_variable": "DERIVED.CRASH_PULSE_DURATION",
            "canonical_name": "crash_pulse_duration",
            "symbol": "delta_t_pulse",
            "label_family": "edr_crash_mechanics",
            "training_role": "intermediate_label",
            "raw_value": None,
            "raw_text": None,
            "training_value": None,
            "unit": "second",
            "validity": "derivable_after_validation",
            "training_usable": False,
            "exclusion_reason": (
                "time_unit_not_validated_and_pulse_boundary_method_not_defined"
            ),
            "normalization_status": "not_applied_stage2",
            "downstream_stages": [3, 4, 5],
            "derivation_candidate": {
                "recorded_time_start": time_start,
                "recorded_time_end": time_end,
                "recorded_time_span": recorded_span,
                "recorded_time_unit": None,
                "candidate_duration_seconds": None,
                "formula": "t_end - t_start",
                "recorded_span_is_physical_pulse_duration": False,
                "blocking_reasons": [
                    "time_unit_not_explicitly_validated",
                    "pulse_boundary_method_not_defined",
                ],
            },
            "source": {
                "worksheet": signal.get("source_table"),
                "column": "PTIME",
                "worksheet_row": None,
                "source_record_key": f"EDREVENT{event_number}",
                "signal_code": signal.get("pcode"),
                "signal_description": signal.get("description"),
            },
        }

    @staticmethod
    def _records(
        sheets: dict[str, dict[str, Any]], worksheet: str
    ) -> list[dict[str, Any]]:
        sheet = sheets.get(worksheet, {})
        records = sheet.get("records", []) if isinstance(sheet, dict) else []
        return records if isinstance(records, list) else []

    @staticmethod
    def _occupant_readiness(
        readiness: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in readiness.get("occupants", []):
            if not isinstance(item, dict):
                continue
            case_id = item.get("case_id")
            vehicle_number = item.get("vehicle_number")
            occupant_number = item.get("occupant_number")
            if None in (case_id, vehicle_number, occupant_number):
                continue
            entity_id = f"{case_id}-V{vehicle_number}-O{occupant_number}"
            result[entity_id] = item
        return result

    @staticmethod
    def _selected_edr_event(edr_audit: dict[str, Any]) -> tuple[int, int] | None:
        event = edr_audit.get("event_selection", {}).get("event")
        if not isinstance(event, dict):
            return None
        vehicle_number = ResearchLabelBuilder._positive_int(
            event.get("vehicle_number")
        )
        event_number = ResearchLabelBuilder._positive_int(
            event.get("edr_event_number")
        )
        if vehicle_number is None or event_number is None:
            return None
        return vehicle_number, event_number

    @staticmethod
    def _entity_id(
        case_id: int,
        worksheet: str,
        record: dict[str, Any],
    ) -> str | None:
        vehicle_number = ResearchLabelBuilder._positive_int(record.get("VEHNO"))
        if worksheet == "OCC":
            occupant_number = ResearchLabelBuilder._positive_int(record.get("OCCNO"))
            if vehicle_number is None or occupant_number is None:
                return None
            return f"{case_id}-V{vehicle_number}-O{occupant_number}"
        if worksheet in {"GV", "CDC"}:
            if vehicle_number is None:
                return None
            return f"{case_id}-V{vehicle_number}"
        if worksheet == "EDREVENT":
            summary_number = (
                ResearchLabelBuilder._positive_int(record.get("EDRSUMMNO")) or 1
            )
            event_number = ResearchLabelBuilder._positive_int(
                record.get("EDREVENTNO")
            )
            if vehicle_number is None or event_number is None:
                return None
            return (
                f"{case_id}-V{vehicle_number}-EDR-S{summary_number}-E{event_number}"
            )
        return None

    @staticmethod
    def _sentinel_reason(source_variable: str, value: Any) -> str | None:
        sentinels = NUMERIC_SENTINEL_VALUES.get(source_variable, {})
        return sentinels.get(value)

    @staticmethod
    def _source_record_key(
        worksheet: str,
        record: dict[str, Any],
        row_number: int,
    ) -> str:
        """Return a stable row qualifier for label identifiers."""

        if worksheet == "CDC":
            event_number = ResearchLabelBuilder._positive_int(
                record.get("EVENTNO")
            )
            if event_number is not None:
                return f"EVENT{event_number}"

        if worksheet == "EDREVENT":
            event_number = ResearchLabelBuilder._positive_int(
                record.get("EDREVENTNO")
            )
            if event_number is not None:
                return f"EDREVENT{event_number}"

        if worksheet == "OCC":
            occupant_number = ResearchLabelBuilder._positive_int(
                record.get("OCCNO")
            )
            if occupant_number is not None:
                return f"OCC{occupant_number}"

        if worksheet == "GV":
            vehicle_number = ResearchLabelBuilder._positive_int(
                record.get("VEHNO")
            )
            if vehicle_number is not None:
                return f"VEH{vehicle_number}"

        return f"ROW{row_number}"

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            converted = int(value)
        except (TypeError, ValueError):
            return None
        return converted if converted > 0 else None
