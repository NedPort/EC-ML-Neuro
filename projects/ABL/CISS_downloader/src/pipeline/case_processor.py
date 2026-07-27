"""
End-to-end processing pipeline for one CISS case.
"""

import json
from pathlib import Path
import zipfile

from src.downloader.case_downloader import CaseDownloader
from src.downloader.file_downloader import FileDownloader
from src.registry.asset_registry import AssetRegistry
from src.validator.case_validator import CaseValidator


class CaseProcessor:
    """
    Build and validate the persistent package for one CISS case.
    """

    def __init__(self, api, data_root="data"):
        self.api = api
        self.data_root = Path(data_root)

        self.file_downloader = FileDownloader(api)
        self.case_downloader = CaseDownloader(api)
        self.registry_builder = AssetRegistry()
        self.validator = CaseValidator()

    def _is_valid_json(self, file_path):
        file_path = Path(file_path)

        if not file_path.exists():
            return False

        try:
            with file_path.open(
                "r",
                encoding="utf-8",
            ) as input_file:
                data = json.load(input_file)

            return bool(data)

        except (OSError, json.JSONDecodeError):
            return False

    def _is_valid_xlsx(self, file_path):
        file_path = Path(file_path)

        if not file_path.exists():
            return False

        if not zipfile.is_zipfile(file_path):
            return False

        with zipfile.ZipFile(file_path, "r") as workbook:
            workbook_files = set(workbook.namelist())

        required_files = {
            "[Content_Types].xml",
            "xl/workbook.xml",
        }

        return required_files.issubset(workbook_files)

    def _extraction_matches_archive(
        self,
        archive_path,
        extracted_directory,
    ):
        """
        Confirm that every file in the ZIP exists after extraction.
        """

        archive_path = Path(archive_path)
        extracted_directory = Path(extracted_directory)

        if not zipfile.is_zipfile(archive_path):
            return False

        if not extracted_directory.exists():
            return False

        with zipfile.ZipFile(archive_path, "r") as archive:
            archive_files = {
                member.filename.replace("\\", "/")
                for member in archive.infolist()
                if not member.is_dir()
            }

        extracted_files = {
            path.relative_to(extracted_directory).as_posix()
            for path in extracted_directory.rglob("*")
            if path.is_file()
        }

        return archive_files == extracted_files

    def _registry_matches_extraction(
        self,
        registry_path,
        extracted_directory,
        case_id,
    ):
        """
        Confirm that an existing registry matches extracted files.
        """

        registry_path = Path(registry_path)
        extracted_directory = Path(extracted_directory)

        if not self._is_valid_json(registry_path):
            return False

        try:
            with registry_path.open(
                "r",
                encoding="utf-8",
            ) as input_file:
                registry = json.load(input_file)

            if registry.get("case_id") != int(case_id):
                return False

            registered_files = {
                asset["relative_path"]
                for asset in registry.get("assets", [])
                if asset.get("relative_path")
            }

            extracted_files = {
                path.relative_to(extracted_directory).as_posix()
                for path in extracted_directory.rglob("*")
                if path.is_file()
            }

            return (
                bool(registered_files)
                and registered_files == extracted_files
            )

        except (KeyError, OSError, json.JSONDecodeError):
            return False

    def process_case(self, case_id):
        """
        Download, extract, inventory, and validate one CISS case.
        """

        case_id = int(case_id)

        case_directory = (
            self.data_root / "raw" / str(case_id)
        )

        temporary_directory = (
            self.data_root / "temp" / str(case_id)
        )

        archive_path = (
            temporary_directory / f"case_{case_id}.zip"
        )

        extracted_directory = (
            temporary_directory / "extracted"
        )

        metadata_path = case_directory / "metadata.json"
        tree_path = case_directory / "navigation_tree.json"
        registry_path = case_directory / "assets.json"
        export_path = case_directory / "export.xlsx"

        case_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        print()
        print(f"Processing CISS case {case_id}")
        print("=" * 50)

        # Stage 1: Structured case records
        if (
            self._is_valid_json(metadata_path)
            and self._is_valid_json(tree_path)
        ):
            print("Metadata and navigation tree already exist.")
        else:
            self.case_downloader.save_case_records(
                case_id=case_id,
                output_directory=case_directory,
            )

        # Stage 2: Complete case archive
        if zipfile.is_zipfile(archive_path):
            print(f"Case ZIP already exists: {archive_path}")
        else:
            self.file_downloader.download_case_zip(
                case_id=case_id,
                destination=archive_path,
            )

        # Stage 3: Archive extraction
        if self._extraction_matches_archive(
            archive_path,
            extracted_directory,
        ):
            print("Existing extraction is complete.")
        else:
            if (
                extracted_directory.exists()
                and any(extracted_directory.iterdir())
            ):
                raise RuntimeError(
                    "The extraction directory exists but does not "
                    "match the ZIP archive. Inspect or remove this "
                    f"specific directory before retrying: "
                    f"{extracted_directory}"
                )

            self.case_downloader.extract_case_zip(
                zip_path=archive_path,
                extraction_directory=extracted_directory,
            )

        # Stage 4: Asset registry
        if self._registry_matches_extraction(
            registry_path,
            extracted_directory,
            case_id,
        ):
            print("Existing asset registry matches extraction.")
        else:
            self.registry_builder.build(
                case_id=case_id,
                extracted_directory=extracted_directory,
                output_path=registry_path,
            )

        # Stage 5: Structured Excel export
        if self._is_valid_xlsx(export_path):
            print(f"Excel export already exists: {export_path}")
        else:
            self.file_downloader.download_case_export(
                case_id=case_id,
                destination=export_path,
            )

        # Stage 6: Final validation
        manifest = self.validator.validate(
            case_id=case_id,
            case_directory=case_directory,
            extracted_directory=extracted_directory,
        )

        print("=" * 50)
        print(
            f"Case {case_id} finished with status: "
            f"{manifest['status']}"
        )

        return manifest
    