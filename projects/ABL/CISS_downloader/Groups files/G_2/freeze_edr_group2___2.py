"""
Freeze and validate Group 2: Recorded events and record structure.

This script does NOT perform new extraction.

It packages the currently validated Group 2 outputs from:

    data/processed/edr/group2_working_v1
    data/processed/edr/group2_extract_v2
    data/processed/edr/group2_pdf_structured_v2

and produces a stable final Group 2 package.

Group 4 PDF time-series candidates are copied as handoff evidence but are
not considered Group 2 observations.

Expected principles
-------------------
- Preserve source evidence.
- Do not invent event identities.
- Do not force unresolved PDF layout fragments into fields.
- Explicit unresolved/absent outcomes are acceptable.
- PDF time-series material is handed off to Group 4.
- Header-only PDF summary evidence remains explicit review evidence.
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
# Basic I/O
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


# ============================================================
# Discovery helpers
# ============================================================

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


def optional_file(
    directory: Path,
    filename: str,
):
    path = (
        directory
        / filename
    )

    return (
        path
        if path.exists()
        else None
    )


def find_first_existing(
    directory: Path,
    candidates: list[str],
):
    for name in candidates:
        path = (
            directory
            / name
        )

        if path.exists():
            return path

    return None


def find_csv_by_terms(
    directory: Path,
    required_terms: list[str],
    excluded_terms: list[str] | None = None,
):
    excluded_terms = (
        excluded_terms
        or []
    )

    matches = []

    for path in directory.glob(
        "*.csv"
    ):
        name = (
            path.name.casefold()
        )

        if not all(
            term.casefold() in name
            for term
            in required_terms
        ):
            continue

        if any(
            term.casefold() in name
            for term
            in excluded_terms
        ):
            continue

        matches.append(
            path
        )

    if not matches:
        return None

    return sorted(
        matches
    )[0]


# ============================================================
# Validation helper
# ============================================================

def add_check(
    checks: list[dict],
    check_name: str,
    passed: bool,
    observed,
    expected,
    severity="error",
    note="",
):
    checks.append({
        "check_name":
            check_name,

        "status":
            (
                "PASS"
                if passed
                else "FAIL"
            ),

        "severity":
            severity,

        "observed":
            str(observed),

        "expected":
            str(expected),

        "note":
            note,
    })


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--working-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_working_v1"
        ),
    )

    parser.add_argument(
        "--extract-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_extract_v2"
        ),
    )

    parser.add_argument(
        "--pdf-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_pdf_structured_v2"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_final_v1"
        ),
    )

    args = parser.parse_args()

    working = (
        args.working_directory
    )

    extract = (
        args.extract_directory
    )

    pdf_dir = (
        args.pdf_directory
    )

    out = (
        args.output_directory
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Required source files
    # ========================================================

    record_status_path = require_file(
        working,
        "record_status_long.csv",
    )

    retrieval_status_path = require_file(
        working,
        "retrieval_status_long.csv",
    )

    context_status_path = require_file(
        working,
        "group2_context_status_long.csv",
    )

    unresolved_status_path = require_file(
        working,
        "unresolved_status_long.csv",
    )

    record_candidates_path = require_file(
        extract,
        "record_candidates.csv",
    )

    report_coverage_path = require_file(
        extract,
        "report_coverage.csv",
    )

    extraction_errors_path = require_file(
        extract,
        "errors.csv",
    )

    pdf_fields_path = require_file(
        pdf_dir,
        "pdf_fields_long.csv",
    )

    pdf_unresolved_path = require_file(
        pdf_dir,
        "pdf_unresolved_lines.csv",
    )

    pdf_table_path = require_file(
        pdf_dir,
        "pdf_table_rows.csv",
    )

    pdf_ts_rows_path = require_file(
        pdf_dir,
        "pdf_timeseries_candidate_rows.csv",
    )

    pdf_ts_sections_path = require_file(
        pdf_dir,
        "pdf_timeseries_candidate_sections.csv",
    )

    pdf_audit_path = require_file(
        pdf_dir,
        "pdf_section_audit.csv",
    )

    pdf_metadata_path = require_file(
        pdf_dir,
        "metadata.json",
    )

    # ========================================================
    # Discover working outputs whose exact legacy names may vary
    # ========================================================

    working_metadata_path = optional_file(
        working,
        "metadata.json",
    )

    summary_path = find_first_existing(
        working,
        [
            "retrieval_summary_rows.csv",
            "summary_rows.csv",
            "linked_summary_rows.csv",
            "summary_and_unresolved_rows.csv",
        ],
    )

    if summary_path is None:
        summary_path = find_csv_by_terms(
            working,
            ["summary"],
            ["cell"],
        )

    summary_cells_path = find_first_existing(
        working,
        [
            "summary_cells.csv",
            "retrieval_summary_cells.csv",
        ],
    )

    if summary_cells_path is None:
        summary_cells_path = find_csv_by_terms(
            working,
            [
                "summary",
                "cell",
            ],
        )

    retrieval_descriptors_path = find_first_existing(
        working,
        [
            "retrieval_event_descriptor_rows.csv",
            "retrieval_event_descriptors.csv",
            "retrieval_descriptors.csv",
        ],
    )

    if retrieval_descriptors_path is None:
        retrieval_descriptors_path = find_csv_by_terms(
            working,
            [
                "retrieval",
                "descriptor",
            ],
        )

    unresolved_table_path = find_first_existing(
        working,
        [
            "unresolved_table_rows.csv",
            "unresolved_rows.csv",
        ],
    )

    if unresolved_table_path is None:
        unresolved_table_path = find_csv_by_terms(
            working,
            [
                "unresolved",
                "table",
            ],
        )

    group3_deferred_path = optional_file(
        working,
        "group3_deferred_from_unresolved_long.csv",
    )

    group6_deferred_path = optional_file(
        working,
        "group6_deferred_from_unresolved_long.csv",
    )

    other_fields_path = optional_file(
        working,
        "other_group_fields_long.csv",
    )

    pending_section_path = optional_file(
        working,
        "pending_section_evidence.csv",
    )

    # ========================================================
    # Read data
    # ========================================================

    record_status = read_csv(
        record_status_path
    )

    retrieval_status = read_csv(
        retrieval_status_path
    )

    context_status = read_csv(
        context_status_path
    )

    unresolved_status = read_csv(
        unresolved_status_path
    )

    record_candidates = read_csv(
        record_candidates_path
    )

    report_coverage = read_csv(
        report_coverage_path
    )

    extraction_errors = read_csv(
        extraction_errors_path
    )

    pdf_fields = read_csv(
        pdf_fields_path
    )

    pdf_unresolved = read_csv(
        pdf_unresolved_path
    )

    pdf_table_rows = read_csv(
        pdf_table_path
    )

    pdf_ts_rows = read_csv(
        pdf_ts_rows_path
    )

    pdf_ts_sections = read_csv(
        pdf_ts_sections_path
    )

    pdf_audit = read_csv(
        pdf_audit_path
    )

    pdf_metadata = read_json(
        pdf_metadata_path
    )

    summaries = (
        read_csv(summary_path)
        if summary_path
        else []
    )

    summary_cells = (
        read_csv(summary_cells_path)
        if summary_cells_path
        else []
    )

    retrieval_descriptors = (
        read_csv(
            retrieval_descriptors_path
        )
        if retrieval_descriptors_path
        else []
    )

    unresolved_table_rows = (
        read_csv(
            unresolved_table_path
        )
        if unresolved_table_path
        else []
    )

    # ========================================================
    # Validation
    # ========================================================

    checks = []

    # --------------------------------------------------------
    # Report count
    # --------------------------------------------------------

    report_ids = {
        row.get(
            "report_id",
            ""
        )
        for row
        in report_coverage
        if row.get(
            "report_id",
            ""
        )
    }

    add_check(
        checks,
        "report_count",
        len(report_ids) == 1422,
        len(report_ids),
        1422,
        note=(
            "Expected Group 2 collection "
            "report count."
        ),
    )

    # --------------------------------------------------------
    # Record candidates
    # --------------------------------------------------------

    add_check(
        checks,
        "record_candidate_count",
        len(record_candidates)
        == 2279,
        len(record_candidates),
        2279,
    )

    # --------------------------------------------------------
    # Core validated working views
    # --------------------------------------------------------

    add_check(
        checks,
        "record_status_count",
        len(record_status)
        == 15925,
        len(record_status),
        15925,
    )

    add_check(
        checks,
        "retrieval_status_count",
        len(retrieval_status)
        == 2677,
        len(retrieval_status),
        2677,
    )

    add_check(
        checks,
        "group2_context_count",
        len(context_status)
        == 79,
        len(context_status),
        79,
    )

    # --------------------------------------------------------
    # Zero unresolved CSV status fields
    # --------------------------------------------------------

    add_check(
        checks,
        "unresolved_csv_status_fields",
        len(unresolved_status)
        == 0,
        len(unresolved_status),
        0,
    )

    # --------------------------------------------------------
    # Zero unresolved CSV table rows
    # --------------------------------------------------------

    if unresolved_table_path:

        add_check(
            checks,
            "unresolved_csv_table_rows",
            len(unresolved_table_rows)
            == 0,
            len(unresolved_table_rows),
            0,
        )

    else:

        add_check(
            checks,
            "unresolved_csv_table_rows",
            True,
            "file_not_present",
            (
                "0 or intentionally omitted "
                "after resolution"
            ),
            severity="warning",
            note=(
                "No unresolved table file was "
                "discovered in the working directory."
            ),
        )

    # --------------------------------------------------------
    # Source extraction errors
    # --------------------------------------------------------

    add_check(
        checks,
        "source_extraction_errors",
        len(extraction_errors)
        == 0,
        len(extraction_errors),
        0,
    )

    # --------------------------------------------------------
    # PDF errors
    # --------------------------------------------------------

    pdf_error_rows = [
        row
        for row
        in pdf_audit
        if row.get(
            "status",
            ""
        )
        in {
            "source_path_unresolved",
            "pdf_open_failed",
            "invalid_page_number",
        }
    ]

    add_check(
        checks,
        "pdf_source_errors",
        len(pdf_error_rows)
        == 0,
        len(pdf_error_rows),
        0,
    )

    # --------------------------------------------------------
    # PDF section count
    # --------------------------------------------------------

    add_check(
        checks,
        "pdf_content_sections",
        pdf_metadata.get(
            "pdf_content_sections"
        )
        == 386,
        pdf_metadata.get(
            "pdf_content_sections"
        ),
        386,
    )

    # --------------------------------------------------------
    # PDF scalar fields
    # --------------------------------------------------------

    add_check(
        checks,
        "pdf_scalar_fields_preserved",
        len(pdf_fields)
        == 7271,
        len(pdf_fields),
        7271,
    )

    # --------------------------------------------------------
    # PDF residual evidence
    # --------------------------------------------------------

    add_check(
        checks,
        "pdf_residual_evidence_preserved",
        len(pdf_unresolved)
        == 1062,
        len(pdf_unresolved),
        1062,
        severity="warning",
        note=(
            "Residual PDF layout/text evidence "
            "is intentionally preserved rather "
            "than force-parsed."
        ),
    )

    # --------------------------------------------------------
    # Time-series handoff
    # --------------------------------------------------------

    add_check(
        checks,
        "pdf_timeseries_candidate_sections",
        len(pdf_ts_sections)
        == 69,
        len(pdf_ts_sections),
        69,
        severity="warning",
        note=(
            "These are Group 4 handoff candidates, "
            "not Group 2 scalar observations."
        ),
    )

    add_check(
        checks,
        "pdf_timeseries_candidate_rows",
        len(pdf_ts_rows)
        == 1508,
        len(pdf_ts_rows),
        1508,
        severity="warning",
    )

    # --------------------------------------------------------
    # Summary header-only PDF evidence
    # --------------------------------------------------------

    summary_header_only = [
        row
        for row
        in pdf_audit
        if row.get(
            "status",
            ""
        )
        == "summary_header_only_requires_review"
    ]

    add_check(
        checks,
        "pdf_summary_header_only_sections",
        len(summary_header_only)
        == 10,
        len(summary_header_only),
        10,
        severity="warning",
        note=(
            "Header-only PDF summary evidence "
            "is preserved and is not merged as "
            "validated summary data."
        ),
    )

    # --------------------------------------------------------
    # Summary link status, if available
    # --------------------------------------------------------

    summary_link_counts = Counter()

    if summaries:

        link_column = None

        for candidate in [
            "summary_link_status",
            "link_status",
            "record_link_status",
        ]:

            if candidate in summaries[0]:
                link_column = candidate
                break

        if link_column:

            summary_link_counts = Counter(
                row.get(
                    link_column,
                    ""
                )
                for row
                in summaries
            )

            linked_count = sum(
                count
                for status, count
                in summary_link_counts.items()
                if status
                in {
                    "linked_exact_label_trigger",
                    "linked_unique_label",
                }
            )

            no_candidate_count = (
                summary_link_counts.get(
                    "no_record_candidate_available",
                    0,
                )
            )

            add_check(
                checks,
                "linked_summary_rows",
                linked_count
                == 693,
                linked_count,
                693,
            )

            add_check(
                checks,
                "summary_rows_no_candidate_available",
                no_candidate_count
                == 2,
                no_candidate_count,
                2,
                severity="warning",
            )

    # ========================================================
    # Determine overall freeze status
    # ========================================================

    hard_failures = [
        row
        for row
        in checks
        if (
            row[
                "status"
            ]
            == "FAIL"

            and row[
                "severity"
            ]
            == "error"
        )
    ]

    freeze_status = (
        "frozen_validated_with_explicit_review_evidence"
        if not hard_failures
        else "freeze_failed_validation"
    )

    # ========================================================
    # Write final stable package
    # ========================================================

    copy_file(
        record_candidates_path,
        out
        / "record_candidates.csv",
    )

    copy_file(
        record_status_path,
        out
        / "record_status_long.csv",
    )

    copy_file(
        retrieval_status_path,
        out
        / "retrieval_status_long.csv",
    )

    copy_file(
        context_status_path,
        out
        / "group2_context_status_long.csv",
    )

    copy_file(
        pdf_fields_path,
        out
        / "pdf_fields_long.csv",
    )

    copy_file(
        pdf_unresolved_path,
        out
        / "pdf_unresolved_evidence.csv",
    )

    copy_file(
        pdf_table_path,
        out
        / "pdf_summary_table_evidence.csv",
    )

    copy_file(
        pdf_ts_sections_path,
        out
        / "group4_pdf_timeseries_handoff_sections.csv",
    )

    copy_file(
        pdf_ts_rows_path,
        out
        / "group4_pdf_timeseries_handoff_rows.csv",
    )

    copy_file(
        report_coverage_path,
        out
        / "report_coverage.csv",
    )

    copy_file(
        pdf_audit_path,
        out
        / "pdf_section_audit.csv",
    )

    # --------------------------------------------------------
    # Optional stable outputs
    # --------------------------------------------------------

    if summary_path:

        copy_file(
            summary_path,
            out
            / "retrieval_summary_rows.csv",
        )

    if summary_cells_path:

        copy_file(
            summary_cells_path,
            out
            / "retrieval_summary_cells.csv",
        )

    if retrieval_descriptors_path:

        copy_file(
            retrieval_descriptors_path,
            out
            / "retrieval_event_descriptors.csv",
        )

    if group3_deferred_path:

        copy_file(
            group3_deferred_path,
            out
            / "group3_deferred_from_group2_review.csv",
        )

    if group6_deferred_path:

        copy_file(
            group6_deferred_path,
            out
            / "group6_deferred_from_group2_review.csv",
        )

    if other_fields_path:

        copy_file(
            other_fields_path,
            out
            / "other_group_fields_long.csv",
        )

    if pending_section_path:

        copy_file(
            pending_section_path,
            out
            / "source_section_review_evidence.csv",
        )

    # ========================================================
    # Validation report
    # ========================================================

    validation_columns = [
        "check_name",
        "status",
        "severity",
        "observed",
        "expected",
        "note",
    ]

    write_csv(
        out
        / "group2_validation_report.csv",
        checks,
        validation_columns,
    )

    # ========================================================
    # Metadata
    # ========================================================

    report_status_counts = Counter(
        row.get(
            "status",
            ""
        )
        for row
        in report_coverage
    )

    context_scope_counts = Counter(
        row.get(
            "resolved_scope",
            ""
        )
        for row
        in context_status
        if row.get(
            "resolved_scope",
            ""
        )
    )

    pdf_audit_status_counts = Counter(
        row.get(
            "status",
            ""
        )
        for row
        in pdf_audit
    )

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "freeze_status":
            freeze_status,

        "group":
            "Group 2 - Recorded events and record structure",

        "reports":
            len(report_ids),

        "record_candidates":
            len(record_candidates),

        "record_status_rows":
            len(record_status),

        "retrieval_status_rows":
            len(retrieval_status),

        "group2_context_rows":
            len(context_status),

        "group2_context_scope_counts":
            dict(
                context_scope_counts
            ),

        "unresolved_csv_status_rows":
            len(unresolved_status),

        "unresolved_csv_table_rows":
            len(
                unresolved_table_rows
            ),

        "retrieval_summary_rows":
            len(summaries),

        "retrieval_summary_cells":
            len(summary_cells),

        "summary_link_status_counts":
            dict(
                summary_link_counts
            ),

        "retrieval_event_descriptor_rows":
            len(
                retrieval_descriptors
            ),

        "pdf_content_sections":
            pdf_metadata.get(
                "pdf_content_sections",
                len(pdf_audit),
            ),

        "pdf_scalar_field_rows":
            len(pdf_fields),

        "pdf_residual_evidence_rows":
            len(pdf_unresolved),

        "pdf_summary_evidence_rows":
            len(pdf_table_rows),

        "pdf_summary_header_only_sections":
            len(
                summary_header_only
            ),

        "group4_pdf_timeseries_candidate_sections":
            len(
                pdf_ts_sections
            ),

        "group4_pdf_timeseries_candidate_rows":
            len(
                pdf_ts_rows
            ),

        "source_extraction_errors":
            len(
                extraction_errors
            ),

        "pdf_source_errors":
            len(
                pdf_error_rows
            ),

        "report_status_counts":
            dict(
                report_status_counts
            ),

        "pdf_section_audit_status_counts":
            dict(
                pdf_audit_status_counts
            ),

        "validation_check_counts": {
            "pass":
                sum(
                    1
                    for row
                    in checks
                    if row[
                        "status"
                    ]
                    == "PASS"
                ),

            "fail":
                sum(
                    1
                    for row
                    in checks
                    if row[
                        "status"
                    ]
                    == "FAIL"
                ),

            "hard_fail":
                len(
                    hard_failures
                ),
        },

        "scope": (
            "Frozen Group 2 extraction package. "
            "CSV record/retrieval/status extraction and routing "
            "are preserved as validated working views. PDF-only "
            "scalar evidence is preserved separately. Residual "
            "PDF layout fragments remain explicit review evidence "
            "rather than being force-parsed. Embedded PDF time-series "
            "structures are excluded from Group 2 scalar extraction "
            "and handed off to Group 4. Header-only PDF summary "
            "evidence is retained without claiming recovered summary "
            "data. No new event identities, semantic mappings, "
            "cross-label merges, or decoded values are introduced "
            "during freeze."
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

    # ========================================================
    # Console output
    # ========================================================

    print(
        json.dumps(
            metadata,
            indent=2,
        )
    )

    print(
        f"Outputs: {out}"
    )

    if hard_failures:

        print()
        print(
            "GROUP 2 FREEZE FAILED:"
        )

        for row in hard_failures:
            print(
                f"- {row['check_name']}: "
                f"observed={row['observed']}, "
                f"expected={row['expected']}"
            )

        raise SystemExit(1)

    print()
    print(
        "GROUP 2 FREEZE COMPLETE."
    )


if __name__ == "__main__":
    main()