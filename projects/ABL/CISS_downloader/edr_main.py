"""
EDR-focused CISS acquisition workflow.

The workflow:
1. Discovers ordinary CISS case IDs.
2. Downloads only metadata and navigation-tree records first.
3. Uses evCdc[].edrObtained == 1 as the EDR-candidate rule.
4. Downloads the complete ZIP only for metadata-positive candidates.
5. Keeps the complete extracted package.
6. Deletes only the ZIP archive after successful extraction/validation.
7. Confirms CDRX presence from the extracted files.

Example:
    uv run python edr_main.py --target-cdrx 10 --max-cases-scanned 200

This means:
    Keep screening cases until 10 NEW cases containing CDRX files
    are confirmed, or until 200 ordinary CISS cases have been screened.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.api.client import CISSApi
from src.pilot.case_discovery import CaseDiscovery
from src.pipeline.case_processor import CaseProcessor


DEFAULT_MANIFEST_PATH = Path("data/manifests/edr_cases.json")
DEFAULT_LEDGER_PATH = Path(
    "data/processed/edr/edr_acquisition_attempts.csv"
)
DEFAULT_SUMMARY_PATH = Path(
    "data/processed/edr/edr_acquisition_summary.json"
)


def utc_now() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def save_json_atomic(data: Any, output_path: Path) -> None:
    """Write JSON through a temporary file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = output_path.with_suffix(
        output_path.suffix + ".part"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        json.dump(
            data,
            output_file,
            indent=2,
            ensure_ascii=False,
        )

    temporary_path.replace(output_path)


def load_json_or_none(input_path: Path) -> dict[str, Any] | None:
    """Load a non-empty JSON object, otherwise return None."""
    if not input_path.is_file():
        return None

    try:
        with input_path.open(
            "r",
            encoding="utf-8",
        ) as input_file:
            data = json.load(input_file)

        if isinstance(data, dict) and data:
            return data

    except (OSError, json.JSONDecodeError):
        pass

    return None


def find_cdrx_files(extracted_directory: Path) -> list[Path]:
    """Find every CDRX file in a complete extracted CISS archive."""
    if not extracted_directory.is_dir():
        return []

    return sorted(
        path
        for path in extracted_directory.rglob("*")
        if path.is_file()
        and path.suffix.casefold() == ".cdrx"
    )


def metadata_has_edr_obtained(metadata: dict[str, Any]) -> bool:
    """
    Return True when any event-level CDC record reports edrObtained == 1.

    This is the EDR eligibility rule. ZIP/CDRX inspection remains the
    final confirmation that an actual CDRX file is present.
    """
    ev_cdc = metadata.get("evCdc", [])

    if isinstance(ev_cdc, dict):
        ev_cdc = [ev_cdc]

    if not isinstance(ev_cdc, list):
        return False

    for event_record in ev_cdc:
        if not isinstance(event_record, dict):
            continue

        value = event_record.get("edrObtained")

        try:
            if int(value) == 1:
                return True
        except (TypeError, ValueError):
            continue

    return False


def get_existing_raw_case_ids(data_root: Path) -> set[int]:
    """
    Return all case IDs that already have a raw package directory.

    This prevents normal historical cases from being rediscovered and
    accidentally reprocessed by the EDR-only workflow.
    """
    raw_root = data_root / "raw"

    if not raw_root.is_dir():
        return set()

    case_ids: set[int] = set()

    for path in raw_root.iterdir():
        if not path.is_dir():
            continue

        try:
            case_ids.add(int(path.name))
        except ValueError:
            continue

    return case_ids


class EdrRunner:
    """Discover, screen, acquire, and inventory EDR-related CISS cases."""

    def __init__(
        self,
        data_root: str = "data",
        manifest_path: str | None = None,
    ) -> None:
        self.data_root = Path(data_root)

        self.manifest_path = (
            Path(manifest_path)
            if manifest_path
            else self.data_root / "manifests" / "edr_cases.json"
        )

        self.ledger_path = (
            self.data_root
            / "processed"
            / "edr"
            / "edr_acquisition_attempts.csv"
        )

        self.summary_path = (
            self.data_root
            / "processed"
            / "edr"
            / "edr_acquisition_summary.json"
        )

    def _empty_manifest(self) -> dict[str, Any]:
        return {
            "created_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "purpose": (
                "EDR-focused acquisition. Metadata is screened first; "
                "complete ZIP archives are downloaded only when "
                "evCdc[].edrObtained == 1."
            ),
            "cases": [],
        }

    def load_manifest(self) -> dict[str, Any]:
        """Load the EDR manifest, creating an in-memory empty version."""
        manifest = load_json_or_none(self.manifest_path)

        if manifest is None:
            return self._empty_manifest()

        if not isinstance(manifest.get("cases"), list):
            manifest["cases"] = []

        return manifest

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        """Save the EDR manifest."""
        manifest["updated_at_utc"] = utc_now()
        save_json_atomic(manifest, self.manifest_path)

    def get_case_record(
        self,
        manifest: dict[str, Any],
        case_id: int,
    ) -> dict[str, Any] | None:
        """Return one manifest record by case ID."""
        for record in manifest["cases"]:
            if int(record["case_id"]) == int(case_id):
                return record

        return None

    def register_case_ids(
        self,
        case_ids: list[int],
    ) -> list[int]:
        """Add newly discovered generic CISS IDs to the EDR manifest."""
        manifest = self.load_manifest()

        existing_ids = {
            int(record["case_id"])
            for record in manifest["cases"]
        }

        registered_ids: list[int] = []

        for case_id in case_ids:
            case_id = int(case_id)

            if case_id in existing_ids:
                continue

            manifest["cases"].append(
                {
                    "case_id": case_id,
                    "registered_at_utc": utc_now(),
                    "status": "discovered",
                    "metadata_edr_obtained": None,
                    "cdrx_file_count": None,
                    "cdrx_source_paths": [],
                    "error_message": "",
                }
            )

            existing_ids.add(case_id)
            registered_ids.append(case_id)

        self.save_manifest(manifest)

        return registered_ids

    def discover_and_register(
        self,
        count: int,
        headless: bool,
    ) -> list[int]:
        """
        Discover ordinary CISS case IDs and register only IDs not already
        represented in the raw data directory or the EDR manifest.
        """
        if count < 1:
            raise ValueError("Discovery count must be positive.")

        manifest = self.load_manifest()

        manifest_case_ids = {
            int(record["case_id"])
            for record in manifest["cases"]
        }

        existing_raw_case_ids = get_existing_raw_case_ids(
            self.data_root
        )

        excluded_case_ids = (
            manifest_case_ids
            | existing_raw_case_ids
        )

        api = CISSApi(headless=headless)

        try:
            discovery = CaseDiscovery(
                driver=api.driver,
                data_root=str(self.data_root),
            )

            discovered_ids = discovery.discover(
                limit=count,
                excluded_case_ids=excluded_case_ids,
            )

        finally:
            api.close()

        registered_ids = self.register_case_ids(
            [int(case_id) for case_id in discovered_ids]
        )

        print(
            "New ordinary CISS cases registered for "
            f"EDR screening: {len(registered_ids)}"
        )

        return registered_ids

    def _paths_for_case(
        self,
        case_id: int,
    ) -> dict[str, Path]:
        """Return the standard raw and temporary paths for one case."""
        case_id = int(case_id)

        raw_directory = self.data_root / "raw" / str(case_id)
        temporary_directory = (
            self.data_root / "temp" / str(case_id)
        )

        return {
            "raw_directory": raw_directory,
            "temporary_directory": temporary_directory,
            "metadata_path": raw_directory / "metadata.json",
            "tree_path": raw_directory / "navigation_tree.json",
            "package_manifest_path": raw_directory / "manifest.json",
            "archive_path": (
                temporary_directory / f"case_{case_id}.zip"
            ),
            "extracted_directory": (
                temporary_directory / "extracted"
            ),
        }

    def _write_ledger_row(
        self,
        *,
        case_id: int,
        status: str,
        metadata_edr_obtained: bool | None,
        cdrx_file_count: int | None,
        cdrx_source_paths: list[Path],
        archive_deleted: bool,
        error_message: str,
    ) -> None:
        """Append one durable processing result to the EDR ledger."""
        self.ledger_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        row = {
            "attempted_at_utc": utc_now(),
            "case_id": case_id,
            "status": status,
            "metadata_edr_obtained": metadata_edr_obtained,
            "cdrx_file_count": cdrx_file_count,
            "cdrx_source_paths_json": json.dumps(
                [str(path) for path in cdrx_source_paths]
            ),
            "archive_deleted": archive_deleted,
            "error_message": error_message,
        }

        write_header = not self.ledger_path.exists()

        with self.ledger_path.open(
            "a",
            newline="",
            encoding="utf-8",
        ) as output_file:
            writer = csv.DictWriter(
                output_file,
                fieldnames=list(row.keys()),
            )

            if write_header:
                writer.writeheader()

            writer.writerow(row)

    def _update_record(
        self,
        case_id: int,
        *,
        status: str,
        metadata_edr_obtained: bool | None,
        cdrx_files: list[Path],
        error_message: str,
    ) -> None:
        """Update one record in the persistent EDR manifest."""
        manifest = self.load_manifest()
        record = self.get_case_record(manifest, case_id)

        if record is None:
            raise RuntimeError(
                f"Case {case_id} is missing from the EDR manifest."
            )

        record["status"] = status
        record["updated_at_utc"] = utc_now()
        record["metadata_edr_obtained"] = metadata_edr_obtained
        record["cdrx_file_count"] = len(cdrx_files)
        record["cdrx_source_paths"] = [
            str(path)
            for path in cdrx_files
        ]
        record["error_message"] = error_message

        self.save_manifest(manifest)

    def process_case(
        self,
        *,
        processor: CaseProcessor,
        case_id: int,
    ) -> str:
        """
        Screen and process one EDR candidate.

        Metadata-negative cases keep only metadata/navigation-tree records.
        Metadata-positive cases receive the ordinary complete CISS package.
        """
        case_id = int(case_id)
        paths = self._paths_for_case(case_id)

        metadata_edr_obtained: bool | None = None
        cdrx_files: list[Path] = []
        archive_deleted = False
        status = "failed"
        error_message = ""

        try:
            paths["raw_directory"].mkdir(
                parents=True,
                exist_ok=True,
            )

            metadata = load_json_or_none(
                paths["metadata_path"]
            )

            if metadata is None:
                processor.case_downloader.save_case_records(
                    case_id=case_id,
                    output_directory=paths["raw_directory"],
                )

                metadata = load_json_or_none(
                    paths["metadata_path"]
                )

            if metadata is None:
                raise RuntimeError(
                    "metadata.json could not be retrieved or parsed."
                )

            metadata_edr_obtained = metadata_has_edr_obtained(
                metadata
            )

            if not metadata_edr_obtained:
                status = "metadata_no_edr_candidate"

                self._update_record(
                    case_id,
                    status=status,
                    metadata_edr_obtained=False,
                    cdrx_files=[],
                    error_message="",
                )

                self._write_ledger_row(
                    case_id=case_id,
                    status=status,
                    metadata_edr_obtained=False,
                    cdrx_file_count=0,
                    cdrx_source_paths=[],
                    archive_deleted=False,
                    error_message="",
                )

                print(
                    f"Case {case_id}: metadata does not indicate "
                    "EDR was obtained. Full ZIP not downloaded."
                )

                return status

            package_manifest = load_json_or_none(
                paths["package_manifest_path"]
            )

            package_is_valid = (
                package_manifest is not None
                and package_manifest.get("status")
                == "ready_for_semantic_processing"
                and paths["extracted_directory"].is_dir()
            )

            if package_is_valid:
                print(
                    f"Case {case_id}: existing validated package found."
                )
            else:
                processor.process_case(case_id)

                package_manifest = load_json_or_none(
                    paths["package_manifest_path"]
                )

                if (
                    package_manifest is None
                    or package_manifest.get("status")
                    != "ready_for_semantic_processing"
                ):
                    raise RuntimeError(
                        "The full CISS package did not pass final "
                        "validation."
                    )

            cdrx_files = find_cdrx_files(
                paths["extracted_directory"]
            )

            # Delete only the ZIP after the package is fully extracted
            # and validated. The extracted contents are retained.
            if paths["archive_path"].is_file():
                paths["archive_path"].unlink()
                archive_deleted = True

            if cdrx_files:
                status = "cdrx_confirmed"
            else:
                status = "metadata_positive_no_cdrx"

            self._update_record(
                case_id,
                status=status,
                metadata_edr_obtained=True,
                cdrx_files=cdrx_files,
                error_message="",
            )

            self._write_ledger_row(
                case_id=case_id,
                status=status,
                metadata_edr_obtained=True,
                cdrx_file_count=len(cdrx_files),
                cdrx_source_paths=cdrx_files,
                archive_deleted=archive_deleted,
                error_message="",
            )

            print(
                f"Case {case_id}: {status}; "
                f"CDRX files found: {len(cdrx_files)}"
            )

            return status

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: {error}"
            )

            self._update_record(
                case_id,
                status="failed",
                metadata_edr_obtained=metadata_edr_obtained,
                cdrx_files=cdrx_files,
                error_message=error_message,
            )

            self._write_ledger_row(
                case_id=case_id,
                status="failed",
                metadata_edr_obtained=metadata_edr_obtained,
                cdrx_file_count=(
                    len(cdrx_files)
                    if cdrx_files
                    else None
                ),
                cdrx_source_paths=cdrx_files,
                archive_deleted=archive_deleted,
                error_message=error_message,
            )

            print(f"Case {case_id} failed: {error_message}")

            return "failed"

    def run_case_ids(
        self,
        *,
        case_ids: list[int],
        headless: bool,
    ) -> Counter:
        """Process specific EDR-manifest case IDs in one browser session."""
        status_counts: Counter = Counter()

        if not case_ids:
            return status_counts

        api = CISSApi(headless=headless)

        try:
            processor = CaseProcessor(
                api=api,
                data_root=str(self.data_root),
            )

            for index, case_id in enumerate(case_ids, start=1):
                print()
                print(
                    f"EDR candidate {index}/{len(case_ids)}: "
                    f"CISS {case_id}"
                )

                status = self.process_case(
                    processor=processor,
                    case_id=int(case_id),
                )

                status_counts[status] += 1

        finally:
            api.close()

        return status_counts

    def run_pending(
        self,
        *,
        headless: bool,
        limit: int | None,
        retry_failed: bool,
    ) -> Counter:
        """
        Process pending EDR candidates.

        Here --limit means the number of ordinary CISS candidates screened,
        not the number of final CDRX-confirmed cases.
        """
        manifest = self.load_manifest()

        eligible_statuses = {"discovered"}

        if retry_failed:
            eligible_statuses.add("failed")

        pending_ids = [
            int(record["case_id"])
            for record in manifest["cases"]
            if record.get("status") in eligible_statuses
        ]

        if limit is not None:
            pending_ids = pending_ids[:limit]

        if not pending_ids:
            print("No pending EDR candidates were found.")
            return Counter()

        return self.run_case_ids(
            case_ids=pending_ids,
            headless=headless,
        )

    def confirmed_cdrx_case_ids(self) -> set[int]:
        """Return all manifest cases currently confirmed to contain CDRX."""
        manifest = self.load_manifest()

        return {
            int(record["case_id"])
            for record in manifest["cases"]
            if record.get("status") == "cdrx_confirmed"
        }

    def run_to_target(
        self,
        *,
        target_cdrx: int,
        max_cases_scanned: int,
        headless: bool,
    ) -> None:
        """
        Discover and screen cases until target_cdrx NEW CDRX-confirmed
        cases have been acquired, or max_cases_scanned is reached.

        Stops immediately after the requested number of confirmed CDRX
        cases is reached; it does not finish an entire discovery batch.
        """
        if target_cdrx < 1:
            raise ValueError("--target-cdrx must be positive.")

        if max_cases_scanned < target_cdrx:
            raise ValueError(
                "--max-cases-scanned must be at least --target-cdrx."
            )

        initial_confirmed_ids = self.confirmed_cdrx_case_ids()
        new_confirmed_ids: set[int] = set()
        screened_count = 0
        discovery_batch_size = 25

        while (
            len(new_confirmed_ids) < target_cdrx
            and screened_count < max_cases_scanned
        ):
            remaining_capacity = (
                max_cases_scanned - screened_count
            )

            discovery_count = min(
                discovery_batch_size,
                remaining_capacity,
            )

            print()
            print(
                f"Discovering up to {discovery_count} "
                "ordinary CISS cases..."
            )

            registered_ids = self.discover_and_register(
                count=discovery_count,
                headless=headless,
            )

            if not registered_ids:
                print(
                    "No additional eligible CISS IDs were discovered."
                )
                break

            api = CISSApi(headless=headless)

            try:
                processor = CaseProcessor(
                    api=api,
                    data_root=str(self.data_root),
                )

                for case_id in registered_ids:
                    if len(new_confirmed_ids) >= target_cdrx:
                        break

                    screened_count += 1

                    print()
                    print(
                        f"EDR candidate {screened_count}/"
                        f"{max_cases_scanned}: CISS {case_id}"
                    )

                    self.process_case(
                        processor=processor,
                        case_id=int(case_id),
                    )

                    confirmed_now = self.confirmed_cdrx_case_ids()

                    new_confirmed_ids = (
                        confirmed_now - initial_confirmed_ids
                    )

                    print(
                        "Target progress: "
                        f"{len(new_confirmed_ids)}/{target_cdrx} "
                        "new CDRX-confirmed cases"
                    )

                    if len(new_confirmed_ids) >= target_cdrx:
                        print(
                            "Requested CDRX target reached. "
                            "Stopping immediately."
                        )
                        break

            finally:
                api.close()

        self.save_summary(
            extra_summary={
                "target_cdrx": target_cdrx,
                "new_cdrx_confirmed": len(new_confirmed_ids),
                "new_cdrx_confirmed_case_ids": sorted(
                    new_confirmed_ids
                ),
                "ordinary_cases_screened_in_target_run": (
                    screened_count
                ),
                "max_cases_scanned": max_cases_scanned,
            }
        )

        print()
        print("EDR target run complete.")
        print(
            f"New CDRX-confirmed cases: "
            f"{len(new_confirmed_ids)}/{target_cdrx}"
        )
        print(
            f"Ordinary cases screened: "
            f"{screened_count}/{max_cases_scanned}"
        )
        print(f"Manifest: {self.manifest_path}")
        print(f"Ledger: {self.ledger_path}")
        print(f"Summary: {self.summary_path}")


    def save_summary(
            self,
            extra_summary: dict[str, Any] | None = None,
        ) -> None:
            """Build a current EDR acquisition summary."""
            manifest = self.load_manifest()

            status_counts = Counter(
                record.get("status", "unknown")
                for record in manifest["cases"]
            )

            summary: dict[str, Any] = {
                "created_at_utc": utc_now(),
                "registered_case_count": len(manifest["cases"]),
                "status_counts": dict(
                    sorted(status_counts.items())
                ),
                "cdrx_confirmed_case_ids": sorted(
                    self.confirmed_cdrx_case_ids()
                ),
                "manifest_path": str(self.manifest_path),
                "ledger_path": str(self.ledger_path),
            }

            if extra_summary:
                summary.update(extra_summary)

            save_json_atomic(summary, self.summary_path)

            print()
            print("EDR acquisition complete.")
            print(
                f"Registered cases: "
                f"{summary['registered_case_count']}"
            )
            print("Status counts:")

            for status, count in sorted(
                status_counts.items()
            ):
                print(f"  {status}: {count}")

            print(f"Manifest: {self.manifest_path}")
            print(f"Ledger: {self.ledger_path}")
            print(f"Summary: {self.summary_path}")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface."""
    parser = argparse.ArgumentParser(
        description=(
            "Acquire CISS cases using metadata-first EDR screening."
        )
    )

    parser.add_argument(
        "--data-root",
        default="data",
        help="Project data directory (default: data).",
    )

    parser.add_argument(
        "--manifest",
        default=None,
        help=(
            "Optional EDR manifest path. Default: "
            "data/manifests/edr_cases.json"
        ),
    )

    parser.add_argument(
        "--add-case",
        type=int,
        action="append",
        default=[],
        help=(
            "Manually add a case ID for EDR screening. "
            "May be supplied multiple times."
        ),
    )

    discovery_group = parser.add_mutually_exclusive_group()

    discovery_group.add_argument(
        "--discover-cases",
        type=int,
        metavar="COUNT",
        help=(
            "Discover COUNT ordinary CISS cases for later "
            "metadata-first EDR screening."
        ),
    )

    discovery_group.add_argument(
        "--discover-all",
        action="store_true",
        help=(
            "Discover all available ordinary CISS cases. "
            "Use with caution."
        ),
    )

    parser.add_argument(
        "--run",
        action="store_true",
        help=(
            "Screen pending EDR candidates. With --limit, the limit "
            "means ordinary candidates screened, not CDRX cases."
        ),
    )

    parser.add_argument(
        "--target-cdrx",
        type=int,
        default=None,
        metavar="COUNT",
        help=(
            "Discover and process cases until COUNT NEW "
            "ZIP-confirmed CDRX cases are acquired."
        ),
    )

    parser.add_argument(
        "--max-cases-scanned",
        type=int,
        default=200,
        metavar="COUNT",
        help=(
            "Maximum ordinary CISS cases screened during "
            "--target-cdrx (default: 200)."
        ),
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome without showing the browser window.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum pending ordinary candidates to screen "
            "with --run."
        ),
    )

    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Include failed EDR candidates in --run.",
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help="Rebuild the EDR summary without downloading cases.",
    )

    return parser


def main() -> None:
    """Run the selected EDR workflow action."""
    args = build_parser().parse_args()

    if args.target_cdrx is not None:
        conflicting_actions = (
            args.add_case
            or args.discover_cases is not None
            or args.discover_all
            or args.run
        )

        if conflicting_actions:
            raise SystemExit(
                "--target-cdrx cannot be combined with --add-case, "
                "--discover-cases, --discover-all, or --run."
            )

    runner = EdrRunner(
        data_root=args.data_root,
        manifest_path=args.manifest,
    )

    action_selected = False

    if args.add_case:
        action_selected = True

        registered_ids = runner.register_case_ids(
            args.add_case
        )

        print(
            f"New manually registered EDR candidates: "
            f"{len(registered_ids)}"
        )

    if args.discover_cases is not None:
        action_selected = True

        if args.discover_cases < 1:
            raise SystemExit(
                "--discover-cases must be positive."
            )

        runner.discover_and_register(
            count=args.discover_cases,
            headless=args.headless,
        )

    if args.discover_all:
        action_selected = True

        raise SystemExit(
            "--discover-all is intentionally disabled for this "
            "EDR workflow. Use --target-cdrx with "
            "--max-cases-scanned instead."
        )

    if args.run:
        action_selected = True

        runner.run_pending(
            headless=args.headless,
            limit=args.limit,
            retry_failed=args.retry_failed,
        )

        runner.save_summary()

    if args.target_cdrx is not None:
        action_selected = True

        runner.run_to_target(
            target_cdrx=args.target_cdrx,
            max_cases_scanned=args.max_cases_scanned,
            headless=args.headless,
        )

    if args.summary:
        action_selected = True
        runner.save_summary()

    if not action_selected:
        raise SystemExit(
            "Choose an action: --add-case, --discover-cases, "
            "--run, --target-cdrx, or --summary."
        )


if __name__ == "__main__":
    main()