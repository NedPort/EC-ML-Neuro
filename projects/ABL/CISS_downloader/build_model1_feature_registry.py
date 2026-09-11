from pathlib import Path

from src.modeling.model1_feature_registry import (
    Model1FeatureRegistryBuilder,
)


def main() -> None:
    modeling_directory = Path("data/processed/modeling")

    paths = Model1FeatureRegistryBuilder(
        flat_table_path=(
            modeling_directory
            / "model1_delta_v_pdof_candidate_flat.parquet"
        ),
    ).build(
        output_directory=modeling_directory,
    )

    print("Model 1 feature registry created.")
    print(f"CSV: {paths.csv}")


if __name__ == "__main__":
    main()
    