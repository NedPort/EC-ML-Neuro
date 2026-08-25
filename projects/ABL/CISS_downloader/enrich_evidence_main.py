"""
Create the audit/asset/tree enriched CISS vehicle-event table.
"""

from __future__ import annotations

import argparse

from src.standardization.audit_asset_tree_enricher import (
    AuditAssetTreeEnricher,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Enrich the CISS rich-core vehicle-event table with "
            "audit, asset, and navigation-tree evidence metadata."
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
            "vehicle_event_rich_core.parquet"
        ),
    )

    parser.add_argument(
        "--output-directory",
        default=None,
        help=(
            "Defaults to the directory containing the input Parquet."
        ),
    )

    arguments = parser.parse_args()

    paths = AuditAssetTreeEnricher(
        data_root=arguments.data_root,
    ).build(
        input_parquet=arguments.input_parquet,
        output_directory=arguments.output_directory,
    )

    print(f"Evidence-enriched table: {paths.parquet}")
    print(f"Evidence metadata: {paths.metadata}")


if __name__ == "__main__":
    main()