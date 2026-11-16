
"""Generate Group 6 manual source-validation worksheets.

Run from the CISS_downloader project root:

uv run --active python .\src\edr_new\rules\build_group6_manual_validation.py

Reads existing Group 6 data without modifying original or normalized datasets.
"""

from pathlib import Path
import json
import random
import re

import pandas as pd


ROOT = Path("data/processed/edr_new/unified/group6")
NORMALIZED = ROOT / "normalized"
OUTPUT = NORMALIZED / "manual_validation"

SEED = 20261116
RANDOM_CHECKS = 80


def load_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def first_existing(paths):
    for path in paths:
        if path.exists():
            return path
    return None


def pick_column(df, candidates):
    lookup = {c.casefold(): c for c in df.columns}
    for name in candidates:
        if name.casefold() in lookup:
            return lookup[name.casefold()]
    return None


def value(row, column):
    if column is None:
        return ""
    return str(row[column]).strip()


def main():
    print("GROUP 6 MANUAL VALIDATION")
    print("=" * 55)

    wide = load_csv(NORMALIZED / "group6_normalized_wide.csv")
    dictionary = load_csv(
        NORMALIZED / "group6_normalized_dictionary.csv"
    )
    lineage = load_csv(
        NORMALIZED / "group6_column_lineage.csv"
    )
    audit = load_csv(
        NORMALIZED / "group6_merge_audit.csv"
    )

    original_long = load_csv(ROOT / "group6_unified_long.csv")

    unresolved_path = first_existing([
        ROOT / "group6_unresolved_issues.csv",
        ROOT / "group6_17_unresolved_adjudication.csv",
    ])

    unresolved = (
        load_csv(unresolved_path)
        if unresolved_path is not None
        else pd.DataFrame()
    )

    print(f"Normalized reports: {len(wide)}")
    print(f"Normalized columns: {len(wide.columns)}")
    print(f"Merge groups: {len(audit)}")
    print(f"Unresolved observations: {len(unresolved)}")

    # Identify report and feature columns.
    report_wide = pick_column(
        wide, ["report_id", "report_key", "report_uid"]
    )
    report_long = pick_column(
        original_long, ["report_id", "report_key", "report_uid"]
    )
    source_feature = pick_column(
        original_long,
        ["feature_column", "column_name", "original_column"]
    )
    source_value = pick_column(
        original_long,
        ["field_value_raw", "value", "field_value", "raw_value"]
    )

    if not report_wide or not report_long or not source_feature:
        raise ValueError(
            "Could not identify report or feature columns in "
            "Group 6 data. Inspect CSV headers."
        )

    if lineage.original_column.duplicated().any():
        raise ValueError("Duplicate original columns in lineage")

    if not set(lineage.normalized_column).issubset(set(wide.columns)):
        raise ValueError("Lineage contains missing normalized columns")

    if dictionary.column_name.tolist() != wide.columns.tolist():
        raise ValueError("Dictionary and normalized wide columns differ")

    # Map each original feature to its normalized column.
    feature_map = dict(zip(
        lineage.original_column,
        lineage.normalized_column
    ))

    wide_index = wide.set_index(report_wide)

    if wide_index.index.has_duplicates:
        raise ValueError("Duplicate report identifiers in normalized wide")

    metadata_candidates = {
        "case_id": ["case_id"],
        "vehicle_number": ["vehicle_number", "vehicle_id"],
        "source_format": ["source_format", "file_format"],
        "source_path": ["source_path", "file_path", "report_path"],
        "pdf_page": ["pdf_page", "page_number"],
        "source_section": [
            "source_section_heading", "source_section", "section"
        ],
        "source_label": [
            "field_label_raw", "source_label", "field_label"
        ],
        "source_line": ["source_line_raw", "source_line"],
        "source_record_index": [
            "source_record_index", "record_index"
        ],
        "family": ["family", "feature_family"],
    }

    metadata_cols = {
        name: pick_column(original_long, choices)
        for name, choices in metadata_candidates.items()
    }

    records = []

    for _, row in original_long.iterrows():
        report_id = value(row, report_long)
        original_column = value(row, source_feature)

        normalized_column = feature_map.get(original_column)

        if not normalized_column:
            continue

        if report_id not in wide_index.index:
            continue

        normalized_value = str(
            wide_index.at[report_id, normalized_column]
        ).strip()

        if not normalized_value:
            continue

        record = {
            "report_id": report_id,
            "original_column": original_column,
            "normalized_column": normalized_column,
            "extracted_value": value(row, source_value),
            "normalized_value": normalized_value,
        }

        for name, col in metadata_cols.items():
            record[name] = value(row, col)

        records.append(record)

    source_records = pd.DataFrame(records)

    if source_records.empty:
        raise ValueError(
            "No source records matched normalized data. "
            "Check report IDs and feature column names."
        )

    print(f"Traceable source records: {len(source_records)}")

    # ---------------------------------------------------------
    # 1. Random validation: balanced by format and feature family
    # ---------------------------------------------------------

    rng = random.Random(SEED)

    source_records["stratum"] = (
        source_records["source_format"].str.lower()
        + "|"
        + source_records["family"].str.lower()
    )

    selected_indices = []

    for _, group in source_records.groupby("stratum", sort=True):
        candidates = group.index.tolist()
        selected_indices.extend(
            rng.sample(candidates, min(2, len(candidates)))
        )

    if len(selected_indices) > RANDOM_CHECKS:
        selected_indices = rng.sample(
            selected_indices, RANDOM_CHECKS
        )

    selected_set = set(selected_indices)

    remaining = [
        i for i in source_records.index
        if i not in selected_set
    ]

    if len(selected_indices) < RANDOM_CHECKS:
        needed = min(
            RANDOM_CHECKS - len(selected_indices),
            len(remaining)
        )
        selected_indices.extend(rng.sample(remaining, needed))

    random_checks = source_records.loc[
        selected_indices
    ].copy()

    random_checks["check_type"] = "RANDOM_SOURCE_VALUE"

    # ---------------------------------------------------------
    # 2. Merge validation: cover every merged group
    # ---------------------------------------------------------

    merge_checks = []

    for _, merge in audit.iterrows():
        target = str(merge["normalized_column"]).strip()

        candidates = source_records[
            source_records.normalized_column == target
        ]

        if candidates.empty:
            print(f"WARNING: No source record for merge: {target}")
            continue

        # Prefer reports containing multiple original source columns.
        counts = (
            candidates.groupby("report_id")["original_column"]
            .nunique()
            .sort_values(ascending=False)
        )

        chosen_report = counts.index[0]

        matching = candidates[
            candidates.report_id == chosen_report
        ].copy()

        matching["check_type"] = "MERGE_SOURCE_AND_MEANING"

        merge_checks.append(matching)

    if merge_checks:
        merge_checks = pd.concat(
            merge_checks, ignore_index=True
        )
    else:
        merge_checks = pd.DataFrame(
            columns=random_checks.columns
        )

    # ---------------------------------------------------------
    # 3. Combine source-level checks
    # ---------------------------------------------------------

    checks = pd.concat(
        [random_checks, merge_checks],
        ignore_index=True
    )

    checks.insert(
        0,
        "check_id",
        [f"G6-{i:04d}" for i in range(1, len(checks) + 1)]
    )

    checks["review_decision"] = ""
    checks["reviewer_notes"] = ""
    checks["source_verified"] = ""
    checks["merge_semantics_verified"] = ""

    # ---------------------------------------------------------
    # 4. Prepare unresolved observations
    # ---------------------------------------------------------

    unresolved_review = unresolved.copy()

    unresolved_review.insert(
        0,
        "check_id",
        [
            f"G6-U{i:03d}"
            for i in range(1, len(unresolved_review) + 1)
        ]
    )

    unresolved_review["review_decision"] = ""
    unresolved_review["reviewer_notes"] = ""

    # ---------------------------------------------------------
    # 5. Save worksheets
    # ---------------------------------------------------------

    OUTPUT.mkdir(parents=True, exist_ok=True)

    checks_path = OUTPUT / "group6_manual_validation_checks.csv"
    unresolved_output = OUTPUT / "group6_unresolved_review.csv"
    summary_path = OUTPUT / "group6_manual_validation_summary.json"

    # Protect any manual decisions already entered.
    for path in [checks_path, unresolved_output]:
        if path.exists():
            existing = load_csv(path)
            if "review_decision" in existing.columns:
                if existing["review_decision"].str.strip().ne("").any():
                    raise RuntimeError(
                        f"Existing reviews found in {path}. "
                        "Back up or rename that file before regenerating."
                    )

    checks.to_csv(checks_path, index=False)
    unresolved_review.to_csv(unresolved_output, index=False)

    summary = {
        "normalized_reports": len(wide),
        "normalized_columns": len(wide.columns),
        "random_source_checks": len(random_checks),
        "merged_groups": len(audit),
        "merge_source_observations": len(merge_checks),
        "unresolved_observations": len(unresolved_review),
        "total_review_rows": len(checks) + len(unresolved_review),
        "status": "PENDING_MANUAL_SOURCE_VALIDATION",
    }

    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8"
    )

    print("\nVALIDATION SUMMARY")
    print(json.dumps(summary, indent=2))

    print("\nFiles generated:")
    print(checks_path)
    print(unresolved_output)
    print(summary_path)

    print("\nAllowed decisions:")
    print("Correct | Needs Correction | Not Found | Ambiguous")


if __name__ == "__main__":
    main()
