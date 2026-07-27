"""
Validate a persistent CISS case package and create its manifest.
"""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

class CaseValidator:
    """
    Validate case records and confirm readiness for semantic processing.
    """

    def _load_json(self, file_path):
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"Required file is missing: {file_path}"
            )

        try:
            with file_path.open("r", encoding="utf-8") as input_file:
                return json.load(input_file)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Invalid JSON file: {file_path}"
            ) from error

    def _save_json(self, data, output_path):
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

    def validate(
        self,
        case_id,
        case_directory,
        extracted_directory,
    ):
        """
        Validate the three persistent JSON files and temporary assets.
        """

        case_id = int(case_id)
        case_directory = Path(case_directory)
        extracted_directory = Path(extracted_directory)

        errors = []
        warnings = []

        metadata_path = case_directory / "metadata.json"
        tree_path = case_directory / "navigation_tree.json"
        assets_path = case_directory / "assets.json"
        export_path = case_directory / "export.xlsx"
        manifest_path = case_directory / "manifest.json"

        # Load the persistent files.
        metadata = self._load_json(metadata_path)
        navigation_tree = self._load_json(tree_path)
        registry = self._load_json(assets_path)

        # Validate metadata case ID.
        metadata_case_id = (
            metadata.get("crashSummary", {}).get("caseId")
            if isinstance(metadata, dict)
            else None
        )

        if metadata_case_id != case_id:
            errors.append(
                f"Metadata case ID is {metadata_case_id}; "
                f"expected {case_id}."
            )

        # Validate navigation tree.
        if not navigation_tree:
            errors.append("Navigation tree is empty.")

        # Validate registry case ID.
        if registry.get("case_id") != case_id:
            errors.append(
                f"Asset registry case ID is "
                f"{registry.get('case_id')}; expected {case_id}."
            )

        assets = registry.get("assets", [])

        if not assets:
            errors.append("Asset registry contains no assets.")

        # Check for duplicate asset IDs.
        asset_ids = [
            asset.get("asset_id")
            for asset in assets
        ]

        if len(asset_ids) != len(set(asset_ids)):
            errors.append("Duplicate asset IDs were found.")

        # Validate temporary files against the registry.
        missing_assets = []
        size_mismatches = []

        for asset in assets:
            relative_path = asset.get("relative_path")

            if not relative_path:
                errors.append(
                    f"Asset {asset.get('asset_id')} has no relative path."
                )
                continue

            file_path = extracted_directory / relative_path

            if not file_path.exists():
                missing_assets.append(relative_path)
                continue

            expected_size = asset.get("size_bytes")
            actual_size = file_path.stat().st_size

            if expected_size != actual_size:
                size_mismatches.append(relative_path)

        if missing_assets:
            errors.append(
                f"{len(missing_assets)} registered assets are missing."
            )

        if size_mismatches:
            errors.append(
                f"{len(size_mismatches)} assets have incorrect sizes."
            )

        if not extracted_directory.exists():
            warnings.append(
                "Temporary extraction directory is unavailable."
            )

        asset_counts = Counter(
            asset.get("asset_type", "unknown")
            for asset in assets
        )

        total_bytes = sum(
            asset.get("size_bytes", 0)
            for asset in assets
        )



        # Validate export.xlsx.
        export_valid = False

        if not export_path.exists():
            errors.append("Required Excel export is missing.")

        elif not zipfile.is_zipfile(export_path):
            errors.append("Excel export is not a valid XLSX package.")

        else:
            with zipfile.ZipFile(export_path, "r") as workbook:
                workbook_files = set(workbook.namelist())

                required_workbook_files = {
                    "[Content_Types].xml",
                    "xl/workbook.xml",
                }

                export_valid = required_workbook_files.issubset(
                    workbook_files
                )

            if not export_valid:
                errors.append(
                    "Excel export does not contain a valid workbook."
                )

        validation_passed = len(errors) == 0

        manifest = {
            "schema_version": "1.0",
            "case_id": case_id,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": (
                "ready_for_semantic_processing"
                if validation_passed
                else "validation_failed"
            ),
            "persistent_files": {
                "metadata": metadata_path.exists(),
                "navigation_tree": tree_path.exists(),
                "asset_registry": assets_path.exists(),
                "excel_export": export_valid,
            },
            "asset_summary": {
                "total_assets": len(assets),
                "total_bytes": total_bytes,
                "assets_by_type": dict(
                    sorted(asset_counts.items())
                ),
            },
            "temporary_workspace": {
                "available": extracted_directory.exists(),
                "directory": extracted_directory.as_posix(),
                "missing_assets": len(missing_assets),
                "size_mismatches": len(size_mismatches),
            },
            "validation": {
                "passed": validation_passed,
                "errors": errors,
                "warnings": warnings,
            },
        }

        self._save_json(manifest, manifest_path)

        print(f"Manifest created: {manifest_path}")
        print(f"Status: {manifest['status']}")
        print(f"Assets validated: {len(assets)}")

        if errors:
            print("Validation errors:")

            for error in errors:
                print(f"  - {error}")

        if warnings:
            print("Validation warnings:")

            for warning in warnings:
                print(f"  - {warning}")

        return manifest
    