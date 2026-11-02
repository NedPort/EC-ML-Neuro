from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

INPUT = Path(
    "data/processed/edr_new/validation/stage2_unseen/"
    "stage2_unseen_report_summary.csv"
)

OUT = Path(
    "data/processed/edr_new/validation/stage3_manual_benchmark"
)

N_CSV = 24
N_PDF = 6

KEY = ("case_id", "vehicle_number", "export_basename")


def norm(v: Any) -> str:
    return " ".join(str(v if v is not None else "").split())


def truthy(v: Any) -> bool:
    return norm(v).casefold() in {"true", "1", "yes", "y"}


def read_csv(path: Path):
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows, columns=None):
    path.parent.mkdir(parents=True, exist_ok=True)

    if columns is None:
        columns = []
        seen = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    columns.append(k)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def group_vector(row):
    return tuple(
        int(truthy(row.get(f"group{i}_has_output", False)))
        for i in range(1, 7)
    )


def group_count(row):
    return sum(group_vector(row))


def select_diverse(rows, n):
    """
    Deterministic greedy selection.

    Priority:
    1. maximize coverage of underrepresented group-presence patterns,
    2. prefer reports with more extraction groups,
    3. diversify by pattern,
    4. stable lexical order for reproducibility.
    """
    rows = sorted(
        rows,
        key=lambda r: (
            -group_count(r),
            norm(r.get("report_id", "")),
            norm(r.get("case_id", "")),
            norm(r.get("vehicle_number", "")),
            norm(r.get("export_basename", "")),
        ),
    )

    selected = []
    remaining = list(rows)
    pattern_counts = Counter()
    group_counts = Counter()

    while remaining and len(selected) < n:
        best = None
        best_score = None

        for row in remaining:
            vec = group_vector(row)
            pattern = "".join(map(str, vec))

            # Reward groups that are currently underrepresented.
            rare_group_bonus = sum(
                1.0 / (1 + group_counts[i])
                for i, present in enumerate(vec, 1)
                if present
            )

            # Reward a new group-presence pattern.
            pattern_bonus = 3.0 / (1 + pattern_counts[pattern])

            # Prefer broader coverage.
            coverage_bonus = group_count(row) * 0.25

            score = (
                rare_group_bonus
                + pattern_bonus
                + coverage_bonus
            )

            tie = (
                score,
                group_count(row),
                norm(row.get("report_id", "")),
                norm(row.get("export_basename", "")),
            )

            if best_score is None or tie > best_score:
                best_score = tie
                best = row

        selected.append(best)
        remaining.remove(best)

        vec = group_vector(best)
        pattern = "".join(map(str, vec))
        pattern_counts[pattern] += 1

        for i, present in enumerate(vec, 1):
            if present:
                group_counts[i] += 1

    return selected


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Missing Stage 2 report summary:\n{INPUT}"
        )

    rows = read_csv(INPUT)

    csv_rows = [
        r for r in rows
        if norm(r.get("source_format", "")).casefold() == "csv"
    ]

    pdf_rows = [
        r for r in rows
        if norm(r.get("source_format", "")).casefold() == "pdf"
    ]

    if len(csv_rows) < N_CSV:
        raise RuntimeError(
            f"Need at least {N_CSV} unseen CSV reports; found {len(csv_rows)}"
        )

    if len(pdf_rows) < N_PDF:
        raise RuntimeError(
            f"Need at least {N_PDF} unseen PDF reports; found {len(pdf_rows)}"
        )

    selected_csv = select_diverse(csv_rows, N_CSV)
    selected_pdf = select_diverse(pdf_rows, N_PDF)

    selected = selected_csv + selected_pdf

    # Stable benchmark IDs.
    selection_rows = []

    for idx, row in enumerate(selected, 1):
        vec = group_vector(row)

        selection_rows.append({
            "benchmark_report_id": f"B{idx:02d}",
            "report_id": norm(row.get("report_id", "")),
            "case_id": norm(row.get("case_id", "")),
            "vehicle_number": norm(row.get("vehicle_number", "")),
            "export_basename": norm(row.get("export_basename", "")),
            "source_format": norm(row.get("source_format", "")).lower(),
            "groups_with_output": group_count(row),
            "group1_has_output": vec[0],
            "group2_has_output": vec[1],
            "group3_has_output": vec[2],
            "group4_has_output": vec[3],
            "group5_has_output": vec[4],
            "group6_has_output": vec[5],
        })

    OUT.mkdir(parents=True, exist_ok=True)

    selection_path = OUT / "stage3_benchmark_report_selection.csv"

    write_csv(
        selection_path,
        selection_rows,
        [
            "benchmark_report_id",
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "source_format",
            "groups_with_output",
            "group1_has_output",
            "group2_has_output",
            "group3_has_output",
            "group4_has_output",
            "group5_has_output",
            "group6_has_output",
        ],
    )

    # --------------------------------------------------------
    # Manual review plan
    # --------------------------------------------------------
    # The plan keeps the workload manageable while checking
    # every available group in every selected report.
    target_items = {
        1: 3,  # metadata/documentation fields
        2: 2,  # event/retrieval records
        3: 5,  # status/condition values
        4: 5,  # structural/time-series checks or sampled values
        5: 3,  # scalar measurements
        6: 3,  # technical/module fields
    }

    plan_rows = []

    for report in selection_rows:
        for group in range(1, 7):
            if int(report[f"group{group}_has_output"]) != 1:
                continue

            for item_no in range(1, target_items[group] + 1):
                plan_rows.append({
                    "benchmark_report_id":
                        report["benchmark_report_id"],
                    "report_id":
                        report["report_id"],
                    "case_id":
                        report["case_id"],
                    "vehicle_number":
                        report["vehicle_number"],
                    "export_basename":
                        report["export_basename"],
                    "source_format":
                        report["source_format"],
                    "group":
                        f"group{group}",
                    "review_item_number":
                        item_no,
                    "source_location":
                        "",
                    "source_label":
                        "",
                    "source_value":
                        "",
                    "source_unit":
                        "",
                    "extracted_label":
                        "",
                    "extracted_value":
                        "",
                    "extracted_unit":
                        "",
                    "record_present_in_source":
                        "",
                    "record_present_in_extraction":
                        "",
                    "label_correct":
                        "",
                    "value_correct":
                        "",
                    "unit_correct":
                        "",
                    "provenance_correct":
                        "",
                    "manual_result":
                        "",
                    "notes":
                        "",
                })

    template_path = OUT / "stage3_manual_benchmark.csv"

    write_csv(
        template_path,
        plan_rows,
        [
            "benchmark_report_id",
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "source_format",
            "group",
            "review_item_number",
            "source_location",
            "source_label",
            "source_value",
            "source_unit",
            "extracted_label",
            "extracted_value",
            "extracted_unit",
            "record_present_in_source",
            "record_present_in_extraction",
            "label_correct",
            "value_correct",
            "unit_correct",
            "provenance_correct",
            "manual_result",
            "notes",
        ],
    )

    # --------------------------------------------------------
    # Review instructions
    # --------------------------------------------------------
    instructions = """STAGE 3 MANUAL BENCHMARK

Purpose
-------
Directly compare the pipeline output against the original source CSV/PDF.

For every row in stage3_manual_benchmark.csv:

1. Open the original source CSV or PDF for that report.
2. Choose one item from the indicated group.
3. Record where it appears in the source:
   - CSV row/section, or
   - PDF page/table/section.
4. Copy the source label/value/unit exactly.
5. Find the corresponding extracted item in edr_new.
6. Copy the extracted label/value/unit.
7. Fill:
   record_present_in_source
   record_present_in_extraction
   label_correct
   value_correct
   unit_correct
   provenance_correct

Use TRUE / FALSE for these fields.

manual_result must be one of:
   correct
   incorrect
   missing
   extra
   not_applicable

Definitions
-----------
correct:
    The intended source item is present and the extracted scientific
    content is correct.

incorrect:
    The record is present in both source and extraction, but one or
    more scientifically relevant fields are wrong.

missing:
    The item exists in the source but the pipeline failed to extract it.

extra:
    The pipeline extracted an item that is not supported by the source.

not_applicable:
    Use only when the planned review item cannot reasonably be scored
    for that report/group. Explain why in notes.

Suggested checks by group
-------------------------
Group 1:
    metadata fields such as VIN, imaging/reporting version, dates,
    filename, device type, documentation.

Group 2:
    event-record/retrieval descriptors and record status.

Group 3:
    event conditions, deployment/status fields, raw values and units.

Group 4:
    verify one series structurally, then sample values from the series.
    Prefer first, middle and last samples plus additional interior samples.

Group 5:
    scalar crash measurements, raw values and units.

Group 6:
    technical/module/configuration fields, values and provenance.

Important
---------
Do not infer or "correct" the source manually.
The source document is the benchmark reference.
Record exactly what is visibly present.
"""

    instructions_path = OUT / "README_stage3_manual_review.txt"
    instructions_path.write_text(
        instructions,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Terminal summary
    # --------------------------------------------------------
    source_counts = Counter(
        r["source_format"]
        for r in selection_rows
    )

    print("=" * 88)
    print("STAGE 3 BENCHMARK SELECTION")
    print("=" * 88)
    print(
        f"Selected reports:  {len(selection_rows)} "
        f"({source_counts['csv']} CSV / {source_counts['pdf']} PDF)"
    )
    print(
        f"Manual review rows: {len(plan_rows)}"
    )
    print()

    for r in selection_rows:
        groups = [
            f"G{i}"
            for i in range(1, 7)
            if int(r[f"group{i}_has_output"]) == 1
        ]

        display_id = (
            r["report_id"]
            or (
                f"{r['case_id']}_"
                f"{r['vehicle_number']}_"
                f"{r['export_basename']}"
            )
        )

        print(
            f"{r['benchmark_report_id']}  "
            f"{r['source_format'].upper():3s}  "
            f"{display_id:<45} "
            f"{','.join(groups)}"
        )

    print()
    print("Saved:")
    print(selection_path)
    print(template_path)
    print(instructions_path)


if __name__ == "__main__":
    main()
