"""
Build an inventory of assets contained in a CISS case archive.
"""

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


class AssetRegistry:
    """
    Create a structured registry of extracted case assets.
    """

    def _calculate_sha256(self, file_path):
        """
        Calculate a file checksum for integrity and reproducibility.
        """

        file_hash = sha256()

        with Path(file_path).open("rb") as input_file:
            for chunk in iter(
                lambda: input_file.read(1024 * 1024),
                b"",
            ):
                file_hash.update(chunk)

        return file_hash.hexdigest()

    def _classify_asset(self, relative_path):
        """
        Classify an asset using its top-level archive folder.
        """

        top_level_folder = relative_path.parts[0].lower()

        if top_level_folder == "images":
            return "image"

        if top_level_folder == "docs":
            return "document"

        if top_level_folder in {
            "sketchesev",
            "sketchesiv",
            "sketchesss",
        }:
            return "sketch"

        return "unknown"

    def build(self, case_id, extracted_directory, output_path):
        """
        Scan an extracted case and create assets.json.
        """

        extracted_directory = Path(extracted_directory)
        output_path = Path(output_path)

        if not extracted_directory.exists():
            raise FileNotFoundError(
                f"Extraction directory does not exist: "
                f"{extracted_directory}"
            )

        files = sorted(
            path
            for path in extracted_directory.rglob("*")
            if path.is_file()
        )

        if not files:
            raise RuntimeError(
                f"No files found in {extracted_directory}"
            )

        assets = []
        type_counts = Counter()
        total_bytes = 0

        for index, file_path in enumerate(files, start=1):
            relative_path = file_path.relative_to(
                extracted_directory
            )

            asset_type = self._classify_asset(relative_path)
            size_bytes = file_path.stat().st_size

            type_counts[asset_type] += 1
            total_bytes += size_bytes

            assets.append(
                {
                    "asset_id": f"case_{case_id}_asset_{index:04d}",
                    "case_id": int(case_id),
                    "asset_type": asset_type,
                    "collection": relative_path.parts[0],
                    "relative_path": relative_path.as_posix(),
                    "parent_group": relative_path.parent.as_posix(),
                    "filename": file_path.name,
                    "extension": file_path.suffix.lower(),
                    "size_bytes": size_bytes,
                    "sha256": self._calculate_sha256(file_path),
                    "object_id": None,
                    "status": "discovered",
                    "semantic_file": None,
                }
            )

        registry = {
            "schema_version": "1.0",
            "case_id": int(case_id),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "type": "ciss_case_archive",
                "archive_name": f"case_{case_id}.zip",
            },
            "summary": {
                "total_assets": len(assets),
                "total_bytes": total_bytes,
                "assets_by_type": dict(sorted(type_counts.items())),
            },
            "assets": assets,
        }

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                registry,
                output_file,
                indent=2,
                ensure_ascii=False,
            )

        print(f"Asset registry created: {output_path}")
        print(f"Total assets: {len(assets)}")

        for asset_type, count in sorted(type_counts.items()):
            print(f"  {asset_type}: {count}")

        return registry
    