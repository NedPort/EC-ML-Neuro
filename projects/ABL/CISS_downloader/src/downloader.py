"""
High-level downloader for the NHTSA CISS database.
"""

import json
from pathlib import Path

from .api import CISSApi
from .config import DATA_DIR


class CISSDownloader:
    """Download CISS crash cases."""

    def __init__(self, api=None):
        self.api = api if api else CISSApi()

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _case_dir(self, case_id: int) -> Path:
        """Create (if necessary) and return the case directory."""

        case_dir = DATA_DIR / str(case_id)
        case_dir.mkdir(parents=True, exist_ok=True)

        return case_dir

    @staticmethod
    def _save_json(data, filename: Path):

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def _save_binary(data: bytes, filename: Path):

        with open(filename, "wb") as f:
            f.write(data)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def download_metadata(self, case_id, overwrite=False):

        case_dir = self._case_dir(case_id)

        output = case_dir / "metadata.json"

        if output.exists() and not overwrite:
            print(f"[SKIP] metadata.json already exists ({case_id})")
            return output

        print(f"[INFO] Downloading metadata for case {case_id}")

        metadata = self.api.get_case_details(case_id)

        self._save_json(metadata, output)

        print("[DONE] metadata.json")

        return output

    # ------------------------------------------------------------------
    # ZIP Package
    # ------------------------------------------------------------------

    def download_case_zip(self, case_id, overwrite=False):

        case_dir = self._case_dir(case_id)

        output = case_dir / "case.zip"

        if output.exists() and not overwrite:
            print(f"[SKIP] case.zip already exists ({case_id})")
            return output

        print(f"[INFO] Downloading case ZIP for {case_id}")

        data = self.api.download_case_zip(case_id)

        self._save_binary(data, output)

        print("[DONE] case.zip")

        return output

    # ------------------------------------------------------------------
    # Main Download
    # ------------------------------------------------------------------

    def download_case(self, case_id, overwrite=False):

        print("=" * 60)
        print(f"Downloading Case {case_id}")
        print("=" * 60)

        # Metadata
        self.download_metadata(case_id, overwrite)

        # Uncomment once the endpoints are verified.
        #
        # self.download_case_zip(case_id, overwrite)
        # self.download_scene(case_id, overwrite)
        # self.download_sketches(case_id, overwrite)

        print(f"[COMPLETE] Case {case_id}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):

        self.api.close()