"""Build deterministic entity identifiers and relationships for one CISS case."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from src.audit.audit_rules import ENTITY_REGISTRY_VERSION


class EntityRegistryBuilder:
    """Create the Stage-2 entity registry without modifying raw source data."""

    _VEHICLE_PATH_PATTERN = re.compile(
        r"(?:^|[/\\])Vehicle\s+(\d+)(?:[/\\]|$)|_V(\d+)(?:\D|$)",
        re.IGNORECASE,
    )

    def build(
        self,
        case_id: int,
        sheets: dict[str, dict[str, Any]],
        asset_registry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return entities, relationships, and unresolved references."""

        case_id = int(case_id)
        case_entity_id = str(case_id)
        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        seen_entities: set[str] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        def add_entity(entity: dict[str, Any]) -> None:
            entity_id = str(entity["entity_id"])
            if entity_id in seen_entities:
                return
            seen_entities.add(entity_id)
            entities.append(entity)

        def add_relationship(
            source_id: str,
            relationship: str,
            target_id: str,
            source: str,
            confidence: str = "authoritative",
        ) -> None:
            key = (source_id, relationship, target_id)
            if key in seen_relationships:
                return
            seen_relationships.add(key)
            relationships.append(
                {
                    "source_entity_id": source_id,
                    "relationship": relationship,
                    "target_entity_id": target_id,
                    "provenance": source,
                    "confidence": confidence,
                }
            )

        add_entity(
            {
                "entity_id": case_entity_id,
                "entity_type": "case",
                "natural_key": {"CASEID": case_id},
                "source": "workbook_and_phase1_metadata",
            }
        )

        vehicle_ids: set[str] = set()
        for record in self._records(sheets, "GV"):
            vehicle_number = self._positive_int(record.get("VEHNO"))
            if vehicle_number is None:
                unresolved.append(
                    {
                        "entity_type": "vehicle",
                        "source": "GV",
                        "reason": "missing_or_invalid_VEHNO",
                    }
                )
                continue
            entity_id = f"{case_id}-V{vehicle_number}"
            vehicle_ids.add(entity_id)
            add_entity(
                {
                    "entity_id": entity_id,
                    "entity_type": "vehicle",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                    },
                    "source": "GV",
                }
            )
            add_relationship(case_entity_id, "has_vehicle", entity_id, "GV")

        occupant_ids: set[str] = set()
        for record in self._records(sheets, "OCC"):
            vehicle_number = self._positive_int(record.get("VEHNO"))
            occupant_number = self._positive_int(record.get("OCCNO"))
            if vehicle_number is None or occupant_number is None:
                unresolved.append(
                    {
                        "entity_type": "occupant",
                        "source": "OCC",
                        "reason": "missing_or_invalid_VEHNO_or_OCCNO",
                    }
                )
                continue
            vehicle_id = f"{case_id}-V{vehicle_number}"
            entity_id = f"{vehicle_id}-O{occupant_number}"
            occupant_ids.add(entity_id)
            add_entity(
                {
                    "entity_id": entity_id,
                    "entity_type": "occupant",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                        "OCCNO": occupant_number,
                    },
                    "source": "OCC",
                }
            )
            if vehicle_id in vehicle_ids:
                add_relationship(vehicle_id, "has_occupant", entity_id, "OCC")
            else:
                unresolved.append(
                    {
                        "entity_id": entity_id,
                        "entity_type": "occupant",
                        "reason": "parent_vehicle_not_found",
                        "expected_parent_id": vehicle_id,
                    }
                )

        edr_summary_ids: set[str] = set()
        for record in self._records(sheets, "EDRSUMM"):
            vehicle_number = self._positive_int(record.get("VEHNO"))
            summary_number = self._positive_int(record.get("EDRSUMMNO")) or 1
            if vehicle_number is None:
                unresolved.append(
                    {
                        "entity_type": "edr_summary",
                        "source": "EDRSUMM",
                        "reason": "missing_or_invalid_VEHNO",
                    }
                )
                continue
            vehicle_id = f"{case_id}-V{vehicle_number}"
            entity_id = f"{vehicle_id}-EDR-S{summary_number}"
            edr_summary_ids.add(entity_id)
            add_entity(
                {
                    "entity_id": entity_id,
                    "entity_type": "edr_summary",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                        "EDRSUMMNO": summary_number,
                    },
                    "source": "EDRSUMM",
                }
            )
            if vehicle_id in vehicle_ids:
                add_relationship(vehicle_id, "has_edr_summary", entity_id, "EDRSUMM")

        for record in self._records(sheets, "EDREVENT"):
            vehicle_number = self._positive_int(record.get("VEHNO"))
            summary_number = self._positive_int(record.get("EDRSUMMNO")) or 1
            event_number = self._positive_int(record.get("EDREVENTNO"))
            if vehicle_number is None or event_number is None:
                unresolved.append(
                    {
                        "entity_type": "edr_event",
                        "source": "EDREVENT",
                        "reason": "missing_or_invalid_entity_key",
                    }
                )
                continue
            summary_id = f"{case_id}-V{vehicle_number}-EDR-S{summary_number}"
            entity_id = f"{summary_id}-E{event_number}"
            add_entity(
                {
                    "entity_id": entity_id,
                    "entity_type": "edr_event",
                    "natural_key": {
                        "CASEID": case_id,
                        "VEHNO": vehicle_number,
                        "EDRSUMMNO": summary_number,
                        "EDREVENTNO": event_number,
                    },
                    "source": "EDREVENT",
                }
            )
            if summary_id in edr_summary_ids:
                add_relationship(summary_id, "has_edr_event", entity_id, "EDREVENT")
            else:
                unresolved.append(
                    {
                        "entity_id": entity_id,
                        "entity_type": "edr_event",
                        "reason": "parent_edr_summary_not_found",
                        "expected_parent_id": summary_id,
                    }
                )

        assets = (
            asset_registry.get("assets", [])
            if isinstance(asset_registry, dict)
            else []
        )
        for position, asset in enumerate(assets, start=1):
            if not isinstance(asset, dict):
                continue
            asset_id = str(asset.get("asset_id") or f"case_{case_id}_asset_{position:04d}")
            asset_type = self._asset_type(asset.get("asset_type"))
            relative_path = str(asset.get("relative_path") or "")
            add_entity(
                {
                    "entity_id": asset_id,
                    "entity_type": asset_type,
                    "natural_key": {
                        "asset_id": asset_id,
                        "relative_path": relative_path or None,
                    },
                    "source": "assets.json",
                    "object_id": asset.get("object_id"),
                }
            )
            add_relationship(case_entity_id, f"has_{asset_type}", asset_id, "assets.json")

            vehicle_number = self._vehicle_from_path(relative_path)
            if vehicle_number is not None:
                vehicle_id = f"{case_id}-V{vehicle_number}"
                if vehicle_id in vehicle_ids:
                    add_relationship(
                        vehicle_id,
                        f"has_{asset_type}",
                        asset_id,
                        "assets.json.relative_path",
                        confidence="path_inferred",
                    )
                else:
                    unresolved.append(
                        {
                            "entity_id": asset_id,
                            "entity_type": asset_type,
                            "reason": "path_references_unknown_vehicle",
                            "expected_parent_id": vehicle_id,
                        }
                    )

        entity_counts = Counter(entity["entity_type"] for entity in entities)
        relationship_counts = Counter(
            item["relationship"] for item in relationships
        )

        return {
            "registry_version": ENTITY_REGISTRY_VERSION,
            "case_id": case_id,
            "id_contract": {
                "case": "<CASEID>",
                "vehicle": "<CASEID>-V<VEHNO>",
                "occupant": "<CASEID>-V<VEHNO>-O<OCCNO>",
                "edr_summary": "<CASEID>-V<VEHNO>-EDR-S<EDRSUMMNO>",
                "edr_event": "<EDR_SUMMARY_ID>-E<EDREVENTNO>",
                "asset": "existing assets.json asset_id",
            },
            "summary": {
                "entity_count": len(entities),
                "entities_by_type": dict(sorted(entity_counts.items())),
                "relationship_count": len(relationships),
                "relationships_by_type": dict(sorted(relationship_counts.items())),
                "unresolved_reference_count": len(unresolved),
            },
            "entities": entities,
            "relationships": relationships,
            "unresolved_references": unresolved,
        }

    @staticmethod
    def _records(
        sheets: dict[str, dict[str, Any]],
        sheet_name: str,
    ) -> list[dict[str, Any]]:
        sheet = sheets.get(sheet_name, {})
        records = sheet.get("records", []) if isinstance(sheet, dict) else []
        return records if isinstance(records, list) else []

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            converted = int(value)
        except (TypeError, ValueError):
            return None
        return converted if converted > 0 else None

    @staticmethod
    def _asset_type(value: Any) -> str:
        normalized = str(value or "unknown_asset").strip().lower()
        return normalized if normalized in {"image", "document", "sketch"} else "unknown_asset"

    def _vehicle_from_path(self, path: str) -> int | None:
        match = self._VEHICLE_PATH_PATTERN.search(path)
        if not match:
            return None
        return int(match.group(1) or match.group(2))
