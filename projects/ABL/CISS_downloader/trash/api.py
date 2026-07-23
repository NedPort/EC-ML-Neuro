"""
Selenium-based API client for the NHTSA Crash Viewer (CISS).
"""

import json
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from .config import BASE_URL


class CISSApi:
    """API client using an authenticated Selenium browser."""

    def __init__(self, headless=False):

        options = Options()

        if headless:
            options.add_argument("--headless=new")

        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )

        print("Opening Crash Viewer...")

        self.driver.get(BASE_URL)

        # Allow Akamai / page initialization to complete
        time.sleep(5)

        print("Browser ready.")

    # ------------------------------------------------------------------
    # Generic Helpers
    # ------------------------------------------------------------------

    def _fetch_json(self, endpoint, method="POST", body=None):
        """
        Execute a fetch() request inside the authenticated browser.

        Parameters
        ----------
        endpoint : str
            API endpoint beginning with "/api/...".

        method : str
            HTTP method.

        body : dict | None
            JSON body for POST requests.

        Returns
        -------
        dict
        """

        body_json = json.dumps(body) if body else "null"

        script = f"""
        const callback = arguments[arguments.length - 1];

        fetch("{endpoint}", {{
            method: "{method}",
            headers: {{
                "Content-Type": "application/json"
            }},
            body: {body_json}
        }})
        .then(async response => {{

            if (!response.ok) {{
                throw new Error(
                    "HTTP " + response.status + " : " +
                    await response.text()
                );
            }}

            return response.json();

        }})
        .then(data => callback(JSON.stringify(data)))
        .catch(error => callback(JSON.stringify({{
            "__error__": error.toString()
        }})));
        """

        result = self.driver.execute_async_script(script)

        result = json.loads(result)

        if "__error__" in result:
            raise RuntimeError(result["__error__"])

        return result

    def _download_blob(self, endpoint, method="GET"):
        """
        Download binary data (ZIP, images, etc.) from the API.

        Returns
        -------
        bytes
        """

        script = f"""
        const callback = arguments[arguments.length - 1];

        fetch("{endpoint}", {{
            method: "{method}"
        }})
        .then(response => {{

            if (!response.ok)
                throw new Error("HTTP " + response.status);

            return response.arrayBuffer();

        }})
        .then(buffer => {{

            const bytes = Array.from(new Uint8Array(buffer));

            callback(JSON.stringify(bytes));

        }})
        .catch(error => callback(JSON.stringify({{
            "__error__": error.toString()
        }})));
        """

        result = self.driver.execute_async_script(script)

        result = json.loads(result)

        if isinstance(result, dict) and "__error__" in result:
            raise RuntimeError(result["__error__"])

        return bytes(result)

    # ------------------------------------------------------------------
    # Case Information
    # ------------------------------------------------------------------

    def get_case_details(self, case_id):
        """
        Retrieve complete metadata for a crash case.
        """

        endpoint = f"/api/case/GetCrashDetails?caseID={case_id}"

        return self._fetch_json(endpoint)

    def get_case_tree(self, case_id):
        """
        Retrieve the navigation tree.
        """

        endpoint = f"/api/case/CaseOverviewTreeResult?caseID={case_id}"

        return self._fetch_json(endpoint)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_cases(self, payload):
        """
        Search the CISS database.

        payload should be the same JSON used by the website.
        """

        endpoint = "/api/case/cases/search"

        return self._fetch_json(
            endpoint,
            method="POST",
            body=payload,
        )

    def search_cases_converge(self, payload):

        endpoint = "/api/case/cases/search/converge"

        return self._fetch_json(
            endpoint,
            method="POST",
            body=payload,
        )

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    def download_case_zip(self, case_id):

        endpoint = f"/api/case/Download?caseId={case_id}"

        return self._download_blob(endpoint)

    def download_scene(self, case_id):

        endpoint = f"/api/case/scenes/download?caseID={case_id}"

        return self._download_blob(endpoint)

    def download_scene_file(self, case_id, object_id):

        endpoint = (
            f"/api/case/scenefiles/download/"
            f"{case_id}?objectId={object_id}"
        )

        return self._download_blob(endpoint)

    def download_sketch(self, case_id, object_id):

        endpoint = (
            f"/api/case/sketches-iv/download/"
            f"{case_id}?objectId={object_id}"
        )

        return self._download_blob(endpoint)

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def close(self):
        """Close the browser."""

        self.driver.quit()
        