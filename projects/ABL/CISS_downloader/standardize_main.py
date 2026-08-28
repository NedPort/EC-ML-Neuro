"""Create Stage 3 standardized CISS indices."""

from __future__ import annotations

import argparse

from src.standardization.occupant_vehicle_index import (
    OccupantVehicleIndexBuilder,
)
from CISS_downloader.src.linked_tables.vehicle_event_index import (
    VehicleEventIndexBuilder,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build Stage 3 standardized CISS Parquet indices."
        )
    )

    parser.add_argument(
        "case_ids",
        metavar="CASE_ID",
        nargs="*",
        type=int,
        help=(
            "Optional CISS case IDs. Omit to standardize "
            "every audited case."
        ),
    )

    parser.add_argument(
        "--data-root",
        default="data",
        help="Project data directory.",
    )

    parser.add_argument(
        "--output-directory",
        default=None,
        help=(
            "Defaults to data/processed/standardized."
        ),
    )

    arguments = parser.parse_args()

    case_ids = arguments.case_ids or None

    occupant_paths = OccupantVehicleIndexBuilder(
        arguments.data_root
    ).build(
        case_ids=case_ids,
        output_directory=arguments.output_directory,
    )

    vehicle_event_paths = VehicleEventIndexBuilder(
        arguments.data_root
    ).build(
        case_ids=case_ids,
        output_directory=arguments.output_directory,
    )

    print("Stage 3 standardization completed.")
    print(
        f"Occupant--vehicle index: "
        f"{occupant_paths.parquet}"
    )
    print(
        f"Vehicle--event index: "
        f"{vehicle_event_paths.parquet}"
    )
    print(
        f"Vehicle--event metadata: "
        f"{vehicle_event_paths.metadata}"
    )


if __name__ == "__main__":
    main()