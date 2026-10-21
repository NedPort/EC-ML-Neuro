from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path("data/processed/edr")
INPUT_DIR = ROOT / "rule_review_context_v1"
OUTPUT_DIR = ROOT / "rule_review_context_summary_v1"

LABEL_CONTEXT = INPUT_DIR / "edr_unresolved_label_context.csv"
SECTION_CONTEXT = INPUT_DIR / "edr_unresolved_section_context.csv"


def clean(value) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def unique_join(values, max_items=12) -> str:
    cleaned = []

    for value in values:
        value = clean(value)

        if value and value not in cleaned:
            cleaned.append(value)

    if len(cleaned) > max_items:
        return " || ".join(cleaned[:max_items]) + f" || ... +{len(cleaned)-max_items} more"

    return " || ".join(cleaned)


def main():
    if not LABEL_CONTEXT.exists():
        raise FileNotFoundError(LABEL_CONTEXT)

    if not SECTION_CONTEXT.exists():
        raise FileNotFoundError(SECTION_CONTEXT)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    labels = pd.read_csv(
        LABEL_CONTEXT,
        dtype=str,
        low_memory=False,
    )

    sections = pd.read_csv(
        SECTION_CONTEXT,
        dtype=str,
        low_memory=False,
    )

    # ========================================================
    # LABEL SUMMARY
    # ========================================================

    label_summary_rows = []

    for raw_label, group in labels.groupby(
        "raw_label",
        dropna=False,
        sort=True,
    ):
        section_counts = Counter(
            clean(x)
            for x in group["current_section"]
            if clean(x)
        )

        top_sections = " || ".join(
            f"{name} [{count}]"
            for name, count in section_counts.most_common(12)
        )

        example_rows = unique_join(
            group["source_row_text"].tolist(),
            max_items=8,
        )

        example_reports = unique_join(
            group["export_basename"].tolist(),
            max_items=8,
        )

        cases = sorted(
            {
                clean(x)
                for x in group["case_id"]
                if clean(x)
            }
        )

        label_summary_rows.append(
            {
                "raw_label": clean(raw_label),
                "occurrence_count": len(group),
                "report_count": group["export_basename"].nunique(),
                "case_count": len(cases),
                "distinct_section_count": len(section_counts),
                "top_sections": top_sections,
                "example_source_rows": example_rows,
                "example_reports": example_reports,
                "proposed_final_decision": "",
                "proposed_final_family": "",
                "review_notes": "",
            }
        )

    label_summary = pd.DataFrame(label_summary_rows)

    label_summary = label_summary.sort_values(
        ["occurrence_count", "raw_label"],
        ascending=[False, True],
    )

    # ========================================================
    # SECTION SUMMARY
    # ========================================================

    section_summary_rows = []

    for raw_section, group in sections.groupby(
        "raw_section",
        dropna=False,
        sort=True,
    ):
        preview_examples = unique_join(
            group["section_preview_text"].tolist(),
            max_items=5,
        )

        example_reports = unique_join(
            group["export_basename"].tolist(),
            max_items=8,
        )

        cases = sorted(
            {
                clean(x)
                for x in group["case_id"]
                if clean(x)
            }
        )

        section_summary_rows.append(
            {
                "raw_section": clean(raw_section),
                "occurrence_count": len(group),
                "report_count": group["export_basename"].nunique(),
                "case_count": len(cases),
                "example_section_contents": preview_examples,
                "example_reports": example_reports,
                "proposed_final_decision": "",
                "proposed_final_family": "",
                "review_notes": "",
            }
        )

    section_summary = pd.DataFrame(
        section_summary_rows
    )

    section_summary = section_summary.sort_values(
        ["occurrence_count", "raw_section"],
        ascending=[False, True],
    )

    # ========================================================
    # Save
    # ========================================================

    label_path = (
        OUTPUT_DIR
        / "edr_unresolved_label_context_summary.csv"
    )

    section_path = (
        OUTPUT_DIR
        / "edr_unresolved_section_context_summary.csv"
    )

    summary_path = (
        OUTPUT_DIR
        / "edr_rule_review_context_summary.json"
    )

    label_summary.to_csv(
        label_path,
        index=False,
    )

    section_summary.to_csv(
        section_path,
        index=False,
    )

    metadata = {
        "unique_unresolved_labels": len(label_summary),
        "label_occurrences": len(labels),
        "unique_unresolved_sections": len(section_summary),
        "section_occurrences": len(sections),
        "label_summary": str(label_path),
        "section_summary": str(section_path),
    }

    with summary_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata,
            f,
            indent=2,
        )

    print()
    print("=" * 72)
    print("EDR RULE REVIEW CONTEXT SUMMARY COMPLETE")
    print("=" * 72)

    print(
        f"Unique unresolved labels: "
        f"{len(label_summary)}"
    )

    print(
        f"Underlying label occurrences: "
        f"{len(labels)}"
    )

    print(
        f"Unique unresolved sections: "
        f"{len(section_summary)}"
    )

    print(
        f"Underlying section occurrences: "
        f"{len(sections)}"
    )

    print()

    print(f"Label summary: {label_path}")
    print(f"Section summary: {section_path}")
    print(f"Metadata: {summary_path}")

    print("=" * 72)


if __name__ == "__main__":
    main()