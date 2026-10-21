from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from src.edr.parsers.observation_parser import (
    Observation,
    parse_observation,
)
from src.edr.routing.router import (
    RouteResult,
    route_observation,
)


VALID_DESTINATIONS = {
    "group1",
    "group2",
    "group3",
    "group4",
    "group5",
    "group5_companion",
    "group6",
    "documentation",
    "exclude",
    "review",
}


# ============================================================
# Regression result
# ============================================================

@dataclass
class RegressionResult:
    report_id: str
    case_id: str
    vehicle_number: str

    source_format: str
    source_location: str

    raw_label: str
    raw_value: str
    section_context: str

    expected_destination: str
    actual_destination: str

    expected_family: str
    actual_family: str

    matched_by: str
    confidence: str

    destination_match: bool
    family_match: bool
    newly_unclassified: bool

    regression_level: str
    regression_status: str

    reason: str
    requires_review: bool
    review_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================
# Normalization
# ============================================================

def clean_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).split()
    )


def normalize_destination(
    value: str,
) -> str:
    """
    Normalize known historical destination aliases.

    Keep this deliberately conservative.
    """

    text = clean_text(
        value
    ).casefold()

    aliases = {
        "g1": "group1",
        "g2": "group2",
        "g3": "group3",
        "g4": "group4",
        "g5": "group5",
        "g6": "group6",

        "group 1": "group1",
        "group 2": "group2",
        "group 3": "group3",
        "group 4": "group4",
        "group 5": "group5",
        "group 6": "group6",

        "group1_report_metadata": "group1",
        "group2_event_structure": "group2",
        "group3_event_status": "group3",
        "group6_technical": "group6",

        "group5 companion": "group5_companion",
        "group5_companion_context": "group5_companion",
    }

    return aliases.get(
        text,
        text,
    )


def normalize_family(
    value: str,
) -> str:
    return clean_text(
        value
    ).casefold()


# ============================================================
# Regression classification
# ============================================================

def classify_regression_level(
    *,
    expected_destination: str,
    actual_destination: str,
    expected_family: str,
    actual_family: str,
) -> tuple[str, str]:
    """
    LEVEL 1:
        destination mismatch

    LEVEL 2:
        historically classified observation became review

    LEVEL 3:
        destination matches but family differs

    LEVEL 4:
        destination and family both match
    """

    expected_destination = (
        normalize_destination(
            expected_destination
        )
    )

    actual_destination = (
        normalize_destination(
            actual_destination
        )
    )

    expected_family = (
        normalize_family(
            expected_family
        )
    )

    actual_family = (
        normalize_family(
            actual_family
        )
    )

    # --------------------------------------------------------
    # Historically accepted but now unresolved
    # --------------------------------------------------------

    if (
        expected_destination
        not in {
            "",
            "review",
        }
        and actual_destination
        == "review"
    ):
        return (
            "LEVEL_2",
            "newly_unclassified",
        )

    # --------------------------------------------------------
    # Destination mismatch
    # --------------------------------------------------------

    if (
        expected_destination
        != actual_destination
    ):
        return (
            "LEVEL_1",
            "destination_mismatch",
        )

    # --------------------------------------------------------
    # Destination matches, family differs
    # --------------------------------------------------------

    if (
        expected_family
        and actual_family
        and expected_family
        != actual_family
    ):
        return (
            "LEVEL_3",
            "family_mismatch",
        )

    # --------------------------------------------------------
    # Exact or destination-only match
    # --------------------------------------------------------

    return (
        "LEVEL_4",
        "match",
    )


# ============================================================
# Main comparison
# ============================================================

def compare_route(
    *,
    observation: Observation,
    expected_destination: str,
    expected_family: str = "",
    report_id: str = "",
    case_id: str = "",
    vehicle_number: str = "",
    source_format: str = "",
    source_location: str = "",
) -> RegressionResult:
    """
    Route one historical observation and compare the result
    against the frozen historical classification.
    """

    route: RouteResult = (
        route_observation(
            observation
        )
    )

    expected_destination_norm = (
        normalize_destination(
            expected_destination
        )
    )

    actual_destination_norm = (
        normalize_destination(
            route.destination
        )
    )

    expected_family_norm = (
        normalize_family(
            expected_family
        )
    )

    actual_family_norm = (
        normalize_family(
            route.family
        )
    )

    (
        regression_level,
        regression_status,
    ) = classify_regression_level(
        expected_destination=(
            expected_destination_norm
        ),
        actual_destination=(
            actual_destination_norm
        ),
        expected_family=(
            expected_family_norm
        ),
        actual_family=(
            actual_family_norm
        ),
    )

    destination_match = (
        expected_destination_norm
        == actual_destination_norm
    )

    family_match = (
        not expected_family_norm
        or expected_family_norm
        == actual_family_norm
    )

    newly_unclassified = (
        expected_destination_norm
        not in {
            "",
            "review",
        }
        and actual_destination_norm
        == "review"
    )

    raw_value = ""

    if observation.values:
        raw_value = " | ".join(
            str(value)
            for value
            in observation.values
        )

    return RegressionResult(
        report_id=clean_text(
            report_id
        ),
        case_id=clean_text(
            case_id
        ),
        vehicle_number=clean_text(
            vehicle_number
        ),

        source_format=clean_text(
            source_format
        ),
        source_location=clean_text(
            source_location
        ),

        raw_label=clean_text(
            observation.label
        ),
        raw_value=clean_text(
            raw_value
        ),
        section_context=clean_text(
            observation.section_context
        ),

        expected_destination=(
            expected_destination_norm
        ),
        actual_destination=(
            actual_destination_norm
        ),

        expected_family=(
            expected_family_norm
        ),
        actual_family=(
            actual_family_norm
        ),

        matched_by=clean_text(
            route.matched_by
        ),
        confidence=clean_text(
            route.confidence
        ),

        destination_match=(
            destination_match
        ),
        family_match=(
            family_match
        ),
        newly_unclassified=(
            newly_unclassified
        ),

        regression_level=(
            regression_level
        ),
        regression_status=(
            regression_status
        ),

        reason=clean_text(
            route.reason
        ),
        requires_review=bool(
            route.requires_review
        ),
        review_reason=clean_text(
            route.review_reason
        ),
    )


# ============================================================
# Convenience helper from raw row
# ============================================================

def compare_raw_row(
    *,
    row: list[str],
    row_index: int,
    section_context: str,
    expected_destination: str,
    expected_family: str = "",
    report_id: str = "",
    case_id: str = "",
    vehicle_number: str = "",
    source_format: str = "",
    source_location: str = "",
) -> RegressionResult:
    observation = parse_observation(
        row=row,
        row_index=row_index,
        section_context=(
            section_context
        ),
    )

    return compare_route(
        observation=observation,
        expected_destination=(
            expected_destination
        ),
        expected_family=(
            expected_family
        ),
        report_id=report_id,
        case_id=case_id,
        vehicle_number=(
            vehicle_number
        ),
        source_format=(
            source_format
        ),
        source_location=(
            source_location
        ),
    )


# ============================================================
# Batch helpers
# ============================================================

def results_to_dicts(
    results: Iterable[
        RegressionResult
    ],
) -> list[dict[str, Any]]:
    return [
        result.to_dict()
        for result
        in results
    ]


def destination_mismatches(
    results: Iterable[
        RegressionResult
    ],
) -> list[RegressionResult]:
    return [
        result
        for result
        in results
        if not result.destination_match
    ]


def family_mismatches(
    results: Iterable[
        RegressionResult
    ],
) -> list[RegressionResult]:
    return [
        result
        for result
        in results
        if (
            result.destination_match
            and not result.family_match
        )
    ]


def newly_unclassified(
    results: Iterable[
        RegressionResult
    ],
) -> list[RegressionResult]:
    return [
        result
        for result
        in results
        if result.newly_unclassified
    ]


# ============================================================
# Summary
# ============================================================

def summarize_results(
    results: Iterable[
        RegressionResult
    ],
) -> dict[str, Any]:
    rows = list(
        results
    )

    total = len(
        rows
    )

    level_counts = Counter(
        row.regression_level
        for row in rows
    )

    status_counts = Counter(
        row.regression_status
        for row in rows
    )

    expected_destination_counts = (
        Counter(
            row.expected_destination
            for row in rows
        )
    )

    actual_destination_counts = (
        Counter(
            row.actual_destination
            for row in rows
        )
    )

    destination_match_count = sum(
        1
        for row in rows
        if row.destination_match
    )

    exact_family_match_count = sum(
        1
        for row in rows
        if (
            row.destination_match
            and row.family_match
        )
    )

    newly_unclassified_count = sum(
        1
        for row in rows
        if row.newly_unclassified
    )

    return {
        "total_observations":
            total,

        "destination_matches":
            destination_match_count,

        "destination_mismatches":
            total
            - destination_match_count,

        "destination_match_rate":
            (
                destination_match_count
                / total
                if total
                else 0.0
            ),

        "destination_and_family_matches":
            exact_family_match_count,

        "family_mismatch_count":
            sum(
                1
                for row in rows
                if (
                    row.destination_match
                    and not row.family_match
                )
            ),

        "newly_unclassified_count":
            newly_unclassified_count,

        "regression_level_counts":
            dict(
                level_counts
            ),

        "regression_status_counts":
            dict(
                status_counts
            ),

        "expected_destination_counts":
            dict(
                expected_destination_counts
            ),

        "actual_destination_counts":
            dict(
                actual_destination_counts
            ),
    }


# ============================================================
# Label-level mismatch summary
# ============================================================

def summarize_mismatch_labels(
    results: Iterable[
        RegressionResult
    ],
) -> list[dict[str, Any]]:
    """
    Summarize mismatches by label and expected/actual destination.
    """

    grouped = defaultdict(
        list
    )

    for result in results:
        if result.regression_level not in {
            "LEVEL_1",
            "LEVEL_2",
            "LEVEL_3",
        }:
            continue

        key = (
            result.raw_label,
            result.expected_destination,
            result.actual_destination,
            result.expected_family,
            result.actual_family,
            result.regression_level,
        )

        grouped[key].append(
            result
        )

    summary = []

    for (
        raw_label,
        expected_destination,
        actual_destination,
        expected_family,
        actual_family,
        regression_level,
    ), rows in grouped.items():

        reports = {
            row.report_id
            for row in rows
            if row.report_id
        }

        cases = {
            row.case_id
            for row in rows
            if row.case_id
        }

        summary.append({
            "raw_label":
                raw_label,

            "expected_destination":
                expected_destination,

            "actual_destination":
                actual_destination,

            "expected_family":
                expected_family,

            "actual_family":
                actual_family,

            "regression_level":
                regression_level,

            "observation_count":
                len(rows),

            "report_count":
                len(reports),

            "case_count":
                len(cases),
        })

    summary.sort(
        key=lambda row: (
            row[
                "regression_level"
            ],
            -row[
                "observation_count"
            ],
            row[
                "raw_label"
            ],
        )
    )

    return summary


# ============================================================
# Hard validation
# ============================================================

def validate_regression(
    results: Iterable[
        RegressionResult
    ],
    *,
    allow_destination_mismatches: int = 0,
    allow_newly_unclassified: int = 0,
) -> dict[str, Any]:
    """
    Hard regression gate.

    Family mismatches are intentionally not hard failures yet.
    """

    rows = list(
        results
    )

    destination_mismatch_count = sum(
        1
        for row in rows
        if (
            row.regression_level
            == "LEVEL_1"
        )
    )

    newly_unclassified_count = sum(
        1
        for row in rows
        if (
            row.regression_level
            == "LEVEL_2"
        )
    )

    checks = {
        "destination_mismatch_count":
            destination_mismatch_count,

        "destination_mismatch_limit":
            allow_destination_mismatches,

        "destination_mismatch_pass":
            (
                destination_mismatch_count
                <= allow_destination_mismatches
            ),

        "newly_unclassified_count":
            newly_unclassified_count,

        "newly_unclassified_limit":
            allow_newly_unclassified,

        "newly_unclassified_pass":
            (
                newly_unclassified_count
                <= allow_newly_unclassified
            ),
    }

    checks[
        "hard_validation_pass"
    ] = (
        checks[
            "destination_mismatch_pass"
        ]
        and checks[
            "newly_unclassified_pass"
        ]
    )

    return checks