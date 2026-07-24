"""
Project configuration.
"""

BASE_URL = "https://crashviewer.nhtsa.dot.gov"


CASE_SEARCH = "/api/case/cases/search"
CASE_SEARCH_CONVERGE = "/api/case/cases/search/converge"

CASE_DETAILS = "/api/case/GetCrashDetails"
CASE_TREE = "/api/case/CaseOverviewTreeResult"
CV_ELEMENTS = "/api/Util/GetCvElements"

CASE_DOWNLOAD = "/api/case/Download"
SCENE_DOWNLOAD = "/api/case/scenes/download"
SCENE_FILE_DOWNLOAD = "/api/case/scenefiles/download"
SKETCH_DOWNLOAD = "/api/case/sketches-iv/download"
