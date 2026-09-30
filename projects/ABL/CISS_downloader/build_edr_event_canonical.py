"""
Build one canonical, source-traceable row per Bosch-reported EDR event.

This script does not choose the "true" CISS crash event and does not
calculate ML features. It only organizes what each Bosch-reported event
contains and preserves its connection to the raw parsed source tables.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


PROCESSED_EDR_DIRECTORY = Path("data/processed/edr")

RAW_EVENT_INDEX_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_csv_raw_event_index.csv"
)

RAW_SECTION_INDEX_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_csv_raw_section_index.csv"
)

OUTPUT_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_event_canonical.csv"
)

METADATA_PATH = (
    PROCESSED_EDR_DIRECTORY
    / "edr_event_canonical_metadata.json"
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV, allowing a UTF-8 BOM when present."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Required input file was not found: {path}"
        )

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as input_file:
        return list(csv.DictReader(input_file))


def parse_json_list(value: str) -> list[str]:
    """Safely parse a JSON list stored inside a CSV cell."""
    if not value:
        return []

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    return [
        str(item)
        for item in parsed
    ]


def normalize_text(value: str | None) -> str:
    """Normalize text for conservative matching."""
    return " ".join(
        (value or "").upper().split()
    )


def classify_event_scope(event_label: str) -> str:
    """Separate report-wide information from Bosch-reported events."""
    normalized_label = normalize_text(event_label)

    if normalized_label == "FILE_LEVEL_OR_UNSPECIFIED_EVENT":
        return "file_level"

    return "reported_event"


def extract_event_recency(event_label: str) -> str:
    """
    Classify Bosch's relative event wording without inferring chronology
    for labels such as EVENT RECORD 1.
    """
    normalized_label = normalize_text(event_label)

    if "MOST RECENT" in normalized_label:
        return "most_recent"

    if re.search(
        r"\b1ST\s+PRIOR\b|\bFIRST\s+PRIOR\b",
        normalized_label,
    ):
        return "first_prior"

    if re.search(
        r"\b2ND\s+PRIOR\b|\bSECOND\s+PRIOR\b",
        normalized_label,
    ):
        return "second_prior"

    if re.search(
        r"\b3RD\s+PRIOR\b|\bTHIRD\s+PRIOR\b",
        normalized_label,
    ):
        return "third_prior"

    if re.search(
        r"\b4TH\s+PRIOR\b|\bFOURTH\s+PRIOR\b",
        normalized_label,
    ):
        return "fourth_prior"

    if re.search(
        r"\b5TH\s+PRIOR\b|\bFIFTH\s+PRIOR\b",
        normalized_label,
    ):
        return "fifth_prior"

    if "PRIOR" in normalized_label:
        return "prior_unspecified"

    return "not_stated"


def extract_source_record_number(
    event_label: str,
) -> str:
    """
    Extract a Bosch record number only when explicitly stated.

    Examples:
      EVENT RECORD 1 -> 1
      FIRST RECORD -> 1
      RECORD 2 -> 2
    """
    normalized_label = normalize_text(event_label)

    match = re.search(
        r"\b(?:EVENT\s+)?RECORD\s*#?\s*(\d+)\b",
        normalized_label,
    )

    if match:
        return match.group(1)

    ordinal_to_number = {
        "FIRST RECORD": "1",
        "SECOND RECORD": "2",
        "THIRD RECORD": "3",
        "FOURTH RECORD": "4",
        "FIFTH RECORD": "5",
    }

    return ordinal_to_number.get(
        normalized_label,
        "",
    )


def extract_source_event_number(
    event_label: str,
) -> str:
    """
    Extract a source event number from labels such as EVENT 1.

    Do not treat it as equivalent to CISS event numbering.
    """
    normalized_label = normalize_text(event_label)

    match = re.fullmatch(
        r"EVENT\s+(\d+)",
        normalized_label,
    )

    if match:
        return match.group(1)

    return ""


def extract_trigger_number(event_label: str) -> str:
    """Extract TRG number when Bosch explicitly provides one."""
    normalized_label = normalize_text(event_label)

    match = re.search(
        r"\bTRG\s*(\d+)\b",
        normalized_label,
    )

    if match:
        return match.group(1)

    return ""


def classify_event_type(event_label: str) -> str:
    """
    Preserve only event-type language explicitly present in the Bosch label.
    """
    normalized_label = normalize_text(event_label)

    if "FRONTAL" in normalized_label or "REAR" in normalized_label:
        return "frontal_or_rear"

    if "SIDE" in normalized_label:
        return "side"

    if "IMPACT" in normalized_label:
        return "impact_unspecified"

    return "not_stated"


def section_matches(
    section_category: str,
    source_heading: str,
    category_terms: tuple[str, ...],
    heading_terms: tuple[str, ...],
) -> bool:
    """Match either a standardized category or a source heading."""
    normalized_category = normalize_text(
        section_category
    )
    normalized_heading = normalize_text(
        source_heading
    )

    return (
        any(
            term in normalized_category
            for term in category_terms
        )
        or any(
            term in normalized_heading
            for term in heading_terms
        )
    )


def capability_flags(
    section_rows: list[dict[str, str]],
) -> dict[str, bool]:
    """
    Determine whether recorded content is available for major EDR concepts.

    A section counts as available only when its parsed availability is
    'recorded'. 'no_recorded_data' remains visible in separate counts.
    """
    flags = {
        "has_system_status_at_event": False,
        "has_precrash_data": False,
        "has_longitudinal_signal": False,
        "has_lateral_signal": False,
        "has_rollover_signal": False,
        "has_deployment_data": False,
        "has_dtc_at_event_data": False,
    }

    for row in section_rows:
        if normalize_text(
            row.get("availability")
        ) != "RECORDED":
            continue

        category = row.get(
            "section_category",
            "",
        )
        heading = row.get(
            "source_heading",
            "",
        )

        if section_matches(
            category,
            heading,
            category_terms=(
                "system_status_at_event",
            ),
            heading_terms=(
                "SYSTEM STATUS AT EVENT",
            ),
        ):
            flags[
                "has_system_status_at_event"
            ] = True

        if section_matches(
            category,
            heading,
            category_terms=(
                "precrash_data",
            ),
            heading_terms=(
                "PRE-CRASH DATA",
                "PRE_CRASH DATA",
            ),
        ):
            flags["has_precrash_data"] = True

        if section_matches(
            category,
            heading,
            category_terms=(
                "longitudinal_crash_pulse",
                "longitudinal_delta_v_table",
            ),
            heading_terms=(
                "LONGITUDINAL CRASH PULSE",
                "DELTA-V, LONGITUDINAL",
                "LONGITUDINAL/LATERAL CRASH PULSE",
            ),
        ):
            flags[
                "has_longitudinal_signal"
            ] = True

        if section_matches(
            category,
            heading,
            category_terms=(
                "lateral_crash_pulse",
                "lateral_delta_v_table",
            ),
            heading_terms=(
                "LATERAL CRASH PULSE",
                "DELTA-V, LATERAL",
                "LONGITUDINAL/LATERAL CRASH PULSE",
            ),
        ):
            flags["has_lateral_signal"] = True

        if section_matches(
            category,
            heading,
            category_terms=(
                "rollover_crash_pulse",
            ),
            heading_terms=(
                "ROLLOVER CRASH PULSE",
            ),
        ):
            flags["has_rollover_signal"] = True

        if section_matches(
            category,
            heading,
            category_terms=(
                "deployment_command_data",
                "deployment_data",
            ),
            heading_terms=(
                "DEPLOYMENT COMMAND DATA",
                "DEPLOYMENT DATA",
            ),
        ):
            flags[
                "has_deployment_data"
            ] = True

        if section_matches(
            category,
            heading,
            category_terms=(
                "dtc_table",
            ),
            heading_terms=(
                "DTCS PRESENT AT",
                "FAULTS PRESENT AT",
            ),
        ):
            flags[
                "has_dtc_at_event_data"
            ] = True

    return flags


def main() -> None:
    raw_event_rows = read_csv_rows(
        RAW_EVENT_INDEX_PATH
    )
    raw_section_rows = read_csv_rows(
        RAW_SECTION_INDEX_PATH
    )

    sections_by_event: dict[
        str,
        list[dict[str, str]],
    ] = defaultdict(list)

    for section_row in raw_section_rows:
        edr_event_id = section_row.get(
            "edr_event_id",
            "",
        )

        if edr_event_id:
            sections_by_event[
                edr_event_id
            ].append(section_row)

    canonical_rows: list[
        dict[str, object]
    ] = []

    for event_row in raw_event_rows:
        edr_event_id = event_row.get(
            "edr_event_id",
            "",
        )

        if not edr_event_id:
            continue

        event_label = event_row.get(
            "event_label",
            "",
        )

        event_sections = sections_by_event.get(
            edr_event_id,
            [],
        )

        availability_counts = Counter(
            row.get("availability", "")
            for row in event_sections
        )

        section_categories = sorted(
            {
                row.get("section_category", "")
                for row in event_sections
                if row.get("section_category", "")
            }
        )

        source_headings = sorted(
            {
                row.get("source_heading", "")
                for row in event_sections
                if row.get("source_heading", "")
            }
        )

        recorded_categories = sorted(
            {
                row.get("section_category", "")
                for row in event_sections
                if normalize_text(
                    row.get("availability")
                ) == "RECORDED"
                and row.get("section_category", "")
            }
        )

        csv_export_paths = sorted(
            {
                row.get("csv_export_path", "")
                for row in event_sections
                if row.get("csv_export_path", "")
            }
        )

        family_ids = sorted(
            {
                row.get("provisional_family_id", "")
                for row in event_sections
                if row.get("provisional_family_id", "")
            }
        )

        flags = capability_flags(event_sections)

        canonical_rows.append(
            {
                "edr_event_id": edr_event_id,
                "edr_file_id": event_row.get(
                    "edr_file_id",
                    "",
                ),
                "case_id": event_row.get(
                    "case_id",
                    "",
                ),
                "vehicle_number": event_row.get(
                    "vehicle_number",
                    "",
                ),
                "export_basename": event_row.get(
                    "export_basename",
                    "",
                ),
                "provisional_family_ids_json": json.dumps(
                    family_ids,
                    ensure_ascii=False,
                ),
                "event_scope": classify_event_scope(
                    event_label
                ),
                "source_event_label": event_label,
                "event_recency": extract_event_recency(
                    event_label
                ),
                "source_record_number": (
                    extract_source_record_number(
                        event_label
                    )
                ),
                "source_event_number": (
                    extract_source_event_number(
                        event_label
                    )
                ),
                "trigger_number": extract_trigger_number(
                    event_label
                ),
                "source_event_type": classify_event_type(
                    event_label
                ),
                "section_count": len(event_sections),
                "recorded_section_count": (
                    availability_counts.get(
                        "recorded",
                        0,
                    )
                ),
                "no_recorded_data_section_count": (
                    availability_counts.get(
                        "no_recorded_data",
                        0,
                    )
                ),
                "empty_section_count": (
                    availability_counts.get(
                        "empty_section",
                        0,
                    )
                ),
                "section_categories_json": json.dumps(
                    section_categories,
                    ensure_ascii=False,
                ),
                "recorded_section_categories_json": (
                    json.dumps(
                        recorded_categories,
                        ensure_ascii=False,
                    )
                ),
                "source_headings_json": json.dumps(
                    source_headings,
                    ensure_ascii=False,
                ),
                "source_csv_paths_json": json.dumps(
                    csv_export_paths,
                    ensure_ascii=False,
                ),
                **flags,
            }
        )

    canonical_rows.sort(
        key=lambda row: (
            int(row["case_id"]),
            int(row["vehicle_number"]),
            str(row["edr_event_id"]),
        )
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "edr_event_id",
        "edr_file_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "provisional_family_ids_json",
        "event_scope",
        "source_event_label",
        "event_recency",
        "source_record_number",
        "source_event_number",
        "trigger_number",
        "source_event_type",
        "section_count",
        "recorded_section_count",
        "no_recorded_data_section_count",
        "empty_section_count",
        "section_categories_json",
        "recorded_section_categories_json",
        "source_headings_json",
        "source_csv_paths_json",
        "has_system_status_at_event",
        "has_precrash_data",
        "has_longitudinal_signal",
        "has_lateral_signal",
        "has_rollover_signal",
        "has_deployment_data",
        "has_dtc_at_event_data",
    ]

    with OUTPUT_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(canonical_rows)

    scope_counts = Counter(
        row["event_scope"]
        for row in canonical_rows
    )

    availability_counts = {
        flag_name: sum(
            bool(row[flag_name])
            for row in canonical_rows
            if row["event_scope"] == "reported_event"
        )
        for flag_name in (
            "has_system_status_at_event",
            "has_precrash_data",
            "has_longitudinal_signal",
            "has_lateral_signal",
            "has_rollover_signal",
            "has_deployment_data",
            "has_dtc_at_event_data",
        )
    }

    metadata = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "script_purpose": (
            "Create a canonical, source-traceable index "
            "of Bosch-reported EDR events. This output "
            "does not select the CISS crash event and "
            "does not compute ML features."
        ),
        "input_raw_event_index": str(
            RAW_EVENT_INDEX_PATH
        ),
        "input_raw_section_index": str(
            RAW_SECTION_INDEX_PATH
        ),
        "canonical_event_count": len(
            canonical_rows
        ),
        "event_scope_counts": dict(
            scope_counts
        ),
        "reported_event_capability_counts": (
            availability_counts
        ),
        "output_csv": str(OUTPUT_PATH),
    }

    with METADATA_PATH.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            metadata,
            output_file,
            indent=2,
            ensure_ascii=False,
        )

    print("Canonical EDR event index completed.")
    print(
        f"Canonical rows: {len(canonical_rows)}"
    )
    print(f"Output: {OUTPUT_PATH}")
    print(f"Metadata: {METADATA_PATH}")
    print()
    print("Event scopes:")

    for scope, count in sorted(
        scope_counts.items()
    ):
        print(f"  {scope}: {count}")

    print()
    print(
        "Recorded capabilities among "
        "reported Bosch events:"
    )

    for capability, count in sorted(
        availability_counts.items()
    ):
        print(f"  {capability}: {count}")


if __name__ == "__main__":
    main()