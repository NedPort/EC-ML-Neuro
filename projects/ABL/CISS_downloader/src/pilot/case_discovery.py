"""
Discover CISS case IDs from the public Crash Viewer search results.

This module reads case IDs from the search-results table. It does not
open or download individual cases.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Iterable

from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait


CATALOG_SCHEMA_VERSION = "1.0"

SEARCH_PAGE_URL = (
    "https://crashviewer.nhtsa.dot.gov/ciss/searchfilter"
)

SEARCH_RESULTS_URL_FRAGMENT = "/ciss/search-results"

CASE_LINK_SELECTOR = 'a[href*="/ciss/details/"]'

CASE_ID_PATTERN = re.compile(
    r"/ciss/details/(\d+)/",
    flags=re.IGNORECASE,
)


class CaseDiscovery:
    """
    Discover unique CISS case IDs through the public search interface.
    """

    def __init__(
        self,
        driver,
        data_root: str | Path = "data",
        timeout: int = 30,
    ) -> None:
        self.driver = driver
        self.data_root = Path(data_root)
        self.timeout = timeout

        self.catalog_path = (
            self.data_root
            / "manifests"
            / "ciss_case_catalog.json"
        )

    def discover(
        self,
        limit: int | None = None,
        excluded_case_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """
        Discover case IDs.

        Parameters
        ----------
        limit:
            Maximum number of new case IDs to return. If None, all
            available search-result pages are processed.

        excluded_case_ids:
            Case IDs that should not be returned, such as cases already
            registered in the pilot manifest.
        """

        if limit is not None and limit < 1:
            raise ValueError("limit must be a positive integer or None")

        excluded_ids = {
            int(case_id)
            for case_id in (excluded_case_ids or [])
        }

        discovered_ids: list[int] = []
        discovered_set: set[int] = set()
        scanned_ids: set[int] = set()

        print("Opening CISS case search...")
        self.driver.get(SEARCH_PAGE_URL)

        self._submit_blank_search()
        self._set_page_size(100)

        page_number = 1
        reached_last_page = False

        while True:
            self._wait_for_case_links()

            page_ids = self._extract_current_page_ids()

            if not page_ids:
                raise RuntimeError(
                    f"No CISS case IDs were found on page {page_number}."
                )

            for case_id in page_ids:
                scanned_ids.add(case_id)

                if case_id in excluded_ids:
                    continue

                if case_id in discovered_set:
                    continue

                discovered_set.add(case_id)
                discovered_ids.append(case_id)

                if (
                    limit is not None
                    and len(discovered_ids) >= limit
                ):
                    break

            print(
                f"Catalog page {page_number}: "
                f"{len(page_ids)} IDs read; "
                f"{len(discovered_ids)} new IDs selected."
            )

            if (
                limit is not None
                and len(discovered_ids) >= limit
            ):
                break

            if not self._go_to_next_page(page_ids):
                reached_last_page = True
                break

            page_number += 1

        catalog = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "created_at": self._utc_now(),
            "source": {
                "system": "NHTSA CISS Crash Viewer",
                "search_url": SEARCH_PAGE_URL,
                "search_policy": "blank_search",
                "page_size": 100,
            },
            "discovery": {
                "pages_scanned": page_number,
                "unique_case_ids_scanned": len(scanned_ids),
                "excluded_existing_cases": len(
                    scanned_ids.intersection(excluded_ids)
                ),
                "selected_case_count": len(discovered_ids),
                "requested_limit": limit,
                "reached_last_page": reached_last_page,
                "catalog_complete": (
                    limit is None and reached_last_page
                ),
            },
            "case_ids": discovered_ids,
        }

        self._save_catalog(catalog)

        print(f"Case catalog saved: {self.catalog_path}")
        print(f"New case IDs discovered: {len(discovered_ids)}")

        return discovered_ids

    def _submit_blank_search(self) -> None:
        """Submit the search form without manually selecting criteria."""

        wait = WebDriverWait(self.driver, self.timeout)

        search_buttons = wait.until(
            lambda driver: driver.find_elements(
                By.XPATH,
                "//button[normalize-space()='Search']",
            )
        )

        visible_button = next(
            (
                button
                for button in search_buttons
                if button.is_displayed() and button.is_enabled()
            ),
            None,
        )

        if visible_button is None:
            raise RuntimeError(
                "No visible CISS Search button was found."
            )

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            visible_button,
        )
        visible_button.click()

        wait.until(
            lambda driver: SEARCH_RESULTS_URL_FRAGMENT
            in driver.current_url.lower()
        )


    def _set_page_size(self, page_size: int) -> None:
        """
        Set the search-results table page size.

        CISS does not necessarily use the displayed page size as the
        HTML option value, so the option is selected using its text.
        """

        wait = WebDriverWait(
            self.driver,
            self.timeout,
        )

        try:
            select_element = wait.until(
                lambda driver: next(
                    (
                        element
                        for element in driver.find_elements(
                            By.TAG_NAME,
                            "select",
                        )
                        if element.is_displayed()
                    ),
                    None,
                )
            )

            page_size_select = Select(select_element)

            target_option = next(
                (
                    option
                    for option in page_size_select.options
                    if option.text.strip().startswith(
                        str(page_size)
                    )
                ),
                None,
            )

            if target_option is None:
                available_options = [
                    option.text.strip()
                    for option in page_size_select.options
                ]

                print(
                    f"Page size {page_size} is unavailable. "
                    f"Available options: {available_options}"
                )
                print(
                    "Continuing with the current page size."
                )
                return

            selected_option = page_size_select.first_selected_option

            if selected_option.text.strip().startswith(
                str(page_size)
            ):
                print(
                    f"Result page size is already {page_size}."
                )
                return

            previous_link_count = len(
                self.driver.find_elements(
                    By.CSS_SELECTOR,
                    CASE_LINK_SELECTOR,
                )
            )

            option_text = target_option.text.strip()

            page_size_select.select_by_visible_text(
                option_text
            )

            wait.until(
                lambda driver: len(
                    driver.find_elements(
                        By.CSS_SELECTOR,
                        CASE_LINK_SELECTOR,
                    )
                )
                != previous_link_count
            )

            current_link_count = len(
                self.driver.find_elements(
                    By.CSS_SELECTOR,
                    CASE_LINK_SELECTOR,
                )
            )

            print(
                f"Result page size changed to {option_text}. "
                f"Rows currently displayed: {current_link_count}"
            )

        except TimeoutException:
            print(
                "The result table did not refresh after changing "
                "the page size. Continuing with the current results."
            )

        except StaleElementReferenceException:
            print(
                "The page-size control refreshed while it was being "
                "accessed. Continuing with the current page size."
            )



    def _wait_for_case_links(self) -> None:
        """Wait until the current page contains case-detail links."""

        WebDriverWait(
            self.driver,
            self.timeout,
        ).until(
            lambda driver: len(
                driver.find_elements(
                    By.CSS_SELECTOR,
                    CASE_LINK_SELECTOR,
                )
            )
            > 0
        )

    def _extract_current_page_ids(self) -> list[int]:
        """Extract unique case IDs from the current result page."""

        page_ids: list[int] = []
        seen: set[int] = set()

        links = self.driver.find_elements(
            By.CSS_SELECTOR,
            CASE_LINK_SELECTOR,
        )

        for link in links:
            try:
                href = link.get_attribute("href") or ""
            except StaleElementReferenceException:
                continue

            match = CASE_ID_PATTERN.search(href)

            if match is None:
                continue

            case_id = int(match.group(1))

            if case_id not in seen:
                seen.add(case_id)
                page_ids.append(case_id)

        return page_ids

    def _go_to_next_page(
        self,
        current_page_ids: list[int],
    ) -> bool:
        """
        Move to the next page.

        Returns False when the current page is the final page.
        """

        next_links = self.driver.find_elements(
            By.CSS_SELECTOR,
            'a[aria-label="Next"]',
        )

        next_link = next(
            (
                link
                for link in next_links
                if link.is_displayed()
            ),
            None,
        )

        if next_link is None:
            return False

        parent_class = next_link.find_element(
            By.XPATH,
            "..",
        ).get_attribute("class") or ""

        if "disabled" in parent_class.lower():
            return False

        old_first_case = (
            current_page_ids[0]
            if current_page_ids
            else None
        )

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            next_link,
        )
        self.driver.execute_script(
            "arguments[0].click();",
            next_link,
        )

        if old_first_case is not None:
            self._wait_for_table_refresh(old_first_case)
        else:
            self._wait_for_case_links()

        return True

    def _wait_for_table_refresh(
        self,
        previous_first_case: int,
    ) -> None:
        """Wait until pagination changes the first result row."""

        WebDriverWait(
            self.driver,
            self.timeout,
        ).until(
            lambda driver: (
                self._first_case_id() is not None
                and self._first_case_id()
                != previous_first_case
            )
        )

    def _first_case_id(self) -> int | None:
        """Return the first visible case ID in the result table."""

        links = self.driver.find_elements(
            By.CSS_SELECTOR,
            CASE_LINK_SELECTOR,
        )

        if not links:
            return None

        try:
            href = links[0].get_attribute("href") or ""
        except StaleElementReferenceException:
            return None

        match = CASE_ID_PATTERN.search(href)

        return int(match.group(1)) if match else None

    def _save_catalog(self, catalog: dict) -> None:
        """Save the discovery result as persistent metadata."""

        self.catalog_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.catalog_path.with_suffix(
            ".json.tmp"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                catalog,
                output_file,
                indent=2,
                ensure_ascii=False,
            )

        temporary_path.replace(self.catalog_path)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()