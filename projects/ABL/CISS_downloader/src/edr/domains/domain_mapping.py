from __future__ import annotations


GROUP_TO_DOMAIN = {
    "group1": "report_technical_context",
    "group6": "report_technical_context",

    "group2": "event_information",
    "group3": "event_information",

    "group4": "time_series_measurements",

    "group5": "scalar_crash_measurements",
    "group5_companion": "scalar_crash_measurements",
}


DOMAIN_NAMES = {
    "report_technical_context":
        "Report & Technical Context",

    "event_information":
        "Event Information",

    "time_series_measurements":
        "Time-Series Measurements",

    "scalar_crash_measurements":
        "Scalar Crash Measurements",
}


def get_domain(
    destination: str,
) -> str:
    """
    Map an extraction-pathway destination to its
    higher-level conceptual domain.
    """

    destination = str(
        destination or ""
    ).strip()

    return GROUP_TO_DOMAIN.get(
        destination,
        "unclassified",
    )


def get_domain_name(
    destination: str,
) -> str:
    """
    Return a human-readable conceptual domain name.
    """

    domain = get_domain(
        destination
    )

    if domain == "unclassified":
        return "Unclassified"

    return DOMAIN_NAMES[
        domain
    ]


def same_domain(
    destination_a: str,
    destination_b: str,
) -> bool:
    """
    Check whether two extraction destinations belong
    to the same conceptual domain.
    """

    domain_a = get_domain(
        destination_a
    )

    domain_b = get_domain(
        destination_b
    )

    if (
        domain_a == "unclassified"
        or domain_b == "unclassified"
    ):
        return False

    return domain_a == domain_b