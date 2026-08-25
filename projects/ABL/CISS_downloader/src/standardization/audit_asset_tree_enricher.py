"""
Enrich the CISS rich-core vehicle-event table with audit, asset, and
navigation-tree evidence metadata.

The output remains one row per:
    case_id × vehicle_number × event_number

This module does not interpret images, PDFs, sketches, or CDRX files.
It records evidence availability, provenance, and audit quality only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class AuditAssetTreeEnrichmentPaths:
    parquet: Path
    metadata: Path


class AuditAssetTreeEnricher:
    """Add audit, asset, and navigation-tree fields to rich-core rows."""

    SCHEMA_VERSION = "1.0"

    def __init__(self, data_root: str | Path = "data") -> None:
        self.data_root = Path(data_root)

    def build(
        self,
        input_parquet: str | Path | None = None,
        output_directory: str | Path | None = None,
    ) -> AuditAssetTreeEnrichmentPaths:
        input_path = (
            Path(input_parquet)
            if input_parquet is not None
            else (
                self.data_root
                / "processed"
                / "standardized"
                / "vehicle_event_rich_core.parquet"
            )
        )

        if not input_path.exists():
            raise FileNotFoundError(
                f"Rich-core input table is missing: {input_path}"
            )

        destination = (
            Path(output_directory)
            if output_directory is not None
            else input_path.parent
        )
        destination.mkdir(parents=True, exist_ok=True)

        output_parquet = (
            destination / "vehicle_event_rich_evidence.parquet"
        )
        output_metadata = (
            destination / "vehicle_event_rich_evidence_metadata.json"
        )

        input_frame = pd.read_parquet(input_path)

        required_columns = {
            "case_id",
            "vehicle_number",
            "event_number",
            "vehicle_event_id",
        }
        missing_columns = required_columns - set(input_frame.columns)

        if missing_columns:
            raise ValueError(
                "Input table is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        case_cache: dict[int, dict[str, Any]] = {}
        rows: list[dict[str, Any]] = []

        for row in input_frame.to_dict(orient="records"):
            case_id = self._positive_int(row.get("case_id"))

            if case_id is None:
                raise ValueError(
                    "A vehicle-event row has no valid case_id: "
                    f"{row.get('vehicle_event_id')}"
                )

            if case_id not in case_cache:
                case_cache[case_id] = self._load_case_evidence(case_id)

            enriched_row = dict(row)
            enriched_row.update(
                self._case_and_vehicle_fields(
                    case_data=case_cache[case_id],
                    vehicle_number=self._positive_int(
                        row.get("vehicle_number")
                    ),
                )
            )
            rows.append(enriched_row)

        output_frame = pd.DataFrame(rows)

        self._validate_output(
            input_frame=input_frame,
            output_frame=output_frame,
        )

        output_frame = self._prepare_for_parquet(output_frame)

        output_frame.to_parquet(
            output_parquet,
            index=False,
        )

        metadata = self._build_metadata(
            input_path=input_path,
            output_path=output_parquet,
            frame=output_frame,
        )

        with output_metadata.open("w", encoding="utf-8") as file:
            json.dump(
                metadata,
                file,
                indent=2,
                ensure_ascii=False,
            )

        print("Audit/asset/tree enrichment completed.")
        print(f"Input rows: {len(input_frame)}")
        print(f"Output rows: {len(output_frame)}")
        print(f"Parquet: {output_parquet}")
        print(f"Coverage report: {output_metadata}")

        return AuditAssetTreeEnrichmentPaths(
            parquet=output_parquet,
            metadata=output_metadata,
        )

    def _load_case_evidence(self, case_id: int) -> dict[str, Any]:
        raw_directory = self.data_root / "raw" / str(case_id)
        audit_path = (
            self.data_root
            / "processed"
            / str(case_id)
            / "audit"
            / "case_audit.json"
        )

        audit = self._load_json(audit_path)
        assets = self._load_json(raw_directory / "assets.json")
        tree = self._load_json(raw_directory / "navigation_tree.json")

        return {
            "audit": audit,
            "assets": assets,
            "tree": tree,
            "audit_path": str(audit_path),
            "assets_path": str(raw_directory / "assets.json"),
            "tree_path": str(raw_directory / "navigation_tree.json"),
        }

    def _case_and_vehicle_fields(
        self,
        case_data: dict[str, Any],
        vehicle_number: int | None,
    ) -> dict[str, Any]:
        audit = case_data["audit"]
        assets = case_data["assets"]
        tree = case_data["tree"]

        audit_summary = self._as_dict(audit.get("audit_summary"))
        contradictions = self._as_dict(
            audit.get("cross_source_contradictions")
        )
        domain_availability = self._as_dict(
            audit.get("domain_availability")
        )
        task_eligibility = self._as_dict(
            audit.get("task_eligibility")
        )
        edr_quality = self._as_dict(
            audit.get("edr_quality_audit")
        )

        asset_list = self._asset_list(assets)
        vehicle_assets = self._assets_for_vehicle(
            assets=asset_list,
            vehicle_number=vehicle_number,
        )

        return {
            # Audit trustworthiness and availability.
            "audit_case_status": audit.get("status"),
            "audit_passed": audit_summary.get("passed"),
            "audit_warning_count": audit_summary.get("warning_count"),
            "audit_error_count": audit_summary.get("error_count"),
            "audit_cross_source_contradiction_count": (
                contradictions.get("contradiction_count")
            ),
            "audit_cross_source_contextual_difference_count": (
                contradictions.get("contextual_difference_count")
            ),
            "audit_crash_mechanics_status": self._nested_status(
                domain_availability,
                "crash_mechanics",
            ),
            "audit_edr_status": self._nested_status(
                domain_availability,
                "edr",
            ),
            "audit_visual_assets_status": self._nested_status(
                domain_availability,
                "visual_assets",
            ),
            "audit_crash_reconstruction_eligibility": self._nested_status(
                task_eligibility,
                "crash_reconstruction",
            ),
            "audit_multimodal_learning_eligibility": self._nested_status(
                task_eligibility,
                "multimodal_learning",
            ),
            "audit_edr_obtained": edr_quality.get("edr_obtained"),
            "audit_edr_summary_records_available": (
                edr_quality.get("summary_records_available")
            ),
            "audit_edr_event_records_available": (
                edr_quality.get("event_records_available")
            ),
            "audit_edr_applicable_event_identified": (
                edr_quality.get("applicable_event_identified")
            ),
            "audit_edr_delta_v_history_available": (
                edr_quality.get("delta_v_history_available")
            ),
            "audit_edr_direct_acceleration_history_available": (
                edr_quality.get("direct_acceleration_history_available")
            ),
            "audit_edr_pulse_candidate_available": (
                edr_quality.get("pulse_candidate_available")
            ),

            # Asset inventory, matched to the vehicle when possible.
            "asset_case_total_count": len(asset_list),
            "asset_vehicle_total_count": len(vehicle_assets),
            "asset_vehicle_image_count": self._count_type(
                vehicle_assets,
                "image",
            ),
            "asset_vehicle_document_count": self._count_type(
                vehicle_assets,
                "document",
            ),
            "asset_vehicle_sketch_count": self._count_type(
                vehicle_assets,
                "sketch",
            ),
            "asset_vehicle_cdrx_count": self._count_extension(
                vehicle_assets,
                ".cdrx",
            ),
            "asset_vehicle_csv_count": self._count_extension(
                vehicle_assets,
                ".csv",
            ),
            "asset_vehicle_pdf_count": self._count_extension(
                vehicle_assets,
                ".pdf",
            ),
            "asset_vehicle_blz_count": self._count_extension(
                vehicle_assets,
                ".blz",
            ),
            "asset_vehicle_nik_count": self._count_extension(
                vehicle_assets,
                ".nik",
            ),
            "asset_has_cdrx_file": (
                self._count_extension(vehicle_assets, ".cdrx") > 0
            ),
            "asset_has_vehicle_images": (
                self._count_type(vehicle_assets, "image") > 0
            ),
            "asset_has_sketches": (
                self._count_type(vehicle_assets, "sketch") > 0
            ),
            "asset_has_scene_diagram_document": self._has_path_text(
                asset_list,
                "scene diagram",
            ),

            # CISS navigation-tree evidence availability.
            "tree_available": isinstance(tree, list),
            "tree_node_count": len(tree) if isinstance(tree, list) else 0,
            "tree_has_scene_diagram": self._tree_has_name(
                tree,
                "scene diagram",
            ),
            "tree_has_edr_section": self._tree_has_name(tree, "edr"),
            "tree_vehicle_image_category_present": (
                self._tree_vehicle_has_name(
                    tree,
                    vehicle_number,
                    "vehicle images",
                )
            ),
            "tree_vehicle_front_image_category_present": (
                self._tree_vehicle_has_name(
                    tree,
                    vehicle_number,
                    "front",
                )
            ),
            "tree_vehicle_side_image_category_present": (
                self._tree_vehicle_has_any_name(
                    tree,
                    vehicle_number,
                    ("left plane", "right plane"),
                )
            ),
            "tree_vehicle_rear_image_category_present": (
                self._tree_vehicle_has_any_name(
                    tree,
                    vehicle_number,
                    ("back plane", "rear"),
                )
            ),
            "tree_vehicle_interior_image_category_present": (
                self._tree_vehicle_has_name(
                    tree,
                    vehicle_number,
                    "interior",
                )
            ),

            # Source provenance.
            "audit_source_path": case_data["audit_path"],
            "asset_source_path": case_data["assets_path"],
            "tree_source_path": case_data["tree_path"],
            "evidence_enrichment_version": self.SCHEMA_VERSION,
        }

    @staticmethod
    def _load_json(path: Path) -> Any:
        if not path.exists():
            return None

        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _asset_list(assets: Any) -> list[dict[str, Any]]:
        if not isinstance(assets, dict):
            return []

        items = assets.get("assets", [])

        return [
            item
            for item in items
            if isinstance(item, dict)
        ]

    @staticmethod
    def _assets_for_vehicle(
        assets: list[dict[str, Any]],
        vehicle_number: int | None,
    ) -> list[dict[str, Any]]:
        if vehicle_number is None:
            return []

        pattern = re.compile(
            rf"(?:^|[/\\])vehicle\s*{vehicle_number}(?:\D|$)",
            flags=re.IGNORECASE,
        )

        return [
            asset
            for asset in assets
            if pattern.search(
                str(asset.get("relative_path", ""))
            )
        ]

    @staticmethod
    def _count_type(
        assets: list[dict[str, Any]],
        asset_type: str,
    ) -> int:
        return sum(
            asset.get("asset_type") == asset_type
            for asset in assets
        )

    @staticmethod
    def _count_extension(
        assets: list[dict[str, Any]],
        extension: str,
    ) -> int:
        return sum(
            str(asset.get("extension", "")).lower() == extension
            for asset in assets
        )

    @staticmethod
    def _has_path_text(
        assets: list[dict[str, Any]],
        text: str,
    ) -> bool:
        text = text.lower()

        return any(
            text in str(asset.get("relative_path", "")).lower()
            for asset in assets
        )

    @staticmethod
    def _tree_has_name(tree: Any, name: str) -> bool:
        if not isinstance(tree, list):
            return False

        name = name.lower()

        return any(
            name in str(node.get("name", "")).lower()
            for node in tree
            if isinstance(node, dict)
        )

    def _tree_vehicle_has_name(
        self,
        tree: Any,
        vehicle_number: int | None,
        name: str,
    ) -> bool:
        return self._tree_vehicle_has_any_name(
            tree,
            vehicle_number,
            (name,),
        )

    def _tree_vehicle_has_any_name(
        self,
        tree: Any,
        vehicle_number: int | None,
        names: tuple[str, ...],
    ) -> bool:
        if not isinstance(tree, list) or vehicle_number is None:
            return False

        node_by_id = {
            node.get("id"): node
            for node in tree
            if isinstance(node, dict)
        }

        vehicle_label = f"vehicle {vehicle_number}".lower()
        normalized_names = tuple(name.lower() for name in names)

        for node in tree:
            if not isinstance(node, dict):
                continue

            if not any(
                name in str(node.get("name", "")).lower()
                for name in normalized_names
            ):
                continue

            if self._node_has_vehicle_ancestor(
                node=node,
                node_by_id=node_by_id,
                vehicle_label=vehicle_label,
            ):
                return True

        return False

    @staticmethod
    def _node_has_vehicle_ancestor(
        node: dict[str, Any],
        node_by_id: dict[Any, dict[str, Any]],
        vehicle_label: str,
    ) -> bool:
        current = node
        visited: set[Any] = set()

        while current:
            current_id = current.get("id")

            if current_id in visited:
                return False

            visited.add(current_id)

            if str(current.get("name", "")).lower() == vehicle_label:
                return True

            parent_id = current.get("parentId")
            current = node_by_id.get(parent_id)

        return False

    @staticmethod
    def _nested_status(
        source: dict[str, Any],
        key: str,
    ) -> str | None:
        value = source.get(key)

        if isinstance(value, dict):
            status = value.get("status")
            return str(status) if status is not None else None

        return None

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            converted = int(value)
        except (TypeError, ValueError):
            return None

        return converted if converted > 0 else None

    @staticmethod
    def _prepare_for_parquet(
        frame: pd.DataFrame,
    ) -> pd.DataFrame:
        prepared = frame.copy()

        for column in prepared.columns:
            if not pd.api.types.is_object_dtype(prepared[column]):
                continue

            values = prepared[column].dropna()

            if values.empty:
                continue

            if len({type(value) for value in values}) > 1:
                prepared[column] = prepared[column].astype("string")

        return prepared

    @staticmethod
    def _validate_output(
        input_frame: pd.DataFrame,
        output_frame: pd.DataFrame,
    ) -> None:
        if len(input_frame) != len(output_frame):
            raise ValueError(
                "Row count changed during evidence enrichment."
            )

        if (
            input_frame["vehicle_event_id"].tolist()
            != output_frame["vehicle_event_id"].tolist()
        ):
            raise ValueError(
                "vehicle_event_id order changed during enrichment."
            )

        if output_frame["vehicle_event_id"].duplicated().any():
            raise ValueError(
                "Duplicate vehicle_event_id values were created."
            )

    def _build_metadata(
        self,
        input_path: Path,
        output_path: Path,
        frame: pd.DataFrame,
    ) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_name": "vehicle_event_rich_evidence",
            "unit_of_analysis": (
                "one audited CISS vehicle involved in one crash event"
            ),
            "row_count": int(len(frame)),
            "case_count": int(frame["case_id"].nunique()),
            "primary_key": "vehicle_event_id",
            "input_parquet": str(input_path),
            "output_parquet": str(output_path),
            "new_column_prefixes": [
                "audit_",
                "asset_",
                "tree_",
            ],
            "important_limitations": [
                "Evidence availability is not evidence interpretation.",
                "CDRX, image, PDF, and sketch contents are not read here.",
                "No Delta-V or PDOF values are changed or inferred.",
                "No event-level EDR records are linked here.",
            ],
            "columns": frame.columns.tolist(),
        }