from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# Paths
# ============================================================

STATUS_FILE = Path(
    "data/processed/edr/unified_extraction_v1/extraction_status.csv"
)

OUTPUT_DIR = Path(
    "data/processed/edr/unified_extraction_v1"
)

PENDING_MANIFEST = (
    OUTPUT_DIR / "pending_source_manifest.csv"
)

METADATA_FILE = (
    OUTPUT_DIR / "pending_source_metadata.json"
)


# ============================================================
# Helpers
# ============================================================

def clean(value: Any) -> str:

    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


# ============================================================
# Source selection
# ============================================================

def choose_source(
    row: pd.Series,
) -> dict[str, str]:

    csv_path = clean(
        row.get("csv_export_path")
    )

    pdf_path = clean(
        row.get("pdf_export_path")
    )

    csv_exists = (
        bool(csv_path)
        and Path(csv_path).exists()
    )

    pdf_exists = (
        bool(pdf_path)
        and Path(pdf_path).exists()
    )

    # CSV is always preferred.
    if csv_exists:

        return {
            "selected_source_format": "csv",
            "selected_source_path": csv_path,
            "source_status": "ready",
        }

    # PDF is fallback only.
    if pdf_exists:

        return {
            "selected_source_format": "pdf",
            "selected_source_path": pdf_path,
            "source_status": "ready",
        }

    return {
        "selected_source_format": "",
        "selected_source_path": "",
        "source_status": "missing_source",
    }


# ============================================================
# Main
# ============================================================

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 80)
    print("UNIFIED EDR PENDING EXTRACTION")
    print("=" * 80)

    status = pd.read_csv(
        STATUS_FILE,
        low_memory=False,
    )

    # --------------------------------------------------------
    # ONLY records that have not already been extracted
    # --------------------------------------------------------

    pending = status[
        status["extraction_status"]
        == "needs_extraction"
    ].copy()

    print(
        f"Records needing extraction: "
        f"{len(pending):,}"
    )

    rows = []

    for _, row in pending.iterrows():

        decision = choose_source(
            row
        )

        rows.append(
            {
                "case_id":
                    clean(row.get("case_id")),

                "vehicle_number":
                    clean(
                        row.get("vehicle_number")
                    ),

                "export_basename":
                    clean(
                        row.get("export_basename")
                    ),

                "csv_export_path":
                    clean(
                        row.get("csv_export_path")
                    ),

                "pdf_export_path":
                    clean(
                        row.get("pdf_export_path")
                    ),

                "extraction_status":
                    "needs_extraction",

                **decision,
            }
        )

    manifest = pd.DataFrame(
        rows
    )

    manifest.to_csv(
        PENDING_MANIFEST,
        index=False,
    )

    # --------------------------------------------------------
    # Counts
    # --------------------------------------------------------

    csv_count = (
        manifest[
            "selected_source_format"
        ]
        == "csv"
    ).sum()

    pdf_count = (
        manifest[
            "selected_source_format"
        ]
        == "pdf"
    ).sum()

    missing_count = (
        manifest[
            "source_status"
        ]
        != "ready"
    ).sum()

    metadata = {
        "created_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "records_needing_extraction":
            len(manifest),

        "csv_selected":
            int(csv_count),

        "pdf_fallback_selected":
            int(pdf_count),

        "missing_sources":
            int(missing_count),

        "policy":
            (
                "Process only records not already "
                "extracted. Prefer CSV; use PDF only "
                "when CSV is unavailable."
            ),
    }

    METADATA_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 80)
    print("PENDING EXTRACTION SUMMARY")
    print("=" * 80)

    print(
        f"Pending records:      "
        f"{len(manifest):,}"
    )

    print(
        f"CSV selected:         "
        f"{csv_count:,}"
    )

    print(
        f"PDF fallback:         "
        f"{pdf_count:,}"
    )

    print(
        f"Missing sources:      "
        f"{missing_count:,}"
    )

    print()
    print(
        f"Manifest: {PENDING_MANIFEST}"
    )


if __name__ == "__main__":
    main()