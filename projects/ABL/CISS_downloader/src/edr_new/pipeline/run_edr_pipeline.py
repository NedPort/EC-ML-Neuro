from __future__ import annotations

"""
Production EDR pipeline for Groups 1-6.

Population
----------
Reads the full EDR inventory and applies the validated reusable Group 1-6
extractors to every report.

Source policy
-------------
Source is selected ONCE per report:

    CSV exists -> CSV only
    otherwise  -> PDF only

The non-selected source is not passed to any group extractor.

Outputs
-------
Default output root:

    data/processed/edr_new/

Each group is written to its own directory. Rows are streamed through temporary
JSONL files and finalized to CSV at the end so the pipeline does not need to
hold large Group 4 datasets in memory.

Top-level outputs:

    report_manifest.csv
    pipeline_errors.csv
    pipeline_review.csv
    metadata.json
"""

import argparse
import csv
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.edr_new.rules.group_1_r import (
    RULE_VERSION as GROUP1_VERSION,
    extract_group1_report,
)
from src.edr_new.rules.group_2_r import (
    RULE_VERSION as GROUP2_VERSION,
    extract_group2_report,
)
from src.edr_new.rules.group_3_r import (
    RULE_VERSION as GROUP3_VERSION,
    extract_group3_report,
)
from src.edr_new.rules.group_4_r import (
    RULE_VERSION as GROUP4_VERSION,
    extract_group4_report,
)
from src.edr_new.rules.group_5_r import (
    RULE_VERSION as GROUP5_VERSION,
    extract_group5_report,
)
from src.edr_new.rules.group_6_r import (
    RULE_VERSION as GROUP6_VERSION,
    extract_group6_report,
)


csv.field_size_limit(100_000_000)


DEFAULT_INVENTORY = Path(
    "data/processed/edr/edr_export_inventory.csv"
)

DEFAULT_HISTORICAL_COVERAGE = Path(
    "data/processed/edr/group2_final_v1/report_coverage.csv"
)

DEFAULT_OUTPUT = Path(
    "data/processed/edr_new"
)


IDENTITY_COLUMNS = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


# ============================================================
# Group output schemas
# ============================================================

GROUP_OUTPUTS = {
    "group1": {
        "fields": "fields",
        "documentation": "documentation",
    },
    "group2": {
        "record_candidates": "record_candidates",
        "record_status": "record_status",
        "retrieval_status": "retrieval_status",
        "context_status": "context_status",
        "summary_rows": "summary_rows",
        "summary_cells": "summary_cells",
        "retrieval_event_descriptors":
            "retrieval_event_descriptors",
        "pdf_fields": "pdf_fields",
        "pdf_unresolved": "pdf_unresolved",
        "group4_handoff_sections":
            "group4_handoff_sections",
        "group4_handoff_rows":
            "group4_handoff_rows",
    },
    "group3": {
        "conditions": "conditions",
        "values": "values",
        "explicit_review_evidence":
            "explicit_review_evidence",
        "excluded": "excluded",
        "unresolved": "unresolved",
    },
    "group4": {
        "series": "series",
        "signals": "signals",
        "samples": "samples",
        "values": "values",
        "companion_metadata":
            "companion_metadata",
        "graphical_review":
            "graphical_review",
        "excluded": "excluded",
        "unresolved": "unresolved",
    },
    "group5": {
        "measurements": "measurements",
        "values": "values",
        "companion_context":
            "companion_context",
        "excluded": "excluded",
        "unresolved": "unresolved",
    },
    "group6": {
        "technical_registry":
            "technical_registry",
        "technical_values":
            "technical_values",
        "review_evidence":
            "explicit_review_evidence",
        "excluded": "excluded",
        "unresolved": "unresolved",
    },
}


GROUP_EXTRACTORS = {
    "group1": extract_group1_report,
    "group2": extract_group2_report,
    "group3": extract_group3_report,
    "group4": extract_group4_report,
    "group5": extract_group5_report,
    "group6": extract_group6_report,
}


GROUP_VERSIONS = {
    "group1": GROUP1_VERSION,
    "group2": GROUP2_VERSION,
    "group3": GROUP3_VERSION,
    "group4": GROUP4_VERSION,
    "group5": GROUP5_VERSION,
    "group6": GROUP6_VERSION,
}


# ============================================================
# Basic helpers
# ============================================================

def norm(value: Any) -> str:
    return " ".join(
        str(
            value
            if value is not None
            else ""
        ).split()
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def first_value(
    row: dict[str, Any],
    *keys: str,
) -> str:
    for key in keys:
        value = norm(row.get(key, ""))
        if value:
            return value
    return ""


def report_key(
    row: dict[str, Any],
) -> tuple[str, str, str]:
    return (
        norm(row.get("case_id", "")),
        norm(row.get("vehicle_number", "")),
        norm(row.get("export_basename", "")),
    )


def resolve_source_path(
    raw: str,
    project_root: Path,
) -> Path | None:
    raw = norm(raw)

    if not raw:
        return None

    path = Path(raw)

    if path.is_file():
        return path

    if not path.is_absolute():
        candidate = project_root / path
        if candidate.is_file():
            return candidate

    return None


def select_source_once(
    row: dict[str, Any],
    project_root: Path,
) -> tuple[str, Path]:
    csv_raw = first_value(
        row,
        "csv_export_path",
        "csv_path",
        "source_csv_path",
    )

    pdf_raw = first_value(
        row,
        "pdf_export_path",
        "pdf_path",
        "source_pdf_path",
    )

    csv_path = resolve_source_path(
        csv_raw,
        project_root,
    )

    pdf_path = resolve_source_path(
        pdf_raw,
        project_root,
    )

    if csv_path is not None:
        return "csv", csv_path

    if pdf_path is not None:
        return "pdf", pdf_path

    raise FileNotFoundError(
        "No usable CSV or PDF source for "
        f"{report_key(row)}"
    )


def build_historical_id_map(
    path: Path | None,
) -> dict[tuple[str, str, str], str]:
    if path is None or not path.is_file():
        return {}

    rows = read_csv(path)

    result = {}

    for row in rows:
        key = report_key(row)
        report_id = norm(
            row.get("report_id", "")
        )

        if all(key) and report_id:
            result[key] = report_id

    return result


def make_identity(
    row: dict[str, Any],
    historical_ids:
        dict[tuple[str, str, str], str],
) -> dict[str, str]:
    key = report_key(row)

    report_id = (
        historical_ids.get(key, "")
        or norm(row.get("report_id", ""))
    )

    if not report_id:
        # Stable fallback only for reports that do not already
        # have the historical/frozen report identifier.
        report_id = (
            f"{key[0]}_"
            f"{key[1]}_"
            f"{key[2]}"
        )

    return {
        "report_id": report_id,
        "case_id": key[0],
        "vehicle_number": key[1],
        "export_basename": key[2],
    }


def json_default(value: Any):
    if isinstance(value, Path):
        return str(value)

    if isinstance(value, set):
        return sorted(value)

    return str(value)


def csv_value(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(
        value,
        (dict, list, tuple, set),
    ):
        return json.dumps(
            value,
            ensure_ascii=False,
            default=json_default,
            sort_keys=True,
        )

    return value


# ============================================================
# Streaming dataset writer
# ============================================================

class DatasetSpool:
    """
    Stream rows to JSONL while tracking the union of columns.
    At finalize(), convert JSONL -> CSV and remove the temporary file.
    """

    def __init__(
        self,
        csv_path: Path,
        preferred_columns:
            list[str] | None = None,
    ):
        self.csv_path = csv_path
        self.tmp_path = csv_path.with_suffix(
            ".jsonl.part"
        )

        self.csv_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.preferred_columns = list(
            preferred_columns
            or IDENTITY_COLUMNS
        )

        self.columns = []
        self._seen = set()

        for column in self.preferred_columns:
            self._add_column(column)

        self.row_count = 0

        self._handle = self.tmp_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        )

    def _add_column(
        self,
        column: str,
    ):
        if column not in self._seen:
            self._seen.add(column)
            self.columns.append(column)

    def write(
        self,
        row: dict[str, Any],
    ):
        clean_row = {}

        for key, value in row.items():
            self._add_column(str(key))
            clean_row[str(key)] = value

        self._handle.write(
            json.dumps(
                clean_row,
                ensure_ascii=False,
                default=json_default,
                sort_keys=False,
            )
            + "\n"
        )

        self.row_count += 1

    def write_many(
        self,
        rows: list[dict[str, Any]],
    ):
        for row in rows:
            self.write(row)

    def finalize(self):
        if not self._handle.closed:
            self._handle.close()

        # Always create a valid CSV, even when no rows were produced.
        with self.csv_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as out:
            writer = csv.DictWriter(
                out,
                fieldnames=self.columns,
                extrasaction="ignore",
            )

            writer.writeheader()

            if self.row_count:
                with self.tmp_path.open(
                    "r",
                    encoding="utf-8",
                ) as src:
                    for line in src:
                        row = json.loads(line)

                        writer.writerow({
                            key:
                                csv_value(
                                    row.get(
                                        key,
                                        "",
                                    )
                                )
                            for key
                            in self.columns
                        })

        if self.tmp_path.exists():
            self.tmp_path.unlink()


# ============================================================
# Pipeline output manager
# ============================================================

class PipelineOutputs:
    def __init__(
        self,
        output_root: Path,
    ):
        self.output_root = output_root
        self.spools = {}

        for group_name, datasets in (
            GROUP_OUTPUTS.items()
        ):
            for output_name in datasets.values():
                key = (
                    group_name,
                    output_name,
                )

                self.spools[key] = (
                    DatasetSpool(
                        output_root
                        / group_name
                        / f"{output_name}.csv"
                    )
                )

        self.manifest = DatasetSpool(
            output_root
            / "report_manifest.csv",
            preferred_columns=[
                *IDENTITY_COLUMNS,
                "source_format",
                "source_path",
                "historical_population",
                "pipeline_status",
            ],
        )

        self.errors = DatasetSpool(
            output_root
            / "pipeline_errors.csv",
            preferred_columns=[
                *IDENTITY_COLUMNS,
                "source_format",
                "source_path",
                "group",
                "error_type",
                "error",
            ],
        )

        self.review = DatasetSpool(
            output_root
            / "pipeline_review.csv",
            preferred_columns=[
                *IDENTITY_COLUMNS,
                "source_format",
                "source_path",
                "group",
                "review_issue",
            ],
        )

    def write_group_result(
        self,
        group_name: str,
        result: Any,
    ) -> dict[str, int]:
        counts = {}

        for (
            result_attribute,
            output_name,
        ) in GROUP_OUTPUTS[
            group_name
        ].items():

            rows = getattr(
                result,
                result_attribute,
                [],
            ) or []

            self.spools[
                (
                    group_name,
                    output_name,
                )
            ].write_many(rows)

            counts[
                f"{group_name}_{output_name}"
            ] = len(rows)

        return counts

    def finalize(self):
        for spool in self.spools.values():
            spool.finalize()

        self.manifest.finalize()
        self.errors.finalize()
        self.review.finalize()


# ============================================================
# Main pipeline
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
    )

    parser.add_argument(
        "--historical-coverage",
        type=Path,
        default=DEFAULT_HISTORICAL_COVERAGE,
        help=(
            "Optional frozen historical coverage used only "
            "to preserve historical report_id values."
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Optional number of reports to process. "
            "Useful for a production smoke test."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Delete the existing output directory before running."
        ),
    )

    args = parser.parse_args()

    project_root = Path.cwd()
    inventory_path = args.inventory

    if not inventory_path.is_file():
        raise FileNotFoundError(
            inventory_path
        )

    output_root = args.output_directory

    if output_root.exists():
        if not args.overwrite:
            raise FileExistsError(
                f"{output_root} already exists. "
                "Use --overwrite to replace it."
            )

        shutil.rmtree(
            output_root
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    inventory = read_csv(
        inventory_path
    )

    if args.limit is not None:
        if args.limit < 1:
            raise ValueError(
                "--limit must be >= 1"
            )

        inventory = inventory[
            :args.limit
        ]

    historical_ids = (
        build_historical_id_map(
            args.historical_coverage
        )
    )

    historical_keys = set(
        historical_ids
    )

    outputs = PipelineOutputs(
        output_root
    )

    source_counts = Counter()
    report_status_counts = Counter()
    group_error_counts = Counter()
    group_review_counts = Counter()
    group_row_totals = Counter()

    started_at = datetime.now(
        timezone.utc
    )

    processed = 0

    for index, row in enumerate(
        inventory,
        start=1,
    ):
        identity = make_identity(
            row,
            historical_ids,
        )

        key = report_key(row)

        manifest_row = {
            **identity,
            "historical_population":
                (
                    "true"
                    if key
                    in historical_keys
                    else "false"
                ),
        }

        try:
            (
                source_format,
                source_path,
            ) = select_source_once(
                row,
                project_root,
            )

            manifest_row.update({
                "source_format":
                    source_format,
                "source_path":
                    str(source_path),
            })

            source_counts[
                source_format
            ] += 1

        except Exception as exc:
            manifest_row.update({
                "source_format":
                    "",
                "source_path":
                    "",
                "pipeline_status":
                    "source_error",
            })

            outputs.errors.write({
                **identity,
                "source_format":
                    "",
                "source_path":
                    "",
                "group":
                    "source_selection",
                "error_type":
                    type(exc).__name__,
                "error":
                    str(exc),
            })

            outputs.manifest.write(
                manifest_row
            )

            report_status_counts[
                "source_error"
            ] += 1

            processed += 1

            if index % 50 == 0:
                print(
                    f"Processed "
                    f"{index}/{len(inventory)}..."
                )

            continue

        selected_csv = (
            source_path
            if source_format == "csv"
            else None
        )

        selected_pdf = (
            source_path
            if source_format == "pdf"
            else None
        )

        report_failed = False

        for group_name in [
            "group1",
            "group2",
            "group3",
            "group4",
            "group5",
            "group6",
        ]:
            extractor = GROUP_EXTRACTORS[
                group_name
            ]

            try:
                result = extractor(
                    identity=identity,
                    csv_path=selected_csv,
                    pdf_path=selected_pdf,
                )

                if (
                    result.source_format
                    != source_format
                ):
                    raise RuntimeError(
                        f"{group_name} selected "
                        f"{result.source_format!r}; "
                        f"pipeline selected "
                        f"{source_format!r}"
                    )

                counts = (
                    outputs.write_group_result(
                        group_name,
                        result,
                    )
                )

                for name, count in (
                    counts.items()
                ):
                    manifest_row[name] = (
                        count
                    )
                    group_row_totals[
                        name
                    ] += count

                issues = (
                    getattr(
                        result,
                        "issues",
                        [],
                    )
                    or []
                )

                if issues:
                    for issue in issues:
                        outputs.review.write({
                            **identity,
                            "source_format":
                                source_format,
                            "source_path":
                                str(
                                    source_path
                                ),
                            "group":
                                group_name,
                            "review_issue":
                                str(issue),
                        })

                        group_review_counts[
                            group_name
                        ] += 1

            except Exception as exc:
                report_failed = True

                outputs.errors.write({
                    **identity,
                    "source_format":
                        source_format,
                    "source_path":
                        str(source_path),
                    "group":
                        group_name,
                    "error_type":
                        type(exc).__name__,
                    "error":
                        str(exc),
                })

                group_error_counts[
                    group_name
                ] += 1

        manifest_row[
            "pipeline_status"
        ] = (
            "completed_with_errors"
            if report_failed
            else "completed"
        )

        outputs.manifest.write(
            manifest_row
        )

        report_status_counts[
            manifest_row[
                "pipeline_status"
            ]
        ] += 1

        processed += 1

        if index % 50 == 0:
            print(
                f"Processed "
                f"{index}/{len(inventory)}..."
            )

    outputs.finalize()

    finished_at = datetime.now(
        timezone.utc
    )

    metadata = {
        "pipeline":
            "edr_new_groups_1_to_6",
        "started_at_utc":
            started_at.isoformat(),
        "finished_at_utc":
            finished_at.isoformat(),
        "inventory_path":
            str(inventory_path),
        "output_directory":
            str(output_root),
        "reports_selected":
            len(inventory),
        "reports_processed":
            processed,
        "historical_id_map_count":
            len(historical_ids),
        "source_counts":
            dict(source_counts),
        "report_status_counts":
            dict(report_status_counts),
        "group_error_counts":
            dict(group_error_counts),
        "group_review_counts":
            dict(group_review_counts),
        "group_row_totals":
            dict(group_row_totals),
        "group_rule_versions":
            GROUP_VERSIONS,
        "source_policy":
            (
                "CSV exists -> CSV only; "
                "otherwise PDF only"
            ),
        "semantic_normalization":
            "not_performed",
        "unit_conversion":
            "not_performed",
        "fuzzy_inference":
            "not_performed",
    }

    (
        output_root
        / "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 80)
    print("EDR NEW PIPELINE COMPLETE")
    print("=" * 80)

    print(
        "\nReports processed:",
        processed,
    )

    print(
        "Source selection:",
        dict(source_counts),
    )

    print(
        "Report status:",
        dict(report_status_counts),
    )

    print(
        "Group errors:",
        dict(group_error_counts),
    )

    print(
        "Review flags:",
        dict(group_review_counts),
    )

    print(
        "\nOutput:",
        output_root,
    )


if __name__ == "__main__":
    main()
