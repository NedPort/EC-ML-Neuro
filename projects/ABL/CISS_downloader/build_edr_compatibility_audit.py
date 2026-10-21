from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# Configuration
# ============================================================

ROOT = Path("data/processed/edr")

EXPORT_INVENTORY = ROOT / "edr_export_inventory.csv"
CSV_PROFILE = ROOT / "edr_csv_profile.csv"

OUTPUT_DIR = ROOT / "compatibility_audit_v1"

REFERENCE_GROUP_DIRS = [
    ROOT / "group2_final_v1",
    ROOT / "group2_final_frozen_v1",
    ROOT / "group3_final_v1",
    ROOT / "group3_final_frozen_v1",
    ROOT / "group4_final_v1",
    ROOT / "group4_final_frozen_v1",
    ROOT / "group5_final_v1",
    ROOT / "group5_final_frozen_v1",
    ROOT / "group6_final_v1",
    ROOT / "group6_final_frozen_v1",
]

EXPECTED_REFERENCE_REPORT_COUNT = 1422


# ============================================================
# Helpers
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()

    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = text.replace("\u2212", "-")
    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text).strip()

    return text


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_csv_flexible(path: Path) -> list[list[str]]:
    """
    Read a CDR CSV conservatively.

    Uses utf-8-sig first and falls back to cp1252.
    Rows are preserved as strings.
    """
    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]

    last_error = None

    for encoding in encodings:
        try:
            with path.open(
                "r",
                encoding=encoding,
                errors="strict",
                newline="",
            ) as f:
                reader = csv.reader(f)
                return [
                    [cell.strip() for cell in row]
                    for row in reader
                ]

        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Unable to read CSV {path}: {last_error}"
    )


def is_empty_row(row: list[str]) -> bool:
    return not any(clean_text(cell) for cell in row)


def nonempty_cells(row: list[str]) -> list[str]:
    return [
        clean_text(cell)
        for cell in row
        if clean_text(cell)
    ]


def looks_like_section_heading(row: list[str]) -> bool:
    """
    Conservative structural heuristic.

    A row is considered a possible section heading when:
      - exactly one non-empty cell is present,
      - text is not purely numeric,
      - text is reasonably short,
      - text contains alphabetic characters.

    This does NOT classify the row into a Group.
    """
    cells = nonempty_cells(row)

    if len(cells) != 1:
        return False

    text = cells[0]

    if not text:
        return False

    if len(text) > 180:
        return False

    if not re.search(r"[A-Za-z]", text):
        return False

    return True


def looks_like_label_value_row(row: list[str]) -> bool:
    """
    Conservative label/value candidate detector.

    Requires:
      - at least two columns,
      - first column non-empty,
      - first column contains letters,
      - at least one later non-empty cell.
    """
    if len(row) < 2:
        return False

    first = clean_text(row[0])

    if not first:
        return False

    if not re.search(r"[A-Za-z]", first):
        return False

    later_values = [
        clean_text(cell)
        for cell in row[1:]
        if clean_text(cell)
    ]

    return len(later_values) > 0


def looks_like_repeated_numeric_table_row(row: list[str]) -> bool:
    """
    Structural hint for potential Group 4 material.

    This is deliberately NOT a Group 4 classifier.

    It only detects rows with multiple numeric-looking cells.
    """
    cells = [
        clean_text(cell)
        for cell in row
        if clean_text(cell)
    ]

    if len(cells) < 3:
        return False

    numeric_count = 0

    for cell in cells:
        candidate = (
            cell.replace(",", "")
            .replace("%", "")
            .strip()
        )

        try:
            float(candidate)
            numeric_count += 1
        except Exception:
            pass

    return numeric_count >= 2


# ============================================================
# Reference report discovery
# ============================================================

REFERENCE_ID_COLUMNS = [
    "export_basename",
    "report_id",
    "source_basename",
    "cdrx_basename",
]


def collect_reference_basenames() -> tuple[set[str], list[dict[str, Any]]]:
    """
    Recover previously processed report identifiers from frozen/final
    Group packages.

    We intentionally scan existing output CSVs rather than hard-code
    filenames inside those packages.
    """
    basenames: set[str] = set()
    evidence: list[dict[str, Any]] = []

    visited_files: set[Path] = set()

    for directory in REFERENCE_GROUP_DIRS:
        if not directory.exists():
            continue

        for path in directory.rglob("*.csv"):
            resolved = path.resolve()

            if resolved in visited_files:
                continue

            visited_files.add(resolved)

            try:
                df = pd.read_csv(
                    path,
                    dtype=str,
                    low_memory=False,
                )
            except Exception:
                continue

            usable_column = None

            for column in REFERENCE_ID_COLUMNS:
                if column in df.columns:
                    usable_column = column
                    break

            if usable_column is None:
                continue

            found_here = set()

            for value in df[usable_column].dropna():
                value = clean_text(value)

                if not value:
                    continue

                # Remove extensions if present.
                value = re.sub(
                    r"\.(csv|pdf|cdrx)$",
                    "",
                    value,
                    flags=re.IGNORECASE,
                )

                found_here.add(value)

            if found_here:
                basenames.update(found_here)

                evidence.append(
                    {
                        "file": str(path),
                        "identifier_column": usable_column,
                        "unique_identifiers_found": len(found_here),
                    }
                )

    return basenames, evidence


# ============================================================
# CSV profiling
# ============================================================

def profile_csv(
    path: Path,
) -> tuple[dict[str, Any], Counter, Counter]:
    rows = read_csv_flexible(path)

    nonempty = [
        row
        for row in rows
        if not is_empty_row(row)
    ]

    label_counter: Counter = Counter()
    section_counter: Counter = Counter()

    label_rows = 0
    section_rows = 0
    possible_numeric_table_rows = 0

    for row in nonempty:
        if looks_like_section_heading(row):
            section = clean_text(nonempty_cells(row)[0])

            section_counter[section] += 1
            section_rows += 1

        if looks_like_label_value_row(row):
            label = clean_text(row[0])

            label_counter[label] += 1
            label_rows += 1

        if looks_like_repeated_numeric_table_row(row):
            possible_numeric_table_rows += 1

    max_columns = max(
        (len(row) for row in rows),
        default=0,
    )

    result = {
        "actual_row_count": len(rows),
        "actual_nonempty_row_count": len(nonempty),
        "actual_maximum_column_count": max_columns,
        "candidate_label_value_rows": label_rows,
        "candidate_section_rows": section_rows,
        "possible_repeated_numeric_rows": possible_numeric_table_rows,
        "unique_candidate_labels": len(label_counter),
        "unique_candidate_sections": len(section_counter),
    }

    return result, label_counter, section_counter


# ============================================================
# Main
# ============================================================

def main() -> None:
    if not EXPORT_INVENTORY.exists():
        raise FileNotFoundError(
            f"Missing inventory: {EXPORT_INVENTORY}"
        )

    if not CSV_PROFILE.exists():
        raise FileNotFoundError(
            f"Missing CSV profile: {CSV_PROFILE}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory = pd.read_csv(
        EXPORT_INVENTORY,
        dtype={
            "case_id": str,
            "vehicle_number": str,
            "export_basename": str,
        },
        low_memory=False,
    )

    existing_profile = pd.read_csv(
        CSV_PROFILE,
        dtype={
            "case_id": str,
            "vehicle_number": str,
            "export_basename": str,
        },
        low_memory=False,
    )

    # --------------------------------------------------------
    # Recover reference report population
    # --------------------------------------------------------

    (
        reference_basenames,
        reference_evidence,
    ) = collect_reference_basenames()

    inventory_basenames = set(
        inventory["export_basename"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    reference_in_inventory = (
        inventory_basenames
        & reference_basenames
    )

    # If frozen packages successfully recover the original
    # population, use them directly.
    reference_recovery_successful = (
        len(reference_in_inventory)
        >= EXPECTED_REFERENCE_REPORT_COUNT
    )

    if not reference_recovery_successful:
        print()
        print("WARNING:")
        print(
            "Could not recover all 1,422 reference reports "
            "from frozen/final group packages."
        )
        print(
            f"Recovered in current inventory: "
            f"{len(reference_in_inventory)}"
        )
        print()
        print(
            "The script will NOT guess which reports are new."
        )
        print(
            "Reports not explicitly confirmed as reference will "
            "be marked 'reference_status_unresolved'."
        )
        print()

    # --------------------------------------------------------
    # Existing profile lookup
    # --------------------------------------------------------

    profile_lookup = {}

    for _, row in existing_profile.iterrows():
        basename = clean_text(
            row.get("export_basename")
        )

        if basename:
            profile_lookup[basename] = row.to_dict()

    # --------------------------------------------------------
    # Process reports
    # --------------------------------------------------------

    report_records = []

    reference_labels: Counter = Counter()
    new_labels: Counter = Counter()

    reference_sections: Counter = Counter()
    new_sections: Counter = Counter()

    errors = []

    # Pass 1:
    # Profile reference CSVs to establish structural vocabulary.
    for _, row in inventory.iterrows():
        basename = clean_text(
            row.get("export_basename")
        )

        csv_path_text = clean_text(
            row.get("csv_export_path")
        )

        if not csv_path_text:
            continue

        if basename not in reference_in_inventory:
            continue

        path = Path(csv_path_text)

        if not path.exists():
            continue

        try:
            _, labels, sections = profile_csv(path)

            reference_labels.update(labels)
            reference_sections.update(sections)

        except Exception as exc:
            errors.append(
                {
                    "export_basename": basename,
                    "stage": "reference_profile",
                    "source_path": str(path),
                    "error": str(exc),
                }
            )

    reference_label_set = {
        normalize_text(label)
        for label in reference_labels
        if normalize_text(label)
    }

    reference_section_set = {
        normalize_text(section)
        for section in reference_sections
        if normalize_text(section)
    }

    # --------------------------------------------------------
    # Pass 2:
    # Audit every report.
    # --------------------------------------------------------

    total = len(inventory)

    for index, (_, row) in enumerate(
        inventory.iterrows(),
        start=1,
    ):
        case_id = clean_text(
            row.get("case_id")
        )

        vehicle_number = clean_text(
            row.get("vehicle_number")
        )

        basename = clean_text(
            row.get("export_basename")
        )

        availability = clean_text(
            row.get("export_availability_status")
        )

        csv_path_text = clean_text(
            row.get("csv_export_path")
        )

        pdf_path_text = clean_text(
            row.get("pdf_export_path")
        )

        has_csv = bool(csv_path_text)
        has_pdf = bool(pdf_path_text)

        if basename in reference_in_inventory:
            dataset_partition = "reference"

        elif reference_recovery_successful:
            dataset_partition = "new"

        else:
            dataset_partition = (
                "reference_status_unresolved"
            )

        record = {
            "case_id": case_id,
            "vehicle_number": vehicle_number,
            "export_basename": basename,
            "dataset_partition": dataset_partition,
            "export_availability_status": availability,
            "has_csv": has_csv,
            "has_pdf": has_pdf,
            "csv_export_path": csv_path_text,
            "pdf_export_path": pdf_path_text,
            "csv_sha256": clean_text(
                row.get("csv_sha256")
            ),
            "pdf_sha256": clean_text(
                row.get("pdf_sha256")
            ),
            "compatibility_status": "",
            "known_label_count": 0,
            "unseen_label_count": 0,
            "known_label_rate": None,
            "known_section_count": 0,
            "unseen_section_count": 0,
            "candidate_label_value_rows": 0,
            "candidate_section_rows": 0,
            "possible_repeated_numeric_rows": 0,
            "unique_candidate_labels": 0,
            "unique_candidate_sections": 0,
            "source_error": "",
        }

        if not has_csv:
            record["compatibility_status"] = (
                "pdf_only_requires_pdf_audit"
            )

            report_records.append(record)
            continue

        csv_path = Path(csv_path_text)

        if not csv_path.exists():
            record["compatibility_status"] = (
                "csv_source_missing"
            )

            record["source_error"] = (
                f"Missing CSV: {csv_path}"
            )

            report_records.append(record)

            errors.append(
                {
                    "export_basename": basename,
                    "stage": "csv_profile",
                    "source_path": str(csv_path),
                    "error": "source_missing",
                }
            )

            continue

        try:
            (
                structural,
                labels,
                sections,
            ) = profile_csv(csv_path)

            record.update(structural)

            normalized_labels = {
                normalize_text(label)
                for label in labels
                if normalize_text(label)
            }

            normalized_sections = {
                normalize_text(section)
                for section in sections
                if normalize_text(section)
            }

            known_labels = (
                normalized_labels
                & reference_label_set
            )

            unseen_labels = (
                normalized_labels
                - reference_label_set
            )

            known_sections = (
                normalized_sections
                & reference_section_set
            )

            unseen_sections = (
                normalized_sections
                - reference_section_set
            )

            total_unique_labels = len(
                normalized_labels
            )

            if total_unique_labels:
                known_rate = (
                    len(known_labels)
                    / total_unique_labels
                )
            else:
                known_rate = None

            record["known_label_count"] = len(
                known_labels
            )

            record["unseen_label_count"] = len(
                unseen_labels
            )

            record["known_label_rate"] = (
                round(known_rate, 6)
                if known_rate is not None
                else None
            )

            record["known_section_count"] = len(
                known_sections
            )

            record["unseen_section_count"] = len(
                unseen_sections
            )

            if dataset_partition == "reference":
                record["compatibility_status"] = (
                    "reference_profiled"
                )

            elif not unseen_labels and not unseen_sections:
                record["compatibility_status"] = (
                    "fully_known_structure"
                )

            elif unseen_labels or unseen_sections:
                record["compatibility_status"] = (
                    "novel_structure_detected"
                )

            else:
                record["compatibility_status"] = (
                    "profiled"
                )

            if dataset_partition == "new":
                new_labels.update(labels)
                new_sections.update(sections)

        except Exception as exc:
            record["compatibility_status"] = (
                "profile_failure"
            )

            record["source_error"] = str(exc)

            errors.append(
                {
                    "export_basename": basename,
                    "stage": "csv_profile",
                    "source_path": str(csv_path),
                    "error": str(exc),
                }
            )

        report_records.append(record)

        if index % 100 == 0 or index == total:
            print(
                f"Profiled {index}/{total} reports"
            )

    # --------------------------------------------------------
    # Novel label registry
    # --------------------------------------------------------

    novel_label_rows = []

    for label, count in sorted(
        new_labels.items(),
        key=lambda item: (
            -item[1],
            item[0].lower(),
        ),
    ):
        normalized = normalize_text(label)

        if normalized in reference_label_set:
            continue

        novel_label_rows.append(
            {
                "raw_label": label,
                "normalized_label": normalized,
                "new_batch_occurrence_count": count,
                "reference_occurrence_count": 0,
                "status": "unseen_label",
            }
        )

    novel_section_rows = []

    for section, count in sorted(
        new_sections.items(),
        key=lambda item: (
            -item[1],
            item[0].lower(),
        ),
    ):
        normalized = normalize_text(section)

        if normalized in reference_section_set:
            continue

        novel_section_rows.append(
            {
                "raw_section": section,
                "normalized_section": normalized,
                "new_batch_occurrence_count": count,
                "reference_occurrence_count": 0,
                "status": "unseen_section",
            }
        )

    # --------------------------------------------------------
    # DataFrames
    # --------------------------------------------------------

    report_df = pd.DataFrame(
        report_records
    )

    novel_labels_df = pd.DataFrame(
        novel_label_rows
    )

    novel_sections_df = pd.DataFrame(
        novel_section_rows
    )

    errors_df = pd.DataFrame(
        errors
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    partition_counts = (
        report_df["dataset_partition"]
        .value_counts(dropna=False)
        .to_dict()
    )

    status_counts = (
        report_df["compatibility_status"]
        .value_counts(dropna=False)
        .to_dict()
    )

    new_df = report_df[
        report_df["dataset_partition"] == "new"
    ].copy()

    new_csv_df = new_df[
        new_df["has_csv"] == True
    ].copy()

    new_pdf_only_df = new_df[
        new_df["has_csv"] == False
    ].copy()

    if len(new_csv_df):
        usable_rates = pd.to_numeric(
            new_csv_df["known_label_rate"],
            errors="coerce",
        ).dropna()

        mean_known_label_rate = (
            float(usable_rates.mean())
            if len(usable_rates)
            else None
        )

        median_known_label_rate = (
            float(usable_rates.median())
            if len(usable_rates)
            else None
        )
    else:
        mean_known_label_rate = None
        median_known_label_rate = None

    summary = {
        "created_at": utc_now(),
        "purpose": (
            "Generalization audit of current EDR export "
            "population against previously validated "
            "reference structures."
        ),
        "input_inventory": str(
            EXPORT_INVENTORY
        ),
        "input_csv_profile": str(
            CSV_PROFILE
        ),
        "total_inventory_reports": int(
            len(inventory)
        ),
        "expected_reference_reports": (
            EXPECTED_REFERENCE_REPORT_COUNT
        ),
        "reference_reports_recovered": int(
            len(reference_in_inventory)
        ),
        "reference_recovery_successful": bool(
            reference_recovery_successful
        ),
        "partition_counts": {
            str(k): int(v)
            for k, v in partition_counts.items()
        },
        "compatibility_status_counts": {
            str(k): int(v)
            for k, v in status_counts.items()
        },
        "new_reports": int(
            len(new_df)
        ),
        "new_csv_reports": int(
            len(new_csv_df)
        ),
        "new_pdf_only_reports": int(
            len(new_pdf_only_df)
        ),
        "reference_unique_csv_labels": int(
            len(reference_label_set)
        ),
        "reference_unique_sections": int(
            len(reference_section_set)
        ),
        "new_unique_unseen_labels": int(
            len(novel_labels_df)
        ),
        "new_unique_unseen_sections": int(
            len(novel_sections_df)
        ),
        "mean_new_report_known_label_rate": (
            mean_known_label_rate
        ),
        "median_new_report_known_label_rate": (
            median_known_label_rate
        ),
        "source_or_profile_errors": int(
            len(errors_df)
        ),
        "notes": [
            (
                "This audit performs structural compatibility "
                "profiling only."
            ),
            (
                "It does not alter Group 1-6 extraction rules."
            ),
            (
                "Unseen labels and sections are retained for "
                "explicit review rather than automatically "
                "classified."
            ),
            (
                "Potential repeated numeric rows are structural "
                "signals only and are not classified as Group 4."
            ),
        ],
    }

    # --------------------------------------------------------
    # Write outputs
    # --------------------------------------------------------

    report_path = (
        OUTPUT_DIR
        / "edr_compatibility_report.csv"
    )

    novel_labels_path = (
        OUTPUT_DIR
        / "edr_unseen_labels.csv"
    )

    novel_sections_path = (
        OUTPUT_DIR
        / "edr_unseen_sections.csv"
    )

    errors_path = (
        OUTPUT_DIR
        / "edr_compatibility_errors.csv"
    )

    reference_evidence_path = (
        OUTPUT_DIR
        / "reference_population_evidence.json"
    )

    summary_path = (
        OUTPUT_DIR
        / "edr_compatibility_summary.json"
    )

    report_df.to_csv(
        report_path,
        index=False,
    )

    novel_labels_df.to_csv(
        novel_labels_path,
        index=False,
    )

    novel_sections_df.to_csv(
        novel_sections_path,
        index=False,
    )

    errors_df.to_csv(
        errors_path,
        index=False,
    )

    with reference_evidence_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            reference_evidence,
            f,
            indent=2,
            ensure_ascii=False,
        )

    with summary_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("EDR COMPATIBILITY AUDIT COMPLETE")
    print("=" * 70)

    print(
        f"Inventory reports: "
        f"{len(inventory)}"
    )

    print(
        f"Reference reports recovered: "
        f"{len(reference_in_inventory)}"
    )

    if reference_recovery_successful:
        print(
            f"New reports detected: "
            f"{len(new_df)}"
        )

        print(
            f"  New CSV reports: "
            f"{len(new_csv_df)}"
        )

        print(
            f"  New PDF-only reports: "
            f"{len(new_pdf_only_df)}"
        )
    else:
        print(
            "New/reference partition could not be "
            "confirmed safely."
        )

    print(
        f"Reference unique CSV labels: "
        f"{len(reference_label_set)}"
    )

    print(
        f"New unseen labels: "
        f"{len(novel_labels_df)}"
    )

    print(
        f"New unseen sections: "
        f"{len(novel_sections_df)}"
    )

    if mean_known_label_rate is not None:
        print(
            "Mean known-label rate, new CSV reports: "
            f"{mean_known_label_rate:.2%}"
        )

    if median_known_label_rate is not None:
        print(
            "Median known-label rate, new CSV reports: "
            f"{median_known_label_rate:.2%}"
        )

    print(
        f"Source/profile errors: "
        f"{len(errors_df)}"
    )

    print()

    print(
        f"Report audit: {report_path}"
    )

    print(
        f"Unseen labels: {novel_labels_path}"
    )

    print(
        f"Unseen sections: {novel_sections_path}"
    )

    print(
        f"Errors: {errors_path}"
    )

    print(
        f"Summary: {summary_path}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()