
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

from selenium.common.exceptions import TimeoutException

from src.api.client import CISSApi
from src.pilot.case_discovery import CaseDiscovery
from src.pipeline.case_processor import CaseProcessor


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def has_cdrx_reference(obj: Any) -> bool:
    """Find explicit .cdrx references in JSON data."""
    if isinstance(obj, str):
        return ".cdrx" in obj.casefold()

    if isinstance(obj, dict):
        return any(
            has_cdrx_reference(k) or has_cdrx_reference(v)
            for k, v in obj.items()
        )

    if isinstance(obj, list):
        return any(has_cdrx_reference(v) for v in obj)

    return False


def edr_status(obj: Any) -> str:
    """
    Inspect evCdc records for edrObtained.

    Returns:
        positive: at least one record indicates EDR obtained
        negative: records exist and all explicitly indicate no EDR
        unknown: missing or ambiguous information
    """
    values = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() == "evcdc":
                    records = (
                        item if isinstance(item, list) else [item]
                    )

                    for record in records:
                        if isinstance(record, dict):
                            for k, v in record.items():
                                if k.casefold() == "edrobtained":
                                    values.append(v)

                if isinstance(item, (dict, list)):
                    visit(item)

        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(obj)

    if not values:
        return "unknown"

    normalized = [
        str(v).strip().lower() for v in values
    ]

    if any(v in ("1", "true") for v in normalized):
        return "positive"

    if all(v in ("0", "false") for v in normalized):
        return "negative"

    return "unknown"


def discover_catalog(
    data_root: Path,
    headless: bool,
    retries: int,
    catalog_path: Path,
) -> list[int]:
    """Discover all CISS case IDs, retrying browser timeouts."""

    for attempt in range(1, retries + 1):
        api = None

        try:
            print(
                f"\nDiscovering CISS cases "
                f"(attempt {attempt}/{retries})..."
            )

            api = CISSApi(headless=headless)

            discovery = CaseDiscovery(
                driver=api.driver,
                data_root=str(data_root),
            )

            found = discovery.discover(
                limit=None,
                excluded_case_ids=set(),
            )

            case_ids = sorted(set(map(int, found)))

            if not case_ids:
                raise RuntimeError(
                    "Discovery returned zero cases."
                )

            atomic_json(catalog_path, case_ids)

            print(
                f"Discovered {len(case_ids)} unique CISS cases."
            )

            return case_ids

        except (TimeoutException, RuntimeError) as exc:
            print(
                f"Discovery attempt {attempt} failed: "
                f"{type(exc).__name__}: {exc}"
            )

            if attempt == retries:
                raise

            time.sleep(5 * attempt)

        finally:
            if api is not None:
                api.close()

    raise RuntimeError("Case discovery failed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory CISS cases using metadata and "
            "navigation records without downloading archives."
        )
    )

    parser.add_argument(
        "--data-root",
        default="data",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse saved catalog and successful case checks.",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
    )

    args = parser.parse_args()

    if args.retries < 1:
        parser.error("--retries must be at least 1")

    data_root = Path(args.data_root)

    out_dir = (
        data_root
        / "processed"
        / "edr"
        / "cdrx_site_inventory"
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = out_dir / "case_ids.json"
    progress_path = out_dir / "progress.json"
    summary_path = out_dir / "summary.json"
    csv_path = out_dir / "cdrx_site_inventory.csv"

    # --------------------------------------------------
    # STEP 1: Load previous successful checks
    # --------------------------------------------------

    previous: dict[int, dict[str, Any]] = {}

    if args.resume and progress_path.exists():
        saved = load_json(progress_path)

        previous = {
            int(row["case_id"]): row
            for row in saved.get("cases", [])
            if row.get("status") == "ok"
            and "edr_status" in row
            and "cdrx_reference" in row
        }

        print(
            f"Loaded {len(previous)} previously "
            f"successful case checks."
        )

    # --------------------------------------------------
    # STEP 2: Discover or load complete case catalog
    # --------------------------------------------------

    if args.resume and catalog_path.exists():
        case_ids = sorted(
            set(map(int, load_json(catalog_path)))
        )

        if not case_ids:
            raise RuntimeError(
                "Saved catalog is empty. "
                "Rerun without --resume."
            )

        print(
            f"Loaded {len(case_ids)} case IDs "
            f"from saved catalog."
        )

    else:
        case_ids = discover_catalog(
            data_root=data_root,
            headless=args.headless,
            retries=args.retries,
            catalog_path=catalog_path,
        )

    total_cases = len(case_ids)
    case_id_set = set(case_ids)

    print(f"\nTOTAL DISCOVERED CISS CASES: {total_cases}")

    # --------------------------------------------------
    # STEP 3: Scan lightweight records
    # --------------------------------------------------

    results_by_id = {
        case_id: row
        for case_id, row in previous.items()
        if case_id in case_id_set
    }

    api = CISSApi(headless=args.headless)

    try:
        processor = CaseProcessor(
            api=api,
            data_root=str(data_root),
        )

        for index, case_id in enumerate(case_ids, 1):
            if case_id in results_by_id:
                continue

            raw_dir = data_root / "raw" / str(case_id)
            raw_dir.mkdir(parents=True, exist_ok=True)

            metadata_path = raw_dir / "metadata.json"
            tree_path = raw_dir / "navigation_tree.json"

            try:
                if (
                    not metadata_path.exists()
                    or not tree_path.exists()
                ):
                    processor.case_downloader.save_case_records(
                        case_id=case_id,
                        output_directory=raw_dir,
                    )

                if (
                    not metadata_path.exists()
                    or not tree_path.exists()
                ):
                    raise FileNotFoundError(
                        "Metadata or navigation tree is missing."
                    )

                metadata = load_json(metadata_path)
                tree = load_json(tree_path)

                row = {
                    "case_id": case_id,
                    "edr_status": edr_status(metadata),
                    "cdrx_reference": (
                        has_cdrx_reference(metadata)
                        or has_cdrx_reference(tree)
                    ),
                    "status": "ok",
                    "error": "",
                }

            except Exception as exc:
                row = {
                    "case_id": case_id,
                    "edr_status": "unknown",
                    "cdrx_reference": False,
                    "status": "error",
                    "error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }

            results_by_id[case_id] = row

            # Persist progress after each case.
            atomic_json(
                progress_path,
                {
                    "total_cases": total_cases,
                    "cases": [
                        results_by_id[k]
                        for k in sorted(results_by_id)
                    ],
                },
            )

            print(
                f"[{index}/{total_cases}] "
                f"Case {case_id}: "
                f"EDR={row['edr_status']}, "
                f"CDRX reference={row['cdrx_reference']}, "
                f"status={row['status']}"
            )

    finally:
        api.close()

    # --------------------------------------------------
    # STEP 4: Calculate results
    # --------------------------------------------------

    results = [
        results_by_id[k]
        for k in sorted(results_by_id)
        if k in case_id_set
    ]

    ok = [
        row for row in results
        if row["status"] == "ok"
    ]

    errors = [
        row for row in results
        if row["status"] != "ok"
    ]

    positive = [
        row for row in ok
        if row["edr_status"] == "positive"
    ]

    negative = [
        row for row in ok
        if row["edr_status"] == "negative"
    ]

    unknown = [
        row for row in ok
        if row["edr_status"] == "unknown"
    ]

    cdrx_refs = [
        row for row in ok
        if row["cdrx_reference"]
    ]

    summary = {
        "total_ciss_cases": total_cases,
        "successfully_checked": len(ok),
        "edr_metadata_positive": len(positive),
        "edr_metadata_negative": len(negative),
        "edr_metadata_unknown": len(unknown),
        "explicit_cdrx_references": len(cdrx_refs),
        "errors": len(errors),
        "cdrx_reference_case_ids": [
            row["case_id"] for row in cdrx_refs
        ],
        "error_case_ids": [
            row["case_id"] for row in errors
        ],
    }

    # --------------------------------------------------
    # STEP 5: Save final results
    # --------------------------------------------------

def atomic_json(path: Path, data: Any) -> None:
    """
    Safely write JSON using a temporary file and atomic replacement.

    On Windows, the destination file can occasionally be temporarily locked
    by antivirus, editors, sync software, etc. Retry the replacement instead
    of terminating the entire scan.
    """
    import os
    import time

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".part")

    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    max_attempts = 10

    for attempt in range(1, max_attempts + 1):
        try:
            os.replace(tmp, path)
            return

        except PermissionError as exc:
            if attempt == max_attempts:
                print(
                    f"WARNING: Could not replace {path} after "
                    f"{max_attempts} attempts."
                )
                print(f"Temporary checkpoint remains at: {tmp}")
                print(f"Error: {exc}")

                # Do NOT crash the entire CISS inventory scan just because
                # the progress checkpoint could not be replaced.
                return

            wait_seconds = min(0.25 * attempt, 2.0)

            print(
                f"Checkpoint file temporarily locked: {path} "
                f"(attempt {attempt}/{max_attempts}). "
                f"Retrying in {wait_seconds:.2f}s..."
            )

            time.sleep(wait_seconds)

    # --------------------------------------------------
    # STEP 6: Print summary
    # --------------------------------------------------

    print("\n" + "=" * 70)
    print("FINAL CISS WEBSITE INVENTORY")
    print("=" * 70)

    print(f"TOTAL CISS CASES:           {total_cases}")
    print(f"SUCCESSFULLY CHECKED:       {len(ok)}")
    print(f"EDR METADATA POSITIVE:      {len(positive)}")
    print(f"EDR METADATA NEGATIVE:      {len(negative)}")
    print(f"EDR METADATA UNKNOWN:       {len(unknown)}")
    print(f"EXPLICIT .CDRX REFERENCES:  {len(cdrx_refs)}")
    print(f"ERROR / UNKNOWN REQUESTS:   {len(errors)}")

    print("\nSaved files:")
    print(summary_path)
    print(csv_path)
    print(catalog_path)


if __name__ == "__main__":
    main()
