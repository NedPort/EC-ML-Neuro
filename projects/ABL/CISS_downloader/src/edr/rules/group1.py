from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.edr.parsers.observation_parser import (
    Observation,
    normalize_text,
)


# ============================================================
# Group definition
# ============================================================

GROUP_NAME = "group1"
RULE_VERSION = "1.1"


# ============================================================
# Canonical Group 1 fields
# ============================================================

GROUP1_FIELD_NAMES = {
    "vin_entered",
    "user_entered",
    "case_number_entered",
    "imaging_date",
    "crash_date",
    "source_filename",
    "saved_on",
    "imaging_cdr_version",
    "reporting_cdr_version",
    "imaging_license_company",
    "reporting_license_company",
    "edr_device_type",
    "events_recovered_text",
    "acm_adapter_detected",
    "restraint_deployment_signal_text",
}


# ============================================================
# Exact / conservative source-label mapping
# ============================================================

GROUP1_LABEL_TO_FIELD = {
    # --------------------------------------------------------
    # VIN
    # --------------------------------------------------------
    "vin entered":
        "vin_entered",

    "vin/frame number":
        "vin_entered",

    "vin / frame number":
        "vin_entered",

    "vin entered / frame number":
        "vin_entered",

    # --------------------------------------------------------
    # User
    # --------------------------------------------------------
    "user entered":
        "user_entered",

    "user":
        "user_entered",

    # --------------------------------------------------------
    # Case
    # --------------------------------------------------------
    "case number":
        "case_number_entered",

    "case number entered":
        "case_number_entered",

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------
    "imaging date":
        "imaging_date",

    "edr data imaging date":
        "imaging_date",

    "crash date":
        "crash_date",

    # --------------------------------------------------------
    # Source file
    # --------------------------------------------------------
    "source filename":
        "source_filename",

    "file name":
        "source_filename",

    "filename":
        "source_filename",

    "saved on":
        "saved_on",

    # --------------------------------------------------------
    # CDR software versions
    # --------------------------------------------------------
    "imaged with cdr version":
        "imaging_cdr_version",

    "imaging cdr version":
        "imaging_cdr_version",

    "reported with cdr version":
        "reporting_cdr_version",

    "reporting cdr version":
        "reporting_cdr_version",

    # --------------------------------------------------------
    # License / company
    # --------------------------------------------------------
    "imaging license company":
        "imaging_license_company",

    "reporting license company":
        "reporting_license_company",

    # --------------------------------------------------------
    # Device
    # --------------------------------------------------------
    "edr device type":
        "edr_device_type",

    # --------------------------------------------------------
    # Recovered event description
    # --------------------------------------------------------
    "events recovered":
        "events_recovered_text",

    "event(s) recovered":
        "events_recovered_text",

    "recovered events":
        "events_recovered_text",

    # --------------------------------------------------------
    # Adapter
    # --------------------------------------------------------
    "acm adapter detected":
        "acm_adapter_detected",

    # --------------------------------------------------------
    # Restraint deployment signal text
    # --------------------------------------------------------
    "restraint deployment signal":
        "restraint_deployment_signal_text",
}


# ============================================================
# Group 1 section vocabulary
# ============================================================

GROUP1_METADATA_SECTION_PATTERNS = (
    "cdr file information",
    "file information",
    "report information",
)


GROUP1_DOCUMENTATION_SECTION_PATTERNS = (
    "data limitations",
    "limitations",
    "comments",
    "comment",
    "important notice",
    "notice",
    "disclaimer",
    "disclaimer of liability",
    "definitions",
    "definition",
    "interpretation",
    "vehicle coverage",
    "cdr tool limitations",
)


# ============================================================
# Documentation categories
# ============================================================

DOCUMENTATION_CATEGORY_PATTERNS = {
    "data_limitations": (
        "data limitations",
        "limitation",
        "limitations",
    ),

    "comments": (
        "comment",
        "comments",
    ),

    "notice": (
        "important notice",
        "notice",
    ),

    "disclaimer": (
        "disclaimer",
        "disclaimer of liability",
    ),

    "definitions": (
        "definition",
        "definitions",
    ),

    "interpretation_guidance": (
        "interpretation",
        "interpretation guidance",
    ),
}


# ============================================================
# Result models
# ============================================================

@dataclass
class Group1RuleResult:
    matched: bool
    destination: str
    field_family: str
    canonical_field: str
    confidence: str
    reason: str
    requires_review: bool = False
    review_reason: str = ""
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "destination": self.destination,
            "field_family": self.field_family,
            "canonical_field": self.canonical_field,
            "confidence": self.confidence,
            "reason": self.reason,
            "requires_review": self.requires_review,
            "review_reason": self.review_reason,
            "rule_version": self.rule_version,
        }


@dataclass
class Group1SelectionResult:
    chosen: dict | None
    selected_source: str
    selection_status: str
    requires_review: bool
    review_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen": self.chosen,
            "selected_source": self.selected_source,
            "selection_status": self.selection_status,
            "requires_review": self.requires_review,
            "review_reasons": self.review_reasons,
        }


# ============================================================
# Helpers
# ============================================================

def normalize_group1_label(
    value: str,
) -> str:
    return normalize_text(
        value
    ).strip(" :")


def is_group1_metadata_section(
    section: str,
) -> bool:
    section_norm = normalize_text(
        section
    )

    return any(
        pattern in section_norm
        for pattern
        in GROUP1_METADATA_SECTION_PATTERNS
    )


def documentation_category(
    text: str,
) -> str:
    normalized = normalize_text(
        text
    )

    for category, patterns in (
        DOCUMENTATION_CATEGORY_PATTERNS.items()
    ):
        if any(
            pattern in normalized
            for pattern in patterns
        ):
            return category

    return ""


def is_group1_documentation_section(
    section: str,
) -> bool:
    section_norm = normalize_text(
        section
    )

    return any(
        pattern in section_norm
        for pattern
        in GROUP1_DOCUMENTATION_SECTION_PATTERNS
    )


def canonical_group1_field(
    label: str,
) -> str:
    """
    Map a source label to the canonical Group 1 field.

    Uses explicit mappings rather than broad substring matching.
    """

    normalized = normalize_group1_label(
        label
    )

    return GROUP1_LABEL_TO_FIELD.get(
        normalized,
        "",
    )


# ============================================================
# Recovered-event safeguards
# ============================================================

def is_recovered_event_field(
    canonical_field: str,
) -> bool:
    return (
        canonical_field
        == "events_recovered_text"
    )


def recovered_event_semantic_status() -> str:
    """
    Recovered-event descriptions remain report-level text.

    They are NOT:
        - validated event IDs,
        - validated event counts,
        - CISS event links,
        - semantic event equivalence.
    """

    return (
        "report_level_source_text_"
        "not_validated_event_identity"
    )


# ============================================================
# PDF documentation quality
# ============================================================

def classify_pdf_text_quality(
    text_raw: str,
) -> str:
    """
    Preserve the quality rule used by the Group 1 CSV-first
    working dataset.
    """

    text = str(
        text_raw or ""
    )

    if "(cid:" in text:
        return (
            "font_encoding_artifact_requires_review"
        )

    return "extracted_text_candidate"


# ============================================================
# Main Group 1 classifier
# ============================================================

def classify_group1(
    observation: Observation,
) -> Group1RuleResult:
    """
    Classify one parsed EDR observation for Group 1.

    Group 1 includes:
        - report-level metadata
        - report introductory documentation

    It explicitly does NOT:
        - create event identities
        - interpret recovered-event text as event count
        - link recovered events to CISS events
        - infer equivalence between different event labels
        - extract crash measurements
        - interpret dates semantically
        - decode hexadecimal data
    """

    label = normalize_group1_label(
        observation.label
    )

    section = normalize_text(
        observation.section_context
    )

    # --------------------------------------------------------
    # Empty rows
    # --------------------------------------------------------

    if observation.is_empty:
        return Group1RuleResult(
            matched=False,
            destination="",
            field_family="",
            canonical_field="",
            confidence="",
            reason="Empty row.",
        )

    # --------------------------------------------------------
    # Repeated measurements do not belong to Group 1
    # --------------------------------------------------------

    if observation.is_repeated:
        return Group1RuleResult(
            matched=False,
            destination="",
            field_family="",
            canonical_field="",
            confidence="",
            reason=(
                "Repeated measurement structure is outside "
                "Group 1 report metadata/documentation scope."
            ),
        )

    # --------------------------------------------------------
    # Time-series headers do not belong to Group 1
    # --------------------------------------------------------

    if observation.is_table_header:
        return Group1RuleResult(
            matched=False,
            destination="",
            field_family="",
            canonical_field="",
            confidence="",
            reason=(
                "Measurement table header is outside Group 1."
            ),
        )

    # --------------------------------------------------------
    # Explicit metadata label mapping
    # --------------------------------------------------------

    canonical = canonical_group1_field(
        label
    )

    if canonical:
        return Group1RuleResult(
            matched=True,
            destination=GROUP_NAME,
            field_family="report_metadata",
            canonical_field=canonical,
            confidence="high",
            reason=(
                "Source label maps explicitly to a canonical "
                "Group 1 metadata field."
            ),
            requires_review=False,
            review_reason="",
        )
    # --------------------------------------------------------
    # Group 1 metadata section fallback
    # --------------------------------------------------------

    if (
        observation.is_scalar
        and is_group1_metadata_section(
            section
        )
    ):
        return Group1RuleResult(
            matched=True,
            destination=GROUP_NAME,
            field_family=(
                "report_metadata_unmapped"
            ),
            canonical_field="",
            confidence="medium",
            reason=(
                "Scalar source observation occurs within a "
                "Group 1 report-information section, but its "
                "label has no explicit canonical mapping."
            ),
            requires_review=True,
            review_reason=(
                "Unknown Group 1 metadata label requires "
                "review before adding a canonical mapping."
            ),
        )

    # --------------------------------------------------------
    # Metadata section heading
    # --------------------------------------------------------

    if (
        observation.is_section_heading
        and is_group1_metadata_section(
            observation.label
        )
    ):
        return Group1RuleResult(
            matched=True,
            destination=GROUP_NAME,
            field_family=(
                "report_metadata_section"
            ),
            canonical_field="",
            confidence="high",
            reason=(
                "Section heading identifies Group 1 "
                "report metadata."
            ),
        )

    # --------------------------------------------------------
    # Documentation heading
    # --------------------------------------------------------

    if (
        observation.is_section_heading
        and is_group1_documentation_section(
            observation.label
        )
    ):
        category = (
            documentation_category(
                observation.label
            )
            or "report_documentation"
        )

        return Group1RuleResult(
            matched=True,
            destination=GROUP_NAME,
            field_family=category,
            canonical_field="",
            confidence="high",
            reason=(
                "Section heading identifies introductory "
                "Group 1 report documentation."
            ),
        )

    # --------------------------------------------------------
    # Documentation content
    # --------------------------------------------------------

    if (
        section
        and is_group1_documentation_section(
            section
        )
    ):
        category = (
            documentation_category(
                section
            )
            or "report_documentation"
        )

        return Group1RuleResult(
            matched=True,
            destination=GROUP_NAME,
            field_family=category,
            canonical_field="",
            confidence="medium",
            reason=(
                "Observation is contained within a Group 1 "
                "introductory documentation section."
            ),
        )

    # --------------------------------------------------------
    # No match
    # --------------------------------------------------------

    return Group1RuleResult(
        matched=False,
        destination="",
        field_family="",
        canonical_field="",
        confidence="",
        reason="No Group 1 rule matched.",
    )


# ============================================================
# Contextual / unlabeled candidate support
# ============================================================

def classify_group1_contextual_candidate(
    source_label_status: str,
    canonical_field: str = "",
) -> tuple[
    bool,
    str,
]:
    """
    Preserve unlabeled/contextual candidates as review evidence.

    Do not promote them automatically to fully validated fields.
    """

    status = normalize_text(
        source_label_status
    )

    if (
        status
        == "absent_contextual_candidate"
    ):
        return (
            True,
            (
                "Source evidence is an unlabeled/contextual "
                "candidate and requires review."
            ),
        )

    if not canonical_field:
        return (
            False,
            "",
        )

    return (
        False,
        "",
    )


# ============================================================
# CSV-first source selection
# ============================================================

def choose_group1_source(
    observations: Iterable[dict],
    agreement_status: str = "not_compared",
    source_issue: str = "",
) -> Group1SelectionResult:
    """
    Preserve the Group 1 CSV-first policy.

    Rules
    -----
    1. CSV evidence takes priority when present.
    2. Blank or explicitly unavailable CSV values still count
       as CSV evidence.
    3. PDF is used only when CSV evidence is absent.
    4. Conflicting values within the preferred source are not
       silently selected.
    5. Contextual/unlabeled candidates remain review evidence.
    6. Multivalue CSV fields remain review evidence.
    7. CSV/PDF disagreement and source-audit issues propagate
       to the final review flag.
    """

    rows = list(
        observations
    )

    csv_rows = [
        row
        for row in rows
        if normalize_text(
            row.get(
                "source_format",
                "",
            )
        )
        == "csv"
    ]

    pdf_rows = [
        row
        for row in rows
        if normalize_text(
            row.get(
                "source_format",
                "",
            )
        )
        == "pdf"
    ]

    preferred = (
        csv_rows
        if csv_rows
        else pdf_rows
    )

    # --------------------------------------------------------
    # No evidence
    # --------------------------------------------------------

    if not preferred:
        return Group1SelectionResult(
            chosen=None,
            selected_source="absent",
            selection_status="not_extracted",
            requires_review=False,
            review_reasons=[],
        )

    selected_source = normalize_text(
        preferred[0].get(
            "source_format",
            "",
        )
    )

    # --------------------------------------------------------
    # Conflicting values within preferred source
    # --------------------------------------------------------

    distinct = {
        (
            row.get(
                "value_text",
                "",
            ),
            row.get(
                "value_status",
                "",
            ),
        )
        for row in preferred
    }

    if len(distinct) > 1:
        return Group1SelectionResult(
            chosen=None,
            selected_source=selected_source,
            selection_status=(
                "multiple_source_values_requires_review"
            ),
            requires_review=True,
            review_reasons=[
                (
                    "Preferred source contains multiple "
                    "distinct values/status combinations."
                )
            ],
        )

    chosen = preferred[0]

    selection_status = "selected"
    review_reasons: list[str] = []

    # --------------------------------------------------------
    # Contextual candidate
    # --------------------------------------------------------

    if (
        chosen.get(
            "source_label_status"
        )
        == "absent_contextual_candidate"
    ):
        selection_status = (
            "candidate_requires_review"
        )

        review_reasons.append(
            "Unlabeled/contextual source candidate."
        )

    # --------------------------------------------------------
    # Multivalue CSV field
    # --------------------------------------------------------

    if (
        chosen.get(
            "extraction_method"
        )
        == "original_csv_intro_field"
        and str(
            chosen.get(
                "value_raw",
                "",
            )
        )
        .lstrip()
        .startswith("[")
    ):
        selection_status = (
            "multivalue_requires_review"
        )

        review_reasons.append(
            "Original CSV field contains multiple values."
        )

    # --------------------------------------------------------
    # CSV/PDF agreement review
    # --------------------------------------------------------

    if (
        agreement_status
        == "source_difference_requires_review"
    ):
        review_reasons.append(
            "CSV and PDF source evidence differ."
        )

    # --------------------------------------------------------
    # Source audit issue
    # --------------------------------------------------------

    if source_issue:
        review_reasons.append(
            f"Source audit issue: {source_issue}"
        )

    requires_review = bool(
        review_reasons
        or "requires_review"
        in selection_status
    )

    return Group1SelectionResult(
        chosen=chosen,
        selected_source=selected_source,
        selection_status=selection_status,
        requires_review=requires_review,
        review_reasons=review_reasons,
    )


# ============================================================
# Selected-value helper
# ============================================================

def selected_group1_value(
    selection: Group1SelectionResult,
    observations_exist: bool = False,
) -> tuple[
    str,
    str,
]:
    """
    Return:
        value_text
        value_status
    """

    if selection.chosen is not None:
        return (
            str(
                selection.chosen.get(
                    "value_text",
                    "",
                )
            ),
            str(
                selection.chosen.get(
                    "value_status",
                    "",
                )
            ),
        )

    if observations_exist:
        return (
            "",
            "ambiguous",
        )

    return (
        "",
        "absent",
    )


# ============================================================
# Provenance helper
# ============================================================

def build_group1_selected_record(
    *,
    identity: dict[str, Any],
    field_name: str,
    observations: Iterable[dict],
    agreement_status: str = "not_compared",
    source_issue: str = "",
) -> dict[str, Any]:
    """
    Build the selected-long representation while preserving
    source provenance and review state.
    """

    observations = list(
        observations
    )

    selection = (
        choose_group1_source(
            observations=observations,
            agreement_status=agreement_status,
            source_issue=source_issue,
        )
    )

    value_text, value_status = (
        selected_group1_value(
            selection,
            observations_exist=bool(
                observations
            ),
        )
    )

    chosen = selection.chosen

    return {
        **identity,

        "field_name":
            field_name,

        "value_text":
            value_text,

        "value_raw":
            (
                chosen.get(
                    "value_raw",
                    "",
                )
                if chosen
                else ""
            ),

        "value_status":
            value_status,

        "selected_source":
            selection.selected_source,

        "selection_status":
            selection.selection_status,

        "agreement_status":
            agreement_status,

        "requires_review":
            selection.requires_review,

        "review_reasons":
            selection.review_reasons,

        "selected_source_issue":
            source_issue,

        "selected_evidence":
            chosen,

        "all_source_evidence":
            observations,

        "semantic_status":
            (
                recovered_event_semantic_status()
                if field_name
                == "events_recovered_text"
                else "source_metadata"
            ),
    }