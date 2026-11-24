from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path
from typing import Any

from selenium.common.exceptions import TimeoutException

from src.api.client import CISSApi
from src.pilot.case_discovery import CaseDiscovery
from src.pipeline.case_processor import CaseProcessor


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = Path(
    os.getenv("CISS_DATA_ROOT", str(PROJECT_ROOT / "data"))
).expanduser().resolve()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def atomic_json(path: Path, data: Any) -> None:
    """Write JSON through a temporary file, retrying Windows file locks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".part")
    temporary_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    max_attempts = 10
    for attempt in range(1, max_attempts + 1):
        try:
            os.replace(temporary_path, path)
            return
        except PermissionError:
            if attempt == max_attempts:
                raise RuntimeError(
                    f"Could not save {path} after {max_attempts} attempts; "
                    f"temporary file remains at {temporary_path}"
                )
            wait_seconds = min(0.25 * attempt, 2.0)
            print(
                f"File temporarily locked: {path} "
                f"(attempt {attempt}/{max_attempts}); "
                f"retrying in {wait_seconds:.2f}s..."
            )
            time.sleep(wait_seconds)


def has_cdrx_reference(obj: Any) -> bool:
    """Find explicit .cdrx references in JSON data."""
    if isinstance(obj, str):
        return ".cdrx" in obj.casefold()
    if isinstance(obj, dict):
        return any(
            has_cdrx_reference(key) or has_cdrx_reference(value)
            for key, value in obj.items()
        )
    if isinstance(obj, list):
        return any(has_cdrx_reference(value) for value in obj)
    return False


def edr_status(obj: Any) -> str:
    """Classify evCdc.edrObtained as positive, negative, or unknown."""
    values: list[Any] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() == "evcdc":
                    records = item if isinstance(item, list) else [item]
                    for record in records:
                        if isinstance(record, dict):
                            for field, field_value in record.items():
                                if field.casefold() == "edrobtained":
                                    values.append(field_value)
                if isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(obj)
    if not values:
        return "unknown"

    normalized = [str(value).strip().lower() for value in values]
    if any(value in ("1", "true") for value in normalized):
        return "positive"
    if all(value in ("0", "false") for value in normalized):
        return "negative"
    return "unknown"


def discover_catalog(
    data_root: Path,
    headless: bool,
    retries: int,
    catalog_path: Path,
    limit: int | None = None,
) -> list[int]:
    """Discover CISS case IDs, retrying browser timeouts."""
    for attempt in range(1, retries + 1):
        api = None
        try:
            print(f"\nDiscovering CISS cases (attempt {attempt}/{retries})...")
            api = CISSApi(headless=headless)
            discovery = CaseDiscovery(
                driver=api.driver,
                data_root=str(data_root),
            )
            found = discovery.discover(
                limit=limit,
                excluded_case_ids=set(),
            )
            case_ids = sorted(set(map(int, found)))
            if not case_ids:
                raise RuntimeError("Discovery returned zero cases.")
            atomic_json(catalog_path, case_ids)
            print(f"Discovered {len(case_ids)} unique CISS cases.")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory CISS cases using metadata and navigation "
            "records without downloading archives."
        )
    )
    parser.add_argument(
        "--data-root",
        default=str(DEFAULT_DATA_ROOT),
        help="Root directory for CISS data.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse saved catalog and successful case checks.",
    )
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of CISS cases to check (partial inventory).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.retries < 1:
        parser.error("--retries must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")

    data_root = Path(args.data_root).expanduser().resolve()
    out_dir = data_root / "processed" / "edr" / "cdrx_site_inventory"
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = out_dir / "case_ids.json"
    progress_path = out_dir / "progress.json"
    summary_path = out_dir / "summary.json"
    csv_path = out_dir / "cdrx_site_inventory.csv"

    # STEP 1: Reuse previously successful checks when resuming.
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
        print(f"Loaded {len(previous)} previously successful case checks.")

    # STEP 2: Reuse a catalog or discover case IDs.
    if args.resume and catalog_path.exists():
        case_ids = sorted(set(map(int, load_json(catalog_path))))
        if not case_ids:
            raise RuntimeError(
                "Saved catalog is empty. Rerun without --resume."
            )
        print(f"Loaded {len(case_ids)} case IDs from saved catalog.")
    else:
        case_ids = discover_catalog(
            data_root=data_root,
            headless=args.headless,
            retries=args.retries,
            catalog_path=catalog_path,
            limit=args.limit,
        )

    # This also limits a previously saved catalog when --resume is used.
    if args.limit is not None:
        case_ids = case_ids[:args.limit]

    total_cases = len(case_ids)
    case_id_set = set(case_ids)
    print(f"\nTOTAL SELECTED CISS CASES: {total_cases}")
    if args.limit is not None:
        print("LIMITED TEST: results do not represent the full CISS catalog.")

    # STEP 3: Scan metadata and navigation records.
    results_by_id: dict[int, dict[str, Any]] = {
        case_id: row
        for case_id, row in previous.items()
        if case_id in case_id_set
    }
    pending_ids = [case_id for case_id in case_ids if case_id not in results_by_id]
    print(f"Previously completed: {len(results_by_id)}; pending: {len(pending_ids)}")

    if pending_ids:
        api = CISSApi(headless=args.headless)
        try:
            processor = CaseProcessor(api=api, data_root=str(data_root))
            for index, case_id in enumerate(case_ids, start=1):
                if case_id in results_by_id:
                    continue

                raw_dir = data_root / "raw" / str(case_id)
                raw_dir.mkdir(parents=True, exist_ok=True)
                metadata_path = raw_dir / "metadata.json"
                tree_path = raw_dir / "navigation_tree.json"

                try:
                    if not metadata_path.exists() or not tree_path.exists():
                        processor.case_downloader.save_case_records(
                            case_id=case_id,
                            output_directory=raw_dir,
                        )
                    if not metadata_path.exists() or not tree_path.exists():
                        raise FileNotFoundError(
                            "Metadata or navigation tree is missing."
                        )
                    metadata = load_json(metadata_path)
                    tree = load_json(tree_path)
                    row: dict[str, Any] = {
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
                        "error": f"{type(exc).__name__}: {exc}",
                    }

                results_by_id[case_id] = row
                atomic_json(
                    progress_path,
                    {
                        "total_cases": total_cases,
                        "cases": [
                            results_by_id[key]
                            for key in sorted(results_by_id)
                        ],
                    },
                )
                print(
                    f"[{index}/{total_cases}] Case {case_id}: "
                    f"EDR={row['edr_status']}, "
                    f"CDRX reference={row['cdrx_reference']}, "
                    f"status={row['status']}"
                )
        finally:
            api.close()

    # STEP 4: Summarize completed and failed checks.
    results = [
        results_by_id[key]
        for key in sorted(results_by_id)
        if key in case_id_set
    ]
    ok = [row for row in results if row["status"] == "ok"]
    errors = [row for row in results if row["status"] != "ok"]
    positive = [row for row in ok if row["edr_status"] == "positive"]
    negative = [row for row in ok if row["edr_status"] == "negative"]
    unknown = [row for row in ok if row["edr_status"] == "unknown"]
    cdrx_refs = [row for row in ok if row["cdrx_reference"]]

    summary = {
        "total_ciss_cases": total_cases,
        "successfully_checked": len(ok),
        "edr_metadata_positive": len(positive),
        "edr_metadata_negative": len(negative),
        "edr_metadata_unknown": len(unknown),
        "explicit_cdrx_references": len(cdrx_refs),
        "errors": len(errors),
        "cdrx_reference_case_ids": [row["case_id"] for row in cdrx_refs],
        "error_case_ids": [row["case_id"] for row in errors],
    }

    # STEP 5: Write final outputs.
    atomic_json(summary_path, summary)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "edr_status",
                "cdrx_reference",
                "status",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    # STEP 6: Print summary.
    print("\n" + "=" * 70)
    print("FINAL CISS WEBSITE INVENTORY")
    print("=" * 70)
    print(f"TOTAL SELECTED CISS CASES:  {total_cases}")
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
