"""
Configuration settings for the NHTSA Downloader.

This file stores all constants used throughout the project.
"""

# =============================================================================
# API CONFIGURATION
# =============================================================================

BASE_URL = "https://nrd.api.nhtsa.dot.gov/nhtsa"

VEHICLE_API = f"{BASE_URL}/vehicle/api/v1"

BIOMECHANICS_API = f"{BASE_URL}/biomechanics/api/v1"

# =============================================================================
# DOWNLOAD SETTINGS
# =============================================================================

PAGE_SIZE = 100

REQUEST_TIMEOUT = 30

# =============================================================================
# PROJECT DIRECTORIES
# =============================================================================

DATA_DIR = "data"

RAW_DATA_DIR = f"{DATA_DIR}/raw"

PROCESSED_DATA_DIR = f"{DATA_DIR}/processed"

LOG_DIR = f"{DATA_DIR}/logs"

# =============================================================================
# OUTPUT FILES
# =============================================================================

TEST_LIST_FILE = "vehicle_tests.csv"

LOG_FILE = "download.log"
