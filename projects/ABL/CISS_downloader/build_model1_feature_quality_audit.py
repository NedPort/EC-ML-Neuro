from pathlib import Path

import pandas as pd


def is_present(series: pd.Series) -> pd.Series:
    return (
        series.notna()
        & series.astype("string").str.strip().ne("")
    )


def main() -> None:
    modeling_directory = Path("data/processed/modeling")

    cohort_files = {
        "total_delta_v": (
            "model1_total_delta_v_context_v1.parquet"
        ),
        "longitudinal_delta_v": (
            "model1_longitudinal_delta_v_context_v1.parquet"
        ),
        "lateral_delta_v": (
            "model1_lateral_delta_v_context_v1.parquet"
        ),
        "pdof": (
            "model1_pdof_context_v1.parquet"
        ),
    }

    key_columns = {
        "case_id",
        "vehicle_id",
        "vehicle_number",
        "event_number",
        "vehicle_event_id",
    }

    target_columns = {
        "total_delta_v_kmh",
        "longitudinal_delta_v_kmh",
        "lateral_delta_v_kmh",
        "pdof_degrees",
    }

    rows = []

    for cohort_name, filename in cohort_files.items():
        frame = pd.read_parquet(
            modeling_directory / filename
        )

        predictor_columns = [
            column
            for column in frame.columns
            if column not in key_columns
            and column not in target_columns
        ]

        for column in predictor_columns:
            series = frame[column]
            present = is_present(series)
            present_values = series[present]

            non_null_count = int(present.sum())
            coverage_percent = round(
                100 * non_null_count / len(frame),
                2,
            )

            unique_value_count = int(
                present_values.nunique(dropna=True)
            )

            is_numeric = pd.api.types.is_numeric_dtype(
                series
            )

            if unique_value_count <= 1:
                review_status = "remove_constant"
            elif coverage_percent < 50:
                review_status = "review_low_coverage"
            elif (
                not is_numeric
                and unique_value_count > 15
            ):
                review_status = "review_high_cardinality"
            else:
                review_status = "candidate_for_baseline"

            rows.append(
                {
                    "cohort": cohort_name,
                    "column_name": column,
                    "data_type": str(series.dtype),
                    "is_numeric": is_numeric,
                    "row_count": len(frame),
                    "non_null_count": non_null_count,
                    "missing_count": int(
                        len(frame) - non_null_count
                    ),
                    "coverage_percent": coverage_percent,
                    "unique_value_count": unique_value_count,
                    "review_status": review_status,
                }
            )

    audit = pd.DataFrame(rows).sort_values(
        [
            "cohort",
            "review_status",
            "coverage_percent",
            "column_name",
        ],
        ascending=[True, True, True, True],
    )

    output_path = (
        modeling_directory
        / "model1_context_feature_quality_audit.csv"
    )

    audit.to_csv(output_path, index=False)

    print(f"Created: {output_path}")
    print("\nReview-status counts:")
    print(
        audit.groupby(
            ["cohort", "review_status"]
        )
        .size()
        .to_string()
    )


if __name__ == "__main__":
    main()