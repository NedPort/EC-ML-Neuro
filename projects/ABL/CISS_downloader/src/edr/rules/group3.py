from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.edr.parsers.observation_parser import (
    Observation,
    normalize_text,
)


# ============================================================
# Group definition
# ============================================================

GROUP_NAME = "group3"
RULE_VERSION = "1.1"


# ============================================================
# Result model
# ============================================================

@dataclass
class Group3RuleResult:
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


# ============================================================
# Helper
# ============================================================

def has(
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
# Strong non-Group-3 boundaries
# ============================================================

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
    r"\bprevious crash type\b",
    r"\bevent record type\b",
    r"\btrg count\b",
    r"\btrip count\b",
    r"\bdeployment command counter\b",
    r"\bcomplete status of event data record\b",
)


GROUP5_PATTERNS = (
    r"\bmaximum\b.*\bdelta[- ]?v\b",
    r"\bmax(?:imum)?\b.*\bvelocity change\b",
    r"\bmaximum\b.*\brecorded vehicle velocity change\b",
    r"\bmaximum\b.*\brecorded velocity change\b",
    r"\btime\b.*\bmaximum\b.*\bdelta[- ]?v\b",
    r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
    r"\bmaximum acceleration\b",
    r"\btime\b.*\bmaximum acceleration\b",
    r"\broll angle peak\b",
    r"\bmaximum\b.*\broll angle\b",
    r"\btime from time zero to trg\b",
    r"\blength of delta[- ]?v\b",
    r"\bclipping time\b",
    r"\baccelerometer range exceeded\b",
    r"\bsensor design range exceeded\b",
    r"\bpdof\b",
    r"\blongitudinal velocity change during algorithm run time\b",
    r"^\s*algorithm run time\b",
)


GROUP6_PATTERNS = (
    r"\bignition cycles? at investigation\b",
    r"\bpower[- ]on cycle at reading\b",
    r"\blifetime operating timer\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bsupplier id\b",
    r"\bproduction date\b",
    r"\bmodule\b.*\b(?:id|identifier|number|version)\b",
    r"\bconfiguration\b",
    r"\bconfigured for\b",
    r"\bodometer\b",
    r"\bvehicle mileage\b",
    r"\boperating time\b",
    r"\bdownload\b",
    r"\binvestigation\b",
    r"\bvin\b",
)


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


# ============================================================
# Group 5 companion context
# ============================================================

GROUP5_CONTEXT_PATTERNS = (
    r"\bpower supply status\b.*"
    r"\bmax(?:imum)?\.?\s*"
    r"(?:delta[- ]?v|velocity change)\b",
)


# ============================================================
# Family patterns
# ============================================================

FAMILY_RULES = (
    (
        "deployment_timing",
        (
            r"\btime\b.*\bdeployment command\b",
            r"\btime from algorithm enable\b.*\bdeployment\b",
            r"\bdeployment command criteria met\b.*\b(?:msec|ms|time)\b",
            r"\b1st stage time\b",
            r"\b2nd stage time\b",
            r"\bstage time from algorithm enable\b",
            r"\btime to deploy\b",
        ),
    ),

    (
        "deployment_status",
        (
            r"\bair ?bag\b.*\b(?:deployed|deployment|commanded|status)\b",
            r"\bdeployment\b.*\b(?:status|level|commanded|occurred)\b",
            r"\bfrontal deployment\b",
            r"\bside deployment\b",
            r"\bknee deployment\b",
            r"\bcurtain deployment\b",
            r"\brollover deployment\b",
            r"\bdeployment level\b",
        ),
    ),

    (
        "pretensioner_status",
        (
            r"\bpretensioner\b",
        ),
    ),

    (
        "restraint_status",
        (
            r"\bbelt switch\b",
            r"\bsafety belt\b",
            r"\bseat belt\b",
            r"\brestraint\b",
            r"\bbuckled\b",
            r"\bunbuckled\b",
        ),
    ),

    (
        "occupant_status",
        (
            r"\boccupant\b",
            r"\bpassenger classification\b",
            r"\bpassenger presence\b",
            r"\bseat occupancy\b",
            r"\boccupancy\b",
            r"\bpassenger seat position\b",
            r"\bseat position switch\b",
        ),
    ),

    (
        "event_severity_status",
        (
            r"\bevent severity\b",
            r"\bseverity status\b",
            r"\bcrash severity\b",
        ),
    ),

    (
        "warning_lamp_status",
        (
            r"\bwarning lamp\b",
            r"\bsir warning lamp\b",
            r"\bair ?bag warning\b",
            r"\bmalfunction indicator\b",
        ),
    ),

    (
        "power_event_condition",
        (
            r"\bpower loss\b.*\bevent\b",
            r"\bpower supply status\b",
            r"\bvehicle power mode status\b",
            r"\brun/crank\b",
            r"\bremote start status\b",
        ),
    ),

    (
        "high_voltage_status",
        (
            r"\bhigh voltage disable\b",
            r"\bhigh voltage\b.*\bnotification\b",
        ),
    ),

    (
        "algorithm_status",
        (
            r"\balgorithm active\b",
            r"\balgorithm status\b",
            r"\btime from time zero to algorithm start\b",
            r"\btime from time zero to algorithm reset\b",
            r"\balgorithm enable status\b",
        ),
    ),

    (
        "sensor_validity_status",
        (
            r"\bdata validity\b",
            r"\belectronic data validity\b",
            r"\bvalidity check status\b",
            r"\bdata valid\b",
            r"\bdata invalid\b",
        ),
    ),

    (
        "other_event_condition",
        (
            r"\brsca disable\b",
            r"\bonstar\b.*\b(?:sent|deployment|status)\b",
            r"\bevent condition\b",
        ),
    ),
)


# ============================================================
# Reviewed residual rules
# ============================================================

def classify_explicit_reviewed_label(
    label: str,
) -> tuple[str, str] | None:
    """
    Final reviewed decisions for residual Group 3 labels.
    """

    text = str(label or "").strip()

    if re.fullmatch(
        r"Side Seat Airbags Deployment, (?:Left|Right)",
        text,
        flags=re.I,
    ):
        return (
            "deployment_status",
            "explicit_side_airbag_deployment_state",
        )

    if re.fullmatch(
        r"Freeze Signal Factor, Side CSA Deployment, "
        r"(?:Left|Right) Side",
        text,
        flags=re.I,
    ):
        return (
            "deployment_sensor_status",
            "deployment_freeze_signal_factor_at_event",
        )

    if re.fullmatch(
        r"Freeze Signal Factor, Rollover CSA Deployment",
        text,
        flags=re.I,
    ):
        return (
            "deployment_sensor_status",
            "rollover_deployment_freeze_signal_factor_at_event",
        )

    if re.fullmatch(
        r"High-Voltage Battery Deactivation, "
        r"Time to Deployment \(ms\)",
        text,
        flags=re.I,
    ):
        return (
            "high_voltage_deactivation_timing",
            "high_voltage_battery_deactivation_deployment_timing",
        )

    if re.fullmatch(
        r"Belt tensioner deployment, "
        r"time to 1st stage, driver \(ms\)",
        text,
        flags=re.I,
    ):
        return (
            "pretensioner_timing",
            "belt_tensioner_first_stage_deployment_timing",
        )

    if re.fullmatch(
        r"Driver Center Inboard Time From Time Zero to "
        r"Deployment Loop Command Criteria Met \(ms\)",
        text,
        flags=re.I,
    ):
        return (
            "deployment_timing",
            "deployment_loop_command_criteria_timing",
        )

    if re.fullmatch(
        r"Time From Time Zero to Deployment "
        r"\(Rollover\) \(ms\)",
        text,
        flags=re.I,
    ):
        return (
            "deployment_timing",
            "rollover_deployment_timing",
        )

    if re.fullmatch(
        r"Active Head-Rest, Time to Deployment, "
        r"Front (?:Passenger|Driver) \(ms\)",
        text,
        flags=re.I,
    ):
        return (
            "restraint_deployment_timing",
            "active_head_restraint_deployment_timing",
        )

    if re.fullmatch(
        r"Tire Pressure Monitoring System Warning Light Status",
        text,
        flags=re.I,
    ):
        return (
            "warning_lamp_status",
            "event_warning_light_state",
        )

    return None


# ============================================================
# Refined special families
# ============================================================

def classify_special_group3_family(
    label: str,
) -> tuple[str, str] | None:

    text = normalize_text(
        label
    )

    # --------------------------------------------------------
    # Pretensioner timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\bpretensioner\b",
        )
        and has(
            text,
            r"\b(?:"
            r"time|time to|time from|fire|"
            r"deployment loop command criteria met"
            r")\b",
        )
    ):
        return (
            "pretensioner_timing",
            "pretensioner_activation_or_deployment_timing",
        )

    # --------------------------------------------------------
    # Restraint/protection-device timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:"
            r"belt[- ]load limiter|"
            r"adaptive load limiter|"
            r"active head ?rest(?:raint)?|"
            r"inflatable knee bolster|"
            r"knee bolster|"
            r"inflatable seatbelt|"
            r"adaptive steering column|"
            r"can(?:n)?ister vent|"
            r"battery disconnect|"
            r"rollover protection system"
            r")\b",
        )
        and has(
            text,
            r"\b(?:"
            r"time|time to|time from|"
            r"fire|deploy|deployment"
            r")\b",
        )
    ):
        return (
            "restraint_deployment_timing",
            "restraint_or_protection_device_activation_timing",
        )

    # --------------------------------------------------------
    # General deployment timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:deployment|deploy|air ?bag)\b",
        )
        and has(
            text,
            r"\b(?:"
            r"time|time to|time from|"
            r"criteria met|1st stage time|2nd stage time"
            r")\b",
        )
    ):
        return (
            "deployment_timing",
            "deployment_command_or_stage_timing",
        )

    # --------------------------------------------------------
    # Event severity timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\bevent severity\b",
        )
        and has(
            text,
            r"\btime\b",
        )
    ):
        return (
            "event_severity_timing",
            "event_severity_threshold_timing",
        )

    # --------------------------------------------------------
    # Warning-lamp history
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\bwarning lamp\b|"
            r"\bmalfunction indicator lamp\b|"
            r"\bMIL\b",
        )
        and has(
            text,
            r"\b(?:"
            r"time|minutes?|seconds?|cycles?"
            r")\b",
        )
    ):
        return (
            "warning_lamp_history",
            "warning_lamp_time_or_cycle_history",
        )

    # --------------------------------------------------------
    # Seat-track state
    # --------------------------------------------------------

    if has(
        text,
        r"\bseat track\b.*"
        r"\b(?:position|forward|foremost|status|fault)\b",
    ):
        return (
            "seat_track_status",
            "seat_track_event_state",
        )

    # --------------------------------------------------------
    # Safing/discriminating deployment
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"discriminating deployment|"
        r"safing deployment"
        r")\b",
    ):
        return (
            "deployment_sensor_status",
            "sensor_discriminating_or_safing_deployment_state",
        )

    # --------------------------------------------------------
    # Other protection devices
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"belt[- ]load limiter|"
        r"adaptive load limiter|"
        r"active head ?rest(?:raint)?|"
        r"inflatable knee bolster|"
        r"knee bolster|"
        r"inflatable seatbelt|"
        r"adaptive steering column|"
        r"battery disconnect|"
        r"rollover protection system|"
        r"can(?:n)?ister vent|"
        r"side seat airbag|"
        r"active glove box"
        r")\b",
    ):
        if has(
            text,
            r"\b(?:time|fire|deploy|deployment)\b",
        ):
            return (
                "restraint_deployment_timing",
                "protection_device_activation_or_deployment",
            )

        return (
            "restraint_activation_status",
            "protection_device_activation_state",
        )

    # --------------------------------------------------------
    # Algorithm timing
    # --------------------------------------------------------

    if has(
        text,
        r"\btime\b.*\balgorithm\b.*"
        r"\b(?:reset|wake[- ]?up|start)\b",
    ):
        return (
            "algorithm_timing",
            "algorithm_event_timing",
        )

    if has(
        text,
        r"\bfuel cutoff algorithm decision time\b",
    ):
        return (
            "algorithm_timing",
            "fuel_cutoff_algorithm_event_timing",
        )

    # --------------------------------------------------------
    # Sensor faults at wake-up
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:sensor|seat track)\b.*"
        r"\bfault\b.*"
        r"\balgorithm wake[- ]?up\b",
    ):
        return (
            "sensor_fault_status",
            "sensor_fault_state_at_algorithm_wakeup",
        )

    # --------------------------------------------------------
    # Electrical condition at algorithm wake-up
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"key on timer|"
        r"battery voltage|"
        r"energy reserve voltage"
        r")\b.*"
        r"\balgorithm wake[- ]?up\b",
    ):
        return (
            "algorithm_wakeup_condition",
            "event_electrical_state_at_algorithm_wakeup",
        )

    # --------------------------------------------------------
    # Occupant/restraint state
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"seat track position switch|"
        r"occupancy status|"
        r"occupant classification|"
        r"passenger classification|"
        r"belt switch|"
        r"safety belt"
        r")\b",
    ):
        return (
            "occupant_restraint_status",
            "occupant_or_restraint_event_state",
        )

    # --------------------------------------------------------
    # Warning state
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"warning status|"
        r"warning lamp|"
        r"brake system warning"
        r")\b",
    ):
        return (
            "warning_lamp_status",
            "warning_state",
        )

    # --------------------------------------------------------
    # Rollover sensor status explicitly recovered in PDF audit
    # --------------------------------------------------------

    if has(
        text,
        r"\brollover sensor status\b",
    ):
        return (
            "sensor_status",
            "rollover_sensor_event_status",
        )

    return None


# ============================================================
# Generic family classification
# ============================================================

def classify_generic_family(
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
# Main Group 3 classifier
# ============================================================

def classify_group3(
    observation: Observation,
) -> Group3RuleResult:
    """
    Classify one structural observation for Group 3.

    Group 3 contains non-time-series event conditions,
    deployment/restraint/occupant states, warnings,
    sensor/power states, and related event timing.

    No semantic value normalization, unit conversion,
    fuzzy event linking, or source mutation occurs here.
    """

    label = normalize_text(
        observation.label
    )

    # --------------------------------------------------------
    # Empty
    # --------------------------------------------------------

    if observation.is_empty:
        return Group3RuleResult(
            matched=False,
            destination="",
            family="",
            confidence="",
            reason="Empty row.",
        )

    # --------------------------------------------------------
    # Structural Group 4 takes precedence
    # --------------------------------------------------------

    if (
        observation.is_repeated
        or observation.is_table_header
    ):
        return Group3RuleResult(
            matched=False,
            destination="group4",
            family="time_series_measurement",
            confidence="high",
            reason=(
                "Repeated/table structure belongs to Group 4."
            ),
        )

    # --------------------------------------------------------
    # Explicit Group 1 exclusions
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.IGNORECASE,
        )
        for pattern in GROUP1_PATTERNS
    ):
        return Group3RuleResult(
            matched=False,
            destination="group1",
            family="report_metadata",
            confidence="high",
            reason="Report metadata belongs to Group 1.",
        )

    # --------------------------------------------------------
    # Group 2 exclusions
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.IGNORECASE,
        )
        for pattern in GROUP2_PATTERNS
    ):
        return Group3RuleResult(
            matched=False,
            destination="group2",
            family="record_structure",
            confidence="high",
            reason=(
                "Record/counter/recording information "
                "belongs to Group 2."
            ),
        )

    # --------------------------------------------------------
    # Group 5 companion context
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.IGNORECASE,
        )
        for pattern in GROUP5_CONTEXT_PATTERNS
    ):
        return Group3RuleResult(
            matched=False,
            destination="group5",
            family="measurement_context",
            confidence="high",
            reason=(
                "Power-supply state is explicitly tied to "
                "maximum Delta-V and therefore belongs with "
                "Group 5 measurement context."
            ),
        )

    # --------------------------------------------------------
    # Group 5 scalar crash measurements
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.IGNORECASE,
        )
        for pattern in GROUP5_PATTERNS
    ):
        return Group3RuleResult(
            matched=False,
            destination="group5",
            family="scalar_crash_measurement",
            confidence="high",
            reason=(
                "Scalar physical crash/event measurement "
                "belongs to Group 5."
            ),
        )

    # --------------------------------------------------------
    # Group 6 exclusions
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.IGNORECASE,
        )
        for pattern in GROUP6_PATTERNS
    ):
        return Group3RuleResult(
            matched=False,
            destination="group6",
            family="technical_or_configuration",
            confidence="high",
            reason=(
                "Technical/configuration/readout information "
                "belongs to Group 6."
            ),
        )

    # Explicit configuration of restraint hardware is Group 6.
    if has(
        label,
        r"\bconfigured\b.*"
        r"\b(?:belt|restraint|head restraint|pretensioner)\b",
    ):
        return Group3RuleResult(
            matched=False,
            destination="group6",
            family="configuration",
            confidence="high",
            reason=(
                "Hardware configuration is not an event-state "
                "observation."
            ),
        )

    # --------------------------------------------------------
    # Explicit reviewed residual labels
    # --------------------------------------------------------

    reviewed = (
        classify_explicit_reviewed_label(
            observation.label
        )
    )

    if reviewed is not None:
        family, reason = reviewed

        return Group3RuleResult(
            matched=True,
            destination=GROUP_NAME,
            family=family,
            confidence="high",
            reason=reason,
        )

    # --------------------------------------------------------
    # Audited special Group 3 rules
    # --------------------------------------------------------

    special = (
        classify_special_group3_family(
            observation.label
        )
    )

    if special is not None:
        family, reason = special

        return Group3RuleResult(
            matched=True,
            destination=GROUP_NAME,
            family=family,
            confidence="high",
            reason=reason,
        )

    # --------------------------------------------------------
    # Generic discovery-family rule
    # --------------------------------------------------------

    family = classify_generic_family(
        observation.label
    )

    if family:
        return Group3RuleResult(
            matched=True,
            destination=GROUP_NAME,
            family=family,
            confidence="medium",
            reason=(
                "Label matches validated Group 3 "
                "event-condition/status vocabulary."
            ),
        )

    # --------------------------------------------------------
    # Manufacturer-specific freeze signal
    #
    # Unknown forms are review, not automatically accepted.
    # --------------------------------------------------------

    if has(
        label,
        r"\bfreeze signal factor\b",
    ):
        return Group3RuleResult(
            matched=False,
            destination="review",
            family="other_event_condition",
            confidence="low",
            reason=(
                "Manufacturer-specific freeze-signal field "
                "does not match an explicitly reviewed form."
            ),
            requires_review=True,
            review_reason=(
                "No explicit reviewed Group 3 freeze-signal "
                "rule matched."
            ),
        )

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    return Group3RuleResult(
        matched=False,
        destination="",
        family="",
        confidence="",
        reason="No Group 3 rule matched.",
    )