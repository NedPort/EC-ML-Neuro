from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.edr.parsers.observation_parser import (
    Observation,
    normalize_text,
)


GROUP_NAME = "group6"
RULE_VERSION = "1.1"


@dataclass
class Group6RuleResult:
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
# Cross-group boundaries
# ============================================================

GROUP1_PATTERNS = (
    r"\bfilename\b",
    r"\bsaved on\b",
    r"\bimaged with\b",
    r"\breported with\b",
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
    r"\buser entered vin\b",
    r"\bcase number entered\b",
)


GROUP2_PATTERNS = (
    r"\bevent recording complete\b",
    r"\brecording status\b",
    r"\bcrash record locked\b",
    r"\brecord complete\b",
    r"\bevent counter\b",
    r"\bdeployment command counter\b",
    r"\bretrieval status\b",
    r"\bmultiple events?\b",
    r"\bmost recent event\b",
    r"\b\d+(?:st|nd|rd|th)\s+prior event\b",
)


GROUP3_PATTERNS = (
    r"\bair ?bag\b.*\b(?:deployment|deployed|status)\b",
    r"\bpretensioner\b",
    r"\bseat belt\b",
    r"\bsafety belt\b",
    r"\boccupant\b",
    r"\bpassenger classification\b",
    r"\bwarning lamp\b",
    r"\bevent severity\b",
    r"\bhigh[- ]?voltage disable\b",
    r"\balgorithm\b.*\b(?:wake|reset|deployment)\b",
)


GROUP5_PATTERNS = (
    r"\bmaximum\b.*\bdelta[- ]?v\b",
    r"\bmax(?:imum)?\b.*\bvelocity change\b",
    r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
    r"\bmaximum acceleration\b",
    r"\btime\b.*\bmaximum acceleration\b",
    r"\broll angle peak\b",
    r"\blength of delta[- ]?v\b",
    r"\bclipping time\b",
    r"\bpdof\b",
)


# ============================================================
# Final Group 6 families
# ============================================================

FAMILY_RULES = (
    (
        "ignition_cycle_readout",
        (
            r"\bignition cycles?\b.*"
            r"\b(?:investigation|readout|reading|download)\b",

            r"\bignition cycle\b.*\bdownload\b",

            r"\bpower[- ]on cycles?\b.*"
            r"\b(?:reading|readout|download)\b",

            r"\bcycles? at investigation\b",
            r"\bcycles? at reading\b",
        ),
    ),

    (
        "part_serial_identifier",
        (
            r"\bpart number\b",
            r"\bserial number\b",
            r"\bhardware number\b",
            r"\bbroadcast code\b",
        ),
    ),

    (
        "module_supplier",
        (
            r"\bsupplier id\b",
            r"\bsupplier code\b",
            r"\bmodule supplier\b",
            r"\bacm supplier\b",
        ),
    ),

    (
        "module_identifier",
        (
            r"\b(?:module|acm|sdm|pcm|ecm)\b.*"
            r"\b(?:id|identifier)\b",

            r"\bmanufacturer id\b",
        ),
    ),

    (
        "software_calibration_version",
        (
            r"\bsoftware\b.*"
            r"\b(?:version|number|id|strategy|date)\b",

            r"\bcalibration\b.*"
            r"\b(?:version|number|id|level|file)\b",

            r"\bfirmware\b",

            r"\bapplication version\b",
            r"\bhardware version\b",
            r"\bbootloader\b",
        ),
    ),

    (
        "production_manufacture_date",
        (
            r"\bproduction date\b",
            r"\bmanufacture date\b",
            r"\bmanufacturing date\b",
            r"\bdate of manufacture\b",
        ),
    ),

    (
        "configuration",
        (
            r"\bconfigured for\b",
            r"\bmodule configuration\b",
            r"\bequipment configuration\b",
            r"\bvehicle configuration\b",
            r"^\s*configuration\b",
        ),
    ),

    (
        "module_key_definition",
        (
            r"\bprimary key definition\b",
            r"\bprimary key\b",
        ),
    ),

    (
        "odometer_mileage",
        (
            r"\bodometer\b",
            r"\bvehicle mileage\b",
            r"\bmileage at\b",
        ),
    ),

    (
        "operating_time",
        (
            r"\boperating time\b",
            r"\blifetime operating timer\b",
            r"\bengine operating time\b",
            r"\bmodule operating time\b",
        ),
    ),

    (
        "readout_voltage",
        (
            r"\bvoltage at time of retrieval\b",
            r"\bsupply voltage at time of retrieval\b",
            r"\bvoltage at retrieval\b",
        ),
    ),

    (
        "readout_tool_status",
        (
            r"\badapter detected\b",
            r"\bdownload tool\b",
            r"\breadout tool\b",
        ),
    ),

    (
        "vehicle_identifier_technical",
        (
            r"\bcurrent vin\b",
            r"\bvehicle identification number\b",
        ),
    ),

    (
        "traceability_identifier",
        (
            r"\btraceability data\b",
            r"\btraceability number\b",
            r"\bserial/lot/batchnumber\b",
            r"\blineid\b",
            r"\bshiftid\b",
            r"\bdayoftheyear\b",
        ),
    ),

    (
        "system_type",
        (
            r"^\s*system type\b",
        ),
    ),

    (
        "edr_generation",
        (
            r"^\s*edr generation\b",
        ),
    ),

    (
        "technical_status",
        (
            r"\bmodule status\b",
            r"\bdiagnostic status\b",
            r"\bcommunication status\b",
            r"\bdata retrieval status\b",
        ),
    ),

    (
        "readout_investigation_context",
        (
            r"\bdownload date\b",
            r"\bdownload time\b",
            r"\breadout date\b",
            r"\breadout time\b",
            r"\binvestigation date\b",
            r"\binvestigator\b",
        ),
    ),
)


def classify_group6_family(
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
# Explicit final Group 3 reroutes
# ============================================================

def classify_group6_event_reroute(
    label: str,
) -> str:
    text = normalize_text(
        label
    )

    if matches(
        text,
        r"^ignition cycles at deployment\b",
    ):
        return "deployment_event_ignition_cycle"

    if matches(
        text,
        r"^ignition cycles at non[- ]deployment\b",
    ):
        return "nondeployment_event_ignition_cycle"

    if matches(
        text,
        r"^ignition cycle key on timer at start of "
        r"(?:frontal|side) event\b",
    ):
        return "event_start_ignition_timer"

    if matches(
        text,
        r"\bignition cycles? at event\b",
    ):
        return "event_ignition_cycle"

    if matches(
        text,
        r"\bignition cycle,\s*crash\b",
    ):
        return "crash_event_ignition_cycle"

    return ""


# ============================================================
# Documentation exclusions
# ============================================================

def looks_like_group6_documentation(
    label: str,
) -> bool:
    text = normalize_text(
        label
    )

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE,
        )
        for pattern in (
            r"^(?:reported|imaged) with software licensed to\b",
            r"\blatest production release\b",
            r"\bcdr software\b.*\b(?:notice|version|viewing)\b",
            r"\bsoftware and/or data\b",
            r"\bsoftware or use thereof\b",
            r"\bignition cycle\b.*\bmeans\b",
            r"\bignition cycle\b.*\bdefinition\b",
        )
    )


# ============================================================
# Main classifier
# ============================================================

def classify_group6(
    observation: Observation,
) -> Group6RuleResult:
    label = normalize_text(
        observation.label
    )

    if observation.is_empty:
        return Group6RuleResult(
            matched=False,
            destination="",
            family="",
            confidence="",
            reason="Empty row.",
        )

    # --------------------------------------------------------
    # Group 4 structural precedence
    # --------------------------------------------------------

    if (
        observation.is_repeated
        or observation.is_table_header
    ):
        return Group6RuleResult(
            matched=False,
            destination="group4",
            family="time_series_measurement",
            confidence="high",
            reason=(
                "Repeated/table structure belongs to Group 4."
            ),
        )

    # --------------------------------------------------------
    # Explicit Group 3 ignition-cycle event cases
    # --------------------------------------------------------

    reroute_reason = classify_group6_event_reroute(
        observation.label
    )

    if reroute_reason:
        return Group6RuleResult(
            matched=False,
            destination="group3",
            family="event_condition_status",
            confidence="high",
            reason=reroute_reason,
        )

    # --------------------------------------------------------
    # Documentation
    # --------------------------------------------------------

    if looks_like_group6_documentation(
        observation.label
    ):
        return Group6RuleResult(
            matched=False,
            destination="documentation",
            family="documentation",
            confidence="high",
            reason=(
                "Software/licensing/explanatory prose is "
                "documentation rather than Group 6 data."
            ),
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
        return Group6RuleResult(
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
        return Group6RuleResult(
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
        return Group6RuleResult(
            matched=False,
            destination="group3",
            family="event_condition_status",
            confidence="high",
            reason=(
                "Event/deployment/restraint/status information "
                "belongs to Group 3."
            ),
        )

    # --------------------------------------------------------
    # Group 5
    # --------------------------------------------------------

    if any(
        re.search(
            pattern,
            label,
            re.I,
        )
        for pattern in GROUP5_PATTERNS
    ):
        return Group6RuleResult(
            matched=False,
            destination="group5",
            family="scalar_crash_measurement",
            confidence="high",
            reason=(
                "Scalar crash/event measurement belongs "
                "to Group 5."
            ),
        )

    # --------------------------------------------------------
    # Final Group 6 family
    # --------------------------------------------------------

    family = classify_group6_family(
        observation.label
    )

    if family:
        return Group6RuleResult(
            matched=True,
            destination=GROUP_NAME,
            family=family,
            confidence="high",
            reason=(
                "Label matches validated Group 6 technical/"
                "configuration/readout vocabulary."
            ),
        )

    return Group6RuleResult(
        matched=False,
        destination="",
        family="",
        confidence="",
        reason="No Group 6 rule matched.",
    )