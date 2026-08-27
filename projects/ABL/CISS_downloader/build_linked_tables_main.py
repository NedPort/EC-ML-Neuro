"""
Build canonical linked CISS tables incrementally.

Current stage:
    case_index only
"""

from __future__ import annotations

import argparse

from src.linked_tables.case_index import CaseIndexBuilder


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
            "the index for every audited case."
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

    paths = CaseIndexBuilder(
        arguments.data_root
    ).build(
        case_ids=arguments.case_ids or None,
        output_directory=arguments.output_directory,
    )

    print("Case index completed.")
    print(f"Parquet: {paths.parquet}")
    print(f"Metadata: {paths.metadata}")


if __name__ == "__main__":
    main()