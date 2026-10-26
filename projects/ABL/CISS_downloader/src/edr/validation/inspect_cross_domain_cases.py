from __future__ import annotations

from pathlib import Path

import pandas as pd


BASE_DIR = Path(
    "data/processed/edr/router_regression_v1"
)

INPUT_FILE = (
    BASE_DIR
    / "cross_domain_mismatches.csv"
)

OUTPUT_DIR = (
    BASE_DIR
    / "cross_domain_review"
)


# ============================================================
# Cases we actually want to inspect
# ============================================================

TARGET_PATTERNS = {
    "time_from_precrash_to_trg":
        r"time from pre-crash to trg",

    "restraint_deployment_signal":
        r"restraint deployment signal received",

    "occupant_size_classification":
        r"occupant size classification",

    "events_recovered":
        r"event\(s\) recovered|events recovered",
}


def print_section(
    title: str,
) -> None:

    print(
        "\n"
        + "=" * 90
    )

    print(title)

    print(
        "=" * 90
    )


def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = pd.read_csv(
        INPUT_FILE,
        low_memory=False,
    )

    print_section(
        "CROSS-DOMAIN REVIEW"
    )

    print(
        f"Total cross-domain rows: "
        f"{len(df):,}"
    )

    print()

    print(
        "Expected -> actual:"
    )

    transition_summary = (
        df.groupby(
            [
                "expected_destination",
                "actual_destination",
            ],
            dropna=False,
        )
        .size()
        .reset_index(
            name="count"
        )
        .sort_values(
            "count",
            ascending=False,
        )
    )

    print(
        transition_summary.to_string(
            index=False
        )
    )

    # ========================================================
    # Extract the small targeted patterns
    # ========================================================

    review_frames = []

    for (
        review_name,
        pattern,
    ) in TARGET_PATTERNS.items():

        mask = (
            df["raw_label"]
            .fillna("")
            .astype(str)
            .str.contains(
                pattern,
                case=False,
                regex=True,
                na=False,
            )
        )

        subset = (
            df.loc[
                mask
            ]
            .copy()
        )

        subset[
            "review_category"
        ] = review_name

        review_frames.append(
            subset
        )

        print_section(
            review_name.upper()
        )

        print(
            f"Rows: "
            f"{len(subset):,}"
        )

        if len(
            subset
        ) == 0:

            continue

        useful_columns = [
            column
            for column
            in [
                "reference_group",
                "reference_file",
                "report_id",
                "case_id",
                "vehicle_number",
                "source_format",
                "source_location",
                "section_context",
                "raw_label",
                "raw_value",
                "expected_destination",
                "actual_destination",
                "expected_family",
                "actual_family",
                "matched_by",
                "confidence",
                "reason",
                "review_reason",
            ]
            if column
            in subset.columns
        ]

        print(
            subset[
                useful_columns
            ]
            .head(
                50
            )
            .to_string(
                index=False
            )
        )

        subset.to_csv(
            OUTPUT_DIR
            / f"{review_name}.csv",
            index=False,
        )

    # ========================================================
    # Combined targeted review
    # ========================================================

    if review_frames:

        targeted = pd.concat(
            review_frames,
            ignore_index=True,
        )

        targeted = (
            targeted
            .drop_duplicates()
        )

    else:

        targeted = pd.DataFrame()

    targeted.to_csv(
        OUTPUT_DIR
        / "targeted_cross_domain_review.csv",
        index=False,
    )

    # ========================================================
    # Remaining large cross-domain cases
    #
    # These are intentionally separated because most are
    # Group 2 -> Group 6 technical/readout migrations.
    # ========================================================

    if len(
        targeted
    ) > 0:

        targeted_indices = set(
            targeted.index
        )

        # Safer selection based on target patterns again.
        target_mask = pd.Series(
            False,
            index=df.index,
        )

        for pattern in TARGET_PATTERNS.values():

            target_mask |= (
                df["raw_label"]
                .fillna("")
                .astype(str)
                .str.contains(
                    pattern,
                    case=False,
                    regex=True,
                    na=False,
                )
            )

        remaining = (
            df.loc[
                ~target_mask
            ]
            .copy()
        )

    else:

        remaining = df.copy()

    remaining.to_csv(
        OUTPUT_DIR
        / "remaining_cross_domain_cases.csv",
        index=False,
    )

    # ========================================================
    # Label summary for remaining cases
    # ========================================================

    remaining_labels = (
        remaining[
            "raw_label"
        ]
        .fillna(
            "<missing>"
        )
        .astype(str)
        .value_counts()
        .rename_axis(
            "raw_label"
        )
        .reset_index(
            name="count"
        )
    )

    remaining_labels.to_csv(
        OUTPUT_DIR
        / "remaining_label_summary.csv",
        index=False,
    )

    print_section(
        "REMAINING CROSS-DOMAIN LABELS"
    )

    print(
        remaining_labels.head(
            100
        ).to_string(
            index=False
        )
    )

    # ========================================================
    # Final
    # ========================================================

    print_section(
        "REVIEW COMPLETE"
    )

    print(
        "Outputs written to:"
    )

    print(
        OUTPUT_DIR
    )


if __name__ == "__main__":
    main()