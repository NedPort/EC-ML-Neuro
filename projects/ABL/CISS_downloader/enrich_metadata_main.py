"""
Create the metadata-enriched vehicle-event table.
"""

from __future__ import annotations

import argparse

from src.standardization.metadata_enricher import (
    MetadataEnricher,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich vehicle_event_index.parquet "
            "with CISS metadata.json fields."
        )
    )

    parser.add_argument(
        "--data-root",
        default="data",
        help="Project data directory.",
    )

    parser.add_argument(
        "--input-parquet",
        default=None,
        help=(
            "Defaults to "
            "data/processed/standardized/"
            "vehicle_event_index.parquet"
        ),
    )

    parser.add_argument(
        "--output-directory",
        default=None,
        help=(
            "Defaults to the directory containing "
            "the input Parquet file."
        ),
    )

    arguments = parser.parse_args()

    paths = MetadataEnricher(
        data_root=arguments.data_root
    ).build(
        input_parquet=arguments.input_parquet,
        output_directory=arguments.output_directory,
    )

    print("Metadata enrichment finished.")
    print(f"Enriched table: {paths.parquet}")
    print(f"Coverage report: {paths.metadata}")


if __name__ == "__main__":
    main()