from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

csv.field_size_limit(200_000_000)

ROOT = Path("data/processed/edr_new")
OUT = ROOT / "validation" / "stage2_unseen"

KEY = ("case_id", "vehicle_number", "export_basename")


def norm(v: Any) -> str:
    return " ".join(str(v if v is not None else "").split())


def truthy(v: Any) -> bool:
    return norm(v).casefold() in {"true", "1", "yes", "y"}


def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return

    cols, seen = [], set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                cols.append(k)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def key(row):
    return tuple(norm(row.get(k, "")) for k in KEY)


def historical_flag(row):
    # supports likely manifest spellings
    for field in (
        "historical_population",
        "is_historical",
        "historical",
    ):
        if field in row:
            return truthy(row.get(field))
    return False


def report_id(row):
    return norm(row.get("report_id", ""))


def extract_keys(rows):
    return {key(r) for r in rows if any(key(r))}


def subset_unseen(rows, unseen_keys):
    if not rows:
        return []
    headers = set(rows[0])

    # Direct report identity available
    if all(k in headers for k in KEY):
        return [r for r in rows if key(r) in unseen_keys]

    return rows


def detect_review(row):
    candidates = [
        "requires_review",
        "review_required",
        "needs_review",
    ]
    for c in candidates:
        if c in row and truthy(row.get(c)):
            return True

    for c in (
        "review_reason",
        "issue",
        "issues",
        "unresolved_reason",
    ):
        if c in row and norm(row.get(c)):
            return True

    return False


def detect_unresolved(row):
    for c in (
        "status",
        "processing_status",
        "audit_status",
        "resolution_status",
    ):
        value = norm(row.get(c, "")).casefold()
        if any(token in value for token in (
            "unresolved",
            "requires_review",
            "needs_review",
            "failed",
            "error",
        )):
            return True
    return False


def main():
    manifest_path = ROOT / "report_manifest.csv"
    manifest = read_csv(manifest_path)

    if not manifest:
        raise FileNotFoundError(f"Missing or empty manifest: {manifest_path}")

    unseen_reports = [
        r for r in manifest
        if not historical_flag(r)
    ]

    unseen_keys = extract_keys(unseen_reports)
    unseen_report_ids = {
        report_id(r)
        for r in unseen_reports
        if report_id(r)
    }

    source_counts = Counter(
        norm(r.get("source_format", "")).casefold()
        for r in unseen_reports
    )

    report_status_counts = Counter(
        norm(r.get("status", r.get("report_status", "")))
        for r in unseen_reports
    )

    # ------------------------------------------------------------
    # Group file inventory
    # ------------------------------------------------------------
    group_files = {
        "group1": [
            "fields.csv",
            "documentation.csv",
        ],
        "group2": [
            "record_candidates.csv",
            "record_status.csv",
            "retrieval_status.csv",
            "retrieval_event_descriptors.csv",
        ],
        "group3": [
            "conditions.csv",
            "values.csv",
            "explicit_review_evidence.csv",
        ],
        "group4": [
            "series.csv",
            "signals.csv",
            "samples.csv",
            "values.csv",
            "companion_metadata.csv",
            "graphical_review.csv",
            "unresolved.csv",
        ],
        "group5": [
            "measurements.csv",
            "values.csv",
            "companion_context.csv",
        ],
        "group6": [
            "technical_registry.csv",
            "technical_values.csv",
            "explicit_review_evidence.csv",
        ],
    }

    group_summary = []
    review_items = []
    per_report = {
        k: {
            "case_id": k[0],
            "vehicle_number": k[1],
            "export_basename": k[2],
        }
        for k in unseen_keys
    }

    # Seed report-level manifest info
    manifest_by_key = {key(r): r for r in unseen_reports}
    for k, row in manifest_by_key.items():
        if k not in per_report:
            continue
        per_report[k].update({
            "report_id": report_id(row),
            "source_format": norm(row.get("source_format", "")),
            "report_status": norm(row.get("status", row.get("report_status", ""))),
        })

    # ID maps for tables without report-level identity
    g3_condition_to_key = {}
    g6_technical_to_key = {}
    g4_series_to_key = {}
    g4_sample_to_key = {}
    g4_signal_to_key = {}
    g5_measurement_to_key = {}

    # Build maps from registry-like tables
    for path, id_col, target in [
        (ROOT/"group3"/"conditions.csv", "group3_condition_id", g3_condition_to_key),
        (ROOT/"group6"/"technical_registry.csv", "group6_technical_id", g6_technical_to_key),
        (ROOT/"group4"/"series.csv", "series_id", g4_series_to_key),
        (ROOT/"group5"/"measurements.csv", "measurement_id", g5_measurement_to_key),
    ]:
        rows = read_csv(path)
        for r in rows:
            k = key(r)
            if k in unseen_keys:
                ident = norm(r.get(id_col, ""))
                if ident:
                    target[ident] = k

    # Group 4 sample/signal maps
    for r in read_csv(ROOT/"group4"/"samples.csv"):
        sid = norm(r.get("series_id", ""))
        if sid in g4_series_to_key:
            sample_id = norm(r.get("sample_id", ""))
            if sample_id:
                g4_sample_to_key[sample_id] = g4_series_to_key[sid]

    for r in read_csv(ROOT/"group4"/"signals.csv"):
        sid = norm(r.get("series_id", ""))
        if sid in g4_series_to_key:
            signal_id = norm(r.get("signal_id", ""))
            if signal_id:
                g4_signal_to_key[signal_id] = g4_series_to_key[sid]

    # ------------------------------------------------------------
    # Table-level analysis
    # ------------------------------------------------------------
    for group, files in group_files.items():
        group_report_keys = set()
        group_total_rows = 0
        group_review_rows = 0
        group_unresolved_rows = 0

        for fname in files:
            path = ROOT / group / fname
            rows = read_csv(path)
            if not rows:
                continue

            selected = []

            headers = set(rows[0])

            # Registry tables that directly carry report identity
            if all(k in headers for k in KEY):
                selected = [r for r in rows if key(r) in unseen_keys]

            # Group 3 child tables inherit report identity through group3_condition_id
            elif group == "group3" and "group3_condition_id" in headers:
                selected = [
                    r for r in rows
                    if norm(r.get("group3_condition_id", "")) in g3_condition_to_key
                ]

            # Group 6 child tables inherit report identity through group6_technical_id
            elif group == "group6" and "group6_technical_id" in headers:
                selected = [
                    r for r in rows
                    if norm(r.get("group6_technical_id", "")) in g6_technical_to_key
                ]

            elif group == "group4":
                if "series_id" in headers:
                    selected = [
                        r for r in rows
                        if norm(r.get("series_id", "")) in g4_series_to_key
                    ]
                elif "sample_id" in headers:
                    selected = [
                        r for r in rows
                        if norm(r.get("sample_id", "")) in g4_sample_to_key
                    ]
                elif "signal_id" in headers:
                    selected = [
                        r for r in rows
                        if norm(r.get("signal_id", "")) in g4_signal_to_key
                    ]

            elif group == "group5" and "measurement_id" in headers:
                selected = [
                    r for r in rows
                    if norm(r.get("measurement_id", "")) in g5_measurement_to_key
                ]

            group_total_rows += len(selected)

            file_report_keys = set()

            for r in selected:
                rk = None

                if all(k in r for k in KEY):
                    candidate = key(r)
                    if candidate in unseen_keys:
                        rk = candidate

                if rk is None:
                    if group == "group3" and "group3_condition_id" in r:
                        rk = g3_condition_to_key.get(
                            norm(r.get("group3_condition_id", ""))
                        )
                    elif group == "group6" and "group6_technical_id" in r:
                        rk = g6_technical_to_key.get(
                            norm(r.get("group6_technical_id", ""))
                        )
                    elif group == "group4":
                        rk = (
                            g4_series_to_key.get(norm(r.get("series_id", "")))
                            or g4_sample_to_key.get(norm(r.get("sample_id", "")))
                            or g4_signal_to_key.get(norm(r.get("signal_id", "")))
                        )
                    elif group == "group5" and "measurement_id" in r:
                        rk = g5_measurement_to_key.get(
                            norm(r.get("measurement_id", ""))
                        )

                if rk is not None:
                    file_report_keys.add(rk)
                    group_report_keys.add(rk)

                    per_report[rk][f"{group}_row_count"] = (
                        int(per_report[rk].get(f"{group}_row_count", 0)) + 1
                    )

                if detect_review(r):
                    group_review_rows += 1
                    review_items.append({
                        "group": group,
                        "file": fname,
                        "case_id": rk[0] if rk else "",
                        "vehicle_number": rk[1] if rk else "",
                        "export_basename": rk[2] if rk else "",
                        "report_id": report_id(r),
                        "review_reason": norm(
                            r.get(
                                "review_reason",
                                r.get("issue", r.get("issues", ""))
                            )
                        ),
                        "status": norm(
                            r.get(
                                "status",
                                r.get("processing_status", r.get("audit_status", ""))
                            )
                        ),
                    })

                if detect_unresolved(r):
                    group_unresolved_rows += 1

            group_summary.append({
                "group": group,
                "file": fname,
                "unseen_rows": len(selected),
                "reports_with_rows": len(file_report_keys),
                "review_rows": sum(1 for r in selected if detect_review(r)),
                "unresolved_or_failure_rows": sum(1 for r in selected if detect_unresolved(r)),
            })

        # summary row per group
        group_summary.append({
            "group": group,
            "file": "__GROUP_TOTAL__",
            "unseen_rows": group_total_rows,
            "reports_with_rows": len(group_report_keys),
            "review_rows": group_review_rows,
            "unresolved_or_failure_rows": group_unresolved_rows,
        })

        for rk in unseen_keys:
            per_report[rk][f"{group}_has_output"] = rk in group_report_keys

    # ------------------------------------------------------------
    # Pipeline errors / review logs
    # ------------------------------------------------------------
    pipeline_errors = read_csv(ROOT / "pipeline_errors.csv")
    pipeline_review = read_csv(ROOT / "pipeline_review.csv")

    unseen_errors = [
        r for r in pipeline_errors
        if key(r) in unseen_keys
        or report_id(r) in unseen_report_ids
    ]

    unseen_pipeline_review = [
        r for r in pipeline_review
        if key(r) in unseen_keys
        or report_id(r) in unseen_report_ids
    ]

    # ------------------------------------------------------------
    # Novelty indicators vs historical population
    # Conservative: compare raw labels/headings/families where available.
    # ------------------------------------------------------------
    novelty_rows = []

    novelty_specs = [
        ("group1", ROOT/"group1"/"fields.csv", ["field_name", "field_label_raw"]),
        ("group2", ROOT/"group2"/"record_candidates.csv", ["field_label_raw", "source_heading"]),
        ("group3", ROOT/"group3"/"conditions.csv", ["field_label_raw", "family", "source_section_heading"]),
        ("group4", ROOT/"group4"/"series.csv", ["source_heading_hint", "family", "component"]),
        ("group5", ROOT/"group5"/"measurements.csv", ["field_label_raw", "family"]),
        ("group6", ROOT/"group6"/"technical_registry.csv", ["field_label_raw", "family"]),
    ]

    for group, path, fields in novelty_specs:
        rows = read_csv(path)
        if not rows:
            continue

        historical_rows = [
            r for r in rows
            if all(k in r for k in KEY) and key(r) not in unseen_keys
        ]
        unseen_rows = [
            r for r in rows
            if all(k in r for k in KEY) and key(r) in unseen_keys
        ]

        for field in fields:
            if field not in rows[0]:
                continue

            hist_values = {
                norm(r.get(field, ""))
                for r in historical_rows
                if norm(r.get(field, ""))
            }

            unseen_counts = Counter(
                norm(r.get(field, ""))
                for r in unseen_rows
                if norm(r.get(field, ""))
            )

            for value, count in unseen_counts.items():
                if value not in hist_values:
                    novelty_rows.append({
                        "group": group,
                        "field": field,
                        "new_value": value,
                        "unseen_occurrences": count,
                    })

    # ------------------------------------------------------------
    # Final report-level output
    # ------------------------------------------------------------
    report_rows = []
    for rk in sorted(unseen_keys):
        row = per_report[rk]
        row["any_group_output"] = any(
            truthy(row.get(f"group{i}_has_output", False))
            for i in range(1, 7)
        )
        row["groups_with_output"] = sum(
            truthy(row.get(f"group{i}_has_output", False))
            for i in range(1, 7)
        )
        report_rows.append(row)

    reports_with_any_output = sum(
        1 for r in report_rows
        if truthy(r.get("any_group_output"))
    )

    reports_with_all_6 = sum(
        1 for r in report_rows
        if int(r.get("groups_with_output", 0)) == 6
    )

    # ------------------------------------------------------------
    # Linkage sanity checks for child tables
    # ------------------------------------------------------------
    linkage_checks = {
        "group3_condition_ids_in_unseen": len(g3_condition_to_key),
        "group6_technical_ids_in_unseen": len(g6_technical_to_key),
        "group4_series_ids_in_unseen": len(g4_series_to_key),
        "group5_measurement_ids_in_unseen": len(g5_measurement_to_key),
    }

    overall_status = "PASS"
    reasons = []

    if len(unseen_reports) != 431:
        overall_status = "NEEDS_REVIEW"
        reasons.append(f"Expected 431 unseen reports, found {len(unseen_reports)}")

    if source_counts.get("csv", 0) != 398 or source_counts.get("pdf", 0) != 33:
        overall_status = "NEEDS_REVIEW"
        reasons.append(
            f"Expected unseen split 398 CSV / 33 PDF, found "
            f"{source_counts.get('csv',0)} CSV / {source_counts.get('pdf',0)} PDF"
        )

    if unseen_errors:
        overall_status = "NEEDS_REVIEW"
        reasons.append(f"{len(unseen_errors)} pipeline error rows found")

    summary = {
        "stage": "Stage 2 - Unseen report evaluation",
        "overall_status": overall_status,
        "unseen_report_count": len(unseen_reports),
        "unseen_unique_report_keys": len(unseen_keys),
        "source_counts": dict(source_counts),
        "report_status_counts": dict(report_status_counts),
        "reports_with_any_group_output": reports_with_any_output,
        "reports_with_all_six_groups_output": reports_with_all_6,
        "pipeline_error_rows": len(unseen_errors),
        "pipeline_review_rows": len(unseen_pipeline_review),
        "review_items_detected": len(review_items),
        "novel_unseen_values": len(novelty_rows),
        "linkage_checks": linkage_checks,
        "notes": reasons,
        "interpretation": (
            "Stage 2 evaluates operational generalization on previously unseen reports. "
            "It does not independently establish source-level extraction accuracy."
        ),
    }

    OUT.mkdir(parents=True, exist_ok=True)

    write_csv(OUT/"stage2_unseen_report_summary.csv", report_rows)
    write_csv(OUT/"stage2_unseen_group_summary.csv", group_summary)
    write_csv(OUT/"stage2_unseen_review_items.csv", review_items)
    write_csv(OUT/"stage2_unseen_errors.csv", unseen_errors)
    write_csv(OUT/"stage2_unseen_novelty.csv", novelty_rows)

    (OUT/"stage2_unseen_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("=" * 100)
    print("STAGE 2 — UNSEEN REPORT EVALUATION")
    print("=" * 100)
    print(f"Unseen reports:                  {len(unseen_reports)}")
    print(f"Unique unseen report keys:       {len(unseen_keys)}")
    print(f"Source split:                    {source_counts.get('csv',0)} CSV / {source_counts.get('pdf',0)} PDF")
    print(f"Reports with any group output:   {reports_with_any_output}")
    print(f"Reports with all 6 groups:       {reports_with_all_6}")
    print(f"Pipeline error rows:             {len(unseen_errors)}")
    print(f"Pipeline review rows:            {len(unseen_pipeline_review)}")
    print(f"Review items detected:           {len(review_items)}")
    print(f"Novel unseen values/headings:    {len(novelty_rows)}")
    print(f"Group 3 unseen condition IDs:    {len(g3_condition_to_key)}")
    print(f"Group 6 unseen technical IDs:    {len(g6_technical_to_key)}")
    print()
    print("STATUS:", overall_status)

    if reasons:
        print("\nReasons:")
        for x in reasons:
            print(" -", x)

    print("\nSaved:")
    for p in [
        OUT/"stage2_unseen_report_summary.csv",
        OUT/"stage2_unseen_group_summary.csv",
        OUT/"stage2_unseen_review_items.csv",
        OUT/"stage2_unseen_errors.csv",
        OUT/"stage2_unseen_novelty.csv",
        OUT/"stage2_unseen_summary.json",
    ]:
        print(p)


if __name__ == "__main__":
    main()
