"""
API client for the NHTSA CISS Crash Viewer.
"""

import json
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config.settings import BASE_URL


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


    def _fetch_json(self, endpoint):
        """
        Execute a fetch() request inside the authenticated browser.
        """

        script = f"""
        const callback = arguments[arguments.length - 1];

        fetch("{endpoint}", {{
            method: "POST",
            credentials: "same-origin"
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

        # Debug output
        print(f"Status : {result['status']}")
        print(f"URL    : {result['url']}")
        print(f"Body   :\n{result['body'][:1000]}")  # Print first 1000 characters

        if not result["ok"]:
            raise RuntimeError(
                f"HTTP {result['status']} returned from {result['url']}"
            )

        try:
            return json.loads(result["body"])
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Response is not valid JSON.\n\n{result['body'][:1000]}"
            )

    def get_case_tree(self, case_id):
        """
        Retrieve the navigation tree.
        """

        endpoint = f"/api/case/CaseOverviewTreeResult?caseID={case_id}"

        return self._fetch_json(endpoint)

    def close(self):

        self.driver.quit()
        