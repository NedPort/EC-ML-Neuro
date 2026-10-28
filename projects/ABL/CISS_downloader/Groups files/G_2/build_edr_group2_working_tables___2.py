"""
Build source-preserving Group 2 CSV working views.

Includes:
- conservative summary parsing
- conservative summary-to-record linking
- standalone retrieval event descriptor classification
- targeted routing of previously unresolved status fields
- contextual Group 2 scope resolution without inventing record identity
"""

import argparse
import csv
import json
import hashlib
import re

from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone

from build_edr_group2_field_audit import route


csv.field_size_limit(10000000)

BASE = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


# ============================================================
# Confirmed standalone retrieval event descriptors
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
# Review decisions for fields that were originally unresolved
#
# IMPORTANT:
# These rules are applied ONLY after the original routing
# placed the observation into unresolved Group-2 scope.
# ============================================================

UNRESOLVED_STATUS_ROUTING = {

    # --------------------------------------------------------
    # Group 2 contextual information
    # --------------------------------------------------------

    "dynamic deployment event counter": {
        "target":
            "group2_context",

        "proposed_group":
            "group2_status_context",

        "resolved_scope":
            "report_event_context",

        "routing_reason":
            (
                "General event counter belongs to Group 2, "
                "but is report-level event context rather "
                "than a validated specific record."
            ),
    },

    "dynamic event counter": {
        "target":
            "group2_context",

        "proposed_group":
            "group2_status_context",

        "resolved_scope":
            "report_event_context",

        "routing_reason":
            (
                "General event counter belongs to Group 2, "
                "but is report-level event context rather "
                "than a validated specific record."
            ),
    },

    "dynamic onstar notification event counter": {
        "target":
            "group2_context",

        "proposed_group":
            "group2_status_context",

        "resolved_scope":
            "report_event_context",

        "routing_reason":
            (
                "General OnStar notification event counter "
                "belongs to Group 2 report-level event context."
            ),
    },

    "recording status, rollover crash info.": {
        "target":
            "group2_context",

        "proposed_group":
            "group2_status_context",

        "resolved_scope":
            "event_context_unlinked",

        "routing_reason":
            (
                "Recording completeness belongs to Group 2 "
                "event status, but no validated record-candidate "
                "identity is available."
            ),
    },

    # --------------------------------------------------------
    # Group 3
    # --------------------------------------------------------

    "event severity status, driver": {
        "target":
            "group3_deferred",

        "proposed_group":
            "group3_event_conditions_deployment",

        "resolved_scope":
            "",

        "routing_reason":
            (
                "Driver-side event severity describes "
                "event/deployment system conditions."
            ),
    },

    "event severity status, passenger": {
        "target":
            "group3_deferred",

        "proposed_group":
            "group3_event_conditions_deployment",

        "resolved_scope":
            "",

        "routing_reason":
            (
                "Passenger-side event severity describes "
                "event/deployment system conditions."
            ),
    },

    # --------------------------------------------------------
    # Group 6
    # --------------------------------------------------------

    "ignition cycles at investigation": {
        "target":
            "group6_deferred",

        "proposed_group":
            "group6_other_recorded_information",

        "resolved_scope":
            "",

        "routing_reason":
            (
                "Investigation-time ignition-cycle count "
                "is post-crash/retrieval context."
            ),
    },
}


# ============================================================
# Basic I/O
# ============================================================

def read(path):

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:

        return list(
            csv.DictReader(f)
        )


def write(
    path,
    rows,
    columns,
):

    tmp = path.with_suffix(
        path.suffix + ".part"
    )

    with tmp.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=columns,
        )

        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


# ============================================================
# Normalization
# ============================================================

def normalize_text(value):

    value = (
        value or ""
    ).strip()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.upper()


def normalize_lower(value):

    value = (
        value or ""
    ).strip()

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.lower()


# ============================================================
# Record label / trigger parsing
# ============================================================

def split_record_label_and_trigger(
    record_label_raw,
):

    text = normalize_text(
        record_label_raw
    )

    match = re.match(
        r"^(.*?)"
        r"(?:\s*[,;\-]?\s*TRG(?:IGGER)?\s*#?\s*([A-Z0-9]+))$",
        text,
    )

    if match:

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

    return (
        text,
        "",
    )


# ============================================================
# Conservative summary -> record candidate linking
# ============================================================

def link_summary_to_record_candidate(
    report_id,
    reported_record_label,
    reported_trigger_reference,
    record_candidates_by_report,
):

    summary_label = normalize_text(
        reported_record_label
    )

    summary_trigger = normalize_text(
        reported_trigger_reference
    )

    report_candidates = (
        record_candidates_by_report.get(
            report_id,
            [],
        )
    )

    # --------------------------------------------------------
    # 1. Exact label + explicit trigger
    # --------------------------------------------------------

    trigger_matches = []

    for candidate in report_candidates:

        candidate_label, candidate_trigger = (
            split_record_label_and_trigger(
                candidate[
                    "record_label_raw"
                ]
            )
        )

        if (
            candidate_label
            == summary_label

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
                candidate[
                    "record_candidate_id"
                ],

            "linked_record_label_raw":
                candidate[
                    "record_label_raw"
                ],

            "link_method":
                "same_report_exact_label_trigger",

            "link_status":
                "linked_exact_label_trigger",

            "link_candidate_count":
                1,

            "requires_review":
                False,
        }

    # --------------------------------------------------------
    # 2. Exact label if unique inside report
    # --------------------------------------------------------

    label_matches = []

    for candidate in report_candidates:

        candidate_label, _ = (
            split_record_label_and_trigger(
                candidate[
                    "record_label_raw"
                ]
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
                candidate[
                    "record_candidate_id"
                ],

            "linked_record_label_raw":
                candidate[
                    "record_label_raw"
                ],

            "link_method":
                "same_report_unique_exact_label",

            "link_status":
                "linked_unique_label",

            "link_candidate_count":
                1,

            "requires_review":
                False,
        }

    # --------------------------------------------------------
    # 3. Report has no record candidates
    # --------------------------------------------------------

    if not report_candidates:

        return {

            "linked_record_candidate_id":
                "",

            "linked_record_label_raw":
                "",

            "link_method":
                "report_has_no_record_candidates",

            "link_status":
                "no_record_candidate_available",

            "link_candidate_count":
                0,

            "requires_review":
                True,
        }

    # --------------------------------------------------------
    # 4. Ambiguous / unresolved
    # --------------------------------------------------------

    unresolved_count = max(
        len(trigger_matches),
        len(label_matches),
    )

    return {

        "linked_record_candidate_id":
            "",

        "linked_record_label_raw":
            "",

        "link_method":
            "no_unique_conservative_match",

        "link_status":
            "ambiguous_or_unresolved",

        "link_candidate_count":
            unresolved_count,

        "requires_review":
            True,
    }


# ============================================================
# Standalone retrieval event descriptor classifier
# ============================================================

def classify_retrieval_event_descriptor(
    row,
):

    if (
        row.get(
            "scope_candidate",
            "",
        )
        != "retrieval_level"
    ):
        return None

    if (
        row.get(
            "row_role",
            "",
        )
        != "unresolved_text"
    ):
        return None

    try:

        values = json.loads(
            row.get(
                "source_row_json",
                "[]",
            )
        )

    except json.JSONDecodeError:

        return None

    if (
        not isinstance(
            values,
            list,
        )
        or len(values) != 1
    ):

        return None

    value_raw = str(
        values[0]
    ).strip()

    value_normalized = (
        normalize_lower(
            value_raw
        )
    )

    descriptor_info = (
        RETRIEVAL_EVENT_DESCRIPTORS.get(
            value_normalized
        )
    )

    if descriptor_info is None:

        return None

    return {

        "descriptor_raw":
            value_raw,

        "descriptor_normalized":
            value_normalized,

        "proposed_group":
            "group2_recorded_events_status",

        "descriptor_type":
            "retrieved_event_descriptor",

        "descriptor_subtype":
            descriptor_info[
                "descriptor_subtype"
            ],

        "record_storage_status":
            descriptor_info[
                "record_storage_status"
            ],

        "routing_reason":
            (
                "Standalone retrieval-level text "
                "matches a confirmed recovered-event "
                "descriptor. Presence of the descriptor "
                "does not itself establish a separately "
                "stored EDR record."
            ),

        "requires_review":
            False,
    }


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_extract_v2"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_working_v1"
        ),
    )

    args = parser.parse_args()

    src = args.input_directory
    out = args.output_directory

    if (
        src.resolve()
        == out.resolve()
    ):

        parser.error(
            "Preserve extraction outputs "
            "in a separate directory"
        )

    # ========================================================
    # Load inputs
    # ========================================================

    sections = read(
        src
        / "section_evidence.csv"
    )

    fields = read(
        src
        / "status_fields_long.csv"
    )

    tables = read(
        src
        / "summary_and_unresolved_rows.csv"
    )

    records = read(
        src
        / "record_candidates.csv"
    )

    coverage = read(
        src
        / "report_coverage.csv"
    )

    # ========================================================
    # Lookups
    # ========================================================

    section_lookup = {

        row["section_id"]:
            row

        for row
        in sections
    }

    record_candidates_by_report = (
        defaultdict(list)
    )

    for record in records:

        record_candidates_by_report[
            record["report_id"]
        ].append(
            record
        )

    # ========================================================
    # Field output buckets
    # ========================================================

    dest = {

        "record_status_long":
            [],

        "retrieval_status_long":
            [],

        "group2_context_status_long":
            [],

        "unresolved_status_long":
            [],

        "other_group_fields_long":
            [],

        "group3_deferred_from_unresolved_long":
            [],

        "group6_deferred_from_unresolved_long":
            [],
    }

    field_columns = (
        list(
            fields[0]
        )
        + [
            "source_format",
            "source_path",
            "source_sha256",
            "source_heading",
            "proposed_group",
            "routing_reason",
            "resolved_scope",
        ]

        if fields

        else
        BASE
    )

    # ========================================================
    # Route fields
    # ========================================================

    for field in fields:

        section = (
            section_lookup[
                field[
                    "section_id"
                ]
            ]
        )

        # ----------------------------------------------------
        # Original routing first
        # ----------------------------------------------------

        original_group, original_reason = (
            route(
                field[
                    "field_label_raw"
                ]
            )
        )

        item = {

            **field,

            **{
                key:
                    section[key]

                for key in [
                    "source_format",
                    "source_path",
                    "source_sha256",
                    "source_heading",
                ]
            },

            "proposed_group":
                original_group,

            "routing_reason":
                original_reason,

            "resolved_scope":
                "",
        }

        # ----------------------------------------------------
        # Preserve existing non-Group-2 classification
        # ----------------------------------------------------

        if (
            original_group
            != "group2_status_context"
        ):

            bucket = (
                "other_group_fields_long"
            )

        # ----------------------------------------------------
        # Existing validated record-level Group 2
        # ----------------------------------------------------

        elif (
            field[
                "scope_candidate"
            ]
            == "reported_record_candidate"
        ):

            bucket = (
                "record_status_long"
            )

        # ----------------------------------------------------
        # Existing validated retrieval-level Group 2
        # ----------------------------------------------------

        elif (
            field[
                "scope_candidate"
            ]
            == "retrieval_level"
        ):

            bucket = (
                "retrieval_status_long"
            )

        # ----------------------------------------------------
        # Only review observations that were already
        # unresolved under the original logic
        # ----------------------------------------------------

        else:

            normalized_label = (
                normalize_lower(
                    field[
                        "field_label_raw"
                    ]
                )
            )

            decision = (
                UNRESOLVED_STATUS_ROUTING.get(
                    normalized_label
                )
            )

            if decision is None:

                bucket = (
                    "unresolved_status_long"
                )

            else:

                item[
                    "proposed_group"
                ] = (
                    decision[
                        "proposed_group"
                    ]
                )

                item[
                    "routing_reason"
                ] = (
                    decision[
                        "routing_reason"
                    ]
                )

                item[
                    "resolved_scope"
                ] = (
                    decision[
                        "resolved_scope"
                    ]
                )

                target = (
                    decision[
                        "target"
                    ]
                )

                if (
                    target
                    == "group2_context"
                ):

                    bucket = (
                        "group2_context_status_long"
                    )

                elif (
                    target
                    == "group3_deferred"
                ):

                    bucket = (
                        "group3_deferred_from_unresolved_long"
                    )

                elif (
                    target
                    == "group6_deferred"
                ):

                    bucket = (
                        "group6_deferred_from_unresolved_long"
                    )

                else:

                    bucket = (
                        "unresolved_status_long"
                    )

        dest[
            bucket
        ].append(
            item
        )

    # ========================================================
    # Process table evidence
    # ========================================================

    summary_rows = []
    summary_cells = []
    unresolved_rows = []
    pcm_buffers = []
    retrieval_event_descriptors = []

    for row in tables:

        section = (
            section_lookup[
                row[
                    "section_id"
                ]
            ]
        )

        # ----------------------------------------------------
        # PCM remains quarantined
        # ----------------------------------------------------

        if (
            section[
                "scope_candidate"
            ]
            ==
            "pcm_buffer_scope_requires_review"
        ):

            pcm_buffers.append(
                row
            )

            continue

        # ----------------------------------------------------
        # Non-summary rows
        # ----------------------------------------------------

        if (
            "summary"
            not in section[
                "source_heading"
            ].lower()
        ):

            descriptor = (
                classify_retrieval_event_descriptor(
                    row
                )
            )

            if (
                descriptor
                is not None
            ):

                retrieval_event_descriptors.append({

                    **row,

                    "source_format":
                        section[
                            "source_format"
                        ],

                    "source_path":
                        section[
                            "source_path"
                        ],

                    "source_sha256":
                        section[
                            "source_sha256"
                        ],

                    "source_heading":
                        section[
                            "source_heading"
                        ],

                    **descriptor,
                })

            else:

                unresolved_rows.append(
                    row
                )

            continue

        # ----------------------------------------------------
        # Summary data rows only
        # ----------------------------------------------------

        if (
            row[
                "row_role"
            ]
            != "data_candidate"
        ):

            continue

        header = json.loads(
            row[
                "source_header_json"
            ]
        )

        values = json.loads(
            row[
                "source_row_json"
            ]
        )

        summary_id = (
            "g2summary_"
            + hashlib.sha256(
                (
                    row[
                        "section_id"
                    ]
                    + "|"
                    + row[
                        "source_record"
                    ]
                ).encode()
            ).hexdigest()[:24]
        )

        label = ""
        trigger = ""

        # ====================================================
        # Primary summary parsing
        # ====================================================

        for index, heading in enumerate(
            header
        ):

            if (
                index
                >= len(values)
            ):

                continue

            heading_normalized = (
                heading
                .strip()
                .lower()
            )

            if (
                heading_normalized
                in [
                    "events recorded",
                    "event recorded",
                    "event record",
                    "event",
                ]
            ):

                label = (
                    values[index]
                )

            if (
                heading_normalized
                in [
                    "trg count",
                    "trigger count",
                ]
            ):

                trigger = (
                    values[index]
                )

        # ====================================================
        # Fallback summary parsing
        # ====================================================

        if (
            not label
            and not trigger
            and len(values) >= 2
        ):

            value_0 = (
                values[0]
                .strip()
            )

            value_1 = (
                values[1]
                .strip()
            )

            if (
                "summary"
                in section[
                    "source_heading"
                ].lower()

                and
                "event"
                in value_0.lower()

                and
                value_1.isdigit()
            ):

                label = value_0
                trigger = value_1

        # ====================================================
        # Conservative candidate linking
        # ====================================================

        link = (
            link_summary_to_record_candidate(

                report_id=
                    row[
                        "report_id"
                    ],

                reported_record_label=
                    label,

                reported_trigger_reference=
                    trigger,

                record_candidates_by_report=
                    record_candidates_by_report,
            )
        )

        summary_rows.append({

            **{
                key:
                    row[key]

                for key
                in BASE
            },

            "summary_row_id":
                summary_id,

            "section_id":
                row[
                    "section_id"
                ],

            "source_record":
                row[
                    "source_record"
                ],

            "reported_record_label":
                label,

            "reported_trigger_reference":
                trigger,

            "source_path":
                section[
                    "source_path"
                ],

            "source_sha256":
                section[
                    "source_sha256"
                ],

            "source_heading":
                section[
                    "source_heading"
                ],

            "row_values_json":
                row[
                    "source_row_json"
                ],

            "linked_record_candidate_id":
                link[
                    "linked_record_candidate_id"
                ],

            "linked_record_label_raw":
                link[
                    "linked_record_label_raw"
                ],

            "link_method":
                link[
                    "link_method"
                ],

            "link_status":
                link[
                    "link_status"
                ],

            "link_candidate_count":
                link[
                    "link_candidate_count"
                ],

            "requires_review":
                link[
                    "requires_review"
                ],
        })

        # ====================================================
        # Preserve summary cells
        # ====================================================

        for index, value in enumerate(
            values
        ):

            heading = (
                header[index]
                if index < len(header)
                else ""
            )

            if (
                not heading.strip()
                and not value.strip()
            ):

                continue

            summary_cells.append({

                **{
                    key:
                        row[key]

                    for key
                    in BASE
                },

                "summary_row_id":
                    summary_id,

                "section_id":
                    row[
                        "section_id"
                    ],

                "source_record":
                    row[
                        "source_record"
                    ],

                "source_column_index":
                    index + 1,

                "source_column_name":
                    heading,

                "value_raw":
                    value,

                "value_status":
                    (
                        "blank"
                        if not value.strip()
                        else "present"
                    ),

                "requires_review":
                    True,
            })

    # ========================================================
    # Create output directory
    # ========================================================

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Write field views
    # ========================================================

    for name, rows in dest.items():

        write(
            out
            / f"{name}.csv",

            rows,

            field_columns,
        )

    # ========================================================
    # Summary outputs
    # ========================================================

    write(
        out
        / "retrieval_summary_rows.csv",

        summary_rows,

        (
            list(
                summary_rows[0]
            )

            if summary_rows

            else
            BASE
            + [
                "summary_row_id"
            ]
        ),
    )

    write(
        out
        / "retrieval_summary_cells_long.csv",

        summary_cells,

        (
            list(
                summary_cells[0]
            )

            if summary_cells

            else
            BASE
            + [
                "summary_row_id"
            ]
        ),
    )

    # ========================================================
    # Standalone retrieval-event descriptors
    # ========================================================

    descriptor_columns = (
        list(
            retrieval_event_descriptors[
                0
            ]
        )

        if retrieval_event_descriptors

        else BASE
    )

    write(
        out
        / "retrieval_event_descriptors_long.csv",

        retrieval_event_descriptors,

        descriptor_columns,
    )

    # ========================================================
    # PCM and unresolved table evidence
    # ========================================================

    table_columns = (
        list(
            tables[0]
        )

        if tables

        else BASE
    )

    write(
        out
        / "pcm_buffer_rows.csv",

        pcm_buffers,

        table_columns,
    )

    write(
        out
        / "unresolved_table_rows.csv",

        unresolved_rows,

        table_columns,
    )

    # ========================================================
    # Preserve record candidates and coverage
    # ========================================================

    write(
        out
        / "record_candidates.csv",

        records,

        (
            list(
                records[0]
            )

            if records

            else BASE
        ),
    )

    write(
        out
        / "report_coverage.csv",

        coverage,

        (
            list(
                coverage[0]
            )

            if coverage

            else BASE
        ),
    )

    # ========================================================
    # Pending section evidence
    # ========================================================

    pending_sections = [

        section

        for section
        in sections

        if (
            section[
                "source_format"
            ]
            == "pdf"

            or
            section[
                "scope_candidate"
            ]
            not in [
                "reported_record_candidate",
                "retrieval_level",
            ]

            or
            section[
                "availability"
            ]
            != "content_present"
        )
    ]

    write(
        out
        / "pending_section_evidence.csv",

        pending_sections,

        (
            list(
                sections[0]
            )

            if sections

            else BASE
        ),
    )

    # ========================================================
    # Statistics
    # ========================================================

    link_status_counts = Counter(

        row[
            "link_status"
        ]

        for row
        in summary_rows
    )

    linked_summary_rows = sum(

        1

        for row
        in summary_rows

        if row[
            "linked_record_candidate_id"
        ]
    )

    summary_rows_requiring_review = sum(

        1

        for row
        in summary_rows

        if row[
            "requires_review"
        ]
    )

    descriptor_counts = Counter(

        row[
            "descriptor_normalized"
        ]

        for row
        in retrieval_event_descriptors
    )

    group2_context_scope_counts = Counter(

        row[
            "resolved_scope"
        ]

        for row
        in dest[
            "group2_context_status_long"
        ]
    )

    # ========================================================
    # Metadata
    # ========================================================

    summary = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "reports":
            len(
                coverage
            ),

        "record_candidates":
            len(
                records
            ),

        "field_view_counts": {

            key:
                len(value)

            for key, value
            in dest.items()
        },

        "group2_context_scope_counts":
            dict(
                group2_context_scope_counts
            ),

        "summary_rows":
            len(
                summary_rows
            ),

        "summary_cells":
            len(
                summary_cells
            ),

        "summary_link_status_counts":
            dict(
                link_status_counts
            ),

        "linked_summary_rows":
            linked_summary_rows,

        "summary_rows_requiring_review":
            summary_rows_requiring_review,

        "retrieval_event_descriptor_rows":
            len(
                retrieval_event_descriptors
            ),

        "retrieval_event_descriptor_counts":
            dict(
                descriptor_counts
            ),

        "pcm_buffer_rows":
            len(
                pcm_buffers
            ),

        "unresolved_table_rows":
            len(
                unresolved_rows
            ),

        "pending_section_evidence":
            len(
                pending_sections
            ),

        "all_field_observations_preserved":
            (
                sum(
                    len(rows)

                    for rows
                    in dest.values()
                )

                == len(
                    fields
                )
            ),

        "all_table_rows_accounted_for":
            True,

        "scope":
            (
                "CSV working views with conservative summary "
                "parsing and record linking. Confirmed retrieval "
                "event descriptors are preserved independently. "
                "Previously unresolved Group-2 counters are "
                "classified as report-level event context, while "
                "rollover recording completeness is retained as "
                "unlinked event context. No record identity is "
                "inferred for contextual fields. Group-3 and "
                "Group-6 observations reviewed from the unresolved "
                "pool are preserved separately. PCM routing, PDF "
                "structured extraction, and final validation remain "
                "pending."
            ),
    }

    # ========================================================
    # Write metadata
    # ========================================================

    metadata_tmp = (
        out
        / "metadata.json.part"
    )

    metadata_tmp.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    metadata_tmp.replace(
        out
        / "metadata.json"
    )

    # ========================================================
    # Console
    # ========================================================

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    print(
        f"Outputs: {out}"
    )


if __name__ == "__main__":
    main()