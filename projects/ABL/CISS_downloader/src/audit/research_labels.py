"""
Build research supervision labels for one audited CISS case.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.audit.audit_rules import (
    NUMERIC_SENTINEL_VALUES,
    RESEARCH_LABEL_DEFINITIONS,
    RESEARCH_LABEL_REGISTRY_VERSION,
)


class ResearchLabelBuilder:
    """
    Register potential research labels without imputing
    or standardizing the raw CISS data.
    """

    def build(
        self,
        case_id: int,
        sheets: dict[str, dict[str, Any]],
        entity_registry: dict[str, Any],
        final_label_readiness: dict[str, Any],
        edr_audit: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create row-level final and intermediate labels.

        Stage 2 preserves raw values. It determines whether
        each value can be used for model supervision but
        does not perform Stage-3 standardization.
        """

        case_id = int(case_id)

        known_entities = {
            entity.get("entity_id")
            for entity
            in entity_registry.get(
                "entities",
                [],
            )
            if isinstance(entity, dict)
        }

        occupant_readiness = (
            self._occupant_readiness(
                final_label_readiness
            )
        )

        selected_edr_event = (
            self._selected_edr_event(
                edr_audit
            )
        )

        labels: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        # ----------------------------------------------------------
        # Process every configured research-label variable
        # ----------------------------------------------------------

        for (
            source_variable,
            definition,
        ) in RESEARCH_LABEL_DEFINITIONS.items():

            worksheet, column = (
                source_variable.split(
                    ".",
                    1,
                )
            )

            records = self._records(
                sheets,
                worksheet,
            )

            for row_number, record in enumerate(
                records,
                start=2,
            ):
                if column not in record:
                    continue

                entity_id = self._entity_id(
                    case_id=case_id,
                    worksheet=worksheet,
                    record=record,
                )

                if (
                    entity_id is None
                    or entity_id
                    not in known_entities
                ):
                    unresolved.append(
                        {
                            "source_variable": (
                                source_variable
                            ),
                            "worksheet_row": (
                                row_number
                            ),
                            "reason": (
                                "target_entity_not_found"
                            ),
                            "expected_entity_id": (
                                entity_id
                            ),
                        }
                    )
                    continue

                raw_value = record.get(
                    column
                )

                text_value = record.get(
                    f"{column}TEXT"
                )

                sentinel_reason = (
                    self._sentinel_reason(
                        source_variable,
                        raw_value,
                    )
                )

                value_available = (
                    raw_value is not None
                )

                training_role = definition[
                    "training_role"
                ]

                validity = "available"
                exclusion_reason = None

                # --------------------------------------------------
                # Missing and sentinel-value evaluation
                # --------------------------------------------------

                if not value_available:
                    validity = "missing"
                    exclusion_reason = (
                        "raw_value_missing"
                    )

                elif sentinel_reason is not None:
                    validity = "source_sentinel"

                    exclusion_reason = (
                        "source_sentinel:"
                        f"{sentinel_reason}"
                    )

                # --------------------------------------------------
                # Final medical label evaluation
                # --------------------------------------------------

                if training_role == "final_label":
                    readiness = (
                        occupant_readiness.get(
                            entity_id
                        )
                    )

                    if (
                        not readiness
                        or not readiness.get(
                            "training_eligible",
                            False,
                        )
                    ):
                        validity = (
                            "outcome_not_reliable"
                        )

                        if readiness:
                            exclusion_reason = (
                                readiness.get(
                                    "exclusion_reason"
                                )
                            )

                        else:
                            exclusion_reason = (
                                "occupant_label_"
                                "readiness_missing"
                            )

                # --------------------------------------------------
                # EDR event relevance evaluation
                # --------------------------------------------------

                if worksheet == "EDREVENT":
                    event_number = (
                        self._positive_int(
                            record.get(
                                "EDREVENTNO"
                            )
                        )
                    )

                    vehicle_number = (
                        self._positive_int(
                            record.get(
                                "VEHNO"
                            )
                        )
                    )

                    event_key = (
                        vehicle_number,
                        event_number,
                    )

                    if selected_edr_event is None:
                        validity = (
                            "applicable_event_"
                            "not_identified"
                        )

                        exclusion_reason = (
                            "applicable_edr_event_"
                            "not_identified"
                        )

                    elif (
                        event_key
                        != selected_edr_event
                    ):
                        validity = (
                            "not_applicable_event"
                        )

                        exclusion_reason = (
                            "edr_event_not_related_"
                            "to_investigated_crash"
                        )

                training_usable = (
                    validity == "available"
                )

                # --------------------------------------------------
                # Stable label identifier
                # --------------------------------------------------

                source_record_key = (
                    self._source_record_key(
                        worksheet=worksheet,
                        record=record,
                        row_number=row_number,
                    )
                )

                label_id = (
                    f"{entity_id}"
                    f"::{source_variable}"
                    f"::{source_record_key}"
                )

                labels.append(
                    {
                        "label_id": label_id,
                        "entity_id": entity_id,
                        "entity_type": definition[
                            "entity_type"
                        ],
                        "source_variable": (
                            source_variable
                        ),
                        "canonical_name": (
                            definition[
                                "canonical_name"
                            ]
                        ),
                        "label_family": (
                            definition[
                                "label_family"
                            ]
                        ),
                        "training_role": (
                            training_role
                        ),
                        "raw_value": raw_value,
                        "raw_text": text_value,
                        "training_value": (
                            raw_value
                            if training_usable
                            else None
                        ),
                        "unit": definition[
                            "unit"
                        ],
                        "validity": validity,
                        "training_usable": (
                            training_usable
                        ),
                        "exclusion_reason": (
                            exclusion_reason
                        ),
                        "normalization_status": (
                            "not_applied_stage2"
                        ),
                        "downstream_stages": list(
                            definition[
                                "downstream_stages"
                            ]
                        ),
                        "source": {
                            "worksheet": (
                                worksheet
                            ),
                            "column": column,
                            "worksheet_row": (
                                row_number
                            ),
                            "source_record_key": (
                                source_record_key
                            ),
                        },
                    }
                )

        # ----------------------------------------------------------
        # Registry summary
        # ----------------------------------------------------------

        family_counts = Counter(
            label["label_family"]
            for label in labels
        )

        role_counts = Counter(
            label["training_role"]
            for label in labels
        )

        validity_counts = Counter(
            label["validity"]
            for label in labels
        )

        usable_by_role = Counter(
            label["training_role"]
            for label in labels
            if label["training_usable"]
        )

        return {
            "registry_version": (
                RESEARCH_LABEL_REGISTRY_VERSION
            ),
            "case_id": case_id,
            "stage2_policy": {
                "raw_values_preserved": True,
                "normalization_applied": False,
                "missing_injury_is_not_no_injury": (
                    True
                ),
                "nonapplicable_edr_events_excluded": (
                    True
                ),
            },
            "summary": {
                "total_label_records": len(
                    labels
                ),
                "training_usable_label_count": (
                    sum(
                        label[
                            "training_usable"
                        ]
                        for label in labels
                    )
                ),
                "labels_by_family": dict(
                    sorted(
                        family_counts.items()
                    )
                ),
                "labels_by_role": dict(
                    sorted(
                        role_counts.items()
                    )
                ),
                "labels_by_validity": dict(
                    sorted(
                        validity_counts.items()
                    )
                ),
                "training_usable_by_role": dict(
                    sorted(
                        usable_by_role.items()
                    )
                ),
                "unresolved_label_count": len(
                    unresolved
                ),
            },
            "labels": labels,
            "unresolved_labels": unresolved,
        }

    # ==============================================================
    # Supporting methods
    # ==============================================================

    @staticmethod
    def _records(
        sheets: dict[str, dict[str, Any]],
        worksheet: str,
    ) -> list[dict[str, Any]]:
        """
        Return the records from one parsed worksheet.
        """

        sheet = sheets.get(
            worksheet,
            {},
        )

        if not isinstance(sheet, dict):
            return []

        records = sheet.get(
            "records",
            [],
        )

        if not isinstance(records, list):
            return []

        return records

    @staticmethod
    def _occupant_readiness(
        readiness: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """
        Index occupant label-readiness results by entity ID.
        """

        result: dict[
            str,
            dict[str, Any],
        ] = {}

        for item in readiness.get(
            "occupants",
            [],
        ):
            if not isinstance(item, dict):
                continue

            case_id = item.get(
                "case_id"
            )

            vehicle_number = item.get(
                "vehicle_number"
            )

            occupant_number = item.get(
                "occupant_number"
            )

            if None in (
                case_id,
                vehicle_number,
                occupant_number,
            ):
                continue

            entity_id = (
                f"{case_id}"
                f"-V{vehicle_number}"
                f"-O{occupant_number}"
            )

            result[entity_id] = item

        return result

    @staticmethod
    def _selected_edr_event(
        edr_audit: dict[str, Any],
    ) -> tuple[int, int] | None:
        """
        Return the selected vehicle and EDR event number.
        """

        event = (
            edr_audit.get(
                "event_selection",
                {},
            ).get(
                "event"
            )
        )

        if not isinstance(event, dict):
            return None

        vehicle_number = (
            ResearchLabelBuilder._positive_int(
                event.get(
                    "vehicle_number"
                )
            )
        )

        event_number = (
            ResearchLabelBuilder._positive_int(
                event.get(
                    "edr_event_number"
                )
            )
        )

        if (
            vehicle_number is None
            or event_number is None
        ):
            return None

        return (
            vehicle_number,
            event_number,
        )

    @staticmethod
    def _entity_id(
        case_id: int,
        worksheet: str,
        record: dict[str, Any],
    ) -> str | None:
        """
        Construct the expected entity ID for a source row.
        """

        vehicle_number = (
            ResearchLabelBuilder._positive_int(
                record.get("VEHNO")
            )
        )

        if worksheet == "OCC":
            occupant_number = (
                ResearchLabelBuilder._positive_int(
                    record.get(
                        "OCCNO"
                    )
                )
            )

            if (
                vehicle_number is None
                or occupant_number is None
            ):
                return None

            return (
                f"{case_id}"
                f"-V{vehicle_number}"
                f"-O{occupant_number}"
            )

        if worksheet in {
            "GV",
            "CDC",
        }:
            if vehicle_number is None:
                return None

            return (
                f"{case_id}"
                f"-V{vehicle_number}"
            )

        if worksheet == "EDREVENT":
            summary_number = (
                ResearchLabelBuilder._positive_int(
                    record.get(
                        "EDRSUMMNO"
                    )
                )
                or 1
            )

            event_number = (
                ResearchLabelBuilder._positive_int(
                    record.get(
                        "EDREVENTNO"
                    )
                )
            )

            if (
                vehicle_number is None
                or event_number is None
            ):
                return None

            return (
                f"{case_id}"
                f"-V{vehicle_number}"
                f"-EDR-S{summary_number}"
                f"-E{event_number}"
            )

        return None

    @staticmethod
    def _sentinel_reason(
        source_variable: str,
        value: Any,
    ) -> str | None:
        """
        Return the meaning of a source sentinel code.
        """

        sentinels = (
            NUMERIC_SENTINEL_VALUES.get(
                source_variable,
                {},
            )
        )

        return sentinels.get(
            value
        )

    @staticmethod
    def _source_record_key(
        worksheet: str,
        record: dict[str, Any],
        row_number: int,
    ) -> str:
        """
        Return a stable row qualifier for label identifiers.
        """

        if worksheet == "CDC":
            event_number = (
                ResearchLabelBuilder._positive_int(
                    record.get(
                        "EVENTNO"
                    )
                )
            )

            if event_number is not None:
                return (
                    f"EVENT{event_number}"
                )

        if worksheet == "EDREVENT":
            event_number = (
                ResearchLabelBuilder._positive_int(
                    record.get(
                        "EDREVENTNO"
                    )
                )
            )

            if event_number is not None:
                return (
                    f"EDREVENT{event_number}"
                )

        if worksheet == "OCC":
            occupant_number = (
                ResearchLabelBuilder._positive_int(
                    record.get(
                        "OCCNO"
                    )
                )
            )

            if occupant_number is not None:
                return (
                    f"OCC{occupant_number}"
                )

        if worksheet == "GV":
            vehicle_number = (
                ResearchLabelBuilder._positive_int(
                    record.get(
                        "VEHNO"
                    )
                )
            )

            if vehicle_number is not None:
                return (
                    f"VEH{vehicle_number}"
                )

        return f"ROW{row_number}"

    @staticmethod
    def _positive_int(
        value: Any,
    ) -> int | None:
        """
        Convert a source value to a positive integer.
        """

        if (
            value is None
            or isinstance(value, bool)
        ):
            return None

        try:
            converted = int(value)

        except (TypeError, ValueError):
            return None

        if converted <= 0:
            return None

        return converted