from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.edr.domains.domain_mapping import (
    get_domain,
    get_domain_name,
)


BASE_DIR = Path(
    "data/processed/edr/router_regression_v1"
)

COMPARISON_FILE = BASE_DIR / "routing_comparison.csv"
MISMATCH_FILE = BASE_DIR / "destination_mismatches.csv"
UNCLASSIFIED_FILE = BASE_DIR / "newly_unclassified.csv"


def add_domain_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add expected/actual conceptual-domain information
    to a regression dataframe.
    """

    out = df.copy()

    out["expected_domain"] = (
        out["expected_destination"]
        .fillna("")
        .map(get_domain)
    )

    out["actual_domain"] = (
        out["actual_destination"]
        .fillna("")
        .map(get_domain)
    )

    out["expected_domain_name"] = (
        out["expected_destination"]
        .fillna("")
        .map(get_domain_name)
    )

    out["actual_domain_name"] = (
        out["actual_destination"]
        .fillna("")
        .map(get_domain_name)
    )

    out["domain_match"] = (
        out["expected_domain"]
        == out["actual_domain"]
    )

    out["exact_group_match"] = (
        out["expected_destination"]
        == out["actual_destination"]
    )

    out["within_domain_reroute"] = (
        (~out["exact_group_match"])
        & out["domain_match"]
    )

    out["cross_domain_mismatch"] = (
        (~out["domain_match"])
        & (
            out["actual_domain"]
            != "unclassified"
        )
    )

    out["domain_unclassified"] = (
        out["actual_domain"]
        == "unclassified"
    )

    return out


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

    # ========================================================
    # Load full historical comparison
    # ========================================================

    comparison = pd.read_csv(
        COMPARISON_FILE,
        low_memory=False,
    )

    comparison = add_domain_columns(
        comparison
    )

    total = len(
        comparison
    )

    exact_matches = int(
        comparison[
            "exact_group_match"
        ].sum()
    )

    domain_matches = int(
        comparison[
            "domain_match"
        ].sum()
    )

    within_domain_reroutes = int(
        comparison[
            "within_domain_reroute"
        ].sum()
    )

    cross_domain_mismatches = int(
        comparison[
            "cross_domain_mismatch"
        ].sum()
    )

    unclassified = int(
        comparison[
            "domain_unclassified"
        ].sum()
    )

    exact_rate = (
        100.0
        * exact_matches
        / total
        if total
        else 0.0
    )

    domain_rate = (
        100.0
        * domain_matches
        / total
        if total
        else 0.0
    )

    # ========================================================
    # Main summary
    # ========================================================

    print_section(
        "CONCEPTUAL DOMAIN REGRESSION SUMMARY"
    )

    print(
        f"Total scalar observations: "
        f"{total:,}"
    )

    print(
        f"Exact extraction-group matches: "
        f"{exact_matches:,}"
    )

    print(
        f"Exact extraction-group agreement: "
        f"{exact_rate:.4f}%"
    )

    print()

    print(
        f"Conceptual-domain matches: "
        f"{domain_matches:,}"
    )

    print(
        f"Conceptual-domain agreement: "
        f"{domain_rate:.4f}%"
    )

    print()

    print(
        f"Within-domain reroutes: "
        f"{within_domain_reroutes:,}"
    )

    print(
        f"Cross-domain mismatches: "
        f"{cross_domain_mismatches:,}"
    )

    print(
        f"Unclassified / non-domain destinations: "
        f"{unclassified:,}"
    )

    # ========================================================
    # Domain transition summary
    # ========================================================

    print_section(
        "EXPECTED DOMAIN -> ACTUAL DOMAIN"
    )

    domain_transitions = (
        comparison.groupby(
            [
                "expected_domain_name",
                "actual_domain_name",
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
        domain_transitions.to_string(
            index=False
        )
    )

    # ========================================================
    # Within-domain reroutes
    # ========================================================

    within = comparison[
        comparison[
            "within_domain_reroute"
        ]
    ].copy()

    print_section(
        "WITHIN-DOMAIN EXTRACTION-PATHWAY REROUTES"
    )

    if len(
        within
    ) == 0:

        print(
            "None."
        )

    else:

        within_summary = (
            within.groupby(
                [
                    "expected_destination",
                    "actual_destination",
                    "expected_domain_name",
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
            within_summary.to_string(
                index=False
            )
        )

    # ========================================================
    # True cross-domain disagreements
    # ========================================================

    cross = comparison[
        comparison[
            "cross_domain_mismatch"
        ]
    ].copy()

    print_section(
        "CROSS-DOMAIN MISMATCHES"
    )

    if len(
        cross
    ) == 0:

        print(
            "None."
        )

    else:

        cross_summary = (
            cross.groupby(
                [
                    "expected_destination",
                    "actual_destination",
                    "expected_domain_name",
                    "actual_domain_name",
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
            cross_summary.head(
                100
            ).to_string(
                index=False
            )
        )

    # ========================================================
    # Top cross-domain labels
    # ========================================================

    label_column = None

    for candidate in [
        "raw_label",
        "label",
    ]:

        if candidate in cross.columns:
            label_column = candidate
            break

    if (
        label_column is not None
        and len(cross) > 0
    ):

        print_section(
            "TOP CROSS-DOMAIN LABELS"
        )

        top_labels = (
            cross[
                label_column
            ]
            .fillna(
                "<missing>"
            )
            .astype(
                str
            )
            .value_counts()
            .rename_axis(
                "label"
            )
            .reset_index(
                name="count"
            )
        )

        print(
            top_labels.head(
                100
            ).to_string(
                index=False
            )
        )

    # ========================================================
    # Save enriched outputs
    # ========================================================

    comparison.to_csv(
        BASE_DIR
        / "comparison_with_domains.csv",
        index=False,
    )

    domain_transitions.to_csv(
        BASE_DIR
        / "domain_transition_summary.csv",
        index=False,
    )

    within.to_csv(
        BASE_DIR
        / "within_domain_reroutes.csv",
        index=False,
    )

    cross.to_csv(
        BASE_DIR
        / "cross_domain_mismatches.csv",
        index=False,
    )

    # ========================================================
    # Final status
    # ========================================================

    print_section(
        "DOMAIN REGRESSION COMPLETE"
    )

    print(
        "Outputs written to:"
    )

    print(
        BASE_DIR
    )


if __name__ == "__main__":
    main()