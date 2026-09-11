from pathlib import Path

from src.modeling.model1_context_view import (
    Model1ContextViewBuilder,
)


def main() -> None:
    modeling_directory = Path("data/processed/modeling")

    paths = Model1ContextViewBuilder(
        flat_table_path=(
            modeling_directory
            / "model1_delta_v_pdof_candidate_flat.parquet"
        ),
    ).build(
        output_directory=modeling_directory,
    )

    print("Model 1 context-only dataset created.")
    print(f"Parquet: {paths.parquet}")
    print(f"Metadata: {paths.metadata}")
    print(f"Feature list: {paths.feature_list}")


if __name__ == "__main__":
    main()