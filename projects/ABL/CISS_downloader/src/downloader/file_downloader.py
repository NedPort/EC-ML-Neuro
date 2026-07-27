"""
Streaming downloader for binary CISS files.
"""

from pathlib import Path
import zipfile

import requests

from config.settings import CASE_DOWNLOAD, CASE_EXPORT
from urllib.parse import urljoin

class FileDownloader:
    """
    Download large CISS files using the authenticated Selenium session.
    """

    def __init__(self, api, chunk_size=1024 * 1024):
        self.api = api
        self.chunk_size = chunk_size

    def _create_authenticated_session(self):
        """
        Copy authentication cookies from Selenium into requests.
        """

        session = requests.Session()

        for cookie in self.api.driver.get_cookies():
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

        user_agent = self.api.driver.execute_script(
            "return navigator.userAgent;"
        )

        session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain, */*",
                "Referer": self.api.driver.current_url,
            }
        )

        return session

    def download_case_zip(self, case_id, destination):
        """
        Stream a complete case ZIP into a temporary location.
        """

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary_path = destination.with_suffix(
            destination.suffix + ".part"
        )


        relative_endpoint = f"{CASE_DOWNLOAD}?caseId={case_id}"

        endpoint = urljoin(
            self.api.driver.current_url,
            relative_endpoint,
        )

        session = self._create_authenticated_session()

        print(f"Downloading case {case_id}...")
        print(f"URL: {endpoint}")

        try:
            with session.get(
                endpoint,
                stream=True,
                timeout=(30, 300),
            ) as response:
                response.raise_for_status()

                total_bytes = 0

                with temporary_path.open("wb") as output_file:
                    for chunk in response.iter_content(
                        chunk_size=self.chunk_size
                    ):
                        if not chunk:
                            continue

                        output_file.write(chunk)
                        total_bytes += len(chunk)

            if not zipfile.is_zipfile(temporary_path):
                raise RuntimeError(
                    "The downloaded response is not a valid ZIP file."
                )

            temporary_path.replace(destination)

            size_mb = total_bytes / (1024 * 1024)

            print(f"Download complete: {destination}")
            print(f"Downloaded size: {size_mb:.2f} MB")
            print("ZIP validation: passed")

            return destination

        except Exception:
            if temporary_path.exists():
                temporary_path.unlink()

            raise

        finally:
            session.close()







    def download_case_export(
        self,
        case_id,
        destination,
        mode=1,
        is_nonmotorist=False,
    ):
        """
        Download the structured CISS Excel export.
        """

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary_path = destination.with_suffix(
            destination.suffix + ".part"
        )

        endpoint = urljoin(
            self.api.driver.current_url,
            CASE_EXPORT,
        )

        parameters = {
            "mode": mode,
            "caseId": case_id,
            "isNonmotorist": str(is_nonmotorist).lower(),
        }

        session = self._create_authenticated_session()

        print(f"Downloading Excel export for case {case_id}...")

        try:
            with session.get(
                endpoint,
                params=parameters,
                stream=True,
                timeout=(30, 300),
            ) as response:
                response.raise_for_status()

                print(f"URL: {response.url}")

                total_bytes = 0

                with temporary_path.open("wb") as output_file:
                    for chunk in response.iter_content(
                        chunk_size=self.chunk_size
                    ):
                        if not chunk:
                            continue

                        output_file.write(chunk)
                        total_bytes += len(chunk)

            # XLSX files are ZIP-based packages.
            if not zipfile.is_zipfile(temporary_path):
                raise RuntimeError(
                    "The exported response is not a valid XLSX file."
                )

            # Confirm that it is an Excel workbook, not an arbitrary ZIP.
            with zipfile.ZipFile(temporary_path, "r") as workbook:
                workbook_files = set(workbook.namelist())

                required_files = {
                    "[Content_Types].xml",
                    "xl/workbook.xml",
                }

                if not required_files.issubset(workbook_files):
                    raise RuntimeError(
                        "The downloaded file is a ZIP, but it is not "
                        "a valid Excel workbook."
                    )

            temporary_path.replace(destination)

            size_kb = total_bytes / 1024

            print(f"Excel export saved: {destination}")
            print(f"Downloaded size: {size_kb:.2f} KB")
            print("XLSX validation: passed")

            return destination

        except Exception:
            if temporary_path.exists():
                temporary_path.unlink()

            raise

        finally:
            session.close()