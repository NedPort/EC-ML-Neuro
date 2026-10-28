import csv
from collections import Counter
from pathlib import Path

from src.edr_new.rules.group_6_r import extract_group6_report


INVENTORY = Path(
    "data/processed/edr/edr_export_inventory.csv"
)

VALIDATED_COVERAGE = Path(
    "data/processed/edr/group2_final_v1/report_coverage.csv"
)


EXPECTED = {
    "reports_selected": 1422,
    "technical_records": 13618,
    "csv_records": 13202,
    "pdf_records": 416,
    "technical_values": 13618,
    "review_evidence": 8637,
    "reports_with_records": 1391,
    "cases_with_records": 1170,
}


def read_csv(path):
    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def resolve_path(raw):
    if not raw:
        return None

    path = Path(raw)

    return path if path.is_file() else None


def main():
    inventory = read_csv(INVENTORY)
    coverage = read_csv(VALIDATED_COVERAGE)

    validated_map = {
        (
            row["case_id"],
            row["vehicle_number"],
            row["export_basename"],
        ): row
        for row in coverage
    }

    rows = [
        row
        for row in inventory
        if (
            row["case_id"],
            row["vehicle_number"],
            row["export_basename"],
        )
        in validated_map
    ]

    print("Reports selected:", len(rows))

    if len(rows) != 1422:
        raise RuntimeError(
            f"Expected 1422 reports, got {len(rows)}"
        )

    totals = Counter()
    source_counts = Counter()
    family_counts = Counter()

    reports_with_records = set()
    cases_with_records = set()

    extraction_errors = []

    for index, row in enumerate(rows, 1):

        key = (
            row["case_id"],
            row["vehicle_number"],
            row["export_basename"],
        )

        historical = validated_map[key]

        report_id = (
            historical.get("report_id", "")
            or row.get("report_id", "")
        )

        identity = {
            "report_id": report_id,
            "case_id": row["case_id"],
            "vehicle_number":
                row["vehicle_number"],
            "export_basename":
                row["export_basename"],
        }

        csv_path = resolve_path(
            row.get("csv_export_path", "")
        )

        pdf_path = resolve_path(
            row.get("pdf_export_path", "")
        )

        try:
            result = extract_group6_report(
                identity=identity,
                csv_path=csv_path,
                pdf_path=pdf_path,
            )

        except Exception as exc:
            extraction_errors.append({
                "report_id": report_id,
                "case_id": row["case_id"],
                "vehicle_number":
                    row["vehicle_number"],
                "error_type":
                    type(exc).__name__,
                "error": str(exc),
            })
            continue

        source_counts[
            result.source_format
        ] += 1

        record_count = len(
            result.technical_registry
        )

        totals[
            "technical_records"
        ] += record_count

        totals[
            f"{result.source_format}_records"
        ] += record_count

        totals[
            "technical_values"
        ] += len(
            result.technical_values
        )

        totals[
            "review_evidence"
        ] += len(
            result.review_evidence
        )

        totals[
            "excluded"
        ] += len(
            result.excluded
        )

        totals[
            "unresolved"
        ] += len(
            result.unresolved
        )

        totals[
            "issues"
        ] += len(
            result.issues
        )

        if record_count:
            reports_with_records.add(
                report_id
            )

            cases_with_records.add(
                row["case_id"]
            )

        for item in result.technical_registry:
            family_counts[
                item.get("family", "")
            ] += 1

        if result.issues:
            for issue in result.issues:
                extraction_errors.append({
                    "report_id":
                        report_id,
                    "case_id":
                        row["case_id"],
                    "vehicle_number":
                        row["vehicle_number"],
                    "error_type":
                        "reported_issue",
                    "error":
                        str(issue),
                })

        if index % 100 == 0:
            print(
                f"Processed {index}/{len(rows)}..."
            )

    actual = {
        "reports_selected":
            len(rows),

        "technical_records":
            totals["technical_records"],

        "csv_records":
            totals["csv_records"],

        "pdf_records":
            totals["pdf_records"],

        "technical_values":
            totals["technical_values"],

        "review_evidence":
            totals["review_evidence"],

        "reports_with_records":
            len(
                reports_with_records
            ),

        "cases_with_records":
            len(
                cases_with_records
            ),
    }

    print("\n" + "=" * 80)
    print("GROUP 6 REGRESSION")
    print("=" * 80)

    print("\nSource selection:")
    print(dict(source_counts))

    print("\nComparison:")

    overall_pass = True

    for name, expected in EXPECTED.items():
        observed = actual[name]

        status = (
            "PASS"
            if observed == expected
            else "FAIL"
        )

        if status == "FAIL":
            overall_pass = False

        print(
            f"{name:<30}"
            f" actual={observed:<10}"
            f" expected={expected:<10}"
            f" {status}"
        )

    print(
        "\nUnresolved:",
        totals["unresolved"],
    )

    print(
        "Issues:",
        totals["issues"],
    )

    print(
        "Extraction errors:",
        len(extraction_errors),
    )

    if (
        totals["unresolved"]
        or totals["issues"]
        or extraction_errors
    ):
        overall_pass = False

    if extraction_errors:
        print("\nFirst errors/issues:")

        for error in extraction_errors[:20]:
            print(error)

    print(
        "\nExcluded total:",
        totals["excluded"],
    )

    print("\nFamilies:")

    for family, count in (
        family_counts.most_common()
    ):
        print(
            f"{count:>8}  {family}"
        )

    print("\nOverall:")
    print(
        "PASS"
        if overall_pass
        else "NEEDS REVISION"
    )


if __name__ == "__main__":
    main()