from pathlib import Path

from src.modeling.model1_target_cohorts import (
    Model1TargetCohortBuilder,
)


def main() -> None:
    modeling_directory = Path("data/processed/modeling")

    paths = Model1TargetCohortBuilder(
        context_table_path=(
            modeling_directory
            / "model1_context_candidate_v1.parquet"
        ),
    ).build(
        output_directory=modeling_directory,
    )

    print("Model 1 target-specific cohorts created.")
    print(f"Metadata: {paths.metadata}")


if __name__ == "__main__":
    main()