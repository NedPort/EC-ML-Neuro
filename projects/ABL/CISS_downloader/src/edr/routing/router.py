from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.edr.parsers.observation_parser import Observation

from src.edr.rules.group1 import classify_group1
from src.edr.rules.group2 import classify_group2
from src.edr.rules.group3 import classify_group3
from src.edr.rules.group4 import classify_group4
from src.edr.rules.group5 import classify_group5
from src.edr.rules.group6 import classify_group6


ROUTER_VERSION = "1.2"


@dataclass
class RouteResult:
    destination: str
    family: str
    confidence: str
    reason: str
    requires_review: bool = False
    review_reason: str = ""
    matched_by: str = ""
    router_version: str = ROUTER_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "family": self.family,
            "confidence": self.confidence,
            "reason": self.reason,
            "requires_review": self.requires_review,
            "review_reason": self.review_reason,
            "matched_by": self.matched_by,
            "router_version": self.router_version,
        }


# ============================================================
# Conversion helper
# ============================================================

def make_route_result(
    result,
    matched_by: str,
) -> RouteResult:
    return RouteResult(
        destination=getattr(
            result,
            "destination",
            "",
        ),
        family=getattr(
            result,
            "family",
            getattr(
                result,
                "field_family",
                "",
            ),
        ),
        confidence=getattr(
            result,
            "confidence",
            "",
        ),
        reason=getattr(
            result,
            "reason",
            "",
        ),
        requires_review=getattr(
            result,
            "requires_review",
            False,
        ),
        review_reason=getattr(
            result,
            "review_reason",
            "",
        ),
        matched_by=matched_by,
    )


# ============================================================
# Native-match logic
# ============================================================

def is_native_match(
    classifier_name: str,
    result,
) -> bool:
    """
    A native match means that a classifier positively classified
    an observation into its own destination.

    Cross-group hints are NOT native matches.

    Example:

        Group 3:
            Maximum Delta-V -> destination group5
            matched=False

        This is only a routing hint.

        Group 5:
            Maximum Delta-V -> destination group5
            matched=True

        This is the authoritative/native classification.
    """

    destination = getattr(
        result,
        "destination",
        "",
    )

    matched = bool(
        getattr(
            result,
            "matched",
            False,
        )
    )

    if not matched:
        return False

    if destination == classifier_name:
        return True

    return False


# ============================================================
# Special native destinations
# ============================================================

def is_special_native_match(
    classifier_name: str,
    result,
) -> bool:
    """
    Some validated outputs are intentionally related to a group
    without being a core accepted measurement.

    Currently the important example is:

        Group 5 -> group5_companion
    """

    destination = getattr(
        result,
        "destination",
        "",
    )

    if (
        classifier_name == "group5"
        and destination
        == "group5_companion"
    ):
        return True

    return False


# ============================================================
# Explicit reviewed reroutes
# ============================================================

def is_explicit_reviewed_reroute(
    classifier_name: str,
    result,
) -> bool:
    """
    Some later audit/review stages made explicit routing decisions
    that must override broader earlier vocabulary rules.

    These are not fuzzy guesses. They are final reviewed decisions.
    """

    destination = getattr(
        result,
        "destination",
        "",
    )

    reason = getattr(
        result,
        "reason",
        "",
    )

    # --------------------------------------------------------
    # Final Group 6 PDF review decisions
    #
    # These event-related ignition-cycle fields were explicitly
    # routed OUT of Group 6 and INTO Group 3.
    # --------------------------------------------------------

    if (
        classifier_name == "group6"
        and destination == "group3"
        and reason in {
            "deployment_event_ignition_cycle",
            "nondeployment_event_ignition_cycle",
            "event_start_ignition_timer",
            "event_ignition_cycle",
            "crash_event_ignition_cycle",
        }
    ):
        return True

    return False


# ============================================================
# Generic cross-group hint
# ============================================================

def is_cross_group_hint(
    classifier_name: str,
    result,
) -> bool:
    destination = getattr(
        result,
        "destination",
        "",
    )

    if not destination:
        return False

    if destination in {
        classifier_name,
        "group5_companion",
    }:
        return False

    if destination.startswith(
        "group"
    ):
        return True

    return False


# ============================================================
# Main router
# ============================================================

def route_observation(
    observation: Observation,
) -> RouteResult:
    """
    Route one parsed observation through the validated Group 1-6
    rule modules.

    Important principles
    --------------------
    1. Repeated/table structures go to Group 4 first.
    2. All scalar classifiers are evaluated before a generic
       cross-group hint is accepted.
    3. A group's own/native classification is preferred over a
       generic hint from another group.
    4. Explicit final reviewed reroutes override broader earlier
       vocabulary rules.
    """

    # ========================================================
    # Empty
    # ========================================================

    if observation.is_empty:
        return RouteResult(
            destination="exclude",
            family="empty",
            confidence="high",
            reason="Empty observation.",
            matched_by="router",
        )

    # ========================================================
    # Structural Group 4 precedence
    # ========================================================

    if (
        observation.is_repeated
        or observation.is_table_header
    ):
        result = classify_group4(
            observation
        )

        if (
            is_native_match(
                "group4",
                result,
            )
            or is_special_native_match(
                "group4",
                result,
            )
        ):
            return make_route_result(
                result,
                "group4",
            )

    # ========================================================
    # Evaluate ALL scalar rule modules
    #
    # Do not stop at the first cross-group hint.
    # ========================================================

    results = {
        "group1":
            classify_group1(
                observation
            ),

        "group2":
            classify_group2(
                observation
            ),

        "group3":
            classify_group3(
                observation
            ),

        "group5":
            classify_group5(
                observation
            ),

        "group6":
            classify_group6(
                observation
            ),
    }

    # ========================================================
    # 1. Explicit final reviewed reroutes
    #
    # These override broad earlier classifiers.
    # ========================================================

    for classifier_name in (
        "group6",
        "group5",
        "group3",
        "group2",
        "group1",
    ):
        result = results[
            classifier_name
        ]

        if is_explicit_reviewed_reroute(
            classifier_name,
            result,
        ):
            return make_route_result(
                result,
                classifier_name,
            )

    # ========================================================
    # 2. Native matches
    #
    # Prefer the classifier responsible for the destination.
    # ========================================================

    for classifier_name in (
        "group1",
        "group2",
        "group3",
        "group5",
        "group6",
    ):
        result = results[
            classifier_name
        ]

        if is_native_match(
            classifier_name,
            result,
        ):
            return make_route_result(
                result,
                classifier_name,
            )

    # ========================================================
    # 3. Special native outputs
    #
    # Example: Group 5 companion context.
    # ========================================================

    for classifier_name in (
        "group1",
        "group2",
        "group3",
        "group5",
        "group6",
    ):
        result = results[
            classifier_name
        ]

        if is_special_native_match(
            classifier_name,
            result,
        ):
            return make_route_result(
                result,
                classifier_name,
            )

    # ========================================================
    # 4. Review / documentation / exclusion decisions
    # ========================================================

    for classifier_name in (
        "group1",
        "group2",
        "group3",
        "group5",
        "group6",
    ):
        result = results[
            classifier_name
        ]

        destination = getattr(
            result,
            "destination",
            "",
        )

        if destination in {
            "review",
            "documentation",
            "exclude",
        }:
            return make_route_result(
                result,
                classifier_name,
            )

    # ========================================================
    # 5. Cross-group fallback
    #
    # Only use this if no destination group's own classifier
    # produced a native classification.
    # ========================================================

    for classifier_name in (
        "group1",
        "group2",
        "group3",
        "group5",
        "group6",
    ):
        result = results[
            classifier_name
        ]

        if is_cross_group_hint(
            classifier_name,
            result,
        ):
            return make_route_result(
                result,
                classifier_name,
            )

    # ========================================================
    # 6. Group 4 lightweight fallback
    # ========================================================

    group4_result = classify_group4(
        observation
    )

    if is_native_match(
        "group4",
        group4_result,
    ):
        return make_route_result(
            group4_result,
            "group4",
        )

    # ========================================================
    # 7. Unknown
    # ========================================================

    return RouteResult(
        destination="review",
        family="unclassified",
        confidence="low",
        reason=(
            "Observation did not match any validated "
            "Group 1-6 rule."
        ),
        requires_review=True,
        review_reason=(
            "No validated routing rule matched."
        ),
        matched_by="router",
    )