"""
Case-level archive extraction and processing.
"""
import json
from pathlib import Path
import zipfile
from pathlib import Path
import zipfile


class CaseDownloader:
    """
    Manage the downloaded archive for a single CISS case.
    """

    def __init__(self, api=None):
        self.api = api

    def _save_json(self, data, output_path):
        """
        Save JSON atomically to avoid incomplete permanent files.
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

        print(f"Saved: {output_path}")

    def save_case_records(self, case_id, output_directory):
        """
        Retrieve and save case metadata and navigation tree.
        """

        if self.api is None:
            raise RuntimeError(
                "CISSApi is required to retrieve case records."
            )

        output_directory = Path(output_directory)

        print(f"Retrieving metadata for case {case_id}...")
        metadata = self.api.get_case_details(case_id)

        print(f"Retrieving navigation tree for case {case_id}...")
        navigation_tree = self.api.get_case_tree(case_id)

        metadata_path = output_directory / "metadata.json"
        tree_path = output_directory / "navigation_tree.json"

        self._save_json(metadata, metadata_path)
        self._save_json(navigation_tree, tree_path)

        return {
            "metadata_path": metadata_path,
            "navigation_tree_path": tree_path,
        }

    def extract_case_zip(self, zip_path, extraction_directory):
        """
        Validate and safely extract a case ZIP archive.
        """

        zip_path = Path(zip_path)
        extraction_directory = Path(extraction_directory)

        if not zip_path.exists():
            raise FileNotFoundError(
                f"Case ZIP does not exist: {zip_path}"
            )

        if not zipfile.is_zipfile(zip_path):
            raise RuntimeError(
                f"File is not a valid ZIP archive: {zip_path}"
            )

        extraction_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Prevent mixing files from different extraction attempts.
        if any(extraction_directory.iterdir()):
            raise RuntimeError(
                "Extraction directory is not empty: "
                f"{extraction_directory}"
            )

        extraction_root = extraction_directory.resolve()

        with zipfile.ZipFile(zip_path, "r") as archive:
            members = archive.infolist()

            # Protect against unsafe paths such as ../../file.txt.
            for member in members:
                destination = (
                    extraction_root / member.filename
                ).resolve()

                try:
                    destination.relative_to(extraction_root)
                except ValueError:
                    raise RuntimeError(
                        f"Unsafe path found in ZIP: {member.filename}"
                    )

            archive.extractall(extraction_root)

        extracted_files = [
            path
            for path in extraction_root.rglob("*")
            if path.is_file()
        ]

        total_bytes = sum(
            path.stat().st_size
            for path in extracted_files
        )

        total_mb = total_bytes / (1024 * 1024)

        print(f"Extracted case archive: {zip_path}")
        print(f"Destination: {extraction_root}")
        print(f"Files extracted: {len(extracted_files)}")
        print(f"Extracted size: {total_mb:.2f} MB")

        return extraction_root
    