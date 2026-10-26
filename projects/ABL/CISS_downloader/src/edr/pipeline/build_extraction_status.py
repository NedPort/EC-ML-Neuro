from __future__ import annotations

from pathlib import Path

import pandas as pd


# ============================================================
# Paths
# ============================================================

INVENTORY_FILE = Path(
    "data/processed/edr/edr_export_inventory.csv"
)

EDR_DIR = Path(
    "data/processed/edr"
)

OUTPUT_FILE = Path(
    "data/processed/edr/unified_extraction_v1/extraction_status.csv"
)


# ============================================================
# Helpers
# ============================================================

def normalize_id(value) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    # Prevent values such as 10015.0
    if text.endswith(".0"):
        text = text[:-2]

    return text


def make_key(
    case_id,
    vehicle_number,
) -> str:

    case_id = normalize_id(case_id)
    vehicle_number = normalize_id(vehicle_number)

    if not case_id or not vehicle_number:
        return ""

    return f"{case_id}__{vehicle_number}"


# ============================================================
# Find frozen / historical extraction outputs
# ============================================================

def find_historical_csv_files() -> list[Path]:

    patterns = [
        "group1*",
        "group2_final_v1",
        "group3_final_frozen_v1",
        "group4_final_v1",
        "group5_final_frozen_v1",
        "group6_final_frozen_v1",
    ]

    files: list[Path] = []

    for pattern in patterns:

        for directory in EDR_DIR.glob(pattern):

            if not directory.is_dir():
                continue

            for csv_file in directory.rglob("*.csv"):
                files.append(csv_file)

    return sorted(set(files))


# ============================================================
# Build set of previously extracted reports
# ============================================================

def collect_existing_keys(
    files: list[Path],
) -> tuple[set[str], list[dict]]:

    existing_keys: set[str] = set()
    source_summary: list[dict] = []

    for path in files:

        try:
            df = pd.read_csv(
                path,
                low_memory=False,
            )

        except Exception as exc:

            source_summary.append(
                {
                    "file": str(path),
                    "status": "read_error",
                    "rows": 0,
                    "keys_found": 0,
                    "error": str(exc),
                }
            )

            continue

        # We only care about files that actually identify
        # case + vehicle.
        if (
            "case_id" not in df.columns
            or "vehicle_number" not in df.columns
        ):

            continue

        file_keys = set()

        for _, row in df.iterrows():

            key = make_key(
                row["case_id"],
                row["vehicle_number"],
            )

            if key:
                file_keys.add(key)
                existing_keys.add(key)

        source_summary.append(
            {
                "file": str(path),
                "status": "used",
                "rows": len(df),
                "keys_found": len(file_keys),
                "error": "",
            }
        )

    return existing_keys, source_summary


# ============================================================
# Main
# ============================================================

def main() -> None:

    print("=" * 80)
    print("EDR EXTRACTION STATUS")
    print("=" * 80)

    inventory = pd.read_csv(
        INVENTORY_FILE,
        low_memory=False,
    )

    print(
        f"Inventory records: {len(inventory):,}"
    )

    historical_files = (
        find_historical_csv_files()
    )

    print(
        f"Historical CSV files inspected: "
        f"{len(historical_files):,}"
    )

    existing_keys, source_summary = (
        collect_existing_keys(
            historical_files
        )
    )

    print(
        f"Existing case/vehicle keys found: "
        f"{len(existing_keys):,}"
    )

    # --------------------------------------------------------
    # Compare inventory to historical extraction
    # --------------------------------------------------------

    rows = []

    for _, row in inventory.iterrows():

        case_id = normalize_id(
            row.get("case_id")
        )

        vehicle_number = normalize_id(
            row.get("vehicle_number")
        )

        key = make_key(
            case_id,
            vehicle_number,
        )

        already_extracted = (
            key in existing_keys
        )

        rows.append(
            {
                "case_id": case_id,
                "vehicle_number": vehicle_number,
                "export_basename":
                    row.get(
                        "export_basename",
                        "",
                    ),
                "export_availability_status":
                    row.get(
                        "export_availability_status",
                        "",
                    ),
                "csv_export_path":
                    row.get(
                        "csv_export_path",
                        "",
                    ),
                "pdf_export_path":
                    row.get(
                        "pdf_export_path",
                        "",
                    ),
                "extraction_status":
                    (
                        "already_extracted"
                        if already_extracted
                        else "needs_extraction"
                    ),
            }
        )

    result = pd.DataFrame(rows)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    already = (
        result["extraction_status"]
        == "already_extracted"
    ).sum()

    needs = (
        result["extraction_status"]
        == "needs_extraction"
    ).sum()

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(
        f"Already extracted: {already:,}"
    )

    print(
        f"Needs extraction:  {needs:,}"
    )

    print(
        f"Total accounted:   "
        f"{already + needs:,}"
    )

    print()
    print(
        f"Output: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()