from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ============================================================
# Configuration
# ============================================================

ROOT = Path("data/processed/edr")

INVENTORY = ROOT / "edr_export_inventory.csv"

COMPATIBILITY_REPORT = (
    ROOT
    / "compatibility_audit_v1"
    / "edr_compatibility_report.csv"
)

RULE_AUDIT_DIR = ROOT / "rule_extension_audit_v1"

LABEL_REVIEW = (
    RULE_AUDIT_DIR
    / "edr_unseen_labels_manual_review.csv"
)

SECTION_REVIEW = (
    RULE_AUDIT_DIR
    / "edr_unseen_sections_manual_review.csv"
)

OUTPUT_DIR = ROOT / "rule_review_context_v1"

NEIGHBOR_ROWS = 3
SECTION_PREVIEW_ROWS = 15


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


def row_nonempty_cells(row: list[str]) -> list[str]:
    return [
        clean_text(cell)
        for cell in row
        if clean_text(cell)
    ]


def is_empty_row(row: list[str]) -> bool:
    return len(row_nonempty_cells(row)) == 0


def looks_like_section_heading(row: list[str]) -> bool:
    cells = row_nonempty_cells(row)

    if len(cells) != 1:
        return False

    text = cells[0]

    if not text:
        return False

    if len(text) > 220:
        return False

    if not re.search(r"[A-Za-z]", text):
        return False

    return True


def read_csv_flexible(path: Path) -> tuple[list[list[str]], str]:
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
                rows = [
                    [clean_text(cell) for cell in row]
                    for row in csv.reader(f)
                ]

            return rows, encoding

        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f"Unable to read {path}: {last_error}"
    )


def row_to_text(row: list[str]) -> str:
    return " | ".join(
        clean_text(cell)
        for cell in row
        if clean_text(cell)
    )


def row_to_json(row: list[str]) -> str:
    return json.dumps(
        row,
        ensure_ascii=False,
    )


def find_current_section(
    rows: list[list[str]],
    row_index: int,
) -> tuple[int | None, str]:
    """
    Walk backward from the current row and locate the nearest
    plausible one-cell section heading.
    """

    for i in range(row_index - 1, -1, -1):
        row = rows[i]

        if looks_like_section_heading(row):
            cells = row_nonempty_cells(row)

            if cells:
                return i, cells[0]

    return None, ""


def get_neighbor_context(
    rows: list[list[str]],
    row_index: int,
    radius: int = NEIGHBOR_ROWS,
) -> list[dict[str, Any]]:
    start = max(
        0,
        row_index - radius,
    )

    end = min(
        len(rows),
        row_index + radius + 1,
    )

    result = []

    for i in range(start, end):
        result.append(
            {
                "row_index_zero_based": i,
                "row_number_one_based": i + 1,
                "is_target": i == row_index,
                "row": rows[i],
            }
        )

    return result


def get_section_preview(
    rows: list[list[str]],
    section_index: int,
) -> list[dict[str, Any]]:
    """
    Capture rows after a section heading until:
      - another section heading is encountered, or
      - SECTION_PREVIEW_ROWS have been collected.
    """

    result = []

    start = section_index + 1

    for i in range(
        start,
        min(len(rows), start + SECTION_PREVIEW_ROWS),
    ):
        row = rows[i]

        if (
            i > start
            and looks_like_section_heading(row)
        ):
            break

        result.append(
            {
                "row_index_zero_based": i,
                "row_number_one_based": i + 1,
                "row": row,
            }
        )

    return result


# ============================================================
# Main
# ============================================================

def main() -> None:

    required = [
        INVENTORY,
        COMPATIBILITY_REPORT,
        LABEL_REVIEW,
        SECTION_REVIEW,
    ]

    for path in required:
        if not path.exists():
            raise FileNotFoundError(
                f"Missing required input: {path}"
            )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory = pd.read_csv(
        INVENTORY,
        dtype=str,
        low_memory=False,
    )

    compatibility = pd.read_csv(
        COMPATIBILITY_REPORT,
        dtype=str,
        low_memory=False,
    )

    label_review = pd.read_csv(
        LABEL_REVIEW,
        dtype=str,
        low_memory=False,
    )

    section_review = pd.read_csv(
        SECTION_REVIEW,
        dtype=str,
        low_memory=False,
    )

    # --------------------------------------------------------
    # Only use reports confirmed as new.
    # --------------------------------------------------------

    new_reports = set(
        compatibility.loc[
            compatibility["dataset_partition"] == "new",
            "export_basename",
        ]
        .dropna()
        .astype(str)
        .str.strip()
    )

    inventory = inventory[
        inventory["export_basename"]
        .astype(str)
        .isin(new_reports)
    ].copy()

    # --------------------------------------------------------
    # Review targets
    # --------------------------------------------------------

    label_targets = {
        normalize_text(v): clean_text(v)
        for v in label_review["raw_label"].dropna()
        if normalize_text(v)
    }

    section_targets = {
        normalize_text(v): clean_text(v)
        for v in section_review["raw_section"].dropna()
        if normalize_text(v)
    }

    label_occurrences = []
    section_occurrences = []
    errors = []

    # --------------------------------------------------------
    # Process every new CSV
    # --------------------------------------------------------

    csv_inventory = inventory[
        inventory["csv_export_path"].notna()
    ].copy()

    total = len(csv_inventory)

    for counter, (_, record) in enumerate(
        csv_inventory.iterrows(),
        start=1,
    ):
        case_id = clean_text(
            record.get("case_id")
        )

        vehicle_number = clean_text(
            record.get("vehicle_number")
        )

        export_basename = clean_text(
            record.get("export_basename")
        )

        csv_path_text = clean_text(
            record.get("csv_export_path")
        )

        if not csv_path_text:
            continue

        path = Path(csv_path_text)

        if not path.exists():
            errors.append(
                {
                    "case_id": case_id,
                    "vehicle_number": vehicle_number,
                    "export_basename": export_basename,
                    "csv_path": csv_path_text,
                    "error": "source_missing",
                }
            )

            continue

        try:
            rows, encoding = read_csv_flexible(
                path
            )

        except Exception as exc:
            errors.append(
                {
                    "case_id": case_id,
                    "vehicle_number": vehicle_number,
                    "export_basename": export_basename,
                    "csv_path": csv_path_text,
                    "error": str(exc),
                }
            )

            continue

        # ----------------------------------------------------
        # Row scan
        # ----------------------------------------------------

        for row_index, row in enumerate(rows):

            if not row:
                continue

            cells = row_nonempty_cells(row)

            if not cells:
                continue

            # ================================================
            # LABEL OCCURRENCE
            # ================================================

            first_cell = clean_text(row[0])

            normalized_first = normalize_text(
                first_cell
            )

            if normalized_first in label_targets:

                (
                    section_index,
                    section_name,
                ) = find_current_section(
                    rows,
                    row_index,
                )

                context = get_neighbor_context(
                    rows,
                    row_index,
                )

                label_occurrences.append(
                    {
                        "case_id": case_id,
                        "vehicle_number": vehicle_number,
                        "export_basename": export_basename,
                        "csv_path": csv_path_text,
                        "csv_encoding": encoding,

                        "raw_label": label_targets[
                            normalized_first
                        ],
                        "matched_source_label": first_cell,

                        "source_row_number": row_index + 1,

                        "current_section": section_name,

                        "current_section_row_number": (
                            section_index + 1
                            if section_index is not None
                            else None
                        ),

                        "source_row_text": row_to_text(
                            row
                        ),

                        "source_row_json": row_to_json(
                            row
                        ),

                        "neighbor_context_json": json.dumps(
                            context,
                            ensure_ascii=False,
                        ),

                        "proposed_final_decision": "",
                        "proposed_final_family": "",
                        "review_notes": "",
                    }
                )

            # ================================================
            # SECTION OCCURRENCE
            # ================================================

            if looks_like_section_heading(row):

                section_text = cells[0]

                normalized_section = normalize_text(
                    section_text
                )

                if normalized_section in section_targets:

                    preview = get_section_preview(
                        rows,
                        row_index,
                    )

                    section_occurrences.append(
                        {
                            "case_id": case_id,
                            "vehicle_number": vehicle_number,
                            "export_basename": export_basename,
                            "csv_path": csv_path_text,
                            "csv_encoding": encoding,

                            "raw_section": section_targets[
                                normalized_section
                            ],

                            "matched_source_section": section_text,

                            "source_row_number": row_index + 1,

                            "section_preview_json": json.dumps(
                                preview,
                                ensure_ascii=False,
                            ),

                            "section_preview_text": "\n".join(
                                row_to_text(item["row"])
                                for item in preview
                                if row_to_text(item["row"])
                            ),

                            "proposed_final_decision": "",
                            "proposed_final_family": "",
                            "review_notes": "",
                        }
                    )

        if (
            counter % 50 == 0
            or counter == total
        ):
            print(
                f"Reviewed source context "
                f"{counter}/{total} new CSV reports"
            )

    # ========================================================
    # Outputs
    # ========================================================

    label_context_df = pd.DataFrame(
        label_occurrences
    )

    section_context_df = pd.DataFrame(
        section_occurrences
    )

    error_df = pd.DataFrame(
        errors
    )

    # --------------------------------------------------------
    # Target coverage
    # --------------------------------------------------------

    labels_found = set()

    if not label_context_df.empty:
        labels_found = set(
            label_context_df["raw_label"]
            .dropna()
            .astype(str)
        )

    sections_found = set()

    if not section_context_df.empty:
        sections_found = set(
            section_context_df["raw_section"]
            .dropna()
            .astype(str)
        )

    all_label_targets = set(
        label_targets.values()
    )

    all_section_targets = set(
        section_targets.values()
    )

    missing_labels = sorted(
        all_label_targets - labels_found
    )

    missing_sections = sorted(
        all_section_targets - sections_found
    )

    missing_label_df = pd.DataFrame(
        {
            "raw_label": missing_labels,
            "status": "target_not_found_in_new_csv_scan",
        }
    )

    missing_section_df = pd.DataFrame(
        {
            "raw_section": missing_sections,
            "status": "target_not_found_in_new_csv_scan",
        }
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = {
        "created_at": utc_now(),

        "purpose": (
            "Recover original CSV context for unresolved "
            "EDR rule-extension candidates."
        ),

        "new_reports_in_compatibility_audit": len(
            new_reports
        ),

        "new_csv_reports_scanned": int(
            len(csv_inventory)
        ),

        "label_review_targets": len(
            all_label_targets
        ),

        "section_review_targets": len(
            all_section_targets
        ),

        "label_occurrences_found": int(
            len(label_context_df)
        ),

        "unique_label_targets_found": len(
            labels_found
        ),

        "label_targets_not_found": len(
            missing_labels
        ),

        "section_occurrences_found": int(
            len(section_context_df)
        ),

        "unique_section_targets_found": len(
            sections_found
        ),

        "section_targets_not_found": len(
            missing_sections
        ),

        "source_errors": len(
            error_df
        ),

        "notes": [
            (
                "No Group 1-6 classification is changed "
                "by this script."
            ),
            (
                "Label decisions should use source section "
                "and neighboring row context."
            ),
            (
                "Section decisions should use the fields "
                "contained within each section."
            ),
            (
                "Standalone DTC codes remain diagnostic "
                "evidence until explicitly resolved."
            ),
        ],
    }

    # ========================================================
    # Save
    # ========================================================

    label_path = (
        OUTPUT_DIR
        / "edr_unresolved_label_context.csv"
    )

    section_path = (
        OUTPUT_DIR
        / "edr_unresolved_section_context.csv"
    )

    missing_label_path = (
        OUTPUT_DIR
        / "edr_unresolved_labels_not_found.csv"
    )

    missing_section_path = (
        OUTPUT_DIR
        / "edr_unresolved_sections_not_found.csv"
    )

    error_path = (
        OUTPUT_DIR
        / "edr_rule_review_context_errors.csv"
    )

    summary_path = (
        OUTPUT_DIR
        / "edr_rule_review_context_summary.json"
    )

    label_context_df.to_csv(
        label_path,
        index=False,
    )

    section_context_df.to_csv(
        section_path,
        index=False,
    )

    missing_label_df.to_csv(
        missing_label_path,
        index=False,
    )

    missing_section_df.to_csv(
        missing_section_path,
        index=False,
    )

    error_df.to_csv(
        error_path,
        index=False,
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

    # ========================================================
    # Console
    # ========================================================

    print()
    print("=" * 72)
    print("EDR RULE REVIEW CONTEXT EXTRACTION COMPLETE")
    print("=" * 72)

    print(
        f"New CSV reports scanned: "
        f"{len(csv_inventory)}"
    )

    print()

    print(
        f"Label review targets: "
        f"{len(all_label_targets)}"
    )

    print(
        f"Label occurrences found: "
        f"{len(label_context_df)}"
    )

    print(
        f"Unique label targets found: "
        f"{len(labels_found)}"
    )

    print(
        f"Label targets not found: "
        f"{len(missing_labels)}"
    )

    print()

    print(
        f"Section review targets: "
        f"{len(all_section_targets)}"
    )

    print(
        f"Section occurrences found: "
        f"{len(section_context_df)}"
    )

    print(
        f"Unique section targets found: "
        f"{len(sections_found)}"
    )

    print(
        f"Section targets not found: "
        f"{len(missing_sections)}"
    )

    print()

    print(
        f"Source errors: "
        f"{len(error_df)}"
    )

    print()

    print(
        f"Label context: {label_path}"
    )

    print(
        f"Section context: {section_path}"
    )

    print(
        f"Missing labels: {missing_label_path}"
    )

    print(
        f"Missing sections: {missing_section_path}"
    )

    print(
        f"Errors: {error_path}"
    )

    print(
        f"Summary: {summary_path}"
    )

    print("=" * 72)


if __name__ == "__main__":
    main()