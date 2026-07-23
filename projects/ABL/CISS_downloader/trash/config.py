"""
Configuration file for the CISS Downloader.

This file contains API endpoints, request settings, and project paths.
"""

from pathlib import Path

# =============================================================================
# Project Paths
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# API Configuration
# =============================================================================

BASE_URL = "https://crashviewer.nhtsa.dot.gov"

# API Endpoints
SEARCH_ENDPOINT = "/api/case/cases/search"
SEARCH_CONVERGE_ENDPOINT = "/api/case/cases/search/converge"

CASE_DETAILS_ENDPOINT = "/api/case/GetCrashDetails"
CASE_TREE_ENDPOINT = "/api/case/CaseOverviewTreeResult"
CV_ELEMENTS_ENDPOINT = "/api/Util/GetCvElements"

CASE_DOWNLOAD_ENDPOINT = "/api/case/Download"
SCENE_DOWNLOAD_ENDPOINT = "/api/case/scenes/download"
SCENE_FILE_DOWNLOAD_ENDPOINT = "/api/case/scenefiles/download"
SKETCH_DOWNLOAD_ENDPOINT = "/api/case/sketches-iv/download"

# =============================================================================
# Request Configuration
# =============================================================================

REQUEST_TIMEOUT = 30          # seconds
PAGE_SIZE = 25
MAX_RETRIES = 3

# =============================================================================
# HTTP Headers
# =============================================================================

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Origin": "https://crashviewer.nhtsa.dot.gov",
    "Referer": "https://crashviewer.nhtsa.dot.gov/",
}

