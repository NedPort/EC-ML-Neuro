"""
Build canonical linked CISS tables incrementally.

Current tables:
- case_index
- vehicle_index
"""

from __future__ import annotations

import argparse

from src.linked_tables.case_index import CaseIndexBuilder
from src.linked_tables.vehicle_index import VehicleIndexBuilder
from src.linked_tables.case_vehicle_reconciliation import (
    CaseVehicleCountReconciler,
)
from src.linked_tables.vehicle_event_index import (
    LinkedVehicleEventIndexBuilder,
)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build canonical linked CISS tables."
    )

    parser.add_argument(
        "case_ids",
        metavar="CASE_ID",
        nargs="*",
        type=int,
        help=(
            "Optional CISS case IDs. Omit to build "
            "tables for every audited case."
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
            "Defaults to "
            "data/processed/linked_tables."
        ),
    )

    arguments = parser.parse_args()

    case_ids = arguments.case_ids or None

    case_paths = CaseIndexBuilder(
        arguments.data_root
    ).build(
        case_ids=case_ids,
        output_directory=arguments.output_directory,
    )

    vehicle_paths = VehicleIndexBuilder(
        arguments.data_root
    ).build(
        case_ids=case_ids,
        output_directory=arguments.output_directory,
    )

    reconciliation_paths = CaseVehicleCountReconciler(
        output_directory=arguments.output_directory,
    ).build()

    event_paths = LinkedVehicleEventIndexBuilder(
        data_root=arguments.data_root,
    ).build(
        output_directory=arguments.output_directory,
    )
    print("Linked-table build completed.")

    print(f"Case index: {case_paths.parquet}")
    print(f"Case metadata: {case_paths.metadata}")

    print(f"Vehicle index: {vehicle_paths.parquet}")
    print(f"Vehicle metadata: {vehicle_paths.metadata}")

    print(f"Reconciled case index: {reconciliation_paths['case_index']}")
    print(f"Reconciliation metadata: {reconciliation_paths['metadata']}")

    print(f"Vehicle-event index: {event_paths.parquet}")
    print(f"Vehicle-event metadata: {event_paths.metadata}")
if __name__ == "__main__":
    main()








# """
# Build canonical linked CISS tables incrementally.

# Current stage:
#     case_index only
# """

# from __future__ import annotations

# import argparse

# from src.linked_tables.case_index import CaseIndexBuilder


# def main() -> None:
#     parser = argparse.ArgumentParser(
#         description="Build canonical linked CISS tables."
#     )

#     parser.add_argument(
#         "case_ids",
#         metavar="CASE_ID",
#         nargs="*",
#         type=int,
#         help=(
#             "Optional CISS case IDs. Omit to build "
#             "the index for every audited case."
#         ),
#     )

#     parser.add_argument(
#         "--data-root",
#         default="data",
#         help="Project data directory.",
#     )

#     parser.add_argument(
#         "--output-directory",
#         default=None,
#         help=(
#             "Defaults to "
#             "data/processed/linked_tables."
#         ),
#     )

#     arguments = parser.parse_args()

#     paths = CaseIndexBuilder(
#         arguments.data_root
#     ).build(
#         case_ids=arguments.case_ids or None,
#         output_directory=arguments.output_directory,
#     )

#     print("Case index completed.")
#     print(f"Parquet: {paths.parquet}")
#     print(f"Metadata: {paths.metadata}")


# if __name__ == "__main__":
#     main()