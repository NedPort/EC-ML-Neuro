"""Command-line entry point for the CISS Stage-2 pilot cohort."""

from __future__ import annotations

import argparse

from src.pilot.pilot_runner import PilotRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage sequential acquisition and audit of pilot cases."
    )
    parser.add_argument("--data-root", default="data")
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional pilot manifest path",
    )
    parser.add_argument(
        "--initialize",
        action="store_true",
        help="Create the manifest with development cases 6028 and 7009",
    )
    parser.add_argument(
        "--add-case",
        type=int,
        action="append",
        default=[],
        help="Add a CISS case ID; may be supplied multiple times",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run pending selected cases",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--cleanup-temp",
        action="store_true",
        help=(
            "Remove data/temp/<case_id> only after the audit contract passes"
        ),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry cases previously marked failed",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of pending cases to process this run",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Rebuild the pilot summary without downloading cases",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    runner = PilotRunner(
        data_root=args.data_root,
        manifest_path=args.manifest,
    )

    if args.initialize:
        manifest = runner.initialize_manifest()
        print(f"Pilot manifest created: {runner.manifest_path}")
        print(f"Registered cases: {len(manifest['cases'])}")

    if args.add_case:
        manifest = runner.add_cases(args.add_case)
        print(f"Pilot manifest updated: {runner.manifest_path}")
        print(f"Registered cases: {len(manifest['cases'])}")

    if args.run:
        runner.run(
            headless=args.headless,
            cleanup_temp=args.cleanup_temp,
            retry_failed=args.retry_failed,
            limit=args.limit,
        )

    if args.summary:
        runner.save_summary()
        print(f"Pilot summary created: {runner.summary_path}")

    if not any((args.initialize, args.add_case, args.run, args.summary)):
        raise SystemExit(
            "Choose at least one action: --initialize, --add-case, "
            "--run, or --summary."
        )


if __name__ == "__main__":
    main()
