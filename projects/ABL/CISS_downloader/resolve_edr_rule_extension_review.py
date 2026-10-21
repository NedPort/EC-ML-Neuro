from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# Configuration
# ============================================================

ROOT = Path("data/processed/edr")

CONTEXT_DIR = ROOT / "rule_review_context_v1"

LABEL_CONTEXT = (
    CONTEXT_DIR
    / "edr_unresolved_label_context.csv"
)

SECTION_CONTEXT = (
    CONTEXT_DIR
    / "edr_unresolved_section_context.csv"
)

OUTPUT_DIR = ROOT / "rule_extension_resolution_v1"


# ============================================================
# Helpers
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def normalize(value: Any) -> str:
    text = clean(value).lower()

    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = text.replace("\u2212", "-")
    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


DTC_RE = re.compile(
    r"^[BCPU][0-9A-F]{4}(?:-[0-9A-F]{2})?$",
    flags=re.IGNORECASE,
)


def is_dtc(value: str) -> bool:
    return bool(
        DTC_RE.fullmatch(
            clean(value)
        )
    )


def parse_source_row(
    value: Any,
) -> list[str]:

    text = clean(value)

    if not text:
        return []

    try:
        parsed = json.loads(text)

        if isinstance(parsed, list):
            return [
                clean(x)
                for x in parsed
            ]

    except Exception:
        pass

    return []


def nonempty_values_after_label(
    source_row_json: Any,
) -> list[str]:

    row = parse_source_row(
        source_row_json
    )

    if len(row) <= 1:
        return []

    return [
        clean(x)
        for x in row[1:]
        if clean(x)
    ]


def is_repeated_measurement_row(
    source_row_json: Any,
) -> bool:
    """
    Detect repeated measurements stored either as:

        Label | v1 | v2 | v3 | ...

    or as:

        Label | "v1, v2, v3, ..."

    A packed comma-separated sequence requires at least
    5 non-empty elements to avoid mistaking ordinary
    descriptive text containing commas for a time series.
    """

    values = nonempty_values_after_label(
        source_row_json
    )

    # --------------------------------------------------------
    # Standard multi-column repeated structure
    # --------------------------------------------------------

    if len(values) >= 3:
        return True

    # --------------------------------------------------------
    # Packed repeated sequence in one CSV cell
    # --------------------------------------------------------

    if len(values) == 1:

        packed = values[0]

        tokens = [
            token.strip()
            for token in packed.split(",")
            if token.strip()
        ]

        if len(tokens) >= 5:
            return True

    return False

# ============================================================
# Explicit rule families
# ============================================================

GROUP1_LABELS = {
    "case number",
    "user",
}


GROUP6_CONFIGURATION_PATTERNS = [
    "forward collision warning present",
    "lane departure warning present",
    "left hand driver / right hand driver",
    "cruise feature is present",
    "acc type",
    "dynamic tire circumference",
]


GROUP3_EVENT_STATUS_PATTERNS = [
    "sensor blocked",
    "ppd status",
    "plausibility",
    "discrimination",
    "operation after power loss during crash",
    "state of charge",
]


GROUP3_IMPACT_PATTERNS = [
    "type of impact - type ",
]


# ============================================================
# Label occurrence resolution
# ============================================================

def resolve_label_occurrence(
    row: pd.Series,
) -> dict[str, Any]:

    raw_label = clean(
        row.get("raw_label")
    )

    label = normalize(raw_label)

    section = normalize(
        row.get("current_section")
    )

    source_row_json = row.get(
        "source_row_json"
    )

    # --------------------------------------------------------
    # Group 1 metadata
    # --------------------------------------------------------

    if label in GROUP1_LABELS:
        return {
            "final_destination": "group1",
            "final_family": "report_documentation_metadata",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Report-level documentation field."
            ),
        }

    # --------------------------------------------------------
    # Diagnostic codes
    # --------------------------------------------------------

    if is_dtc(raw_label):
        return {
            "final_destination": "diagnostic_evidence",
            "final_family": "diagnostic_trouble_code",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Standalone DTC code preserved separately; "
                "not forced into Groups 1-6."
            ),
        }

    # --------------------------------------------------------
    # IMPORTANT:
    # structural repeated-value rule before semantic routing
    # --------------------------------------------------------

    if is_repeated_measurement_row(
        source_row_json
    ):
        return {
            "final_destination": "group4",
            "final_family": "repeated_measurement",
            "resolution_confidence": "high",
            "resolution_reason": (
                "One source label is followed by multiple "
                "aligned values; structurally a repeated "
                "measurement regardless of section title."
            ),
        }

    # --------------------------------------------------------
    # Group 6 configuration
    # --------------------------------------------------------

    if any(
        pattern in label
        for pattern in GROUP6_CONFIGURATION_PATTERNS
    ):
        return {
            "final_destination": "group6",
            "final_family": "configuration",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Static technical/configuration attribute."
            ),
        }

    # --------------------------------------------------------
    # Group 3 event status
    # --------------------------------------------------------

    if any(
        pattern in label
        for pattern in GROUP3_EVENT_STATUS_PATTERNS
    ):
        return {
            "final_destination": "group3",
            "final_family": "event_condition_or_status",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Scalar state/status explicitly associated "
                "with the recorded event."
            ),
        }

    # --------------------------------------------------------
    # Group 3 impact indicators
    # --------------------------------------------------------

    if any(
        pattern in label
        for pattern in GROUP3_IMPACT_PATTERNS
    ):
        return {
            "final_destination": "group3",
            "final_family": "impact_type_status",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Boolean/event-status indicator describing "
                "impact classification."
            ),
        }

    # --------------------------------------------------------
    # Explicit event-status container
    # --------------------------------------------------------

    if "system status at event" in section:
        return {
            "final_destination": "group3",
            "final_family": "event_condition_or_status",
            "resolution_confidence": "medium",
            "resolution_reason": (
                "Scalar field occurs in event-status context "
                "and is not structurally repeated."
            ),
        }

    # --------------------------------------------------------
    # Explicit configuration container
    # --------------------------------------------------------

    if "system configuration at event" in section:
        return {
            "final_destination": "group6",
            "final_family": "configuration",
            "resolution_confidence": "medium",
            "resolution_reason": (
                "Scalar field occurs in system-configuration "
                "context."
            ),
        }

    return {
        "final_destination": "review",
        "final_family": "",
        "resolution_confidence": "low",
        "resolution_reason": (
            "No sufficiently conservative occurrence-level "
            "resolution rule matched."
        ),
    }


# ============================================================
# Section resolution
# ============================================================

def resolve_section(
    raw_section: str,
) -> dict[str, Any]:

    text = normalize(
        raw_section
    )

    # --------------------------------------------------------
    # Standalone DTC heading
    # --------------------------------------------------------

    if is_dtc(raw_section):
        return {
            "final_destination": "diagnostic_evidence",
            "final_family": "diagnostic_marker",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Standalone diagnostic trouble-code marker."
            ),
        }

    # --------------------------------------------------------
    # DTC-at-event sections
    # --------------------------------------------------------

    if (
        "dtcs present at start of event" in text
        or
        "dtcs present at time of event" in text
    ):
        return {
            "final_destination": "mixed_diagnostic_container",
            "final_family": "event_associated_diagnostic_section",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Container includes event-associated diagnostic "
                "status and may also contain repeated measurements. "
                "Rows must be routed individually."
            ),
        }

    # --------------------------------------------------------
    # System configuration
    # --------------------------------------------------------

    if "system configuration at event" in text:
        return {
            "final_destination": "group6",
            "final_family": "event_linked_configuration_container",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Section predominantly contains static technical "
                "and installed-system configuration fields."
            ),
        }

    # --------------------------------------------------------
    # System status
    # --------------------------------------------------------

    if "system status at event" in text:
        return {
            "final_destination": "mixed_container",
            "final_family": "event_system_status_container",
            "resolution_confidence": "high",
            "resolution_reason": (
                "Section contains multiple extraction families "
                "including record structure, event status, "
                "Delta-V, and technical information. "
                "Rows must be routed individually."
            ),
        }

    return {
        "final_destination": "review",
        "final_family": "",
        "resolution_confidence": "low",
        "resolution_reason": (
            "No conservative section-level resolution matched."
        ),
    }


# ============================================================
# Main
# ============================================================

def main() -> None:

    for required in [
        LABEL_CONTEXT,
        SECTION_CONTEXT,
    ]:
        if not required.exists():
            raise FileNotFoundError(
                required
            )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    labels = pd.read_csv(
        LABEL_CONTEXT,
        dtype=str,
        low_memory=False,
    )

    sections = pd.read_csv(
        SECTION_CONTEXT,
        dtype=str,
        low_memory=False,
    )

    # ========================================================
    # Resolve label occurrences
    # ========================================================

    resolved_label_rows = []

    for _, row in labels.iterrows():

        resolution = (
            resolve_label_occurrence(row)
        )

        output = row.to_dict()
        output.update(resolution)

        resolved_label_rows.append(
            output
        )

    resolved_labels = pd.DataFrame(
        resolved_label_rows
    )

    # ========================================================
    # Aggregate label-level decisions
    # ========================================================

    label_rule_rows = []

    for raw_label, group in (
        resolved_labels.groupby(
            "raw_label",
            dropna=False,
        )
    ):

        destination_counts = Counter(
            group["final_destination"]
        )

        family_counts = Counter(
            group["final_family"]
        )

        # -----------------------------------------------
        # Same label may legitimately route differently
        # under different structures.
        # -----------------------------------------------

        destinations = sorted(
            destination_counts
        )

        if len(destinations) == 1:
            label_rule_type = (
                "global_label_rule"
            )

            final_destination = (
                destinations[0]
            )

        else:
            label_rule_type = (
                "context_dependent_rule"
            )

            final_destination = (
                "context_dependent"
            )

        label_rule_rows.append(
            {
                "raw_label": clean(
                    raw_label
                ),

                "occurrence_count": int(
                    len(group)
                ),

                "rule_type": (
                    label_rule_type
                ),

                "final_destination": (
                    final_destination
                ),

                "destination_counts": json.dumps(
                    dict(destination_counts),
                    sort_keys=True,
                ),

                "family_counts": json.dumps(
                    dict(family_counts),
                    sort_keys=True,
                ),

                "requires_context": (
                    len(destinations) > 1
                ),

                "unresolved_occurrences": int(
                    (
                        group[
                            "final_destination"
                        ]
                        == "review"
                    ).sum()
                ),
            }
        )

    label_rules = pd.DataFrame(
        label_rule_rows
    )

    # ========================================================
    # Resolve sections
    # ========================================================

    section_rows = []

    for _, row in sections.iterrows():

        raw_section = clean(
            row.get("raw_section")
        )

        resolution = resolve_section(
            raw_section
        )

        output = row.to_dict()
        output.update(resolution)

        section_rows.append(
            output
        )

    resolved_sections = pd.DataFrame(
        section_rows
    )

    # ========================================================
    # Summary
    # ========================================================

    label_destination_counts = Counter(
        resolved_labels[
            "final_destination"
        ]
    )

    section_destination_counts = Counter(
        resolved_sections[
            "final_destination"
        ]
    )

    unresolved_labels = (
        resolved_labels[
            resolved_labels[
                "final_destination"
            ]
            == "review"
        ]
    )

    unresolved_sections = (
        resolved_sections[
            resolved_sections[
                "final_destination"
            ]
            == "review"
        ]
    )

    summary = {
        "created_at": utc_now(),

        "label_occurrences_processed": int(
            len(resolved_labels)
        ),

        "unique_labels_processed": int(
            resolved_labels[
                "raw_label"
            ].nunique()
        ),

        "section_occurrences_processed": int(
            len(resolved_sections)
        ),

        "unique_sections_processed": int(
            resolved_sections[
                "raw_section"
            ].nunique()
        ),

        "label_destination_counts": {
            str(k): int(v)
            for k, v
            in label_destination_counts.items()
        },

        "section_destination_counts": {
            str(k): int(v)
            for k, v
            in section_destination_counts.items()
        },

        "unresolved_label_occurrences": int(
            len(unresolved_labels)
        ),

        "unresolved_section_occurrences": int(
            len(unresolved_sections)
        ),

        "important_rules": [
            (
                "Repeated-value structure overrides "
                "section-name semantics and routes to Group 4."
            ),
            (
                "Standalone diagnostic trouble codes are "
                "preserved as diagnostic evidence rather than "
                "forced into Groups 1-6."
            ),
            (
                "SYSTEM STATUS AT EVENT is a mixed container; "
                "rows are routed independently."
            ),
            (
                "SYSTEM CONFIGURATION AT EVENT is treated as "
                "a Group 6 configuration container, while "
                "individual rows remain independently auditable."
            ),
        ],
    }

    # ========================================================
    # Save
    # ========================================================

    occurrence_path = (
        OUTPUT_DIR
        / "edr_resolved_label_occurrences.csv"
    )

    label_rule_path = (
        OUTPUT_DIR
        / "edr_resolved_label_rules.csv"
    )

    section_path = (
        OUTPUT_DIR
        / "edr_resolved_sections.csv"
    )

    unresolved_label_path = (
        OUTPUT_DIR
        / "edr_remaining_label_review.csv"
    )

    unresolved_section_path = (
        OUTPUT_DIR
        / "edr_remaining_section_review.csv"
    )

    summary_path = (
        OUTPUT_DIR
        / "edr_rule_extension_resolution_summary.json"
    )

    resolved_labels.to_csv(
        occurrence_path,
        index=False,
    )

    label_rules.to_csv(
        label_rule_path,
        index=False,
    )

    resolved_sections.to_csv(
        section_path,
        index=False,
    )

    unresolved_labels.to_csv(
        unresolved_label_path,
        index=False,
    )

    unresolved_sections.to_csv(
        unresolved_section_path,
        index=False,
    )

    with summary_path.open(
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
    # Console
    # ========================================================

    print()
    print("=" * 72)
    print("EDR RULE EXTENSION REVIEW RESOLUTION COMPLETE")
    print("=" * 72)

    print(
        f"Label occurrences processed: "
        f"{len(resolved_labels)}"
    )

    print(
        f"Unique labels: "
        f"{resolved_labels['raw_label'].nunique()}"
    )

    print()

    print("Label destinations:")

    for destination, count in sorted(
        label_destination_counts.items()
    ):
        print(
            f"  {destination}: {count}"
        )

    print()

    print(
        f"Section occurrences processed: "
        f"{len(resolved_sections)}"
    )

    print(
        f"Unique sections: "
        f"{resolved_sections['raw_section'].nunique()}"
    )

    print()

    print("Section destinations:")

    for destination, count in sorted(
        section_destination_counts.items()
    ):
        print(
            f"  {destination}: {count}"
        )

    print()

    print(
        f"Remaining unresolved label occurrences: "
        f"{len(unresolved_labels)}"
    )

    print(
        f"Remaining unresolved section occurrences: "
        f"{len(unresolved_sections)}"
    )

    print()

    print(
        f"Resolved occurrences: "
        f"{occurrence_path}"
    )

    print(
        f"Generalized label rules: "
        f"{label_rule_path}"
    )

    print(
        f"Resolved sections: "
        f"{section_path}"
    )

    print(
        f"Summary: {summary_path}"
    )

    print("=" * 72)


if __name__ == "__main__":
    main()