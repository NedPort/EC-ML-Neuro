"""Command-line entry point for the final Stage-2 characterization."""

from __future__ import annotations

import argparse

from src.pilot.dataset_characterization import DatasetCharacterizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create the final CISS Stage-2 dataset "
            "characterization report."
        )
    )
    parser.add_argument(
        "--data-root",
        default="data",
        help="Root data directory",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Optional pilot_audit_summary.json path",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output JSON path",
    )
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    characterizer = DatasetCharacterizer(
        data_root=arguments.data_root,
        summary_path=arguments.summary,
        output_path=arguments.output,
    )
    characterizer.build_and_save()


if __name__ == "__main__":
    main()
