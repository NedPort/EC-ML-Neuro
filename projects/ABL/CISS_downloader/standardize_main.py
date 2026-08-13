"""Create the Stage 3 standardized occupant--vehicle index."""

from __future__ import annotations

import argparse

from src.standardization.occupant_vehicle_index import OccupantVehicleIndexBuilder


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the CISS Stage 3 occupant--vehicle Parquet index."
    )
    parser.add_argument(
        "case_ids",
        metavar="CASE_ID",
        nargs="*",
        type=int,
        help="Optional CISS case IDs. Omit to standardize every audited case.",
    )
    parser.add_argument("--data-root", default="data", help="Project data directory.")
    parser.add_argument(
        "--output-directory",
        default=None,
        help="Defaults to data/processed/standardized.",
    )
    arguments = parser.parse_args()

    paths = OccupantVehicleIndexBuilder(arguments.data_root).build(
        case_ids=arguments.case_ids or None,
        output_directory=arguments.output_directory,
    )
    print(f"Stage 3 table created: {paths.parquet}")
    print(f"Schema and provenance: {paths.metadata}")


if __name__ == "__main__":
    main()
