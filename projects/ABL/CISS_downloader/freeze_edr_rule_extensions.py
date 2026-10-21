from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("data/processed/edr")

SOURCE_DIR = ROOT / "rule_extension_resolution_v1"

OUTPUT_DIR = ROOT / "rules_v1_1"

REQUIRED_FILES = [
    "edr_resolved_label_occurrences.csv",
    "edr_resolved_label_rules.csv",
    "edr_resolved_sections.csv",
    "edr_remaining_label_review.csv",
    "edr_remaining_section_review.csv",
    "edr_rule_extension_resolution_summary.json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def main() -> None:

    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Missing source directory: {SOURCE_DIR}"
        )

    # --------------------------------------------------------
    # Verify required files
    # --------------------------------------------------------

    missing = []

    for filename in REQUIRED_FILES:
        path = SOURCE_DIR / filename

        if not path.exists():
            missing.append(str(path))

    if missing:
        raise RuntimeError(
            "Missing required rule-resolution files:\n"
            + "\n".join(missing)
        )

    # --------------------------------------------------------
    # Confirm zero unresolved before freezing
    # --------------------------------------------------------

    summary_path = (
        SOURCE_DIR
        / "edr_rule_extension_resolution_summary.json"
    )

    with summary_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        summary = json.load(f)

    unresolved_labels = int(
        summary.get(
            "unresolved_label_occurrences",
            -1,
        )
    )

    unresolved_sections = int(
        summary.get(
            "unresolved_section_occurrences",
            -1,
        )
    )

    if unresolved_labels != 0:
        raise RuntimeError(
            f"Cannot freeze: "
            f"{unresolved_labels} unresolved label occurrences."
        )

    if unresolved_sections != 0:
        raise RuntimeError(
            f"Cannot freeze: "
            f"{unresolved_sections} unresolved section occurrences."
        )

    # --------------------------------------------------------
    # Prevent accidental overwrite
    # --------------------------------------------------------

    if OUTPUT_DIR.exists():
        raise RuntimeError(
            f"Output already exists: {OUTPUT_DIR}\n"
            "Frozen rule packages must not be overwritten."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    # --------------------------------------------------------
    # Copy authoritative resolution files
    # --------------------------------------------------------

    copied_files = []

    for filename in REQUIRED_FILES:
        src = SOURCE_DIR / filename
        dst = OUTPUT_DIR / filename

        shutil.copy2(
            src,
            dst,
        )

        copied_files.append(
            dst
        )

    # --------------------------------------------------------
    # Freeze metadata
    # --------------------------------------------------------

    freeze_metadata = {
        "created_at": utc_now(),
        "rule_version": "1.1",
        "status": (
            "frozen_validated_rule_extension_package"
        ),
        "source_package": str(
            SOURCE_DIR
        ),
        "purpose": (
            "Generalized EDR rule extensions derived from "
            "independent compatibility testing of newly "
            "downloaded CISS EDR reports."
        ),
        "validation": {
            "unresolved_label_occurrences": (
                unresolved_labels
            ),
            "unresolved_section_occurrences": (
                unresolved_sections
            ),
            "ready_for_production_rule_promotion": True,
        },
        "principles": [
            (
                "Original source observations remain authoritative."
            ),
            (
                "Repeated-measurement structure takes precedence "
                "over section-name semantics."
            ),
            (
                "Mixed sections must be routed at row level."
            ),
            (
                "Standalone DTC codes remain diagnostic evidence "
                "rather than being forced into Groups 1-6."
            ),
            (
                "Frozen reference datasets remain immutable."
            ),
            (
                "New rules supplement existing validated rules "
                "rather than replacing historical provenance."
            ),
        ],
    }

    metadata_path = (
        OUTPUT_DIR
        / "rule_package_metadata.json"
    )

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            freeze_metadata,
            f,
            indent=2,
            ensure_ascii=False,
        )

    copied_files.append(
        metadata_path
    )

    # --------------------------------------------------------
    # SHA-256 manifest
    # --------------------------------------------------------

    manifest = []

    for path in sorted(copied_files):

        manifest.append(
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    manifest_path = (
        OUTPUT_DIR
        / "freeze_manifest_sha256.json"
    )

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            {
                "created_at": utc_now(),
                "rule_version": "1.1",
                "files": manifest,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("EDR RULE EXTENSION PACKAGE FROZEN")
    print("=" * 72)

    print("Rule version: 1.1")

    print(
        f"Unresolved label occurrences: "
        f"{unresolved_labels}"
    )

    print(
        f"Unresolved section occurrences: "
        f"{unresolved_sections}"
    )

    print()

    print(
        f"Frozen package: {OUTPUT_DIR}"
    )

    print(
        f"SHA-256 manifest: {manifest_path}"
    )

    print()

    print(
        "Status: "
        "frozen_validated_rule_extension_package"
    )

    print("=" * 72)


if __name__ == "__main__":
    main()