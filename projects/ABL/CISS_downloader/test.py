from pathlib import Path

import pandas as pd


BASE_DIR = Path(
    "data/processed/edr/router_regression_v1"
)

MISMATCH_FILE = BASE_DIR / "destination_mismatches.csv"
UNCLASSIFIED_FILE = BASE_DIR / "newly_unclassified.csv"


def print_section(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


# ============================================================
# Destination mismatches
# ============================================================

mismatch = pd.read_csv(
    MISMATCH_FILE,
    low_memory=False,
)

print_section("DESTINATION MISMATCH OVERVIEW")

print(f"Rows: {len(mismatch):,}")

print("\nColumns:")
for column in mismatch.columns:
    print(f"  - {column}")


# ------------------------------------------------------------
# Expected destination -> actual destination
# ------------------------------------------------------------

if {
    "expected_destination",
    "actual_destination",
}.issubset(mismatch.columns):

    print_section(
        "EXPECTED DESTINATION -> ACTUAL DESTINATION"
    )

    transition_counts = (
        mismatch.groupby(
            [
                "expected_destination",
                "actual_destination",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="count")
        .sort_values(
            "count",
            ascending=False,
        )
    )

    print(
        transition_counts.head(50).to_string(
            index=False
        )
    )

    transition_counts.to_csv(
        BASE_DIR
        / "mismatch_transition_summary.csv",
        index=False,
    )


# ------------------------------------------------------------
# Mismatches by historical/reference group
# ------------------------------------------------------------

if "reference_group" in mismatch.columns:

    print_section(
        "MISMATCHES BY REFERENCE GROUP"
    )

    reference_summary = (
        mismatch["reference_group"]
        .fillna("<missing>")
        .value_counts()
        .rename_axis("reference_group")
        .reset_index(name="count")
    )

    print(
        reference_summary.to_string(
            index=False
        )
    )

    reference_summary.to_csv(
        BASE_DIR
        / "mismatch_by_reference_group.csv",
        index=False,
    )


# ------------------------------------------------------------
# Top problematic labels
# ------------------------------------------------------------

label_column = None

for candidate in [
    "raw_label",
    "label",
]:
    if candidate in mismatch.columns:
        label_column = candidate
        break


if label_column is not None:

    print_section(
        "TOP MISMATCH LABELS"
    )

    label_summary = (
        mismatch[label_column]
        .fillna("<missing>")
        .astype(str)
        .value_counts()
        .rename_axis("label")
        .reset_index(name="count")
    )

    print(
        label_summary.head(100).to_string(
            index=False
        )
    )

    label_summary.to_csv(
        BASE_DIR
        / "mismatch_label_summary.csv",
        index=False,
    )


# ------------------------------------------------------------
# Label + expected + actual routing
# ------------------------------------------------------------

if (
    label_column is not None
    and {
        "expected_destination",
        "actual_destination",
    }.issubset(mismatch.columns)
):

    print_section(
        "TOP LABEL / EXPECTED / ACTUAL PATTERNS"
    )

    pattern_summary = (
        mismatch.groupby(
            [
                label_column,
                "expected_destination",
                "actual_destination",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="count")
        .sort_values(
            "count",
            ascending=False,
        )
    )

    print(
        pattern_summary.head(100).to_string(
            index=False
        )
    )

    pattern_summary.to_csv(
        BASE_DIR
        / "mismatch_pattern_summary.csv",
        index=False,
    )


# ============================================================
# Newly unclassified
# ============================================================

unclassified = pd.read_csv(
    UNCLASSIFIED_FILE,
    low_memory=False,
)

print_section(
    "NEWLY UNCLASSIFIED OVERVIEW"
)

print(
    f"Rows: {len(unclassified):,}"
)


unclassified_label_column = None

for candidate in [
    "raw_label",
    "label",
]:
    if candidate in unclassified.columns:
        unclassified_label_column = candidate
        break


if unclassified_label_column is not None:

    print_section(
        "TOP NEWLY UNCLASSIFIED LABELS"
    )

    unclassified_summary = (
        unclassified[
            unclassified_label_column
        ]
        .fillna("<missing>")
        .astype(str)
        .value_counts()
        .rename_axis("label")
        .reset_index(name="count")
    )

    print(
        unclassified_summary.head(100).to_string(
            index=False
        )
    )

    unclassified_summary.to_csv(
        BASE_DIR
        / "newly_unclassified_label_summary.csv",
        index=False,
    )


print_section(
    "ANALYSIS COMPLETE"
)

print(
    "Summary files written to:"
)
print(BASE_DIR)