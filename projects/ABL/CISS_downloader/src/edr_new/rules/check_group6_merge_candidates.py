
"""Audit Group 6 merge candidates without modifying original data."""

from pathlib import Path
import pandas as pd

ROOT = Path("data/processed/edr_new/unified/group6")
REVIEW = ROOT / "feature_name_review"

WIDE = ROOT / "group6_unified_wide.csv"
CANDIDATES = REVIEW / "group6_merge_decisions.csv"
OUTPUT = REVIEW / "group6_merge_value_audit.csv"


def main():
    df = pd.read_csv(WIDE, dtype="string", keep_default_na=False)
    candidates = pd.read_csv(
        CANDIDATES, dtype="string", keep_default_na=False
    )

    out = []

    for _, r in candidates.iterrows():
        cols = [x.strip() for x in r["original_columns"].split("|")]

        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(
                f'Missing columns for {r["cleaned_title"]}: {missing}'
            )

        subset = df[cols].apply(
            lambda s: s.str.strip().replace("", pd.NA)
        )

        populated = subset.notna().sum(axis=1)
        overlap = populated.ge(2)
        conflict = subset.nunique(
            axis=1, dropna=True
        ).gt(1) & overlap

        overlap_count = int(overlap.sum())
        conflict_count = int(conflict.sum())

        if conflict_count:
            verdict = "REVIEW_CONFLICT"
        elif overlap_count:
            verdict = "REVIEW_OVERLAP_COMPATIBLE"
        else:
            verdict = "REVIEW_NO_OVERLAP"

        examples = []

        for i in df.index[conflict][:3]:
            rid = (
                str(df.at[i, "report_id"])
                if "report_id" in df.columns
                else str(i)
            )

            values = "; ".join(
                f"{c}={subset.at[i, c]}"
                for c in cols
                if pd.notna(subset.at[i, c])
            )

            examples.append(rid + ": " + values)

        out.append({
            "cleaned_title": r["cleaned_title"],
            "family": r["family"],
            "context": r["context"],
            "occurrence_slot": r["occurrence_slot"],
            "source_sections": r["source_sections"],
            "source_labels": r["source_labels"],
            "original_columns": r["original_columns"],
            "column_count": len(cols),
            "nonempty_cells": int(subset.notna().sum().sum()),
            "reports_with_any_value": int(populated.gt(0).sum()),
            "reports_with_multiple_values": overlap_count,
            "reports_with_conflicting_values": conflict_count,
            "audit_status": verdict,
            "sample_conflicts": " | ".join(examples),
            "decision": r["decision"],
            "notes": r["notes"],
        })

    audit = pd.DataFrame(out)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUTPUT, index=False)

    print(
        f"Original rows: {len(df):,}; "
        f"original columns: {len(df.columns):,}"
    )
    print(f"Candidate groups audited: {len(audit)}")
    print(audit["audit_status"].value_counts().to_string())
    print(f"Output: {OUTPUT}")
    print("No original values or columns changed.")


if __name__ == "__main__":
    main()
