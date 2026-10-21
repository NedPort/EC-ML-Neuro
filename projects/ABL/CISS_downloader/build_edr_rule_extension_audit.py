from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# Configuration
# ============================================================

ROOT = Path("data/processed/edr")

COMPAT_DIR = ROOT / "compatibility_audit_v1"

UNSEEN_LABELS = COMPAT_DIR / "edr_unseen_labels.csv"
UNSEEN_SECTIONS = COMPAT_DIR / "edr_unseen_sections.csv"

OUTPUT_DIR = ROOT / "rule_extension_audit_v1"


# ============================================================
# General helpers
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()

    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = text.replace("\u2212", "-")
    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text).strip()

    return text


def contains_any(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def regex_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


# ============================================================
# DTC / diagnostic detection
# ============================================================

DTC_RE = re.compile(
    r"^[BCPU][0-9A-F]{4}(?:-[0-9A-F]{2})?$",
    flags=re.IGNORECASE,
)


def is_dtc_code(text: str) -> bool:
    return bool(DTC_RE.fullmatch(text.strip()))


# ============================================================
# Group-specific rule families
# ============================================================

# ------------------------------------------------------------
# Group 2
# Record structure / record availability / retrieval structure
# ------------------------------------------------------------

GROUP2_PATTERNS = [
    "event record",
    "record number",
    "record status",
    "recorded event",
    "events recovered",
    "event(s) recovered",
    "retrieval status",
    "record available",
    "record complete",
    "record locked",
    "number of events",
]


# ------------------------------------------------------------
# Group 3
# Event conditions, deployment, restraint, warnings, status
# ------------------------------------------------------------

GROUP3_PATTERNS = [
    "deployment",
    "deployed",
    "deploy",
    "pretensioner",
    "airbag",
    "air bag",
    "warning lamp",
    "warning light",
    "occupant",
    "seat belt",
    "seatbelt",
    "restraint",
    "safing",
    "discriminating",
    "sensor fault",
    "is faulted",
    "fault status",
    "algorithm wakeup",
    "algorithm status",
    "time from algorithm wakeup",
    "event severity",
    "activation status",
    "pyrofuse",
    "load limiter",
    "railing flag",
    "roll rate",
    "high-g",
    "low-g",
]

GROUP3_STATUS_PATTERNS = [
    " status",
    " present",
    " on - off",
    " flashing",
    " lamp",
    " fault",
    " deployment",
    " safing",
]


# ------------------------------------------------------------
# Group 4
# Repeated measurements / time series / crash pulse
# ------------------------------------------------------------

GROUP4_PATTERNS = [
    "crash pulse",
    "pre-crash data",
    "pre crash data",
    "acceleration data record",
    "angular rate",
    "time history",
    "time series",
    "sample",
]

GROUP4_EVENT_CONTEXT_PATTERNS = [
    r"most recent event",
    r"\d+(?:st|nd|rd|th) prior event",
    r"\btrg\s*\d+\b",
    r"table\s+\d+\s+of\s+\d+",
    r"deployment event",
    r"non-deployment event",
]


# ------------------------------------------------------------
# Group 5
# Scalar crash/event measurements
# ------------------------------------------------------------

GROUP5_PATTERNS = [
    "delta-v",
    "delta v",
    "velocity change",
    "maximum total delta-v",
    "maximum delta-v",
    "max delta-v",
    "peak acceleration",
    "maximum acceleration",
    "resultant",
    "pdof",
    "principal direction of force",
    "clipping time",
    "time to maximum",
    "time to peak",
    "integration time",
    "time zero offset",
    "duration",
]

GROUP5_EXCLUSIONS = [
    "recorder status",
    "recording status",
    "available",
    "not available",
]


# ------------------------------------------------------------
# Group 6
# Technical / configuration / investigation / readout metadata
# ------------------------------------------------------------

GROUP6_PATTERNS = [
    "configured for",
    "configuration",
    "configured left or right hand driver",
    "operation system time",
    "operating time",
    "system time",
    "part number",
    "serial number",
    "software version",
    "calibration",
    "module identifier",
    "module supplier",
    "component identifier",
    "traceability",
    "production date",
    "manufacture date",
    "manufacturing",
    "odometer",
    "mileage",
    "vehicle identification",
    "vin",
    "energy reserve",
    "dynamic tire circumference",
    "acc type",
    "cruise feature is present",
    "command ignition",
]


# ------------------------------------------------------------
# Documentation / diagnostic candidates
# ------------------------------------------------------------

DOCUMENTATION_PATTERNS = [
    "copyright",
    "disclaimer",
    "important notice",
    "limitations",
    "warning:",
    "software license",
    "bosch copyright",
    "cdr tool",
    "manual",
    "reference information",
]


# ============================================================
# Classification
# ============================================================

def classify_label(raw_text: str) -> dict[str, Any]:
    text = normalize_text(raw_text)

    result = {
        "proposed_destination": "review",
        "proposed_family": "",
        "novelty_class": "requires_manual_review",
        "confidence": "low",
        "reason": "",
    }

    # --------------------------------------------------------
    # Diagnostic trouble codes
    # --------------------------------------------------------

    if is_dtc_code(raw_text):
        result.update(
            {
                "proposed_destination": "review",
                "proposed_family": "diagnostic_trouble_code",
                "novelty_class": "diagnostic_or_documentation",
                "confidence": "high",
                "reason": (
                    "Standalone DTC-style code. Preserve for explicit "
                    "diagnostic review; do not automatically assign to "
                    "a scientific extraction group."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Documentation
    # --------------------------------------------------------

    if contains_any(text, DOCUMENTATION_PATTERNS):
        result.update(
            {
                "proposed_destination": "exclude",
                "proposed_family": "documentation",
                "novelty_class": "diagnostic_or_documentation",
                "confidence": "high",
                "reason": (
                    "Text matches documentation/explanatory content."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Group 4 must be checked before generic timing rules
    # --------------------------------------------------------

    if contains_any(text, GROUP4_PATTERNS):
        result.update(
            {
                "proposed_destination": "group4",
                "proposed_family": "time_series_or_repeated_measurement",
                "novelty_class": "known_group_new_structure",
                "confidence": "medium",
                "reason": (
                    "Label refers to repeated/time-indexed measurement "
                    "structure or crash-pulse/pre-crash data."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Group 3 deployment/status timing
    # --------------------------------------------------------

    if contains_any(text, GROUP3_PATTERNS):
        family = "event_condition_or_status"

        if (
            "time to" in text
            or "time from" in text
            or "(ms)" in text
            or "(msec)" in text
        ):
            family = "deployment_or_event_timing"

        elif contains_any(text, GROUP3_STATUS_PATTERNS):
            family = "event_status"

        result.update(
            {
                "proposed_destination": "group3",
                "proposed_family": family,
                "novelty_class": "known_group_new_wording",
                "confidence": "high",
                "reason": (
                    "Field describes event-associated deployment, "
                    "restraint, occupant, warning, safing, sensor, "
                    "or related status/timing information."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Group 5 scalar physics values
    # --------------------------------------------------------

    if (
        contains_any(text, GROUP5_PATTERNS)
        and not contains_any(text, GROUP5_EXCLUSIONS)
    ):
        result.update(
            {
                "proposed_destination": "group5",
                "proposed_family": "scalar_crash_measurement",
                "novelty_class": "known_group_new_wording",
                "confidence": "high",
                "reason": (
                    "Field describes a scalar crash/event measurement "
                    "rather than repeated time-series data."
                ),
            }
        )
        return result

    # Recorder status belongs to status/condition, not measurement.
    if (
        "recorder status" in text
        or "recording status" in text
    ):
        result.update(
            {
                "proposed_destination": "group3",
                "proposed_family": "recording_or_event_status",
                "novelty_class": "known_group_new_wording",
                "confidence": "medium",
                "reason": (
                    "Field reports status/availability of an event "
                    "measurement rather than the physical measurement itself."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Group 6 technical/configuration metadata
    # --------------------------------------------------------

    if contains_any(text, GROUP6_PATTERNS):
        family = "technical_metadata"

        if "configured" in text or "configuration" in text:
            family = "configuration"

        elif "operating time" in text or "operation system time" in text:
            family = "operating_time"

        elif "traceability" in text or "component identifier" in text:
            family = "traceability_identifier"

        elif "odometer" in text or "mileage" in text:
            family = "odometer_mileage"

        result.update(
            {
                "proposed_destination": "group6",
                "proposed_family": family,
                "novelty_class": "known_group_new_wording",
                "confidence": "high",
                "reason": (
                    "Field represents technical, module, configuration, "
                    "investigation, or readout metadata."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Group 2 structure
    # --------------------------------------------------------

    if contains_any(text, GROUP2_PATTERNS):
        result.update(
            {
                "proposed_destination": "group2",
                "proposed_family": "record_structure_or_status",
                "novelty_class": "known_group_new_wording",
                "confidence": "medium",
                "reason": (
                    "Field describes EDR record structure, recovery, "
                    "availability, or record-level organization."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    result["reason"] = (
        "No conservative Group 2-6 rule matched. "
        "Manual review required."
    )

    return result


def classify_section(raw_text: str) -> dict[str, Any]:
    text = normalize_text(raw_text)

    result = {
        "proposed_destination": "review",
        "proposed_family": "",
        "novelty_class": "requires_manual_review",
        "confidence": "low",
        "reason": "",
    }

    # --------------------------------------------------------
    # DTC section headings
    # --------------------------------------------------------

    if is_dtc_code(raw_text):
        result.update(
            {
                "proposed_destination": "review",
                "proposed_family": "diagnostic_trouble_code_section",
                "novelty_class": "diagnostic_or_documentation",
                "confidence": "high",
                "reason": (
                    "Section heading is a standalone DTC-style code."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Strong Group 4 structural recognition
    # --------------------------------------------------------

    if contains_any(text, GROUP4_PATTERNS):
        event_context = regex_any(
            text,
            GROUP4_EVENT_CONTEXT_PATTERNS,
        )

        family = "time_series_section"

        if "crash pulse" in text:
            family = "crash_pulse"

        elif "pre-crash" in text or "pre crash" in text:
            family = "precrash_time_series"

        elif "angular rate" in text:
            family = "angular_rate_time_series"

        elif "acceleration data record" in text:
            family = "acceleration_time_series"

        result.update(
            {
                "proposed_destination": "group4",
                "proposed_family": family,
                "novelty_class": "known_group_new_structure",
                "confidence": "high" if event_context else "medium",
                "reason": (
                    "Section represents repeated/event-indexed "
                    "measurement data. Recognition is based on structure "
                    "rather than exact section-name matching."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Deployment command sections
    # --------------------------------------------------------

    if "deployment command data" in text:
        result.update(
            {
                "proposed_destination": "group3",
                "proposed_family": "deployment_status_or_timing_section",
                "novelty_class": "known_group_new_structure",
                "confidence": "high",
                "reason": (
                    "Section contains event-associated deployment command "
                    "status/timing information."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # DTC sections with event context
    # --------------------------------------------------------

    if (
        "dtcs present at time of event" in text
        or "dtcs present at start of event" in text
    ):
        result.update(
            {
                "proposed_destination": "review",
                "proposed_family": "event_associated_diagnostic_status",
                "novelty_class": "diagnostic_or_documentation",
                "confidence": "medium",
                "reason": (
                    "Section contains diagnostics associated with an event. "
                    "Preserve for explicit review rather than automatically "
                    "including all diagnostic codes as Group 3 variables."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Traceability / technical sections
    # --------------------------------------------------------

    if (
        "traceability" in text
        or "component identifier" in text
    ):
        result.update(
            {
                "proposed_destination": "group6",
                "proposed_family": "traceability_identifier",
                "novelty_class": "known_group_new_structure",
                "confidence": "high",
                "reason": (
                    "Section contains technical component/manufacturing "
                    "traceability information."
                ),
            }
        )
        return result

    # --------------------------------------------------------
    # Generic documentation
    # --------------------------------------------------------

    if contains_any(text, DOCUMENTATION_PATTERNS):
        result.update(
            {
                "proposed_destination": "exclude",
                "proposed_family": "documentation",
                "novelty_class": "diagnostic_or_documentation",
                "confidence": "high",
                "reason": (
                    "Section appears to contain explanatory or "
                    "documentation material."
                ),
            }
        )
        return result

    result["reason"] = (
        "No conservative structural rule matched. "
        "Manual review required."
    )

    return result


# ============================================================
# Main
# ============================================================

def main() -> None:
    if not UNSEEN_LABELS.exists():
        raise FileNotFoundError(
            f"Missing unseen-label file: {UNSEEN_LABELS}"
        )

    if not UNSEEN_SECTIONS.exists():
        raise FileNotFoundError(
            f"Missing unseen-section file: {UNSEEN_SECTIONS}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    labels = pd.read_csv(
        UNSEEN_LABELS,
        dtype=str,
        low_memory=False,
    )

    sections = pd.read_csv(
        UNSEEN_SECTIONS,
        dtype=str,
        low_memory=False,
    )

    # ========================================================
    # Labels
    # ========================================================

    label_records = []

    for _, row in labels.iterrows():
        raw_label = clean_text(
            row.get("raw_label")
        )

        classification = classify_label(
            raw_label
        )

        label_records.append(
            {
                "raw_label": raw_label,
                "normalized_label": normalize_text(raw_label),
                "new_batch_occurrence_count": int(
                    float(
                        clean_text(
                            row.get(
                                "new_batch_occurrence_count"
                            )
                        )
                        or 0
                    )
                ),
                "reference_occurrence_count": int(
                    float(
                        clean_text(
                            row.get(
                                "reference_occurrence_count"
                            )
                        )
                        or 0
                    )
                ),
                **classification,
                "final_decision": "",
                "final_family": "",
                "review_notes": "",
            }
        )

    label_df = pd.DataFrame(
        label_records
    )

    # ========================================================
    # Sections
    # ========================================================

    section_records = []

    for _, row in sections.iterrows():
        raw_section = clean_text(
            row.get("raw_section")
        )

        classification = classify_section(
            raw_section
        )

        section_records.append(
            {
                "raw_section": raw_section,
                "normalized_section": normalize_text(raw_section),
                "new_batch_occurrence_count": int(
                    float(
                        clean_text(
                            row.get(
                                "new_batch_occurrence_count"
                            )
                        )
                        or 0
                    )
                ),
                "reference_occurrence_count": int(
                    float(
                        clean_text(
                            row.get(
                                "reference_occurrence_count"
                            )
                        )
                        or 0
                    )
                ),
                **classification,
                "final_decision": "",
                "final_family": "",
                "review_notes": "",
            }
        )

    section_df = pd.DataFrame(
        section_records
    )

    # ========================================================
    # Summary
    # ========================================================

    label_destination_counts = Counter(
        label_df["proposed_destination"]
    )

    section_destination_counts = Counter(
        section_df["proposed_destination"]
    )

    label_novelty_counts = Counter(
        label_df["novelty_class"]
    )

    section_novelty_counts = Counter(
        section_df["novelty_class"]
    )

    label_confidence_counts = Counter(
        label_df["confidence"]
    )

    section_confidence_counts = Counter(
        section_df["confidence"]
    )

    label_review = label_df[
        label_df["proposed_destination"] == "review"
    ].copy()

    section_review = section_df[
        section_df["proposed_destination"] == "review"
    ].copy()

    summary = {
        "created_at": utc_now(),
        "purpose": (
            "Conservative proposed routing of previously unseen "
            "EDR labels and sections before production rule updates."
        ),
        "input_unseen_labels": str(
            UNSEEN_LABELS
        ),
        "input_unseen_sections": str(
            UNSEEN_SECTIONS
        ),
        "unseen_labels": int(
            len(label_df)
        ),
        "unseen_sections": int(
            len(section_df)
        ),
        "label_proposed_destination_counts": {
            str(k): int(v)
            for k, v in label_destination_counts.items()
        },
        "section_proposed_destination_counts": {
            str(k): int(v)
            for k, v in section_destination_counts.items()
        },
        "label_novelty_class_counts": {
            str(k): int(v)
            for k, v in label_novelty_counts.items()
        },
        "section_novelty_class_counts": {
            str(k): int(v)
            for k, v in section_novelty_counts.items()
        },
        "label_confidence_counts": {
            str(k): int(v)
            for k, v in label_confidence_counts.items()
        },
        "section_confidence_counts": {
            str(k): int(v)
            for k, v in section_confidence_counts.items()
        },
        "labels_requiring_manual_review": int(
            len(label_review)
        ),
        "sections_requiring_manual_review": int(
            len(section_review)
        ),
        "notes": [
            (
                "This script proposes routing only. "
                "It does not modify Group 1-6 rules."
            ),
            (
                "Standalone DTC codes are preserved for review "
                "rather than automatically promoted to scientific "
                "features."
            ),
            (
                "Group 4 recognition prioritizes structural "
                "patterns such as crash pulse, pre-crash data, "
                "angular rate, acceleration records, event context, "
                "trigger numbers, and multi-table structure."
            ),
            (
                "Manual final_decision fields remain empty so "
                "review outcomes can be recorded explicitly."
            ),
        ],
    }

    # ========================================================
    # Write outputs
    # ========================================================

    label_output = (
        OUTPUT_DIR
        / "edr_unseen_label_rule_audit.csv"
    )

    section_output = (
        OUTPUT_DIR
        / "edr_unseen_section_rule_audit.csv"
    )

    label_review_output = (
        OUTPUT_DIR
        / "edr_unseen_labels_manual_review.csv"
    )

    section_review_output = (
        OUTPUT_DIR
        / "edr_unseen_sections_manual_review.csv"
    )

    summary_output = (
        OUTPUT_DIR
        / "edr_rule_extension_audit_summary.json"
    )

    label_df.to_csv(
        label_output,
        index=False,
    )

    section_df.to_csv(
        section_output,
        index=False,
    )

    label_review.to_csv(
        label_review_output,
        index=False,
    )

    section_review.to_csv(
        section_review_output,
        index=False,
    )

    with summary_output.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # ========================================================
    # Console summary
    # ========================================================

    print()
    print("=" * 72)
    print("EDR RULE EXTENSION AUDIT COMPLETE")
    print("=" * 72)

    print(
        f"Unseen labels audited: "
        f"{len(label_df)}"
    )

    for destination, count in sorted(
        label_destination_counts.items()
    ):
        print(
            f"  labels -> {destination}: "
            f"{count}"
        )

    print()

    print(
        f"Unseen sections audited: "
        f"{len(section_df)}"
    )

    for destination, count in sorted(
        section_destination_counts.items()
    ):
        print(
            f"  sections -> {destination}: "
            f"{count}"
        )

    print()

    print(
        f"Labels requiring manual review: "
        f"{len(label_review)}"
    )

    print(
        f"Sections requiring manual review: "
        f"{len(section_review)}"
    )

    print()

    print(
        f"Label audit: {label_output}"
    )

    print(
        f"Section audit: {section_output}"
    )

    print(
        f"Label manual review: {label_review_output}"
    )

    print(
        f"Section manual review: {section_review_output}"
    )

    print(
        f"Summary: {summary_output}"
    )

    print("=" * 72)


if __name__ == "__main__":
    main()