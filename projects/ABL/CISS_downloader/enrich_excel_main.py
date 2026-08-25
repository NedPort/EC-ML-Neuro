"""
Create the Excel-enriched core vehicle-event table.
"""

from __future__ import annotations

import argparse

from src.standardization.excel_core_enricher import (
    ExcelCoreEnricher,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich the metadata-enriched CISS vehicle-event "
            "table using selected export.xlsx worksheets."
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
            "Defaults to data/processed/standardized/"
            "vehicle_event_metadata_enriched.parquet"
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

    paths = ExcelCoreEnricher(
        data_root=arguments.data_root
    ).build(
        input_parquet=arguments.input_parquet,
        output_directory=arguments.output_directory,
    )

    print("Excel enrichment finished.")
    print(f"Rich core table: {paths.parquet}")
    print(f"Coverage report: {paths.metadata}")


if __name__ == "__main__":
    main()