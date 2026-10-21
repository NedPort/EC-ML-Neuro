from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from src.edr.validation.router_regression import (
    RegressionResult,
    compare_raw_row,
    family_mismatches,
    newly_unclassified,
    results_to_dicts,
    summarize_mismatch_labels,
    summarize_results,
    validate_regression,
)


csv.field_size_limit(100_000_000)


# ============================================================
# Generic I/O
# ============================================================

def clean(
    value: Any,
) -> str:
    return " ".join(
        str(
            value
            if value is not None
            else ""
        ).split()
    )


def read_csv(
    path: Path,
) -> list[dict[str, str]]:
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(
            csv.DictReader(f)
        )


def read_header(
    path: Path,
) -> list[str]:
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        reader = csv.reader(f)

        try:
            return next(reader)
        except StopIteration:
            return []


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if columns is None:
        columns = union_columns(
            rows
        )

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
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(
            rows
        )

    tmp.replace(
        path
    )


def union_columns(
    rows: list[dict[str, Any]],
) -> list[str]:
    seen = set()
    columns = []

    preferred = [
        "reference_group",
        "reference_file",
        "report_id",
        "case_id",
        "vehicle_number",
        "source_format",
        "source_location",
        "raw_label",
        "raw_value",
        "section_context",
        "expected_destination",
        "actual_destination",
        "expected_family",
        "actual_family",
        "matched_by",
        "confidence",
        "destination_match",
        "family_match",
        "newly_unclassified",
        "regression_level",
        "regression_status",
        "requires_review",
        "reason",
        "review_reason",
    ]

    for column in preferred:
        if column not in seen:
            seen.add(
                column
            )
            columns.append(
                column
            )

    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(
                    key
                )
                columns.append(
                    key
                )

    return columns


def first_existing(
    directory: Path,
    filenames: list[str],
) -> Path | None:
    for filename in filenames:
        path = (
            directory
            / filename
        )

        if path.exists():
            return path

    return None


def first_value(
    row: dict[str, Any],
    candidates: list[str],
    default: str = "",
) -> str:
    for key in candidates:
        value = clean(
            row.get(
                key,
                "",
            )
        )

        if value:
            return value

    return default


def json_dict(
    value: Any,
) -> dict[str, Any]:
    text = clean(
        value
    )

    if not text:
        return {}

    try:
        parsed = json.loads(
            text
        )
    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return {}

    if isinstance(
        parsed,
        dict,
    ):
        return parsed

    return {}


# ============================================================
# Regression record helper
# ============================================================

def compare_historical_row(
    *,
    row_index: int,
    label: str,
    value: str,
    section_context: str,
    expected_destination: str,
    expected_family: str,
    report_id: str,
    case_id: str,
    vehicle_number: str,
    source_format: str,
    source_location: str,
) -> RegressionResult | None:

    label = clean(
        label
    )

    value = clean(
        value
    )

    if not label:
        return None

    return compare_raw_row(
        row=[
            label,
            value,
        ],
        row_index=row_index,
        section_context=clean(
            section_context
        ),
        expected_destination=(
            expected_destination
        ),
        expected_family=(
            expected_family
        ),
        report_id=clean(
            report_id
        ),
        case_id=clean(
            case_id
        ),
        vehicle_number=clean(
            vehicle_number
        ),
        source_format=clean(
            source_format
        ),
        source_location=clean(
            source_location
        ),
    )


# ============================================================
# Group 1
# ============================================================

def load_group1(
    directory: Path,
) -> list[RegressionResult]:

    path = (
        directory
        / "report_metadata_selected_long.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing Group 1 regression source: {path}"
        )

    rows = read_csv(
        path
    )

    results = []

    for index, row in enumerate(
        rows
    ):
        selection_status = clean(
            row.get(
                "selection_status",
                "",
            )
        ).casefold()

        # No historical observation exists to route.
        if selection_status in {
            "not_extracted",
            "absent",
        }:
            continue

        evidence = json_dict(
            row.get(
                "selected_evidence_json",
                "",
            )
        )

        label = first_value(
            evidence,
            [
                "source_label_raw",
                "source_label",
                "field_label_raw",
                "label_raw",
                "label",
            ],
        )

        # Fallback only when raw source label is unavailable.
        if not label:
            label = clean(
                row.get(
                    "field_name",
                    "",
                )
            )

        value = first_value(
            evidence,
            [
                "value_raw",
                "field_value_raw",
                "raw_value",
                "value_text",
            ],
        )

        if not value:
            value = first_value(
                row,
                [
                    "value_raw",
                    "value_text",
                ],
            )

        section = first_value(
            evidence,
            [
                "source_section_heading",
                "section_heading",
                "section_context",
                "source_section",
            ],
        )

        result = compare_historical_row(
            row_index=index,
            label=label,
            value=value,
            section_context=section,
            expected_destination="group1",
            expected_family="",
            report_id=row.get(
                "report_id",
                "",
            ),
            case_id=row.get(
                "case_id",
                "",
            ),
            vehicle_number=row.get(
                "vehicle_number",
                "",
            ),
            source_format=first_value(
                evidence,
                [
                    "source_format",
                ],
                default=row.get(
                    "selected_source",
                    "",
                ),
            ),
            source_location=first_value(
                evidence,
                [
                    "source_path",
                    "source_location",
                ],
                default=str(
                    path
                ),
            ),
        )

        if result:
            results.append(
                result
            )

    return results


# ============================================================
# Group 2
# ============================================================

GROUP2_LABEL_COLUMNS = [
    "field_label_raw",
    "label_raw",
    "status_label",
    "field_label",
    "label",
    "attribute",
    "field_name",
    "descriptor_label",
]

GROUP2_VALUE_COLUMNS = [
    "field_value_raw",
    "value_raw",
    "status_value",
    "field_value",
    "value",
    "attribute_value",
    "descriptor_value",
]

GROUP2_SECTION_COLUMNS = [
    "source_section_heading",
    "section_heading",
    "section_context",
    "source_heading",
    "section",
]

GROUP2_FAMILY_COLUMNS = [
    "family",
    "audited_family",
    "candidate_family",
    "status_family",
    "record_family",
]


def looks_like_group2_observation_table(
    path: Path,
) -> bool:
    name = path.name.casefold()

    reject_tokens = [
        "summary",
        "validation",
        "manifest",
        "metadata",
        "error",
        "coverage",
        "family",
        "audit",
        "review",
        "handoff",
        "unresolved",
    ]

    if any(
        token in name
        for token in reject_tokens
    ):
        return False

    header = {
        clean(x)
        for x in read_header(
            path
        )
    }

    has_report_id = (
        "report_id"
        in header
    )

    has_label = any(
        candidate
        in header
        for candidate
        in GROUP2_LABEL_COLUMNS
    )

    has_value = any(
        candidate
        in header
        for candidate
        in GROUP2_VALUE_COLUMNS
    )

    return (
        has_report_id
        and has_label
        and has_value
    )


def load_group2(
    directory: Path,
) -> tuple[
    list[RegressionResult],
    list[str],
]:
    if not directory.exists():
        raise FileNotFoundError(
            directory
        )

    candidate_files = [
        path
        for path
        in sorted(
            directory.glob(
                "*.csv"
            )
        )
        if looks_like_group2_observation_table(
            path
        )
    ]

    results = []
    used_files = []

    # Prevent derivative Group 2 tables from causing duplicate
    # comparisons of the same historical source observation.
    seen = set()

    for path in candidate_files:
        rows = read_csv(
            path
        )

        used_here = 0

        for index, row in enumerate(
            rows
        ):
            label = first_value(
                row,
                GROUP2_LABEL_COLUMNS,
            )

            value = first_value(
                row,
                GROUP2_VALUE_COLUMNS,
            )

            if not label:
                continue

            section = first_value(
                row,
                GROUP2_SECTION_COLUMNS,
            )

            source_location = first_value(
                row,
                [
                    "source_path",
                    "source_location",
                    "pdf_path",
                    "csv_path",
                ],
                default=str(
                    path
                ),
            )

            dedupe_key = (
                clean(
                    row.get(
                        "report_id",
                        "",
                    )
                ),
                clean(
                    row.get(
                        "case_id",
                        "",
                    )
                ),
                clean(
                    row.get(
                        "vehicle_number",
                        "",
                    )
                ),
                clean(
                    label
                ).casefold(),
                clean(
                    value
                ),
                clean(
                    section
                ).casefold(),
                clean(
                    row.get(
                        "source_record_index",
                        row.get(
                            "pdf_line_number",
                            "",
                        ),
                    )
                ),
            )

            if dedupe_key in seen:
                continue

            seen.add(
                dedupe_key
            )

            result = compare_historical_row(
                row_index=index,
                label=label,
                value=value,
                section_context=section,
                expected_destination="group2",
                # Group 2 historical family taxonomy changed
                # across extraction stages. Destination is the
                # hard criterion here.
                expected_family="",
                report_id=row.get(
                    "report_id",
                    "",
                ),
                case_id=row.get(
                    "case_id",
                    "",
                ),
                vehicle_number=row.get(
                    "vehicle_number",
                    "",
                ),
                source_format=first_value(
                    row,
                    [
                        "source_format",
                    ],
                ),
                source_location=(
                    source_location
                ),
            )

            if result:
                results.append(
                    result
                )
                used_here += 1

        if used_here:
            used_files.append(
                path.name
            )

    if not results:
        raise RuntimeError(
            "No observation-like Group 2 tables were found. "
            "Inspect the files in "
            f"{directory}"
        )

    return (
        results,
        used_files,
    )


# ============================================================
# Group 3
# ============================================================

def load_group3(
    directory: Path,
) -> list[RegressionResult]:

    path = first_existing(
        directory,
        [
            "condition_registry.csv",
        ],
    )

    if path is None:
        raise FileNotFoundError(
            "Missing Group 3 condition_registry.csv "
            f"in {directory}"
        )

    rows = read_csv(
        path
    )

    results = []

    for index, row in enumerate(
        rows
    ):
        result = compare_historical_row(
            row_index=index,
            label=row.get(
                "field_label_raw",
                "",
            ),
            value=row.get(
                "field_value_raw",
                "",
            ),
            section_context=first_value(
                row,
                [
                    "source_section_heading",
                    "section_heading",
                    "section_context",
                ],
            ),
            expected_destination="group3",
            expected_family=row.get(
                "family",
                "",
            ),
            report_id=row.get(
                "report_id",
                "",
            ),
            case_id=row.get(
                "case_id",
                "",
            ),
            vehicle_number=row.get(
                "vehicle_number",
                "",
            ),
            source_format=row.get(
                "source_format",
                "",
            ),
            source_location=first_value(
                row,
                [
                    "source_path",
                ],
                default=str(
                    path
                ),
            ),
        )

        if result:
            results.append(
                result
            )

    return results


# ============================================================
# Group 5
# ============================================================

def load_group5(
    directory: Path,
) -> list[RegressionResult]:

    registry_path = (
        directory
        / "measurement_registry.csv"
    )

    companion_path = (
        directory
        / "companion_context.csv"
    )

    if not registry_path.exists():
        raise FileNotFoundError(
            registry_path
        )

    results = []

    registry = read_csv(
        registry_path
    )

    for index, row in enumerate(
        registry
    ):
        result = compare_historical_row(
            row_index=index,
            label=row.get(
                "field_label_raw",
                "",
            ),
            value=row.get(
                "field_value_raw",
                "",
            ),
            section_context=first_value(
                row,
                [
                    "source_section_heading",
                    "section_heading",
                    "section_context",
                ],
            ),
            expected_destination="group5",
            expected_family=first_value(
                row,
                [
                    "family",
                    "audited_family",
                    "candidate_family",
                ],
            ),
            report_id=row.get(
                "report_id",
                "",
            ),
            case_id=row.get(
                "case_id",
                "",
            ),
            vehicle_number=row.get(
                "vehicle_number",
                "",
            ),
            source_format=row.get(
                "source_format",
                "",
            ),
            source_location=first_value(
                row,
                [
                    "source_path",
                ],
                default=str(
                    registry_path
                ),
            ),
        )

        if result:
            results.append(
                result
            )

    if companion_path.exists():
        companions = read_csv(
            companion_path
        )

        offset = len(
            registry
        )

        for index, row in enumerate(
            companions,
            start=offset,
        ):
            result = compare_historical_row(
                row_index=index,
                label=first_value(
                    row,
                    [
                        "field_label_raw",
                        "label_raw",
                        "field_label",
                    ],
                ),
                value=first_value(
                    row,
                    [
                        "field_value_raw",
                        "value_raw",
                        "field_value",
                    ],
                ),
                section_context=first_value(
                    row,
                    [
                        "source_section_heading",
                        "section_heading",
                        "section_context",
                    ],
                ),
                expected_destination=(
                    "group5_companion"
                ),
                expected_family=first_value(
                    row,
                    [
                        "family",
                        "context_family",
                    ],
                ),
                report_id=row.get(
                    "report_id",
                    "",
                ),
                case_id=row.get(
                    "case_id",
                    "",
                ),
                vehicle_number=row.get(
                    "vehicle_number",
                    "",
                ),
                source_format=row.get(
                    "source_format",
                    "",
                ),
                source_location=first_value(
                    row,
                    [
                        "source_path",
                    ],
                    default=str(
                        companion_path
                    ),
                ),
            )

            if result:
                results.append(
                    result
                )

    return results


# ============================================================
# Group 6
# ============================================================

def load_group6(
    directory: Path,
) -> list[RegressionResult]:

    path = (
        directory
        / "technical_registry.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            path
        )

    rows = read_csv(
        path
    )

    results = []

    for index, row in enumerate(
        rows
    ):
        result = compare_historical_row(
            row_index=index,
            label=row.get(
                "field_label_raw",
                "",
            ),
            value=row.get(
                "field_value_raw",
                "",
            ),
            section_context=first_value(
                row,
                [
                    "source_section_heading",
                    "section_heading",
                    "section_context",
                ],
            ),
            expected_destination="group6",
            expected_family=row.get(
                "family",
                "",
            ),
            report_id=row.get(
                "report_id",
                "",
            ),
            case_id=row.get(
                "case_id",
                "",
            ),
            vehicle_number=row.get(
                "vehicle_number",
                "",
            ),
            source_format=row.get(
                "source_format",
                "",
            ),
            source_location=first_value(
                row,
                [
                    "source_path",
                ],
                default=str(
                    path
                ),
            ),
        )

        if result:
            results.append(
                result
            )

    return results


# ============================================================
# Group 4 structural audit
# ============================================================

def find_group4_registry(
    directory: Path,
) -> Path | None:

    preferred = [
        "timeseries_registry.csv",
        "series_registry.csv",
        "time_series_registry.csv",
    ]

    path = first_existing(
        directory,
        preferred,
    )

    if path:
        return path

    for candidate in sorted(
        directory.glob(
            "*.csv"
        )
    ):
        header = set(
            read_header(
                candidate
            )
        )

        if (
            "series_id"
            in header
            and "family"
            in header
        ):
            return candidate

    return None


def structural_group4_audit(
    directory: Path,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:

    registry_path = (
        find_group4_registry(
            directory
        )
    )

    if registry_path is None:
        raise FileNotFoundError(
            "Could not locate Group 4 series registry in "
            f"{directory}"
        )

    registry = read_csv(
        registry_path
    )

    rows = []

    for row in registry:
        rows.append({
            "report_id":
                clean(
                    row.get(
                        "report_id",
                        "",
                    )
                ),

            "case_id":
                clean(
                    row.get(
                        "case_id",
                        "",
                    )
                ),

            "vehicle_number":
                clean(
                    row.get(
                        "vehicle_number",
                        "",
                    )
                ),

            "series_id":
                clean(
                    row.get(
                        "series_id",
                        "",
                    )
                ),

            "source_format":
                clean(
                    row.get(
                        "source_format",
                        "",
                    )
                ),

            "source_package":
                clean(
                    row.get(
                        "source_package",
                        "",
                    )
                ),

            "source_heading":
                first_value(
                    row,
                    [
                        "source_heading",
                        "source_section_heading",
                        "section_heading",
                    ],
                ),

            "family":
                clean(
                    row.get(
                        "family",
                        "",
                    )
                ),

            "component":
                clean(
                    row.get(
                        "component",
                        "",
                    )
                ),

            "orientation":
                clean(
                    row.get(
                        "orientation",
                        "",
                    )
                ),

            "axis_type":
                clean(
                    row.get(
                        "axis_type",
                        "",
                    )
                ),

            "structural_status":
                "historical_group4_series_preserved",
        })

    reports = {
        row["report_id"]
        for row in rows
        if row["report_id"]
    }

    source_formats = Counter(
        row["source_format"]
        for row in rows
        if row["source_format"]
    )

    families = Counter(
        row["family"]
        for row in rows
        if row["family"]
    )

    summary = {
        "registry_file":
            str(
                registry_path
            ),

        "series_count":
            len(
                rows
            ),

        "report_count":
            len(
                reports
            ),

        "source_format_counts":
            dict(
                source_formats
            ),

        "family_counts":
            dict(
                families
            ),

        "comparison_method":
            (
                "structural coverage only; Group 4 historical "
                "records are complete time-series structures and "
                "are not forced into scalar row reconstruction"
            ),
    }

    return (
        rows,
        summary,
    )


# ============================================================
# Add reference metadata to output rows
# ============================================================

def decorated_rows(
    group_name: str,
    reference_file: str,
    results: list[
        RegressionResult
    ],
) -> list[dict[str, Any]]:

    output = []

    for result in results:
        row = result.to_dict()

        row = {
            "reference_group":
                group_name,

            "reference_file":
                reference_file,

            **row,
        }

        output.append(
            row
        )

    return output


# ============================================================
# Main
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Run the new EDR observation parser/router against "
            "historical validated Group 1-6 outputs."
        )
    )

    parser.add_argument(
        "--group1-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group1_csv_first_v1"
        ),
    )

    parser.add_argument(
        "--group2-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group2_final_v1"
        ),
    )

    parser.add_argument(
        "--group3-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_final_frozen_v1"
        ),
    )

    parser.add_argument(
        "--group4-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group4_final_v1"
        ),
    )

    parser.add_argument(
        "--group5-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group5_final_frozen_v1"
        ),
    )

    parser.add_argument(
        "--group6-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group6_final_frozen_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/router_regression_v1"
        ),
    )

    args = parser.parse_args()

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Load historical observations
    # ========================================================

    print()
    print(
        "Loading historical Group 1..."
    )

    group1 = load_group1(
        args.group1_directory
    )

    print(
        f"  Group 1 observations: {len(group1):,}"
    )

    print()
    print(
        "Loading historical Group 2..."
    )

    (
        group2,
        group2_files,
    ) = load_group2(
        args.group2_directory
    )

    print(
        f"  Group 2 observations: {len(group2):,}"
    )

    print(
        "  Group 2 source tables:"
    )

    for filename in group2_files:
        print(
            f"    - {filename}"
        )

    print()
    print(
        "Loading historical Group 3..."
    )

    group3 = load_group3(
        args.group3_directory
    )

    print(
        f"  Group 3 observations: {len(group3):,}"
    )

    print()
    print(
        "Auditing historical Group 4 structure..."
    )

    (
        group4_rows,
        group4_summary,
    ) = structural_group4_audit(
        args.group4_directory
    )

    print(
        f"  Group 4 series: "
        f"{group4_summary['series_count']:,}"
    )

    print()
    print(
        "Loading historical Group 5..."
    )

    group5 = load_group5(
        args.group5_directory
    )

    print(
        f"  Group 5 observations: {len(group5):,}"
    )

    print()
    print(
        "Loading historical Group 6..."
    )

    group6 = load_group6(
        args.group6_directory
    )

    print(
        f"  Group 6 observations: {len(group6):,}"
    )

    # ========================================================
    # Combined scalar regression population
    # ========================================================

    all_results = (
        group1
        + group2
        + group3
        + group5
        + group6
    )

    # ========================================================
    # Comparison tables
    # ========================================================

    comparison_rows = []

    comparison_rows.extend(
        decorated_rows(
            "group1",
            "report_metadata_selected_long.csv",
            group1,
        )
    )

    comparison_rows.extend(
        decorated_rows(
            "group2",
            ";".join(
                group2_files
            ),
            group2,
        )
    )

    comparison_rows.extend(
        decorated_rows(
            "group3",
            "condition_registry.csv",
            group3,
        )
    )

    comparison_rows.extend(
        decorated_rows(
            "group5",
            (
                "measurement_registry.csv;"
                "companion_context.csv"
            ),
            group5,
        )
    )

    comparison_rows.extend(
        decorated_rows(
            "group6",
            "technical_registry.csv",
            group6,
        )
    )

    write_csv(
        out
        / "routing_comparison.csv",
        comparison_rows,
    )

    # ========================================================
    # Destination mismatches
    # ========================================================

    destination_mismatch_rows = [
        row
        for row in comparison_rows
        if not row[
            "destination_match"
        ]
    ]

    write_csv(
        out
        / "destination_mismatches.csv",
        destination_mismatch_rows,
        columns=union_columns(
            comparison_rows
        ),
    )

    # ========================================================
    # Family mismatches
    # ========================================================

    family_mismatch_results = (
        family_mismatches(
            all_results
        )
    )

    family_mismatch_rows = (
        results_to_dicts(
            family_mismatch_results
        )
    )

    write_csv(
        out
        / "family_mismatches.csv",
        family_mismatch_rows,
    )

    # ========================================================
    # Newly unclassified
    # ========================================================

    newly_unclassified_results = (
        newly_unclassified(
            all_results
        )
    )

    newly_unclassified_rows = (
        results_to_dicts(
            newly_unclassified_results
        )
    )

    write_csv(
        out
        / "newly_unclassified.csv",
        newly_unclassified_rows,
    )

    # ========================================================
    # Label mismatch summary
    # ========================================================

    mismatch_label_rows = (
        summarize_mismatch_labels(
            all_results
        )
    )

    write_csv(
        out
        / "mismatch_label_summary.csv",
        mismatch_label_rows,
    )

    # ========================================================
    # Per-group summary
    # ========================================================

    group_sets = {
        "group1": group1,
        "group2": group2,
        "group3": group3,
        "group5": group5,
        "group6": group6,
    }

    group_summary_rows = []

    for group_name, rows in (
        group_sets.items()
    ):
        summary = summarize_results(
            rows
        )

        group_summary_rows.append({
            "reference_group":
                group_name,

            "total_observations":
                summary[
                    "total_observations"
                ],

            "destination_matches":
                summary[
                    "destination_matches"
                ],

            "destination_mismatches":
                summary[
                    "destination_mismatches"
                ],

            "destination_match_rate":
                summary[
                    "destination_match_rate"
                ],

            "destination_and_family_matches":
                summary[
                    "destination_and_family_matches"
                ],

            "family_mismatch_count":
                summary[
                    "family_mismatch_count"
                ],

            "newly_unclassified_count":
                summary[
                    "newly_unclassified_count"
                ],
        })

    group_summary_rows.append({
        "reference_group":
            "group4_structural",

        "total_observations":
            group4_summary[
                "series_count"
            ],

        "destination_matches":
            "",

        "destination_mismatches":
            "",

        "destination_match_rate":
            "",

        "destination_and_family_matches":
            "",

        "family_mismatch_count":
            "",

        "newly_unclassified_count":
            "",
    })

    write_csv(
        out
        / "group_summary.csv",
        group_summary_rows,
    )

    # ========================================================
    # Group 4 structural evidence
    # ========================================================

    write_csv(
        out
        / "group4_structural_coverage.csv",
        group4_rows,
    )

    # ========================================================
    # Overall summary / hard gate
    # ========================================================

    overall_summary = summarize_results(
        all_results
    )

    validation = validate_regression(
        all_results,
        allow_destination_mismatches=0,
        allow_newly_unclassified=0,
    )

    validation_rows = [
        {
            "check":
                "destination_mismatches_zero",

            "status":
                (
                    "PASS"
                    if validation[
                        "destination_mismatch_pass"
                    ]
                    else "FAIL"
                ),

            "observed":
                validation[
                    "destination_mismatch_count"
                ],

            "expected":
                validation[
                    "destination_mismatch_limit"
                ],
        },

        {
            "check":
                "newly_unclassified_zero",

            "status":
                (
                    "PASS"
                    if validation[
                        "newly_unclassified_pass"
                    ]
                    else "FAIL"
                ),

            "observed":
                validation[
                    "newly_unclassified_count"
                ],

            "expected":
                validation[
                    "newly_unclassified_limit"
                ],
        },
    ]

    write_csv(
        out
        / "validation_checks.csv",
        validation_rows,
        [
            "check",
            "status",
            "observed",
            "expected",
        ],
    )

    # ========================================================
    # Metadata
    # ========================================================

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "stage":
            "historical_router_regression_v1",

        "router_population_groups": [
            "group1",
            "group2",
            "group3",
            "group5",
            "group6",
        ],

        "group4_method":
            (
                "structural coverage only; historical Group 4 "
                "records are full time-series structures and "
                "are not reduced to synthetic scalar observations"
            ),

        "group_counts": {
            "group1":
                len(
                    group1
                ),

            "group2":
                len(
                    group2
                ),

            "group3":
                len(
                    group3
                ),

            "group4_series":
                group4_summary[
                    "series_count"
                ],

            "group5":
                len(
                    group5
                ),

            "group6":
                len(
                    group6
                ),
        },

        "group2_observation_tables":
            group2_files,

        "overall_scalar_regression":
            overall_summary,

        "group4_structural_summary":
            group4_summary,

        "hard_validation":
            validation,

        "hard_validation_pass":
            validation[
                "hard_validation_pass"
            ],

        "rules": [
            (
                "Historical frozen/validated outputs are "
                "read-only reference truth."
            ),
            (
                "Destination mismatch is a hard regression."
            ),
            (
                "Historically classified observation becoming "
                "review is a hard regression."
            ),
            (
                "Family mismatch alone is preserved for audit "
                "but is not yet a hard failure."
            ),
            (
                "Group 4 remains structural and is not forced "
                "through scalar observation reconstruction."
            ),
        ],
    }

    metadata_tmp = (
        out
        / "metadata.json.part"
    )

    metadata_tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    metadata_tmp.replace(
        out
        / "metadata.json"
    )

    # ========================================================
    # Console summary
    # ========================================================

    print()
    print("=" * 80)
    print(
        "HISTORICAL ROUTER REGRESSION SUMMARY"
    )
    print("=" * 80)

    print(
        f"Scalar observations compared: "
        f"{overall_summary['total_observations']:,}"
    )

    print(
        f"Destination matches: "
        f"{overall_summary['destination_matches']:,}"
    )

    print(
        f"Destination mismatches: "
        f"{overall_summary['destination_mismatches']:,}"
    )

    print(
        f"Destination match rate: "
        f"{overall_summary['destination_match_rate']:.4%}"
    )

    print(
        f"Family mismatches: "
        f"{overall_summary['family_mismatch_count']:,}"
    )

    print(
        f"Newly unclassified: "
        f"{overall_summary['newly_unclassified_count']:,}"
    )

    print(
        f"Group 4 historical series structurally preserved: "
        f"{group4_summary['series_count']:,}"
    )

    print()
    print(
        f"Outputs: {out}"
    )

    print()

    if validation[
        "hard_validation_pass"
    ]:
        print(
            "HISTORICAL ROUTER REGRESSION HARD CHECKS PASSED."
        )
    else:
        print(
            "HISTORICAL ROUTER REGRESSION FOUND "
            "HARD DISAGREEMENTS."
        )

        print(
            "Inspect:"
        )

        print(
            "  destination_mismatches.csv"
        )

        print(
            "  newly_unclassified.csv"
        )

        raise SystemExit(
            1
        )


if __name__ == "__main__":
    main()