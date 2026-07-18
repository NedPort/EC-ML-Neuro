"""
Functions for communicating with the NHTSA Vehicle API.
"""

import requests

from .config import (
    VEHICLE_API,
    REQUEST_TIMEOUT,
    PAGE_SIZE,
)

def _make_request(endpoint):
    """
    Send a GET request to the NHTSA API.

    Parameters
    ----------
    endpoint : str
        API endpoint relative to the vehicle API.

    Returns
    -------
    dict
        JSON response from the API.
    """

    url = f"{VEHICLE_API}/{endpoint}"

    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
    )

    # Raise an exception if the request failed
    response.raise_for_status()

    return response.json()


def get_test_detail(test_number):
    """
    Retrieve detailed information for a single crash test.

    Parameters
    ----------
    test_number : int
        NHTSA crash test number.

    Returns
    -------
    dict
        Crash test metadata.
    """

    endpoint = (
        "vehicle-database-test-results/"
        f"get-test-detail/{test_number}"
    )

    return _make_request(endpoint)


def get_test_list(page_number=0):
    """
    Retrieve one page of crash test summaries.

    Parameters
    ----------
    page_number : int, optional
        Page number to retrieve (default is 0).

    Returns
    -------
    dict
        JSON response containing a page of crash tests.
    """

    endpoint = (
        "vehicle-database-test-results/"
        f"by-search?count={PAGE_SIZE}"
        f"&pageNumber={page_number}"
        "&orderBy=testNo"
        "&sortBy=DESC"
        "&excludeNhtsaVehicles=true"
    )

    return _make_request(endpoint)

def get_documents(test_number):
    """
    Get all documents associated with a crash test.
    """
    endpoint = f"vehicle-documents/test-no/{test_number}"
    return _make_request(endpoint)

def get_test_numbers(page_number=0):
    """
    Return the crash test numbers from one page.
    """

    data = get_test_list(page_number)

    return [
        item["testNo"]
        for item in data["results"]
    ]