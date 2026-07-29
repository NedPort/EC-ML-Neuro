"""
Organize CISS images into normalized and multi-view groups.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re


class ImageGrouping:
    """
    Transform image records from assets.json into image_groups.json.
    """

    EXTERIOR_CATEGORIES = {
        "front_plane",
        "front_right_oblique",
        "right_plane",
        "back_right_oblique",
        "back_plane",
        "back_left_oblique",
        "left_plane",
        "front_left_oblique",
        "top",
    }

    FRONT_CATEGORIES = {
        "front_plane",
        "front_left_oblique",
        "front_right_oblique",
    }

    REAR_CATEGORIES = {
        "back_plane",
        "back_left_oblique",
        "back_right_oblique",
    }

    LEFT_CATEGORIES = {
        "left_plane",
        "front_left_oblique",
        "back_left_oblique",
    }

    RIGHT_CATEGORIES = {
        "right_plane",
        "front_right_oblique",
        "back_right_oblique",
    }

    def _load_json(self, file_path):
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"Asset registry does not exist: {file_path}"
            )

        try:
            with file_path.open(
                "r",
                encoding="utf-8",
            ) as input_file:
                return json.load(input_file)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Asset registry is not valid JSON: {file_path}"
            ) from error

    def _save_json(self, data, output_path):
        """
        Save the generated file atomically.
        """

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path = output_path.with_suffix(
            output_path.suffix + ".part"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                indent=2,
                ensure_ascii=False,
            )

        temporary_path.replace(output_path)

    def _extract_vehicle_number(self, label):
        """
        Extract a number from labels such as 'Vehicle 1'.
        """

        match = re.search(
            r"vehicle\s+(\d+)",
            label,
            flags=re.IGNORECASE,
        )

        if match:
            return int(match.group(1))

        return None

    def _normalize_category(self, category):
        """
        Convert varying CISS labels into a stable vocabulary.
        """

        cleaned = " ".join(category.strip().lower().split())

        direct_mappings = {
            "crash scene": "crash_scene",
            "front plane": "front_plane",
            "front right oblique": "front_right_oblique",
            "right plane": "right_plane",
            "back right oblique": "back_right_oblique",
            "back plane": "back_plane",
            "back left oblique": "back_left_oblique",
            "left plane": "left_plane",
            "front left oblique": "front_left_oblique",
            "top": "top",
            "fuel system": "fuel_system",
            "miscellaneous": "miscellaneous",
        }

        if cleaned in direct_mappings:
            return direct_mappings[cleaned]

        contains_airbag = (
            "airbag" in cleaned
            or "air bag" in cleaned
        )

        if (
            "1st row" in cleaned
            or "first row" in cleaned
        ):
            if contains_airbag:
                return "interior_first_row_airbag"

            return "interior_first_row"

        if (
            "2nd row" in cleaned
            or "second row" in cleaned
        ):
            if contains_airbag:
                return "interior_second_row_airbag"

            return "interior_second_row"

        if contains_airbag:
            return "airbag"

        # Preserve new categories using a stable snake_case label.
        normalized = re.sub(r"[^a-z0-9]+", "_", cleaned)
        normalized = normalized.strip("_")

        return normalized or "unclassified"

    def _expert_routes(
        self,
        image_collection,
        normalized_category,
    ):
        """
        Select suitable expert pipelines for an image category.
        """

        routes = ["visual_evidence"]

        if image_collection == "crash_scene":
            routes.extend(
                [
                    "roadway_scene",
                    "crash_mechanics",
                ]
            )

        elif normalized_category in self.EXTERIOR_CATEGORIES:
            routes.extend(
                [
                    "vehicle_engineering",
                    "crash_mechanics",
                ]
            )

        elif normalized_category.startswith("interior_"):
            routes.extend(
                [
                    "occupant_safety",
                    "vehicle_interior",
                ]
            )

        elif normalized_category == "airbag":
            routes.extend(
                [
                    "occupant_safety",
                    "safety_system",
                ]
            )

        elif normalized_category == "fuel_system":
            routes.extend(
                [
                    "vehicle_engineering",
                    "safety_system",
                ]
            )

        elif normalized_category == "miscellaneous":
            routes.append("image_router")

        else:
            routes.append("image_router")

        return list(dict.fromkeys(routes))

    def _parse_image(self, asset):
        """
        Parse collection, vehicle, and category from an asset path.
        """

        relative_path = asset.get("relative_path")

        if not relative_path:
            raise RuntimeError(
                f"Image asset has no path: "
                f"{asset.get('asset_id')}"
            )

        path = PurePosixPath(relative_path)
        parts = path.parts

        if len(parts) < 4 or parts[0].lower() != "images":
            raise RuntimeError(
                f"Unexpected image path structure: {relative_path}"
            )

        collection_label = parts[1]

        if collection_label.lower() == "crash scene":
            image_collection = "crash_scene"
            vehicle_label = parts[2]
            ciss_category = "Crash Scene"

        elif collection_label.lower() == "vehicle images":
            if len(parts) < 5:
                raise RuntimeError(
                    f"Incomplete vehicle-image path: {relative_path}"
                )

            image_collection = "vehicle_images"
            vehicle_label = parts[2]

            # Supports a nested category if CISS introduces one.
            ciss_category = "/".join(parts[3:-1])

        else:
            image_collection = self._normalize_category(
                collection_label
            )
            vehicle_label = parts[2]
            ciss_category = collection_label

        vehicle_number = self._extract_vehicle_number(
            vehicle_label
        )

        normalized_category = self._normalize_category(
            ciss_category
        )

        return {
            "asset_id": asset["asset_id"],
            "case_id": asset["case_id"],
            "vehicle_number": vehicle_number,
            "image_collection": image_collection,
            "ciss_category": ciss_category,
            "normalized_category": normalized_category,
            "relative_path": relative_path,
            "filename": asset.get("filename"),
            "size_bytes": asset.get("size_bytes"),
            "sha256": asset.get("sha256"),
            "expert_routes": self._expert_routes(
                image_collection,
                normalized_category,
            ),
            "processing_status": "not_processed",
            "semantic_file": None,
        }

    def _create_ciss_groups(self, images):
        """
        Group images using the original CISS categories.
        """

        grouped_images = defaultdict(list)

        for image in images:
            key = (
                image["image_collection"],
                image["vehicle_number"],
                image["normalized_category"],
            )

            grouped_images[key].append(image)

        groups = []

        for index, (key, members) in enumerate(
            sorted(
                grouped_images.items(),
                key=lambda item: (
                    item[0][0],
                    item[0][1] or -1,
                    item[0][2],
                ),
            ),
            start=1,
        ):
            collection, vehicle_number, category = key

            groups.append(
                {
                    "group_id": f"ciss_group_{index:03d}",
                    "group_type": "ciss_category",
                    "image_collection": collection,
                    "vehicle_number": vehicle_number,
                    "ciss_categories": sorted(
                        {
                            member["ciss_category"]
                            for member in members
                        }
                    ),
                    "normalized_category": category,
                    "asset_count": len(members),
                    "asset_ids": [
                        member["asset_id"]
                        for member in members
                    ],
                    "relative_paths": [
                        member["relative_path"]
                        for member in members
                    ],
                    "expert_routes": sorted(
                        {
                            route
                            for member in members
                            for route in member["expert_routes"]
                        }
                    ),
                }
            )

        return groups

    def _make_analysis_group(
        self,
        case_id,
        vehicle_number,
        group_name,
        members,
        expert_routes,
    ):
        """
        Create one multi-view analysis group.
        """

        if not members:
            return None

        members = sorted(
            members,
            key=lambda image: (
                image["normalized_category"],
                image["relative_path"],
            ),
        )

        return {
            "group_id": (
                f"case_{case_id}_vehicle_"
                f"{vehicle_number}_{group_name}"
            ),
            "group_type": "multi_view_analysis",
            "group_name": group_name,
            "vehicle_number": vehicle_number,
            "contributing_categories": sorted(
                {
                    image["normalized_category"]
                    for image in members
                }
            ),
            "asset_count": len(members),
            "asset_ids": [
                image["asset_id"]
                for image in members
            ],
            "relative_paths": [
                image["relative_path"]
                for image in members
            ],
            "expert_routes": expert_routes,
        }

    def _create_analysis_groups(self, case_id, images):
        """
        Build broader multi-view groups for expert VLM analysis.
        """

        groups = []
        vehicle_numbers = sorted(
            {
                image["vehicle_number"]
                for image in images
                if image["vehicle_number"] is not None
            }
        )

        for vehicle_number in vehicle_numbers:
            vehicle_images = [
                image
                for image in images
                if image["vehicle_number"] == vehicle_number
            ]

            detailed_vehicle_images = [
                image
                for image in vehicle_images
                if image["image_collection"] == "vehicle_images"
            ]

            crash_scene_images = [
                image
                for image in vehicle_images
                if image["image_collection"] == "crash_scene"
            ]

            group_definitions = [
                (
                    "front_damage",
                    [
                        image
                        for image in detailed_vehicle_images
                        if image["normalized_category"]
                        in self.FRONT_CATEGORIES
                    ],
                    [
                        "visual_evidence",
                        "vehicle_engineering",
                        "crash_mechanics",
                    ],
                ),
                (
                    "rear_damage",
                    [
                        image
                        for image in detailed_vehicle_images
                        if image["normalized_category"]
                        in self.REAR_CATEGORIES
                    ],
                    [
                        "visual_evidence",
                        "vehicle_engineering",
                        "crash_mechanics",
                    ],
                ),
                (
                    "left_side",
                    [
                        image
                        for image in detailed_vehicle_images
                        if image["normalized_category"]
                        in self.LEFT_CATEGORIES
                    ],
                    [
                        "visual_evidence",
                        "vehicle_engineering",
                        "crash_mechanics",
                    ],
                ),
                (
                    "right_side",
                    [
                        image
                        for image in detailed_vehicle_images
                        if image["normalized_category"]
                        in self.RIGHT_CATEGORIES
                    ],
                    [
                        "visual_evidence",
                        "vehicle_engineering",
                        "crash_mechanics",
                    ],
                ),
                (
                    "interior_safety",
                    [
                        image
                        for image in detailed_vehicle_images
                        if (
                            image["normalized_category"].startswith(
                                "interior_"
                            )
                            or image["normalized_category"] == "airbag"
                        )
                    ],
                    [
                        "visual_evidence",
                        "occupant_safety",
                        "vehicle_interior",
                        "safety_system",
                    ],
                ),
                (
                    "vehicle_overview",
                    [
                        image
                        for image in detailed_vehicle_images
                        if image["normalized_category"]
                        in self.EXTERIOR_CATEGORIES
                    ],
                    [
                        "visual_evidence",
                        "vehicle_engineering",
                        "crash_mechanics",
                    ],
                ),
                (
                    "safety_system",
                    [
                        image
                        for image in detailed_vehicle_images
                        if (
                            "airbag"
                            in image["normalized_category"]
                            or image["normalized_category"]
                            == "fuel_system"
                        )
                    ],
                    [
                        "visual_evidence",
                        "occupant_safety",
                        "safety_system",
                    ],
                ),
                (
                    "miscellaneous_unrouted",
                    [
                        image
                        for image in detailed_vehicle_images
                        if image["normalized_category"]
                        == "miscellaneous"
                    ],
                    [
                        "visual_evidence",
                        "image_router",
                    ],
                ),
                (
                    "crash_scene",
                    crash_scene_images,
                    [
                        "visual_evidence",
                        "roadway_scene",
                        "crash_mechanics",
                    ],
                ),
            ]

            for group_name, members, routes in group_definitions:
                group = self._make_analysis_group(
                    case_id=case_id,
                    vehicle_number=vehicle_number,
                    group_name=group_name,
                    members=members,
                    expert_routes=routes,
                )

                if group is not None:
                    groups.append(group)

        return groups

    def build(self, case_id, registry_path, output_path):
        """
        Build image_groups.json for one CISS case.
        """

        case_id = int(case_id)
        registry = self._load_json(registry_path)

        if registry.get("case_id") != case_id:
            raise RuntimeError(
                f"Registry case ID is {registry.get('case_id')}; "
                f"expected {case_id}."
            )

        image_assets = [
            asset
            for asset in registry.get("assets", [])
            if asset.get("asset_type") == "image"
        ]

        if not image_assets:
            raise RuntimeError(
                f"No image assets found for case {case_id}."
            )

        images = [
            self._parse_image(asset)
            for asset in image_assets
        ]

        images.sort(
            key=lambda image: (
                image["vehicle_number"] or -1,
                image["image_collection"],
                image["normalized_category"],
                image["relative_path"],
            )
        )

        ciss_groups = self._create_ciss_groups(images)
        analysis_groups = self._create_analysis_groups(
            case_id,
            images,
        )

        category_counts = Counter(
            image["normalized_category"]
            for image in images
        )

        output = {
            "schema_version": "1.0",
            "case_id": case_id,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "source_registry": Path(registry_path).as_posix(),
            "summary": {
                "total_images": len(images),
                "total_ciss_groups": len(ciss_groups),
                "total_analysis_groups": len(analysis_groups),
                "images_by_category": dict(
                    sorted(category_counts.items())
                ),
            },
            "images": images,
            "ciss_groups": ciss_groups,
            "analysis_groups": analysis_groups,
        }

        self._save_json(output, output_path)

        print(f"Image grouping created: {output_path}")
        print(f"Total images: {len(images)}")
        print(f"CISS groups: {len(ciss_groups)}")
        print(f"Analysis groups: {len(analysis_groups)}")

        return output
    