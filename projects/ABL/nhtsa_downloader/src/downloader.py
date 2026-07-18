import json
from pathlib import Path

import requests

from .api import get_documents, get_test_detail, get_test_numbers



# Default filenames
METADATA_FILENAME = "metadata.json"
EV_FILENAME = "ev.zip"
UDS_FILENAME = "uds.zip"
ABF_FILENAME = "data.abf"
ISO_FILENAME = "iso.zip"
TDMS_FILENAME = "tdms.zip"


def download_file(url: str, output_path: Path, overwrite: bool = False) -> None:
    """
    Download a file from a URL.

    Parameters
    ----------
    url : str
        File URL.
    output_path : Path
        Destination path.
    overwrite : bool
        Whether to overwrite an existing file.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        print(f"Skipping existing file: {output_path.name}")
        return

    print(f"Downloading {output_path.name}...")

    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    print(f"Saved: {output_path}")



def download_test_files(
    test_number: int,
    download_metadata: bool = True,
    download_ev: bool = True,
    download_uds: bool = True,
    download_abf: bool = True,
    download_iso: bool = True,
    download_tdms: bool = True,
    download_videos: bool = False,
    download_photos: bool = False,
    overwrite: bool = False,
):
    """
    Download selected files associated with a single NHTSA crash test.

    Parameters
    ----------
    test_number : int
        Unique NHTSA crash test identifier.

    download_metadata : bool, optional
        Download the metadata JSON file containing crash test information,
        vehicle specifications, occupant data, instrumentation details,
        available download links, videos, and photos.

    download_ev : bool, optional
        Download the EV archive containing the standard NHTSA signal exports
        (typically TSV time-history files for all recorded sensor channels).

    download_uds : bool, optional
        Download the UDS (Universal Data Set) archive when available.
        UDS is a common biomechanics/crash-test data format supported by
        many analysis tools.

    download_abf : bool, optional
        Download the ABF (ATB Binary File) when available.
        These files are primarily intended for Articulated Total Body (ATB)
        occupant simulations and advanced biomechanics software.

    download_iso : bool, optional
        Download the ISO archive when available.
        ISO files store crash measurement data using an international
        standardized exchange format.

    download_tdms : bool, optional
        Download the TDMS (Technical Data Management Streaming) archive
        when available. TDMS is the native measurement format used by
        National Instruments (LabVIEW/DIAdem).

    download_videos : bool, optional
        Download all crash test videos associated with the test.
        Disabled by default because video files require substantial storage.

    download_photos : bool, optional
        Download all crash test photographs associated with the test.
        Disabled by default because they are not required for most
        signal-processing workflows.

    overwrite : bool, optional
        If True, existing files will be replaced. Otherwise, previously
        downloaded files are skipped.
    """
    
    print(f"\n========== Test {test_number} ==========")

    output_dir = Path("data") / str(test_number)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Save metadata
    # ------------------------------------------------------------------
    if download_metadata:

        metadata = get_test_detail(test_number)

        metadata_path = output_dir / METADATA_FILENAME

        if not metadata_path.exists() or overwrite:

            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)

            print(f"Saved: {metadata_path}")

        else:
            print(f"Skipping existing file: {metadata_path.name}")

    # ------------------------------------------------------------------
    # Get download URLs
    # ------------------------------------------------------------------
    documents = get_documents(test_number)

    if not documents.get("results"):
        print("No downloadable files found.")
        return

    document = documents["results"][0]

    downloads = [
        ("evFiles", download_ev, EV_FILENAME),
        ("udsFiles", download_uds, UDS_FILENAME),
        ("abfFiles", download_abf, ABF_FILENAME),
        ("isoFiles", download_iso, ISO_FILENAME),
        ("tdmsFiles", download_tdms, TDMS_FILENAME),
    ]

    # ------------------------------------------------------------------
    # Download requested files
    # ------------------------------------------------------------------
    for api_key, enabled, filename in downloads:

        if not enabled:
            continue

        url = document.get(api_key)

        if not url:
            print(f"{api_key} not available.")
            continue

        download_file(
            url=url,
            output_path=output_dir / filename,
            overwrite=overwrite,
        )

    print(f"Finished downloading test {test_number}.")

from .api import get_test_numbers


def download_all_tests(
    start_page=0,
    end_page=None,
    max_tests=None,
):
    """
    Download crash tests from the NHTSA database.

    Parameters
    ----------
    start_page : int
        First API page to download.

    end_page : int | None
        Last API page to download.
        If None, continue until the API has no more pages.

    max_tests : int | None
        Maximum number of tests to download.
        If None, download all tests.
    """

    page = start_page
    downloaded = 0

    while True:

        if end_page is not None and page > end_page:
            break

        print(f"\n========== Reading page {page} ==========")

        test_numbers = get_test_numbers(page)

        if not test_numbers:
            print("No more crash tests found.")
            break

        for test_number in test_numbers:

            if max_tests is not None and downloaded >= max_tests:
                print("Reached requested number of downloads.")
                return

            try:
                download_test_files(test_number)
                downloaded += 1

            except Exception as e:
                print(f"Failed {test_number}: {e}")

        page += 1
