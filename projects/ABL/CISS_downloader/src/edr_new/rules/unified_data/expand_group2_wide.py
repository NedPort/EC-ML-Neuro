
"""
ABLs — Group 2 Wide-Format Expansion
====================================

Run after unify_group2.py.

Creates:
    group2_unified_records_wide.csv
    group2_unified_reports_wide.csv
    group2_records_wide_dictionary.csv
    group2_reports_wide_dictionary.csv
    group2_wide_conflicts.csv
    group2_wide_summary.json

Python 3.10+
Dependencies: pandas

Usage:
    uv run --active python -m src.edr_new.rules.unified_data.expand_group2_wide

Optional:
    --input-dir PATH
    --output-dir PATH

Original files are never modified.
"""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd


# ============================================================
# 1. PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

DEFAULT_INPUT_DIR = (
    PROJECT_ROOT / "data" / "processed" / "edr_new" / "unified" / "group2"
)

DEFAULT_OUTPUT_DIR = DEFAULT_INPUT_DIR / "wide_v2"


# ============================================================
# 2. UTILITIES
# ============================================================

def load_csv(path: Path) -> pd.DataFrame:
    """Read CSV while preserving string values and empty cells."""

    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )


def save_csv(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame with Excel-compatible UTF-8 encoding."""

    df.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
    )


def validate_columns(
    df: pd.DataFrame,
    required_columns: list[str],
    filename: str,
) -> None:
    """Check required columns before processing."""

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{filename} is missing required columns: {missing}"
        )


def slug(text: str) -> str:
    """Convert a source label to a safe column name."""

    result = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(text).lower(),
    ).strip("_")

    return result or "unnamed"


def create_column_names(
    labels: list[str],
    prefix: str,
    reserved_columns: set[str],
) -> dict[str, str]:
    """
    Generate deterministic, unique feature names.

    Different original labels are never intentionally merged.
    """

    names = {}
    used = set(reserved_columns)

    for label in sorted(labels):
        base_name = prefix + slug(label)
        column_name = base_name

        if column_name in used:
            digest = hashlib.sha1(
                label.encode("utf-8")
            ).hexdigest()[:10]

            column_name = f"{base_name}_{digest}"

            suffix = 2
            while column_name in used:
                column_name = f"{base_name}_{digest}_{suffix}"
                suffix += 1

        names[label] = column_name
        used.add(column_name)

    return names


# ============================================================
# 3. WIDE-FORMAT EXPANSION
# ============================================================

def make_wide(
    base: pd.DataFrame,
    source: pd.DataFrame,
    key: str,
    prefix: str,
    level: str,
    provenance: str,
    output_dir: Path,
) -> dict:
    """
    Expand source field labels into wide columns.

    Rules:
    - One output row per existing base row.
    - No many-to-many joins.
    - Blank source values are ignored.
    - Identical repeated values are collapsed.
    - Conflicting nonblank values remain blank.
    - Original source rows remain in evidence files.
    """

    label_col = "field_label_raw"
    value_col = "value_raw"

    base = base.copy()
    source = source.copy()

    validate_columns(
        base,
        [key],
        f"group2_unified_{level}.csv",
    )

    validate_columns(
        source,
        [key, label_col, value_col],
        f"group2_evidence_{provenance}.csv",
    )

    # --------------------------------------------------------
    # 3.1 Validate identifiers
    # --------------------------------------------------------

    if base[key].eq("").any():
        raise ValueError(
            f"Blank identifiers detected in {level}: {key}"
        )

    if base[key].duplicated().any():
        examples = (
            base.loc[base[key].duplicated(), key]
            .head(5)
            .tolist()
        )

        raise ValueError(
            f"Duplicate {key} values in {level}: {examples}"
        )

    source = source[
        source[key].ne("") &
        source[label_col].ne("")
    ].copy()

    # Keep only source rows belonging to the base dataset.
    eligible = source[
        source[key].isin(set(base[key]))
    ].copy()

    labels = eligible[label_col].unique().tolist()

    column_names = create_column_names(
        labels=labels,
        prefix=prefix,
        reserved_columns=set(base.columns),
    )

    # --------------------------------------------------------
    # 3.2 Group measurements
    # --------------------------------------------------------

    grouped = defaultdict(list)

    for entity_id, label, value in eligible[
        [key, label_col, value_col]
    ].itertuples(index=False, name=None):

        grouped[(entity_id, label)].append(value)

    features = defaultdict(dict)
    conflicts = []

    duplicate_pairs = 0
    expanded_values = 0

    for (entity_id, label), values in grouped.items():

        nonblank = sorted({
            value.strip()
            for value in values
            if value.strip()
        })

        if len(values) > 1:
            duplicate_pairs += 1

        if len(nonblank) > 1:

            conflicts.append({
                "table": level,
                "entity_id": entity_id,
                "source_table": provenance,
                "field_label_raw": label,
                "distinct_values_json": json.dumps(
                    nonblank,
                    ensure_ascii=False,
                ),
                "row_count": len(values),
            })

        elif len(nonblank) == 1:

            feature_name = column_names[label]

            features[entity_id][feature_name] = nonblank[0]

            expanded_values += 1

    # --------------------------------------------------------
    # 3.3 Build wide table
    # --------------------------------------------------------

    if features:

        extra = pd.DataFrame.from_dict(
            features,
            orient="index",
        )

        extra.index.name = key

        base = base.merge(
            extra.reset_index(),
            on=key,
            how="left",
            validate="one_to_one",
        )

    # Include every observed label as a column.
    for column in column_names.values():

        if column not in base.columns:
            base[column] = ""

        base[column] = base[column].fillna("")

    # Preserve original column order and sort added features.
    original_columns = [
        col for col in base.columns
        if col not in column_names.values()
    ]

    feature_columns = sorted(column_names.values())

    base = base[
        original_columns + feature_columns
    ]

    # --------------------------------------------------------
    # 3.4 Create complete data dictionary
    # --------------------------------------------------------

    reverse_names = {
        column: label
        for label, column in column_names.items()
    }

    dictionary_rows = []

    identifier_columns = {
        "report_id",
        "record_candidate_id",
        "case_id",
        "vehicle_number",
        "export_basename",
    }

    for column in base.columns:

        is_feature = column in reverse_names

        if is_feature:
            source_table = provenance
            source_label = reverse_names[column]
            definition = f"Original source label: {source_label}"
            role = "candidate_feature_requires_review"
            conflict_policy = (
                "Conflicting nonblank values left blank; "
                "see group2_wide_conflicts.csv"
            )
        else:
            source_table = "previous_unified_table"
            source_label = ""
            definition = (
                "Preserved from Group 2 unified v1. "
                "See the original Group 2 dictionary."
            )
            role = (
                "identifier"
                if column in identifier_columns
                else "context_or_evidence"
            )
            conflict_policy = "preserved"

        dictionary_rows.append({
            "column_name": column,
            "table_level": level,
            "source_table": source_table,
            "source_label_raw": source_label,
            "definition": definition,
            "role": role,
            "nonblank_rows": int(
                base[column].astype(str).str.strip().ne("").sum()
            ),
            "manual_validation": "pending",
            "conflict_policy": conflict_policy,
        })

    dictionary = pd.DataFrame(dictionary_rows)

    # --------------------------------------------------------
    # 3.5 Save outputs
    # --------------------------------------------------------

    wide_path = (
        output_dir /
        f"group2_unified_{level}_wide.csv"
    )

    dictionary_path = (
        output_dir /
        f"group2_{level}_wide_dictionary.csv"
    )

    save_csv(base, wide_path)
    save_csv(dictionary, dictionary_path)

    # --------------------------------------------------------
    # 3.6 Integrity checks
    # --------------------------------------------------------

    if len(dictionary) != len(base.columns):
        raise AssertionError(
            f"Dictionary mismatch for {level}"
        )

    if base[key].duplicated().any():
        raise AssertionError(
            f"Duplicate output identifiers in {level}"
        )

    return {
        "table": level,
        "rows": len(base),
        "total_columns": len(base.columns),
        "wide_feature_columns": len(feature_columns),
        "expanded_nonblank_values": expanded_values,
        "repeated_entity_label_pairs": duplicate_pairs,
        "conflicting_entity_label_pairs": len(conflicts),
        "conflicts": conflicts,
    }


# ============================================================
# 4. MAIN PIPELINE
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description="ABLs Group 2 wide-format expansion"
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Group 2 unified v1 directory",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Group 2 wide v2 output directory",
    )

    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()

    print("\n" + "=" * 60)
    print("ABLs — GROUP 2 WIDE-FORMAT EXPANSION")
    print("=" * 60)

    print(f"Project root : {PROJECT_ROOT}")
    print(f"Input folder : {input_dir}")
    print(f"Output folder: {output_dir}")

    # --------------------------------------------------------
    # 4.1 Load inputs
    # --------------------------------------------------------

    print("\n[1/4] Loading Group 2 unified data...")

    records = load_csv(
        input_dir / "group2_unified_records.csv"
    )

    reports = load_csv(
        input_dir / "group2_unified_reports.csv"
    )

    record_status = load_csv(
        input_dir / "group2_evidence_record_status.csv"
    )

    retrieval_status = load_csv(
        input_dir / "group2_evidence_retrieval_status.csv"
    )

    print(f"  Record candidates: {len(records):,}")
    print(f"  Reports          : {len(reports):,}")
    print(f"  Record status rows: {len(record_status):,}")
    print(f"  Retrieval rows   : {len(retrieval_status):,}")

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # 4.2 Expand records
    # --------------------------------------------------------

    print("\n[2/4] Expanding record-level features...")

    record_result = make_wide(
        base=records,
        source=record_status,
        key="record_candidate_id",
        prefix="status__",
        level="records",
        provenance="record_status",
        output_dir=output_dir,
    )

    print(
        f"  {record_result['rows']:,} rows, "
        f"{record_result['total_columns']:,} columns"
    )

    # --------------------------------------------------------
    # 4.3 Expand reports
    # --------------------------------------------------------

    print("\n[3/4] Expanding report-level features...")

    report_result = make_wide(
        base=reports,
        source=retrieval_status,
        key="report_id",
        prefix="retrieval__",
        level="reports",
        provenance="retrieval_status",
        output_dir=output_dir,
    )

    print(
        f"  {report_result['rows']:,} rows, "
        f"{report_result['total_columns']:,} columns"
    )

    # --------------------------------------------------------
    # 4.4 Save conflict report and summary
    # --------------------------------------------------------

    print("\n[4/4] Saving validation information...")

    all_conflicts = (
        record_result["conflicts"] +
        report_result["conflicts"]
    )

    conflict_columns = [
        "table",
        "entity_id",
        "source_table",
        "field_label_raw",
        "distinct_values_json",
        "row_count",
    ]

    save_csv(
        pd.DataFrame(
            all_conflicts,
            columns=conflict_columns,
        ),
        output_dir / "group2_wide_conflicts.csv",
    )

    summary = {
        "project": "ABLs",
        "group": 2,
        "stage": "wide_v2",
        "input_directory": str(input_dir),
        "output_directory": str(output_dir),
        "tables": [
            {
                k: v
                for k, v in result.items()
                if k != "conflicts"
            }
            for result in [
                record_result,
                report_result,
            ]
        ],
        "total_conflicts": len(all_conflicts),
        "manual_validation": "pending",
        "notes": [
            "Original unified v1 files remain unchanged.",
            "Original evidence files remain unchanged.",
            "Record candidate identity is preserved.",
            "Report-scoped retrieval fields are not assigned to events.",
            "Different source labels are not automatically harmonized.",
            "Conflicting values are documented, not selected arbitrarily.",
            "PDF fields and other evidence are not yet semantically expanded.",
            "Wide columns require manual validation before ML.",
        ],
    }

    summary_path = (
        output_dir / "group2_wide_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("GROUP 2 WIDE EXPANSION COMPLETE")
    print("=" * 60)

    for result in [record_result, report_result]:
        print(
            f"{result['table']}: "
            f"{result['rows']:,} rows, "
            f"{result['total_columns']:,} columns, "
            f"{result['wide_feature_columns']:,} expanded features"
        )

    print(f"\nConflicts: {len(all_conflicts):,}")
    print(f"Outputs  : {output_dir}")
    print("\nNext stage: Group 2 feature review and manual validation.")


# ============================================================
# 5. ENTRY POINT — REQUIRED
# ============================================================

if __name__ == "__main__":
    main()
