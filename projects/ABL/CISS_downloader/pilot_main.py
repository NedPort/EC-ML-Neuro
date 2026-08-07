"""
Command-line entry point for the CISS Stage-2 pilot cohort.
"""

from __future__ import annotations

import argparse

from src.api.client import CISSApi
from src.pilot.case_discovery import CaseDiscovery
from src.pilot.pilot_runner import PilotRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover, register, acquire, and audit "
            "CISS pilot cases."
        )
    )

    parser.add_argument(
        "--data-root",
        default="data",
    )

    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional pilot manifest path",
    )

    parser.add_argument(
        "--initialize",
        action="store_true",
        help=(
            "Create the manifest with development "
            "cases 6028 and 7009"
        ),
    )

    parser.add_argument(
        "--add-case",
        type=int,
        action="append",
        default=[],
        help=(
            "Manually add a CISS case ID; "
            "may be supplied multiple times"
        ),
    )

    discovery_group = parser.add_mutually_exclusive_group()

    discovery_group.add_argument(
        "--discover-cases",
        type=int,
        metavar="COUNT",
        help=(
            "Automatically discover and register COUNT "
            "new CISS case IDs"
        ),
    )

    discovery_group.add_argument(
        "--discover-all",
        action="store_true",
        help=(
            "Discover every available CISS case ID. "
            "This may take considerable time."
        ),
    )

    parser.add_argument(
        "--run",
        action="store_true",
        help="Run pending selected cases",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome without displaying the browser window",
    )

    parser.add_argument(
        "--cleanup-temp",
        action="store_true",
        help=(
            "Remove data/temp/<case_id> only after "
            "the audit contract passes"
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
        help=(
            "Maximum number of pending cases to process "
            "during this run"
        ),
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help=(
            "Rebuild the pilot summary without "
            "downloading cases"
        ),
    )

    return parser


def discover_and_register_cases(
    runner: PilotRunner,
    count: int | None,
    headless: bool,
    data_root: str,
) -> None:
    """
    Discover CISS case IDs and add them to the pilot manifest.
    """

    manifest = runner.initialize_manifest()

    existing_case_ids = {
        int(case_record["case_id"])
        for case_record in manifest["cases"]
    }

    api = CISSApi(headless=headless)

    try:
        discovery = CaseDiscovery(
            driver=api.driver,
            data_root=data_root,
        )

        discovered_ids = discovery.discover(
            limit=count,
            excluded_case_ids=existing_case_ids,
        )

        updated_manifest = runner.add_cases(
            discovered_ids
        )

        print(
            "Pilot manifest updated: "
            f"{runner.manifest_path}"
        )
        print(
            "Registered cases: "
            f"{len(updated_manifest['cases'])}"
        )

    finally:
        api.close()


def main() -> None:
    args = build_parser().parse_args()

    runner = PilotRunner(
        data_root=args.data_root,
        manifest_path=args.manifest,
    )

    action_selected = False

    if args.initialize:
        action_selected = True

        manifest = runner.initialize_manifest()

        print(
            f"Pilot manifest created: "
            f"{runner.manifest_path}"
        )
        print(
            f"Registered cases: "
            f"{len(manifest['cases'])}"
        )

    if args.add_case:
        action_selected = True

        manifest = runner.add_cases(
            args.add_case
        )

        print(
            f"Pilot manifest updated: "
            f"{runner.manifest_path}"
        )
        print(
            f"Registered cases: "
            f"{len(manifest['cases'])}"
        )

    if args.discover_cases is not None:
        action_selected = True

        if args.discover_cases < 1:
            raise SystemExit(
                "--discover-cases must be a positive integer."
            )

        discover_and_register_cases(
            runner=runner,
            count=args.discover_cases,
            headless=args.headless,
            data_root=args.data_root,
        )

    if args.discover_all:
        action_selected = True

        discover_and_register_cases(
            runner=runner,
            count=None,
            headless=args.headless,
            data_root=args.data_root,
        )

    if args.run:
        action_selected = True

        runner.run(
            headless=args.headless,
            cleanup_temp=args.cleanup_temp,
            retry_failed=args.retry_failed,
            limit=args.limit,
        )

    if args.summary:
        action_selected = True

        runner.save_summary()

        print(
            f"Pilot summary created: "
            f"{runner.summary_path}"
        )

    if not action_selected:
        raise SystemExit(
            "Choose at least one action: --initialize, "
            "--add-case, --discover-cases, --discover-all, "
            "--run, or --summary."
        )


if __name__ == "__main__":
    main()