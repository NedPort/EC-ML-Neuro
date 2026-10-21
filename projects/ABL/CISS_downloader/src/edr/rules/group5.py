from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.edr.parsers.observation_parser import (
    Observation,
    normalize_text,
)


GROUP_NAME = "group5"
RULE_VERSION = "1.1"


@dataclass
class Group5RuleResult:
    matched: bool
    destination: str
    family: str
    confidence: str
    reason: str
    requires_review: bool = False
    review_reason: str = ""
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "destination": self.destination,
            "family": self.family,
            "confidence": self.confidence,
            "reason": self.reason,
            "requires_review": self.requires_review,
            "review_reason": self.review_reason,
            "rule_version": self.rule_version,
        }


def matches(
    text: str,
    pattern: str,
) -> bool:
    return bool(
        re.search(
            pattern,
            text,
            re.IGNORECASE,
        )
    )


# ============================================================
# Strong cross-group boundaries
# ============================================================

GROUP1_PATTERNS = (
    r"\bfilename\b",
    r"\bsaved on\b",
    r"\bimaged with\b",
    r"\breported with\b",
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
    r"\buser entered vin\b",
    r"\bdevice type\b",
)


GROUP2_PATTERNS = (
    r"\bevent recording complete\b",
    r"\bcrash record locked\b",
    r"\brecording complete\b",
    r"\brecording status\b",
    r"\bmultiple events?\b",
    r"\bevent counter\b",
    r"\brecord status\b",
    r"\bretrieval status\b",
    r"\bassociated events?\b",
    r"\bevents? not recorded\b",
    r"\btime between\b.*\bevents?\b",
    r"\bevent record type\b",
    r"\btrg count\b",
    r"\btrip count\b",
)


GROUP3_PATTERNS = (
    r"\bair ?bag\b",
    r"\bpretensioner\b",
    r"\bdeployment command\b",
    r"\bdeployment criteria\b",
    r"\b1st stage\b",
    r"\b2nd stage\b",
    r"\bbelt switch\b",
    r"\bsafety belt\b",
    r"\bseat belt\b",
    r"\boccupant\b",
    r"\bpassenger classification\b",
    r"\bsuppression\b",
    r"\bwarning lamp\b",
    r"\bsir\b",
    r"\bdtc\b",
    r"\bdiagnostic trouble\b",
    r"\bseat position\b",
    r"\brestraint\b",
    r"\bhigh voltage disable\b",
    r"\bpower loss detected during event\b",
)


GROUP6_PATTERNS = (
    r"\bignition cycles?\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bsupplier id\b",
    r"\bproduction date\b",
    r"\bconfiguration\b",
    r"\bconfigured for\b",
    r"\bvehicle mileage\b",
    r"\bodometer\b",
    r"\boperating time\b",
    r"\binvestigation\b",
)


# ============================================================
# Final Group 5 family rules
# ============================================================

FAMILY_RULES = (
    (
        "range_clipping_timing",
        (
            r"\bclipping time\b",
            r"\baccelerometer range exceeded\b",
            r"\bsensor design range (?:was )?exceeded\b",
            r"\breached maximum sensor range\b",
            r"\breached maximum sensor range\b",
        ),
    ),

    (
        "acceleration_peak_timing",
        (
            r"\btime\b.*\bmaximum acceleration\b",
        ),
    ),

    (
        "acceleration_peak",
        (
            r"\bmaximum acceleration\b",
            r"\bpeak acceleration\b",
        ),
    ),

    (
        "delta_v_time_zero_offset",
        (
            r"\bdelta[- ]?v\b.*\btime zero offset\b",
        ),
    ),

    (
        "delta_v_duration",
        (
            r"\blength of delta[- ]?v\b",
            r"\bduration\b.*\bdelta[- ]?v\b",
            r"\bcrash pulse\b.*\bduration\b",
            r"\bdelta[- ]?v\b.*\bduration\b",
        ),
    ),

    (
        "delta_v_integration_time",
        (
            r"\bintegration time\b.*\bdelta[- ]?v\b",
        ),
    ),

    (
        "delta_v_component_at_maximum",
        (
            r"\b(?:longitudinal|lateral)\b.*"
            r"\bvelocity change\b.*"
            r"\bat time of maximum\b",
        ),
    ),

    (
        "delta_v_timing",
        (
            r"\balgorithm enable\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime\b.*\bmaximum\b.*\bdelta[- ]?v\b",
            r"\btime to\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime from\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime\b.*\bmax(?:imum)?\b.*\brecorded velocity change\b",
            r"\btime\b.*\bmax(?:imum)?\b.*\brecorded vehicle velocity change\b",
        ),
    ),

    (
        "delta_v_summary",
        (
            r"\bmaximum\b.*\bvelocity change\b",
            r"\bmaximum\b.*\bdelta[- ]?v\b",
            r"\bmax(?:imum)?\b.*\bvelocity change\b",
            r"\bmax(?:imum)?\b.*\bdelta[- ]?v\b",
            r"\bresultant\b.*\bdelta[- ]?v\b",
            r"\bresultant\b.*\bvelocity change\b",
            r"\bfinal\b.*\bdelta[- ]?v\b",
            r"\bfinal\b.*\bvelocity change\b",
            r"\blongitudinal\b.*\bvelocity change\b",
            r"\blateral\b.*\bvelocity change\b",
            r"\blongitudinal\b.*\bdelta[- ]?v\b",
            r"\blateral\b.*\bdelta[- ]?v\b",
        ),
    ),

    (
        "roll_peak",
        (
            r"\broll ?angle peak\b",
            r"\brollangle peak\b",
            r"\bmaximum\b.*\broll angle\b",
            r"\bpeak\b.*\broll angle\b",
        ),
    ),

    (
        "roll_at_trigger",
        (
            r"\broll angle at the time of trg\b",
        ),
    ),

    (
        "roll_time_zero_offset",
        (
            r"\broll angle time zero offset\b",
        ),
    ),

    (
        "angular_rate_summary",
        (
            r"\b(?:maximum|max|peak)\b.*"
            r"\b(?:angular rate|yaw rate|roll rate)\b",

            r"\b(?:angular rate|yaw rate|roll rate)\b.*"
            r"\b(?:maximum|max|peak)\b",
        ),
    ),

    (
        "trigger_relative_timing",
        (
            r"\btime from time zero to trg\b",
        ),
    ),

    (
        "precrash_time_alignment",
        (
            r"\btime from last speed data sample\b.*\btime zero\b",
        ),
    ),

    (
        "sensor_loss_timing",
        (
            r"\btime yaw rate lost\b",
        ),
    ),

    (
        "direction_summary",
        (
            r"\brecorded side\b",
            r"\bpdof\b",
            r"\bprincipal direction of force\b",
            r"\bprincipal direction\b",
            r"\bcrash direction\b",
            r"\brecorded direction\b",
        ),
    ),
)


def classify_group5_family(
    label: str,
) -> str:
    text = normalize_text(
        label
    )

    for family, patterns in FAMILY_RULES:
        if any(
            re.search(
                pattern,
                text,
                re.IGNORECASE,
            )
            for pattern in patterns
        ):
            return family

    return ""


# ============================================================
# Companion/context rules
# ============================================================

def classify_group5_companion(
    label: str,
) -> str:
    text = normalize_text(
        label
    )

    if matches(
        text,
        r"\bpower supply status\b.*"
        r"\bmax\.?\s*delta[- ]?v\b",
    ):
        return "measurement_context"

    if matches(
        text,
        r"\bclipping flag\b",
    ):
        return "measurement_quality_context"

    if matches(
        text,
        r"\btime from pre[- ]?crash to trg\b",
    ):
        return "temporal_alignment_context"

    if matches(
        text,
        r"\btime from trg to next sample\b",
    ):
        return "temporal_alignment_context"

    return ""


# ============================================================
# Explicit final review-resolution destinations
# ============================================================

def classify_group5_review_resolution(
    label: str,
) -> tuple[str, str] | None:
    text = normalize_text(
        label
    )

    if text == "saved on":
        return (
            "group1",
            "report_saved_timestamp",
        )

    if text == (
        "high voltage disable notification sent"
    ):
        return (
            "group3",
            "event_related_high_voltage_status",
        )

    if text == (
        "power loss detected during event"
    ):
        return (
            "group3",
            "power_loss_event_condition",
        )

    if text == "supplier id, acm":
        return (
            "group6",
            "module_supplier_identifier",
        )

    if text == "production date, acm":
        return (
            "group6",
            "module_production_metadata",
        )

    if re.fullmatch(
        r"(?:"
        r"most recent event|"
        r"\d+(?:st|nd|rd|th) prior event"
        r")",
        text,
        re.I,
    ):
        return (
            "group2",
            "event_record_label",
        )

    return None


# ============================================================
# PDF parse artifact
# ============================================================

def is_group5_pdf_label_split_artifact(
    label: str,
    value: str,
    source_line: str,
) -> bool:
    """
    Example bad PDF split:

        Maximum Delta-V, Lateral Left to | Right

    where Right belongs to the label phrase:
        Left to Right
    """

    return (
        bool(
            re.search(
                r"\bmaximum delta[- ]?v,\s*"
                r"lateral left to$",
                str(label or ""),
                re.I,
            )
        )
        and normalize_text(
            value
        ) == "right"
        and bool(
            re.search(
                r"\bmaximum delta[- ]?v,\s*"
                r"lateral left to right\b",
                str(source_line or ""),
                re.I,
            )
        )
    )


# ============================================================
# Main Group 5 classifier
# ============================================================

def classify_group5(
    observation: Observation,
) -> Group5RuleResult:
    """
    Classify a scalar/non-time-series crash measurement.

    Group 5 does not normalize values or units and does not infer
    semantic event identity.
    """

    label = normalize_text(
        observation.label
    )

    if observation.is_empty:
        return Group5RuleResult(
            matched=False,
            destination="",
            family="",
            confidence="",
            reason="Empty row.",
        )

    # --------------------------------------------------------
    # Group 4 precedence
    # --------------------------------------------------------

    if (
        observation.is_repeated
        or observation.is_table_header
    ):
        return Group5RuleResult(
            matched=False,
            destination="group4",
            family="time_series_measurement",
            confidence="high",
            reason=(
                "Repeated/table structure belongs to Group 4."
            ),
        )

    # --------------------------------------------------------
    # Final explicit cross-group review resolutions
    # --------------------------------------------------------

    reviewed = (
        classify_group5_review_resolution(
            observation.label
        )
    )

    if reviewed is not None:
        destination, reason = reviewed

        return Group5RuleResult(
            matched=False,
            destination=destination,
            family="cross_group_resolution",
            confidence="high",
            reason=reason,
        )

    # --------------------------------------------------------
    # Group 1
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.I,
        )
        for pattern in GROUP1_PATTERNS
    ):
        return Group5RuleResult(
            matched=False,
            destination="group1",
            family="report_metadata",
            confidence="high",
            reason="Report metadata belongs to Group 1.",
        )

    # --------------------------------------------------------
    # Group 2
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.I,
        )
        for pattern in GROUP2_PATTERNS
    ):
        return Group5RuleResult(
            matched=False,
            destination="group2",
            family="record_structure",
            confidence="high",
            reason=(
                "Record/event structure belongs to Group 2."
            ),
        )

    # --------------------------------------------------------
    # Group 3
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.I,
        )
        for pattern in GROUP3_PATTERNS
    ):
        return Group5RuleResult(
            matched=False,
            destination="group3",
            family="event_condition_status",
            confidence="high",
            reason=(
                "Deployment/restraint/status information "
                "belongs to Group 3."
            ),
        )

    # Algorithm start/reset timing belongs to Group 3,
    # not Group 5 physical measurements.
    if matches(
        label,
        r"\btime from time zero to algorithm "
        r"(?:start|reset)\b",
    ):
        return Group5RuleResult(
            matched=False,
            destination="group3",
            family="algorithm_status_timing",
            confidence="high",
            reason=(
                "Algorithm-state timing belongs to Group 3."
            ),
        )

    # Roll angle used specifically for deployment belongs to G3.
    if matches(
        label,
        r"\broll angle\b.*\bdeployment\b",
    ):
        return Group5RuleResult(
            matched=False,
            destination="group3",
            family="deployment_status",
            confidence="high",
            reason=(
                "Deployment-related roll angle belongs to Group 3."
            ),
        )

    # --------------------------------------------------------
    # Group 6
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.I,
        )
        for pattern in GROUP6_PATTERNS
    ):
        return Group5RuleResult(
            matched=False,
            destination="group6",
            family="technical_or_configuration",
            confidence="high",
            reason=(
                "Technical/configuration information belongs "
                "to Group 6."
            ),
        )

    # --------------------------------------------------------
    # Group 5 companion context
    # --------------------------------------------------------

    companion = classify_group5_companion(
        observation.label
    )

    if companion:
        return Group5RuleResult(
            matched=False,
            destination="group5_companion",
            family=companion,
            confidence="high",
            reason=(
                "Field provides context for a Group 5 "
                "measurement rather than a core measurement."
            ),
        )

    # --------------------------------------------------------
    # Core Group 5 measurement
    # --------------------------------------------------------

    family = classify_group5_family(
        observation.label
    )

    if family:
        return Group5RuleResult(
            matched=True,
            destination=GROUP_NAME,
            family=family,
            confidence="high",
            reason=(
                "Label matches validated Group 5 "
                "scalar crash/event measurement vocabulary."
            ),
        )

    return Group5RuleResult(
        matched=False,
        destination="",
        family="",
        confidence="",
        reason="No Group 5 rule matched.",
    )