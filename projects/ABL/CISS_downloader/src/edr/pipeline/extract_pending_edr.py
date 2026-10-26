from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.edr.parsers.csv_parser import (
    parse_csv_file,
)

from src.edr.parsers.pdf_parser import (
    parse_pdf_file,
)

from src.edr.routing.router import (
    route_observation,
)


# ============================================================
# Paths
# ============================================================

MANIFEST_FILE = Path(
    "data/processed/edr/unified_extraction_v1/"
    "pending_source_manifest.csv"
)

OUTPUT_DIR = Path(
    "data/processed/edr/unified_extraction_v1/"
    "extracted_pending_v1"
)

OBSERVATIONS_FILE = (
    OUTPUT_DIR / "observations.csv"
)

REVIEW_FILE = (
    OUTPUT_DIR / "review_observations.csv"
)

ERROR_FILE = (
    OUTPUT_DIR / "extraction_errors.csv"
)

REPORT_SUMMARY_FILE = (
    OUTPUT_DIR / "report_summary.csv"
)

METADATA_FILE = (
    OUTPUT_DIR / "metadata.json"
)


# ============================================================
# Helpers
# ============================================================

def clean(
    value: Any,
) -> str:

    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


def safe_json(
    value: Any,
) -> str:

    return json.dumps(
        value,
        ensure_ascii=False,
    )


# ============================================================
# Parse one source
# ============================================================

def parse_source(
    source_format: str,
    source_path: str,
):

    source_format = (
        source_format
        .strip()
        .lower()
    )

    if source_format == "csv":

        return parse_csv_file(
            source_path
        )

    if source_format == "pdf":

        return parse_pdf_file(
            source_path
        )

    raise ValueError(
        f"Unsupported source format: "
        f"{source_format}"
    )


# ============================================================
# Main extraction
# ============================================================

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 80)
    print("UNIFIED EDR EXTRACTION")
    print("=" * 80)

    manifest = pd.read_csv(
        MANIFEST_FILE,
        low_memory=False,
    )

    print(
        f"Pending records: "
        f"{len(manifest):,}"
    )

    observation_rows = []
    error_rows = []
    report_summary_rows = []

    destination_counter = Counter()
    source_counter = Counter()

    # ========================================================
    # Process each case / vehicle once
    # ========================================================

    for report_index, row in manifest.iterrows():

        case_id = clean(
            row.get("case_id")
        )

        vehicle_number = clean(
            row.get("vehicle_number")
        )

        export_basename = clean(
            row.get("export_basename")
        )

        source_format = clean(
            row.get(
                "selected_source_format"
            )
        ).lower()

        source_path = clean(
            row.get(
                "selected_source_path"
            )
        )

        print(
            f"[{report_index + 1}/{len(manifest)}] "
            f"Case {case_id} "
            f"Vehicle {vehicle_number} "
            f"({source_format.upper()})"
        )

        # ----------------------------------------------------
        # Parse source
        # ----------------------------------------------------

        try:

            observations = parse_source(
                source_format,
                source_path,
            )

        except NotImplementedError as exc:

            # PDF adapter not connected yet.
            error_rows.append(
                {
                    "case_id":
                        case_id,

                    "vehicle_number":
                        vehicle_number,

                    "export_basename":
                        export_basename,

                    "source_format":
                        source_format,

                    "source_path":
                        source_path,

                    "error_type":
                        "pdf_adapter_pending",

                    "error":
                        str(exc),
                }
            )

            continue

        except Exception as exc:

            error_rows.append(
                {
                    "case_id":
                        case_id,

                    "vehicle_number":
                        vehicle_number,

                    "export_basename":
                        export_basename,

                    "source_format":
                        source_format,

                    "source_path":
                        source_path,

                    "error_type":
                        type(exc).__name__,

                    "error":
                        str(exc),
                }
            )

            continue

        source_counter[
            source_format
        ] += 1

        report_destinations = Counter()

        # ----------------------------------------------------
        # Route every parsed observation
        # ----------------------------------------------------

        for observation in observations:

            route = route_observation(
                observation
            )

            destination_counter[
                route.destination
            ] += 1

            report_destinations[
                route.destination
            ] += 1

            observation_rows.append(
                {
                    # ----------------------------------------
                    # Identity
                    # ----------------------------------------

                    "case_id":
                        case_id,

                    "vehicle_number":
                        vehicle_number,

                    "export_basename":
                        export_basename,

                    # ----------------------------------------
                    # Provenance
                    # ----------------------------------------

                    "source_format":
                        source_format,

                    "source_path":
                        source_path,

                    "row_index":
                        observation.row_index,

                    "row_number":
                        observation.row_number,

                    "section_context":
                        observation.section_context,

                    # ----------------------------------------
                    # Original extracted information
                    # ----------------------------------------

                    "raw_row":
                        safe_json(
                            observation.raw_row
                        ),

                    "observation_type":
                        observation.observation_type,

                    "raw_label":
                        observation.label,

                    "values":
                        safe_json(
                            observation.values
                        ),

                    "value_count":
                        observation.value_count,

                    # ----------------------------------------
                    # Structural interpretation
                    # ----------------------------------------

                    "is_empty":
                        observation.is_empty,

                    "is_section_heading":
                        observation.is_section_heading,

                    "is_scalar":
                        observation.is_scalar,

                    "is_repeated":
                        observation.is_repeated,

                    "is_table_header":
                        observation.is_table_header,

                    "packed_sequence":
                        observation.packed_sequence,

                    "packed_sequence_count":
                        observation.packed_sequence_count,

                    "parser_status":
                        observation.parser_status,

                    # ----------------------------------------
                    # Group routing
                    # ----------------------------------------

                    "destination":
                        route.destination,

                    "family":
                        route.family,

                    "confidence":
                        route.confidence,

                    "matched_by":
                        route.matched_by,

                    "requires_review":
                        route.requires_review,

                    "reason":
                        route.reason,

                    "review_reason":
                        route.review_reason,

                    "router_version":
                        route.router_version,
                }
            )

        # ----------------------------------------------------
        # Report-level summary
        # ----------------------------------------------------

        report_summary_rows.append(
            {
                "case_id":
                    case_id,

                "vehicle_number":
                    vehicle_number,

                "export_basename":
                    export_basename,

                "source_format":
                    source_format,

                "source_path":
                    source_path,

                "observation_count":
                    len(observations),

                "group1_count":
                    report_destinations[
                        "group1"
                    ],

                "group2_count":
                    report_destinations[
                        "group2"
                    ],

                "group3_count":
                    report_destinations[
                        "group3"
                    ],

                "group4_count":
                    report_destinations[
                        "group4"
                    ],

                "group5_count":
                    report_destinations[
                        "group5"
                    ],

                "group5_companion_count":
                    report_destinations[
                        "group5_companion"
                    ],

                "group6_count":
                    report_destinations[
                        "group6"
                    ],

                "documentation_count":
                    report_destinations[
                        "documentation"
                    ],

                "review_count":
                    report_destinations[
                        "review"
                    ],

                "exclude_count":
                    report_destinations[
                        "exclude"
                    ],
            }
        )

    # ========================================================
    # Create output tables
    # ========================================================

    observations_df = pd.DataFrame(
        observation_rows
    )

    errors_df = pd.DataFrame(
        error_rows
    )

    report_summary_df = pd.DataFrame(
        report_summary_rows
    )

    # --------------------------------------------------------
    # Reviews
    # --------------------------------------------------------

    if not observations_df.empty:

        review_df = observations_df[
            (
                observations_df[
                    "requires_review"
                ]
                == True
            )
            |
            (
                observations_df[
                    "destination"
                ]
                == "review"
            )
        ].copy()

    else:

        review_df = pd.DataFrame()

    # ========================================================
    # Write outputs
    # ========================================================

    observations_df.to_csv(
        OBSERVATIONS_FILE,
        index=False,
    )

    review_df.to_csv(
        REVIEW_FILE,
        index=False,
    )

    errors_df.to_csv(
        ERROR_FILE,
        index=False,
    )

    report_summary_df.to_csv(
        REPORT_SUMMARY_FILE,
        index=False,
    )

    # ========================================================
    # Metadata
    # ========================================================

    metadata = {
        "pipeline_version":
            "unified_pending_extraction_v1",

        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "pending_records":
            len(manifest),

        "records_successfully_parsed":
            len(report_summary_df),

        "source_counts_processed":
            dict(source_counter),

        "total_observations":
            len(observations_df),

        "destination_counts":
            dict(destination_counter),

        "review_observations":
            len(review_df),

        "extraction_errors":
            len(errors_df),

        "normalization_stage":
            (
                "Existing parser/rule normalization only. "
                "Canonical feature normalization deferred "
                "until after full extraction and validation."
            ),
    }

    METADATA_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # Console summary
    # ========================================================

    print()
    print("=" * 80)
    print("UNIFIED EXTRACTION SUMMARY")
    print("=" * 80)

    print(
        f"Pending records:             "
        f"{len(manifest):,}"
    )

    print(
        f"Successfully parsed:         "
        f"{len(report_summary_df):,}"
    )

    print(
        f"Observations extracted:      "
        f"{len(observations_df):,}"
    )

    print(
        f"Review observations:         "
        f"{len(review_df):,}"
    )

    print(
        f"Errors / pending adapters:   "
        f"{len(errors_df):,}"
    )

    print()
    print("Destinations:")

    for destination, count in (
        destination_counter
        .most_common()
    ):

        print(
            f"  {destination:<20} "
            f"{count:,}"
        )

    print()
    print(
        f"Outputs: {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()