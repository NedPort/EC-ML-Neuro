"""
Build Group 4 working tables: Time-Series Measurements.

Purpose
-------
Group 4 is an extraction-oriented category containing repeated measurements
indexed by time, buffer order, or another ordered sampling axis.

Two source families are currently available:

1. PCM CSV-derived time series
   - already structurally parsed
   - stored in group4_timeseries_v1

2. PDF-derived time-series candidates
   - detected during Group 2 PDF processing
   - preserved in group2_final_v1 as a handoff to Group 4
   - not yet fully reconstructed into signal columns

This script creates a unified Group 4 registry while preserving the
different processing maturity of the two source families.

Important:
- PCM structured samples are preserved unchanged.
- PDF candidate blocks are NOT force-parsed.
- No signal semantics are inferred.
- No units are converted.
- No missing time axis is invented.
- No PDF signal columns are reconstructed at this stage.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


csv.field_size_limit(10_000_000)


# ============================================================
# I/O
# ============================================================

def read_csv(path: Path):
    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
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


def read_json(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def copy_file(
    source: Path,
    destination: Path,
):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = destination.with_suffix(
        destination.suffix + ".part"
    )

    shutil.copyfile(
        source,
        tmp,
    )

    tmp.replace(
        destination
    )


def require_file(
    directory: Path,
    filename: str,
):
    path = (
        directory
        / filename
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Required file missing: {path}"
        )

    return path


# ============================================================
# Helpers
# ============================================================

def clean(value):
    return str(
        value or ""
    ).strip()


def first_value(
    row: dict,
    candidates: list[str],
    default="",
):
    for key in candidates:

        value = clean(
            row.get(
                key,
                ""
            )
        )

        if value:
            return value

    return default


def as_int(
    value,
    default=0,
):
    try:
        return int(
            float(
                clean(value)
            )
        )

    except (
        ValueError,
        TypeError,
    ):
        return default


def json_compact(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--pcm-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_timeseries_v1"
        ),
    )

    parser.add_argument(
        "--group2-final-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_final_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_working_v1"
        ),
    )

    args = parser.parse_args()

    pcm_dir = (
        args.pcm_directory
    )

    group2_dir = (
        args.group2_final_directory
    )

    out = (
        args.output_directory
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Required PCM inputs
    # ========================================================

    pcm_registry_path = require_file(
        pcm_dir,
        "timeseries_registry.csv",
    )

    pcm_wide_path = require_file(
        pcm_dir,
        "timeseries_samples_wide.csv",
    )

    pcm_long_path = require_file(
        pcm_dir,
        "timeseries_values_long.csv",
    )

    pcm_metadata_path = require_file(
        pcm_dir,
        "metadata.json",
    )

    # Audit filename may be either of these.
    pcm_audit_path = None

    for candidate in [
        "timeseries_audit.csv",
        "timeseries_source_audit.csv",
    ]:
        path = (
            pcm_dir
            / candidate
        )

        if path.exists():
            pcm_audit_path = path
            break

    # ========================================================
    # Required PDF handoff inputs
    # ========================================================

    pdf_sections_path = require_file(
        group2_dir,
        "group4_pdf_timeseries_handoff_sections.csv",
    )

    pdf_rows_path = require_file(
        group2_dir,
        "group4_pdf_timeseries_handoff_rows.csv",
    )

    # ========================================================
    # Read inputs
    # ========================================================

    pcm_registry = read_csv(
        pcm_registry_path
    )

    pcm_wide = read_csv(
        pcm_wide_path
    )

    pcm_long = read_csv(
        pcm_long_path
    )

    pcm_metadata = read_json(
        pcm_metadata_path
    )

    pdf_sections = read_csv(
        pdf_sections_path
    )

    pdf_rows = read_csv(
        pdf_rows_path
    )

    pcm_audit = (
        read_csv(
            pcm_audit_path
        )
        if pcm_audit_path
        else []
    )

    # ========================================================
    # Unified series registry
    # ========================================================

    registry = []

    # --------------------------------------------------------
    # PCM registry
    # --------------------------------------------------------

    for index, row in enumerate(
        pcm_registry
    ):

        source_series_id = first_value(
            row,
            [
                "series_id",
                "timeseries_id",
                "time_series_id",
            ],
            default=(
                f"pcm_series_{index:04d}"
            ),
        )

        report_id = first_value(
            row,
            [
                "report_id",
            ],
        )

        case_id = first_value(
            row,
            [
                "case_id",
            ],
        )

        vehicle_number = first_value(
            row,
            [
                "vehicle_number",
                "vehicle_no",
            ],
        )

        record_candidate_id = first_value(
            row,
            [
                "record_candidate_id",
            ],
        )

        source_heading = first_value(
            row,
            [
                "source_heading",
                "section_heading",
                "heading",
            ],
            default="PCM EDR DATA",
        )

        time_axis_type = first_value(
            row,
            [
                "time_axis_status",
                "time_axis_type",
            ],
            default="unknown",
        )

        sample_count = as_int(
            first_value(
                row,
                [
                    "sample_count",
                    "samples",
                    "row_count",
                ],
            )
        )

        registry.append({

            "group4_series_id":
                (
                    "g4_pcm_"
                    + source_series_id
                ),

            "source_series_id":
                source_series_id,

            "report_id":
                report_id,

            "case_id":
                case_id,

            "vehicle_number":
                vehicle_number,

            "record_candidate_id":
                record_candidate_id,

            "source_format":
                "csv",

            "source_family":
                "pcm_edr",

            "source_heading":
                source_heading,

            "time_axis_type":
                time_axis_type,

            "sample_count":
                sample_count,

            "data_candidate_count":
                sample_count,

            "processing_status":
                "structured_ready",

            "target_group":
                "group4_timeseries",

            "requires_review":
                False,

            "source_registry_json":
                json_compact(
                    row
                ),
        })

    # --------------------------------------------------------
    # PDF registry
    # --------------------------------------------------------

    for row in pdf_sections:

        source_series_id = first_value(
            row,
            [
                "timeseries_candidate_id",
            ],
        )

        registry.append({

            "group4_series_id":
                (
                    "g4_pdf_"
                    + source_series_id
                ),

            "source_series_id":
                source_series_id,

            "report_id":
                first_value(
                    row,
                    [
                        "report_id",
                    ],
                ),

            "case_id":
                first_value(
                    row,
                    [
                        "case_id",
                    ],
                ),

            "vehicle_number":
                first_value(
                    row,
                    [
                        "vehicle_number",
                    ],
                ),

            "record_candidate_id":
                first_value(
                    row,
                    [
                        "record_candidate_id",
                    ],
                ),

            "source_format":
                "pdf",

            "source_family":
                "pdf_embedded_timeseries",

            "source_heading":
                first_value(
                    row,
                    [
                        "source_heading",
                    ],
                ),

            "time_axis_type":
                "candidate_requires_reconstruction",

            "sample_count":
                as_int(
                    first_value(
                        row,
                        [
                            "row_count",
                        ],
                    )
                ),

            "data_candidate_count":
                as_int(
                    first_value(
                        row,
                        [
                            "data_candidate_count",
                        ],
                    )
                ),

            "processing_status":
                "candidate_requires_header_reconstruction",

            "target_group":
                "group4_timeseries",

            "requires_review":
                True,

            "source_registry_json":
                json_compact(
                    row
                ),
        })

    # ========================================================
    # PDF candidate row normalization
    # ========================================================

    pdf_candidate_rows = []

    for row in pdf_rows:

        source_series_id = first_value(
            row,
            [
                "timeseries_candidate_id",
            ],
        )

        pdf_candidate_rows.append({

            "group4_series_id":
                (
                    "g4_pdf_"
                    + source_series_id
                ),

            "source_series_id":
                source_series_id,

            "report_id":
                first_value(
                    row,
                    [
                        "report_id",
                    ],
                ),

            "case_id":
                first_value(
                    row,
                    [
                        "case_id",
                    ],
                ),

            "vehicle_number":
                first_value(
                    row,
                    [
                        "vehicle_number",
                    ],
                ),

            "record_candidate_id":
                first_value(
                    row,
                    [
                        "record_candidate_id",
                    ],
                ),

            "source_page":
                first_value(
                    row,
                    [
                        "source_page",
                    ],
                ),

            "source_heading":
                first_value(
                    row,
                    [
                        "source_heading",
                    ],
                ),

            "block_index":
                first_value(
                    row,
                    [
                        "block_index",
                    ],
                ),

            "pdf_row_index":
                first_value(
                    row,
                    [
                        "pdf_row_index",
                    ],
                ),

            "row_role":
                first_value(
                    row,
                    [
                        "row_role",
                    ],
                ),

            "source_row_json":
                first_value(
                    row,
                    [
                        "source_row_json",
                    ],
                ),

            "processing_status":
                "raw_pdf_timeseries_candidate",

            "requires_review":
                True,
        })

    # ========================================================
    # Source audit
    # ========================================================

    audit = []

    # PCM source
    audit.append({

        "source_family":
            "pcm_edr",

        "source_format":
            "csv",

        "series_count":
            len(
                pcm_registry
            ),

        "source_row_count":
            len(
                pcm_wide
            ),

        "long_value_count":
            len(
                pcm_long
            ),

        "processing_status":
            "structured_ready",

        "requires_review":
            False,

        "note":
            (
                "Existing structured PCM Group 4 "
                "time-series extraction."
            ),
    })

    # PDF source
    pdf_data_rows = sum(
        1
        for row
        in pdf_candidate_rows
        if row[
            "row_role"
        ]
        == "data_candidate"
    )

    pdf_header_rows = sum(
        1
        for row
        in pdf_candidate_rows
        if row[
            "row_role"
        ]
        in {
            "header_candidate",
            "header_or_unit_continuation",
        }
    )

    audit.append({

        "source_family":
            "pdf_embedded_timeseries",

        "source_format":
            "pdf",

        "series_count":
            len(
                pdf_sections
            ),

        "source_row_count":
            len(
                pdf_candidate_rows
            ),

        "long_value_count":
            "",

        "processing_status":
            "candidate_requires_header_reconstruction",

        "requires_review":
            True,

        "note":
            (
                f"{pdf_data_rows} data-candidate rows; "
                f"{pdf_header_rows} header/unit candidate rows."
            ),
    })

    # ========================================================
    # Validation checks
    # ========================================================

    checks = []

    def check(
        name,
        condition,
        observed,
        expected,
    ):
        checks.append({
            "check":
                name,

            "status":
                (
                    "PASS"
                    if condition
                    else "FAIL"
                ),

            "observed":
                str(
                    observed
                ),

            "expected":
                str(
                    expected
                ),
        })

    check(
        "pcm_series_count",
        len(
            pcm_registry
        )
        == 10,
        len(
            pcm_registry
        ),
        10,
    )

    check(
        "pcm_sample_count",
        len(
            pcm_wide
        )
        == 3190,
        len(
            pcm_wide
        ),
        3190,
    )

    check(
        "pcm_long_value_count",
        len(
            pcm_long
        )
        == 51040,
        len(
            pcm_long
        ),
        51040,
    )

    check(
        "pdf_timeseries_section_count",
        len(
            pdf_sections
        )
        == 69,
        len(
            pdf_sections
        ),
        69,
    )

    check(
        "pdf_timeseries_row_count",
        len(
            pdf_rows
        )
        == 1508,
        len(
            pdf_rows
        ),
        1508,
    )

    check(
        "pdf_data_candidate_count",
        pdf_data_rows
        == 897,
        pdf_data_rows,
        897,
    )

    expected_registry_count = (
        len(
            pcm_registry
        )
        + len(
            pdf_sections
        )
    )

    check(
        "combined_registry_count",
        len(
            registry
        )
        == expected_registry_count,
        len(
            registry
        ),
        expected_registry_count,
    )

    # ========================================================
    # Write outputs
    # ========================================================

    registry_columns = [
        "group4_series_id",
        "source_series_id",
        "report_id",
        "case_id",
        "vehicle_number",
        "record_candidate_id",
        "source_format",
        "source_family",
        "source_heading",
        "time_axis_type",
        "sample_count",
        "data_candidate_count",
        "processing_status",
        "target_group",
        "requires_review",
        "source_registry_json",
    ]

    write_csv(
        out
        / "timeseries_registry.csv",
        registry,
        registry_columns,
    )

    # Preserve PCM structured datasets unchanged.
    copy_file(
        pcm_wide_path,
        out
        / "timeseries_samples_wide.csv",
    )

    copy_file(
        pcm_long_path,
        out
        / "timeseries_values_long.csv",
    )

    # Preserve PDF candidate structures separately.
    copy_file(
        pdf_sections_path,
        out
        / "pdf_timeseries_candidate_sections.csv",
    )

    write_csv(
        out
        / "pdf_timeseries_candidate_rows.csv",
        pdf_candidate_rows,
        [
            "group4_series_id",
            "source_series_id",
            "report_id",
            "case_id",
            "vehicle_number",
            "record_candidate_id",
            "source_page",
            "source_heading",
            "block_index",
            "pdf_row_index",
            "row_role",
            "source_row_json",
            "processing_status",
            "requires_review",
        ],
    )

    write_csv(
        out
        / "timeseries_source_audit.csv",
        audit,
        [
            "source_family",
            "source_format",
            "series_count",
            "source_row_count",
            "long_value_count",
            "processing_status",
            "requires_review",
            "note",
        ],
    )

    write_csv(
        out
        / "validation_report.csv",
        checks,
        [
            "check",
            "status",
            "observed",
            "expected",
        ],
    )

    if pcm_audit_path:

        copy_file(
            pcm_audit_path,
            out
            / "pcm_timeseries_audit.csv",
        )

    # ========================================================
    # Metadata
    # ========================================================

    time_axis_counts = Counter(
        row[
            "time_axis_type"
        ]
        for row
        in registry
    )

    processing_status_counts = Counter(
        row[
            "processing_status"
        ]
        for row
        in registry
    )

    source_family_counts = Counter(
        row[
            "source_family"
        ]
        for row
        in registry
    )

    pdf_role_counts = Counter(
        row[
            "row_role"
        ]
        for row
        in pdf_candidate_rows
    )

    failed_checks = [
        row
        for row
        in checks
        if row[
            "status"
        ]
        == "FAIL"
    ]

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 4 - Time-series measurements",

        "registry_series_count":
            len(
                registry
            ),

        "source_family_counts":
            dict(
                source_family_counts
            ),

        "processing_status_counts":
            dict(
                processing_status_counts
            ),

        "time_axis_type_counts":
            dict(
                time_axis_counts
            ),

        "pcm_series_count":
            len(
                pcm_registry
            ),

        "pcm_sample_count":
            len(
                pcm_wide
            ),

        "pcm_long_value_count":
            len(
                pcm_long
            ),

        "pdf_candidate_series_count":
            len(
                pdf_sections
            ),

        "pdf_candidate_row_count":
            len(
                pdf_candidate_rows
            ),

        "pdf_candidate_role_counts":
            dict(
                pdf_role_counts
            ),

        "validation_checks":
            len(
                checks
            ),

        "validation_failures":
            len(
                failed_checks
            ),

        "scope":
            (
                "Initial unified Group 4 working package. "
                "Structured PCM time-series datasets are preserved "
                "unchanged. PDF-derived temporal blocks from the "
                "frozen Group 2 package are registered as candidate "
                "time-series but remain separate until their "
                "multi-row headers, units, time axes, and signal "
                "columns are reconstructed and validated. No signal "
                "semantics, missing time coordinates, units, or event "
                "identities are inferred."
            ),
    }

    metadata_tmp = (
        out
        / "metadata.json.part"
    )

    metadata_tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    metadata_tmp.replace(
        out
        / "metadata.json"
    )

    print(
        json.dumps(
            metadata,
            indent=2,
        )
    )

    print(
        f"Outputs: {out}"
    )

    if failed_checks:

        print()
        print(
            "GROUP 4 WORKING BUILD HAS VALIDATION FAILURES:"
        )

        for row in failed_checks:
            print(
                f"- {row['check']}: "
                f"observed={row['observed']}, "
                f"expected={row['expected']}"
            )

        raise SystemExit(1)

    print()
    print(
        "GROUP 4 WORKING BUILD COMPLETE."
    )


if __name__ == "__main__":
    main()