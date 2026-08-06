"""
Build deterministic entity identifiers and relationships
for one CISS case.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from src.audit.audit_rules import (
    ENTITY_REGISTRY_VERSION,
)


class EntityRegistryBuilder:
    """
    Create the Stage-2 entity registry without modifying
    the original CISS source data.

    The registry assigns stable identifiers to:

    - Case
    - Vehicle
    - Occupant
    - EDR summary
    - EDR event
    - Image
    - Document
    - Sketch

    It also records relationships between these entities.
    """

    _VEHICLE_PATH_PATTERN = re.compile(
        r"(?:^|[/\\])Vehicle\s+(\d+)(?:[/\\]|$)"
        r"|_V(\d+)(?:\D|$)",
        re.IGNORECASE,
    )

    def build(
        self,
        case_id: int,
        sheets: dict[str, dict[str, Any]],
        asset_registry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Build the complete entity registry for one CISS case.

        Parameters
        ----------
        case_id:
            CISS case identifier.

        sheets:
            Parsed Excel worksheets produced by CaseAuditor.

        asset_registry:
            Contents of the Phase-1 assets.json file.

        Returns
        -------
        dict[str, Any]
            Entity registry containing identifiers,
            relationships, summary counts, and unresolved
            references.
        """

        case_id = int(case_id)
        case_entity_id = str(case_id)

        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        seen_entities: set[str] = set()

        seen_relationships: set[
            tuple[str, str, str]
        ] = set()

        # ----------------------------------------------------------
        # Local helper: add one entity
        # ----------------------------------------------------------

        def add_entity(
            entity: dict[str, Any],
        ) -> None:
            """
            Add an entity unless its identifier already exists.
            """

            entity_id = str(
                entity["entity_id"]
            )

            if entity_id in seen_entities:
                return

            seen_entities.add(entity_id)
            entities.append(entity)

        # ----------------------------------------------------------
        # Local helper: add one relationship
        # ----------------------------------------------------------

        def add_relationship(
            source_id: str,
            relationship: str,
            target_id: str,
            source: str,
            confidence: str = "authoritative",
        ) -> None:
            """
            Add a unique relationship between two entities.
            """

            relationship_key = (
                source_id,
                relationship,
                target_id,
            )

            if relationship_key in seen_relationships:
                return

            seen_relationships.add(
                relationship_key
            )

            relationships.append(
                {
                    "source_entity_id": source_id,
                    "relationship": relationship,
                    "target_entity_id": target_id,
                    "provenance": source,
                    "confidence": confidence,
                }
            )

        # ==========================================================
        # Case entity
        # ==========================================================

        add_entity(
            {
                "entity_id": case_entity_id,
                "entity_type": "case",
                "natural_key": {
                    "CASEID": case_id,
                },
                "source": (
                    "workbook_and_phase1_metadata"
                ),
            }
        )

        # ==========================================================
        # Vehicle entities
        # ==========================================================

        vehicle_ids: set[str] = set()

        for record in self._records(
            sheets,
            "GV",
        ):
            vehicle_number = self._positive_int(
                record.get("VEHNO")
            )

            if vehicle_number is None:
                unresolved.append(
                    {
                        "entity_type": "vehicle",
                        "source": "GV",
                        "reason": (
                            "missing_or_invalid_VEHNO"
                        ),
                    }
                )
                continue

            vehicle_entity_id = (
                f"{case_id}-V{vehicle_number}"
            )

            vehicle_ids.add(
                vehicle_entity_id
            )

            add_entity(
                {
                    "entity_id": (
                        vehicle_entity_id
                    ),
                    "entity_type": "vehicle",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                    },
                    "source": "GV",
                }
            )

            add_relationship(
                source_id=case_entity_id,
                relationship="has_vehicle",
                target_id=vehicle_entity_id,
                source="GV",
            )

        # ==========================================================
        # Occupant entities
        # ==========================================================

        occupant_ids: set[str] = set()

        for record in self._records(
            sheets,
            "OCC",
        ):
            vehicle_number = self._positive_int(
                record.get("VEHNO")
            )

            occupant_number = self._positive_int(
                record.get("OCCNO")
            )

            if (
                vehicle_number is None
                or occupant_number is None
            ):
                unresolved.append(
                    {
                        "entity_type": "occupant",
                        "source": "OCC",
                        "reason": (
                            "missing_or_invalid_"
                            "VEHNO_or_OCCNO"
                        ),
                    }
                )
                continue

            vehicle_entity_id = (
                f"{case_id}-V{vehicle_number}"
            )

            occupant_entity_id = (
                f"{vehicle_entity_id}"
                f"-O{occupant_number}"
            )

            occupant_ids.add(
                occupant_entity_id
            )

            add_entity(
                {
                    "entity_id": (
                        occupant_entity_id
                    ),
                    "entity_type": "occupant",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                        "OCCNO": occupant_number,
                    },
                    "source": "OCC",
                }
            )

            if vehicle_entity_id in vehicle_ids:
                add_relationship(
                    source_id=vehicle_entity_id,
                    relationship="has_occupant",
                    target_id=(
                        occupant_entity_id
                    ),
                    source="OCC",
                )

            else:
                unresolved.append(
                    {
                        "entity_id": (
                            occupant_entity_id
                        ),
                        "entity_type": "occupant",
                        "reason": (
                            "parent_vehicle_not_found"
                        ),
                        "expected_parent_id": (
                            vehicle_entity_id
                        ),
                    }
                )

        # ==========================================================
        # EDR summary entities
        # ==========================================================

        edr_summary_ids: set[str] = set()

        for record in self._records(
            sheets,
            "EDRSUMM",
        ):
            vehicle_number = self._positive_int(
                record.get("VEHNO")
            )

            summary_number = (
                self._positive_int(
                    record.get("EDRSUMMNO")
                )
                or 1
            )

            if vehicle_number is None:
                unresolved.append(
                    {
                        "entity_type": (
                            "edr_summary"
                        ),
                        "source": "EDRSUMM",
                        "reason": (
                            "missing_or_invalid_VEHNO"
                        ),
                    }
                )
                continue

            vehicle_entity_id = (
                f"{case_id}-V{vehicle_number}"
            )

            summary_entity_id = (
                f"{vehicle_entity_id}"
                f"-EDR-S{summary_number}"
            )

            edr_summary_ids.add(
                summary_entity_id
            )

            add_entity(
                {
                    "entity_id": (
                        summary_entity_id
                    ),
                    "entity_type": "edr_summary",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                        "EDRSUMMNO": (
                            summary_number
                        ),
                    },
                    "source": "EDRSUMM",
                }
            )

            if vehicle_entity_id in vehicle_ids:
                add_relationship(
                    source_id=vehicle_entity_id,
                    relationship=(
                        "has_edr_summary"
                    ),
                    target_id=(
                        summary_entity_id
                    ),
                    source="EDRSUMM",
                )

            else:
                unresolved.append(
                    {
                        "entity_id": (
                            summary_entity_id
                        ),
                        "entity_type": (
                            "edr_summary"
                        ),
                        "reason": (
                            "parent_vehicle_not_found"
                        ),
                        "expected_parent_id": (
                            vehicle_entity_id
                        ),
                    }
                )

        # ==========================================================
        # EDR event entities
        # ==========================================================

        for record in self._records(
            sheets,
            "EDREVENT",
        ):
            vehicle_number = self._positive_int(
                record.get("VEHNO")
            )

            summary_number = (
                self._positive_int(
                    record.get("EDRSUMMNO")
                )
                or 1
            )

            event_number = self._positive_int(
                record.get("EDREVENTNO")
            )

            if (
                vehicle_number is None
                or event_number is None
            ):
                unresolved.append(
                    {
                        "entity_type": "edr_event",
                        "source": "EDREVENT",
                        "reason": (
                            "missing_or_invalid_"
                            "entity_key"
                        ),
                    }
                )
                continue

            summary_entity_id = (
                f"{case_id}"
                f"-V{vehicle_number}"
                f"-EDR-S{summary_number}"
            )

            event_entity_id = (
                f"{summary_entity_id}"
                f"-E{event_number}"
            )

            add_entity(
                {
                    "entity_id": (
                        event_entity_id
                    ),
                    "entity_type": "edr_event",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                        "EDRSUMMNO": (
                            summary_number
                        ),
                        "EDREVENTNO": (
                            event_number
                        ),
                    },
                    "source": "EDREVENT",
                }
            )

            if (
                summary_entity_id
                in edr_summary_ids
            ):
                add_relationship(
                    source_id=summary_entity_id,
                    relationship="has_edr_event",
                    target_id=event_entity_id,
                    source="EDREVENT",
                )

            else:
                unresolved.append(
                    {
                        "entity_id": (
                            event_entity_id
                        ),
                        "entity_type": (
                            "edr_event"
                        ),
                        "reason": (
                            "parent_edr_summary_"
                            "not_found"
                        ),
                        "expected_parent_id": (
                            summary_entity_id
                        ),
                    }
                )

        # ==========================================================
        # Asset entities
        # ==========================================================

        if isinstance(
            asset_registry,
            dict,
        ):
            assets = asset_registry.get(
                "assets",
                [],
            )

        else:
            assets = []

        if not isinstance(assets, list):
            assets = []

        for position, asset in enumerate(
            assets,
            start=1,
        ):
            if not isinstance(asset, dict):
                continue

            asset_id = str(
                asset.get("asset_id")
                or (
                    f"case_{case_id}_"
                    f"asset_{position:04d}"
                )
            )

            asset_type = self._asset_type(
                asset.get("asset_type")
            )

            relative_path = str(
                asset.get("relative_path")
                or ""
            )

            add_entity(
                {
                    "entity_id": asset_id,
                    "entity_type": asset_type,
                    "natural_key": {
                        "asset_id": asset_id,
                        "relative_path": (
                            relative_path
                            or None
                        ),
                    },
                    "source": "assets.json",
                    "object_id": asset.get(
                        "object_id"
                    ),
                }
            )

            # Every asset belongs to the case.
            add_relationship(
                source_id=case_entity_id,
                relationship=(
                    f"has_{asset_type}"
                ),
                target_id=asset_id,
                source="assets.json",
            )

            # Some paths explicitly identify a vehicle.
            # This is useful, but it is path-derived rather
            # than an authoritative workbook relationship.
            vehicle_number = (
                self._vehicle_from_path(
                    relative_path
                )
            )

            if vehicle_number is not None:
                vehicle_entity_id = (
                    f"{case_id}"
                    f"-V{vehicle_number}"
                )

                if (
                    vehicle_entity_id
                    in vehicle_ids
                ):
                    add_relationship(
                        source_id=(
                            vehicle_entity_id
                        ),
                        relationship=(
                            f"has_{asset_type}"
                        ),
                        target_id=asset_id,
                        source=(
                            "assets.json."
                            "relative_path"
                        ),
                        confidence=(
                            "path_inferred"
                        ),
                    )

                else:
                    unresolved.append(
                        {
                            "entity_id": asset_id,
                            "entity_type": (
                                asset_type
                            ),
                            "reason": (
                                "path_references_"
                                "unknown_vehicle"
                            ),
                            "expected_parent_id": (
                                vehicle_entity_id
                            ),
                        }
                    )

        # ==========================================================
        # Registry summary
        # ==========================================================

        entity_counts = Counter(
            entity["entity_type"]
            for entity in entities
        )

        relationship_counts = Counter(
            relationship["relationship"]
            for relationship
            in relationships
        )

        return {
            "registry_version": (
                ENTITY_REGISTRY_VERSION
            ),
            "case_id": case_id,
            "id_contract": {
                "case": "<CASEID>",
                "vehicle": (
                    "<CASEID>-V<VEHNO>"
                ),
                "occupant": (
                    "<CASEID>-V<VEHNO>"
                    "-O<OCCNO>"
                ),
                "edr_summary": (
                    "<CASEID>-V<VEHNO>"
                    "-EDR-S<EDRSUMMNO>"
                ),
                "edr_event": (
                    "<EDR_SUMMARY_ID>"
                    "-E<EDREVENTNO>"
                ),
                "asset": (
                    "existing assets.json "
                    "asset_id"
                ),
            },
            "summary": {
                "entity_count": len(
                    entities
                ),
                "entities_by_type": dict(
                    sorted(
                        entity_counts.items()
                    )
                ),
                "relationship_count": len(
                    relationships
                ),
                "relationships_by_type": dict(
                    sorted(
                        relationship_counts.items()
                    )
                ),
                "unresolved_reference_count": (
                    len(unresolved)
                ),
            },
            "entities": entities,
            "relationships": relationships,
            "unresolved_references": unresolved,
        }

    # ==============================================================
    # Supporting methods
    # ==============================================================

    @staticmethod
    def _records(
        sheets: dict[str, dict[str, Any]],
        sheet_name: str,
    ) -> list[dict[str, Any]]:
        """
        Return records from one parsed worksheet.
        """

        sheet = sheets.get(
            sheet_name,
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
    def _positive_int(
        value: Any,
    ) -> int | None:
        """
        Convert a value to a positive integer.

        Return None when conversion is not possible.
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

    @staticmethod
    def _asset_type(
        value: Any,
    ) -> str:
        """
        Normalize supported asset types.
        """

        normalized = str(
            value or "unknown_asset"
        ).strip().lower()

        supported_types = {
            "image",
            "document",
            "sketch",
        }

        if normalized in supported_types:
            return normalized

        return "unknown_asset"

    def _vehicle_from_path(
        self,
        path: str,
    ) -> int | None:
        """
        Extract a vehicle number from an asset path.

        Examples
        --------
        Images/Vehicle Images/Vehicle 1/Front Plane/a.jpg

        Docs/Vehicle 1/case_V1.cdrx
        """

        match = (
            self._VEHICLE_PATH_PATTERN.search(
                path
            )
        )

        if match is None:
            return None

        vehicle_number = (
            match.group(1)
            or match.group(2)
        )

        return int(vehicle_number)