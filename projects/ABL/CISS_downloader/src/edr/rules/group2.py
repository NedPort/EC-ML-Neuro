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

GROUP_NAME = "group2"
RULE_VERSION = "1.1"


# ============================================================
# Result model
# ============================================================

@dataclass
class Group2RuleResult:
    matched: bool
    destination: str
    field_family: str
    confidence: str
    reason: str
    resolved_scope: str = ""
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "destination": self.destination,
            "field_family": self.field_family,
            "confidence": self.confidence,
            "reason": self.reason,
            "resolved_scope": self.resolved_scope,
            "rule_version": self.rule_version,
        }


# ============================================================
# Group 2 section-heading recognition
# ============================================================

GROUP2_TARGET_HEADING_RE = re.compile(
    r"^(?:"
    r"system status"
    r"|status (?:at|of)"
    r"|event (?:record )?summary"
    r"|front/?rear event record summary"
    r"|event data"
    r"|crash event data"
    r"|record status"
    r"|event record(?: information| status)?\b"
    r"|impact event record\b"
    r"|pcm module information"
    r"|pcm edr data"
    r")",
    re.IGNORECASE,
)


GROUP2_EVENT_RE = re.compile(
    r"(?:"
    r"(?:most recent|\d+(?:st|nd|rd|th) prior|prior|first|second|third|\d+)"
    r"\s+(?:frontal\s*/\s*rear\s+)?(?:event|record)"
    r"|(?:impact )?event record\s*\d+"
    r"|record\s*\d+"
    r"|event\s*\d+"
    r"|rollover event record"
    r"|TRG INVALID\s*#\d+"
    r")",
    re.IGNORECASE,
)


HEX_BLOCK_RE = re.compile(
    r"^(?:"
    r"pidsstart"
    r"|pidsend"
    r"|hexadecimal data"
    r"|raw (?:hex|byte)"
    r")\b",
    re.IGNORECASE,
)


# ============================================================
# Original Group 2 field-routing vocabulary
# ============================================================

GROUP2_FIELD_RE = re.compile(
    r"(?:"
    r"event record type"
    r"|algorithm active"
    r"|life\s*time counter"
    r"|record.*status"
    r"|recording status"
    r"|complete.*record"
    r"|record.*complete"
    r"|locked"
    r"|freeze signal"
    r"|data (?:sent|recorded|available)"
    r"|concurrent event"
    r"|event (?:counter|number|type)"
    r"|crash type"
    r"|trg count"
    r"|number of events"
    r"|timer"
    r"|time from event"
    r"|time from pre-crash"
    r"|linked.*page"
    r"|event recorded last"
    r")",
    re.IGNORECASE,
)


# ============================================================
# Reviewed unresolved Group 2 decisions
# ============================================================

GROUP2_CONTEXT_LABELS = {
    "dynamic deployment event counter":
        "report_event_context",

    "dynamic event counter":
        "report_event_context",

    "dynamic onstar notification event counter":
        "report_event_context",

    "recording status, rollover crash info.":
        "event_context_unlinked",
}


GROUP3_DEFERRED_LABELS = {
    "event severity status, driver",
    "event severity status, passenger",
}


GROUP6_DEFERRED_LABELS = {
    "ignition cycles at investigation",
}


# ============================================================
# Retrieval event descriptors
# ============================================================

RETRIEVAL_EVENT_DESCRIPTORS = {
    "unlocked event": {
        "descriptor_subtype":
            "standard_retrieved_event",

        "record_storage_status":
            "not_assumed",
    },

    "locked side event": {
        "descriptor_subtype":
            "standard_retrieved_event",

        "record_storage_status":
            "not_assumed",
    },

    "locked rollover event": {
        "descriptor_subtype":
            "standard_retrieved_event",

        "record_storage_status":
            "not_assumed",
    },

    "fuel cutoff level 1": {
        "descriptor_subtype":
            "fuel_cutoff_event_descriptor",

        "record_storage_status":
            "not_assumed",
    },
}


# ============================================================
# Heading helpers
# ============================================================

def is_group2_target_heading(
    heading: str,
) -> bool:
    """
    Conservative Group 2 structural-heading recognition.

    Recognition of a heading does NOT establish a validated event.
    """

    text = str(
        heading or ""
    ).strip()

    if not text:
        return False

    if not GROUP2_TARGET_HEADING_RE.search(
        text
    ):
        return False

    # Narrative lines are not headings.
    if re.search(
        r"\b(?:"
        r"section of the report"
        r"|reflects the"
        r"|experienced from"
        r"|refer to"
        r"|indicates that"
        r")\b",
        text,
        re.IGNORECASE,
    ):
        return False

    # Key/value field, not section heading.
    if re.match(
        r"^Event Record Type\b",
        text,
        re.IGNORECASE,
    ):
        return False

    if len(text) > 180:
        return False

    if re.match(
        r"^(?:Impact )?Event Record\b",
        text,
        re.IGNORECASE,
    ):
        return bool(
            re.fullmatch(
                r"(?:Impact )?"
                r"Event Record"
                r"(?:"
                r"\s+#?\d+"
                r"|\s+(?:Information|Status)"
                r"|\s+Summary(?:\s+At\s+Retrieval)?"
                r")"
                r"(?:\s*\([^)]*\))?",
                text,
                re.IGNORECASE,
            )
        )

    return True


def classify_group2_heading(
    heading: str,
) -> tuple[str, str, str]:
    """
    Returns:
        scope
        event_label_candidate
        label_status

    IMPORTANT:
    Event labels remain provisional source-label candidates.
    """

    text = str(
        heading or ""
    ).strip()

    if re.fullmatch(
        r"PCM MODULE INFORMATION",
        text,
        re.IGNORECASE,
    ):
        return (
            "module_level",
            "",
            "not_event_specific",
        )

    if re.fullmatch(
        r"PCM EDR DATA",
        text,
        re.IGNORECASE,
    ):
        return (
            "pcm_buffer_scope_requires_review",
            "",
            "buffer_not_assumed_event",
        )

    if re.search(
        r"retrieval|download|current",
        text,
        re.IGNORECASE,
    ):
        return (
            "retrieval_level",
            "",
            "not_event_specific",
        )

    if re.search(
        r"event.*summary|summary.*event",
        text,
        re.IGNORECASE,
    ):
        return (
            "record_summary_scope_requires_review",
            "",
            "summary_not_one_event",
        )

    # Preserve complete parenthetical source text if it contains
    # the apparent record/event description.
    match = re.search(
        r"\((.*)\)",
        text,
    )

    label = ""

    if (
        match
        and GROUP2_EVENT_RE.search(
            match.group(1)
        )
    ):
        label = match.group(1)

    if not label:
        event_match = (
            GROUP2_EVENT_RE.search(
                text
            )
        )

        if event_match:
            label = event_match.group(0)

    if label:
        return (
            "reported_record_candidate",
            label,
            "provisional_source_label",
        )

    return (
        "scope_requires_review",
        "",
        "unspecified",
    )


# ============================================================
# Record label / trigger handling
# ============================================================

def split_record_label_and_trigger(
    record_label_raw: str,
) -> tuple[str, str]:
    """
    Split source record descriptions such as:

        MOST RECENT EVENT, TRG #1

    without inventing an event identity.
    """

    text = (
        str(record_label_raw or "")
        .strip()
        .upper()
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    match = re.match(
        r"^(.*?)"
        r"(?:\s*[,;\-]?\s*"
        r"TRG(?:IGGER)?\s*#?\s*"
        r"([A-Z0-9]+))$",
        text,
    )

    if not match:
        return (
            text,
            "",
        )

    base_label = (
        match.group(1)
        .strip(" ,;-")
    )

    trigger = (
        match.group(2)
        .strip()
    )

    return (
        base_label,
        trigger,
    )


# ============================================================
# Conservative summary-to-record linking
# ============================================================

def link_summary_to_record_candidate(
    report_id: str,
    reported_record_label: str,
    reported_trigger_reference: str,
    record_candidates_by_report: dict[
        str,
        list[dict],
    ],
) -> dict[str, Any]:
    """
    Link only when there is conservative same-report evidence.

    No fuzzy matching.
    No cross-report matching.
    No semantic event equivalence.
    """

    summary_label = re.sub(
        r"\s+",
        " ",
        str(
            reported_record_label or ""
        ).strip(),
    ).upper()

    summary_trigger = re.sub(
        r"\s+",
        " ",
        str(
            reported_trigger_reference or ""
        ).strip(),
    ).upper()

    candidates = (
        record_candidates_by_report.get(
            report_id,
            [],
        )
    )

    # --------------------------------------------------------
    # Exact label + explicit trigger
    # --------------------------------------------------------

    trigger_matches = []

    for candidate in candidates:
        (
            candidate_label,
            candidate_trigger,
        ) = split_record_label_and_trigger(
            candidate.get(
                "record_label_raw",
                "",
            )
        )

        if (
            candidate_label == summary_label
            and candidate_trigger
            and candidate_trigger
            == summary_trigger
        ):
            trigger_matches.append(
                candidate
            )

    if len(trigger_matches) == 1:
        candidate = (
            trigger_matches[0]
        )

        return {
            "linked_record_candidate_id":
                candidate.get(
                    "record_candidate_id",
                    "",
                ),

            "linked_record_label_raw":
                candidate.get(
                    "record_label_raw",
                    "",
                ),

            "link_method":
                "same_report_exact_label_trigger",

            "link_status":
                "linked_exact_label_trigger",

            "link_candidate_count": 1,

            "requires_review": False,
        }

    # --------------------------------------------------------
    # Exact label, unique within report
    # --------------------------------------------------------

    label_matches = []

    for candidate in candidates:
        candidate_label, _ = (
            split_record_label_and_trigger(
                candidate.get(
                    "record_label_raw",
                    "",
                )
            )
        )

        if (
            candidate_label
            == summary_label
        ):
            label_matches.append(
                candidate
            )

    if len(label_matches) == 1:
        candidate = (
            label_matches[0]
        )

        return {
            "linked_record_candidate_id":
                candidate.get(
                    "record_candidate_id",
                    "",
                ),

            "linked_record_label_raw":
                candidate.get(
                    "record_label_raw",
                    "",
                ),

            "link_method":
                "same_report_unique_exact_label",

            "link_status":
                "linked_unique_label",

            "link_candidate_count": 1,

            "requires_review": False,
        }

    # --------------------------------------------------------
    # No candidates in report
    # --------------------------------------------------------

    if not candidates:
        return {
            "linked_record_candidate_id": "",
            "linked_record_label_raw": "",

            "link_method":
                "report_has_no_record_candidates",

            "link_status":
                "no_record_candidate_available",

            "link_candidate_count": 0,

            "requires_review": True,
        }

    # --------------------------------------------------------
    # Ambiguous
    # --------------------------------------------------------

    return {
        "linked_record_candidate_id": "",
        "linked_record_label_raw": "",

        "link_method":
            "no_unique_conservative_match",

        "link_status":
            "ambiguous_or_unresolved",

        "link_candidate_count":
            max(
                len(trigger_matches),
                len(label_matches),
            ),

        "requires_review": True,
    }


# ============================================================
# Retrieval-event descriptor
# ============================================================

def classify_retrieval_event_descriptor(
    value: str,
) -> dict[str, str] | None:
    """
    Recognize only reviewed standalone retrieval descriptors.

    These descriptors must NOT be interpreted as proof that a
    separate EDR event record was stored.
    """

    text = normalize_text(
        value
    )

    definition = (
        RETRIEVAL_EVENT_DESCRIPTORS.get(
            text
        )
    )

    if definition is None:
        return None

    return {
        "descriptor_normalized":
            text,

        **definition,
    }


# ============================================================
# Main field classifier
# ============================================================

def classify_group2(
    observation: Observation,
) -> Group2RuleResult:
    """
    Decide whether a structural observation belongs to Group 2.

    Group 2:
        recorded events,
        record structure,
        record/retrieval status,
        event counters and contextual record information.

    This classifier does NOT establish semantic event identity.
    """

    label = normalize_text(
        observation.label
    )

    section = normalize_text(
        observation.section_context
    )

    # --------------------------------------------------------
    # Structural exclusions
    # --------------------------------------------------------

    if observation.is_empty:
        return Group2RuleResult(
            matched=False,
            destination="",
            field_family="",
            confidence="",
            reason="Empty row.",
        )

    # Repeated temporal structure always belongs to Group 4,
    # even if located inside a Group 2-looking section.
    if (
        observation.is_repeated
        or observation.is_table_header
    ):
        return Group2RuleResult(
            matched=False,
            destination="",
            field_family="",
            confidence="",
            reason=(
                "Repeated/table structure must be evaluated "
                "by Group 4 before Group 2 semantics."
            ),
        )

    # --------------------------------------------------------
    # Reviewed explicit deferrals
    # --------------------------------------------------------

    if label in GROUP3_DEFERRED_LABELS:
        return Group2RuleResult(
            matched=False,
            destination="group3",
            field_family=(
                "event_conditions_deployment"
            ),
            confidence="high",
            reason=(
                "Reviewed Group 2 unresolved field was "
                "explicitly deferred to Group 3."
            ),
        )

    if label in GROUP6_DEFERRED_LABELS:
        return Group2RuleResult(
            matched=False,
            destination="group6",
            field_family=(
                "other_recorded_information"
            ),
            confidence="high",
            reason=(
                "Investigation-time ignition-cycle count is "
                "post-crash/retrieval technical context."
            ),
        )

    # --------------------------------------------------------
    # Reviewed Group 2 contextual fields
    # --------------------------------------------------------

    if label in GROUP2_CONTEXT_LABELS:
        return Group2RuleResult(
            matched=True,
            destination="group2",
            field_family="status_context",
            confidence="high",
            reason=(
                "Reviewed contextual Group 2 field."
            ),
            resolved_scope=(
                GROUP2_CONTEXT_LABELS[
                    label
                ]
            ),
        )

    # --------------------------------------------------------
    # Explicit record/status vocabulary
    # --------------------------------------------------------

    if GROUP2_FIELD_RE.search(
        label
    ):
        return Group2RuleResult(
            matched=True,
            destination="group2",
            field_family=(
                "record_structure_or_status"
            ),
            confidence="high",
            reason=(
                "Label matches validated Group 2 "
                "record/status vocabulary."
            ),
            resolved_scope=(
                "record_or_event_context"
            ),
        )

    # --------------------------------------------------------
    # Section scope
    # --------------------------------------------------------

    scope, _, _ = (
        classify_group2_heading(
            section
        )
    )

    if scope == "reported_record_candidate":
        return Group2RuleResult(
            matched=True,
            destination="group2",
            field_family="record_status",
            confidence="medium",
            reason=(
                "Scalar observation occurs within a "
                "provisional source record candidate."
            ),
            resolved_scope="record_candidate",
        )

    if scope == "retrieval_level":
        return Group2RuleResult(
            matched=True,
            destination="group2",
            field_family="retrieval_status",
            confidence="medium",
            reason=(
                "Scalar observation occurs within "
                "retrieval-level Group 2 context."
            ),
            resolved_scope="retrieval_level",
        )

    # PCM data remain quarantined until structural evaluation.
    if (
        scope
        == "pcm_buffer_scope_requires_review"
    ):
        return Group2RuleResult(
            matched=False,
            destination="review",
            field_family="pcm_buffer",
            confidence="high",
            reason=(
                "PCM EDR data are not assumed to be "
                "ordinary Group 2 scalar fields."
            ),
            resolved_scope=scope,
        )

    if (
        scope
        == "record_summary_scope_requires_review"
    ):
        return Group2RuleResult(
            matched=False,
            destination="review",
            field_family="record_summary",
            confidence="high",
            reason=(
                "Summary structure requires dedicated "
                "summary parsing/linking rather than "
                "ordinary scalar routing."
            ),
            resolved_scope=scope,
        )

    return Group2RuleResult(
        matched=False,
        destination="",
        field_family="",
        confidence="",
        reason="No Group 2 rule matched.",
    )