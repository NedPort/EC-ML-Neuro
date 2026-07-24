"""
API client for the NHTSA CISS Crash Viewer.
"""

import json
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from config.settings import (
    BASE_URL,
    CASE_SEARCH,
    CASE_SEARCH_CONVERGE,
    CASE_DETAILS,
    CASE_TREE,
    CV_ELEMENTS,
    CASE_DOWNLOAD,
    SCENE_DOWNLOAD,
    SCENE_FILE_DOWNLOAD,
    SKETCH_DOWNLOAD,
)

class CISSApi:
    """
    Simple API client for the Crash Viewer.
    """

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

        time.sleep(5)

        print("Browser ready.")


    def _fetch_json(self, endpoint, method="POST", body=None):
        """
        Execute a fetch() request inside the authenticated browser.
        """

        body_json = json.dumps(body) if body else "null"

        script = f"""
        const callback = arguments[arguments.length - 1];

        fetch("{endpoint}", {{
            method: "{method}",
            credentials: "same-origin",
            headers: {{
                "Content-Type": "application/json"
            }},
            body: {body_json}
        }})
        .then(async response => {{

            const text = await response.text();

            callback(JSON.stringify({{
                ok: response.ok,
                status: response.status,
                url: response.url,
                body: text
            }}));

        }})
        .catch(error => {{

            callback(JSON.stringify({{
                "__error__": error.toString()
            }}));

        }});
        """

        result = self.driver.execute_async_script(script)
        result = json.loads(result)

        if "__error__" in result:
            raise RuntimeError(result["__error__"])

        print(f"Status : {result['status']}")
        print(f"URL    : {result['url']}")

        if not result["ok"]:
            raise RuntimeError(
                f"HTTP {result['status']} returned from {result['url']}\n\n"
                f"{result['body'][:1000]}"
            )

        try:
            return json.loads(result["body"])

        except json.JSONDecodeError:

            raise RuntimeError(
                f"Response is not JSON.\n\n"
                f"{result['body'][:1000]}"
            )
    def _download_blob(self, endpoint, method="GET"):
        """
        Download binary files (ZIP, images, PDFs, etc.).
        """

        script = f"""
        const callback = arguments[arguments.length - 1];

        fetch("{endpoint}", {{
            method: "{method}",
            credentials: "same-origin"
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
        .catch(error => {{

            callback(JSON.stringify({{
                "__error__": error.toString()
            }}));

        }});
        """

        result = self.driver.execute_async_script(script)
        result = json.loads(result)

        if "__error__" in result:
            raise RuntimeError(result["__error__"])

        return bytes(result)

    def get_case_details(self, case_id):

        endpoint = f"{CASE_DETAILS}?caseID={case_id}"

        return self._fetch_json(endpoint)


    def get_case_tree(self, case_id):

        endpoint = f"{CASE_TREE}?caseID={case_id}"

        return self._fetch_json(endpoint)


    def get_cv_elements(self):

        return self._fetch_json(CV_ELEMENTS)

    def search_cases(self, payload):

        return self._fetch_json(
            CASE_SEARCH,
            method="POST",
            body=payload,
        )


    def search_cases_converge(self, payload):

        return self._fetch_json(
            CASE_SEARCH_CONVERGE,
            method="POST",
            body=payload,
        )        

    def download_case(self, case_id):

        endpoint = f"{CASE_DOWNLOAD}?caseID={case_id}"

        return self._download_blob(endpoint)


    def download_scene(self, case_id):

        endpoint = f"{SCENE_DOWNLOAD}?caseID={case_id}"

        return self._download_blob(endpoint)


    def download_scene_file(self, case_id, object_id):

        endpoint = (
            f"{SCENE_FILE_DOWNLOAD}/{case_id}"
            f"?objectId={object_id}"
        )

        return self._download_blob(endpoint)


    def download_sketch(self, case_id, object_id):

        endpoint = (
            f"{SKETCH_DOWNLOAD}/{case_id}"
            f"?objectId={object_id}"
        )

        return self._download_blob(endpoint)
    
    def close(self):

        self.driver.quit()


