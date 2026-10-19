"""
Build structured Group 6 PDF-only package from resolved audit fields.

Input
-----
data/processed/edr/group6_pdf_resolved_v1/
    accepted_group6_pdf_fields.csv
    remaining_review_fields.csv

Output
------
data/processed/edr/group6_pdf_structured_v1/
    technical_registry.csv
    technical_values.csv
    extraction_failures.csv
    family_summary.csv
    validation_checks.csv
    metadata.json

Rules
-----
- One accepted PDF source observation becomes one structured Group 6 record.
- Preserve report/case/vehicle/export provenance.
- Preserve PDF page, line number, full source line, raw label, raw value,
  and audited family.
- Parse numeric scalar values conservatively.
- Preserve identifiers, versions, VINs, serials, part numbers,
  configuration strings, traceability values, and textual states raw.
- No OCR.
- No semantic normalization.
- No unit conversion.
- No fuzzy inference.
- No source mutation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

csv.field_size_limit(100_000_000)


def read_csv(path: Path):
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")

    with tmp.open(
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

    tmp.replace(path)


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").strip(),
    )


def stable_id(*parts):
    text = "|".join(norm(part) for part in parts)
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:24]


MISSING_VALUES = {
    "",
    "n/a",
    "na",
    "sna",
    "not available",
    "not applicable",
    "unknown",
    "invalid",
    "data not available",
    "no data",
}


NUMERIC_RE = re.compile(
    r"""
    ^\s*
    (?P<num>
        [-+]?
        (?:
            \d+(?:\.\d*)?
            |
            \.\d+
        )
        (?:[eE][-+]?\d+)?
    )
    \s*
    (?P<unit>
        %
        |
        V
        |
        volts?
        |
        cycles?
        |
        times?
        |
        miles?
        |
        mi
        |
        km
        |
        hours?
        |
        hrs?
        |
        minutes?
        |
        min
        |
        mph
        |
        km/h
        |
        kph
    )?
    \s*$
    """,
    re.I | re.X,
)


def is_missing_like(value):
    return norm(value).casefold() in MISSING_VALUES


def parse_numeric_scalar(value):
    text = norm(value)

    if not text or is_missing_like(text):
        return None, "", "missing_or_unavailable"

    cleaned = text.replace(",", "")
    match = NUMERIC_RE.fullmatch(cleaned)

    if not match:
        return None, "", "textual_or_identifier"

    try:
        number = float(match.group("num"))
    except Exception:
        return None, "", "numeric_parse_failed"

    unit = norm(match.group("unit") or "")

    return number, unit, "numeric_scalar"


def raw_unit_from_label(label):
    text = norm(label)

    match = re.search(r"\(([^()]*)\)\s*$", text)

    if not match:
        return ""

    candidate = norm(match.group(1))

    if re.fullmatch(
        r"(?:"
        r"V|volts?|cycles?|times?|miles?|mi|km|"
        r"hours?|hrs?|minutes?|min|%|mph|km/h|kph"
        r")",
        candidate,
        flags=re.I,
    ):
        return candidate

    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--resolved-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group6_pdf_resolved_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group6_pdf_structured_v1"
        ),
    )

    args = parser.parse_args()

    src = args.resolved_directory
    out = args.output_directory

    accepted_path = src / "accepted_group6_pdf_fields.csv"
    unresolved_path = src / "remaining_review_fields.csv"

    if not accepted_path.exists():
        raise FileNotFoundError(accepted_path)

    if not unresolved_path.exists():
        raise FileNotFoundError(unresolved_path)

    accepted = read_csv(accepted_path)
    unresolved = read_csv(unresolved_path)

    if unresolved:
        raise RuntimeError(
            f"Refusing extraction: {len(unresolved)} unresolved Group 6 PDF rows remain."
        )

    registry = []
    values = []
    failures = []

    family_counts = Counter()
    parse_status_counts = Counter()
    reports = set()
    cases = set()

    for row in accepted:
        try:
            report_id = norm(row.get("report_id", ""))
            case_id = norm(row.get("case_id", ""))
            vehicle_number = norm(row.get("vehicle_number", ""))
            export_basename = norm(row.get("export_basename", ""))
            source_path = norm(row.get("source_path", ""))
            page = norm(row.get("pdf_page", ""))
            line_no = norm(row.get("pdf_line_number", ""))
            source_line = norm(row.get("source_line_raw", ""))
            raw_label = norm(row.get("field_label_raw", ""))
            raw_value = norm(row.get("field_value_raw", ""))
            family = norm(row.get("audited_family", ""))

            if not raw_label:
                raise ValueError("blank field_label_raw")

            if not family:
                raise ValueError("blank audited_family")

            source_candidate_id = norm(
                row.get("group6_candidate_id", "")
            )

            technical_id = (
                "g6pdf_"
                + stable_id(
                    report_id,
                    case_id,
                    vehicle_number,
                    export_basename,
                    source_path,
                    page,
                    line_no,
                    raw_label,
                    raw_value,
                    family,
                )
            )

            numeric_value, value_unit, parse_status = (
                parse_numeric_scalar(raw_value)
            )

            label_unit = raw_unit_from_label(raw_label)
            raw_unit = value_unit or label_unit

            registry.append({
                "group6_technical_id": technical_id,
                "source_candidate_id": source_candidate_id,
                "report_id": report_id,
                "case_id": case_id,
                "vehicle_number": vehicle_number,
                "export_basename": export_basename,
                "source_format": "pdf",
                "source_path": source_path,
                "pdf_page": page,
                "pdf_line_number": line_no,
                "source_line_raw": source_line,
                "family": family,
                "field_label_raw": raw_label,
                "field_value_raw": raw_value,
                "raw_unit": raw_unit,
                "semantic_normalization_status": "not_normalized",
                "unit_conversion_status": "not_converted",
            })

            values.append({
                "group6_technical_id": technical_id,
                "field_value_raw": raw_value,
                "numeric_value":
                    ""
                    if numeric_value is None
                    else repr(numeric_value),
                "raw_unit": raw_unit,
                "value_parse_status": parse_status,
                "missing_or_unavailable":
                    "true"
                    if is_missing_like(raw_value)
                    else "false",
            })

            family_counts[family] += 1
            parse_status_counts[parse_status] += 1

            if report_id:
                reports.add(report_id)

            if case_id:
                cases.add(case_id)

        except Exception as exc:
            failures.append({
                "report_id": norm(row.get("report_id", "")),
                "case_id": norm(row.get("case_id", "")),
                "vehicle_number": norm(row.get("vehicle_number", "")),
                "export_basename": norm(row.get("export_basename", "")),
                "group6_candidate_id":
                    norm(row.get("group6_candidate_id", "")),
                "pdf_page": norm(row.get("pdf_page", "")),
                "pdf_line_number": norm(row.get("pdf_line_number", "")),
                "field_label_raw":
                    norm(row.get("field_label_raw", "")),
                "field_value_raw":
                    norm(row.get("field_value_raw", "")),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    checks = []

    def check(
        name,
        condition,
        observed,
        expected,
        severity="hard",
        note="",
    ):
        checks.append({
            "check": name,
            "status": "PASS" if condition else "FAIL",
            "severity": severity,
            "observed": str(observed),
            "expected": str(expected),
            "note": note,
        })

    check(
        "accepted_input_expected_count",
        len(accepted) == 416,
        len(accepted),
        416,
    )

    check(
        "structured_count_matches_input",
        len(registry) == len(accepted),
        len(registry),
        len(accepted),
    )

    check(
        "value_count_matches_registry",
        len(values) == len(registry),
        len(values),
        len(registry),
    )

    check(
        "extraction_failures_zero",
        len(failures) == 0,
        len(failures),
        0,
    )

    ids = [
        row["group6_technical_id"]
        for row in registry
    ]

    duplicate_ids = len(ids) - len(set(ids))

    check(
        "duplicate_technical_ids",
        duplicate_ids == 0,
        duplicate_ids,
        0,
    )

    value_ids = {
        row["group6_technical_id"]
        for row in values
    }

    check(
        "registry_value_id_sets_equal",
        set(ids) == value_ids,
        len(set(ids) ^ value_ids),
        0,
    )

    check(
        "blank_report_ids",
        sum(
            1
            for row in registry
            if not norm(row["report_id"])
        ) == 0,
        sum(
            1
            for row in registry
            if not norm(row["report_id"])
        ),
        0,
    )

    check(
        "blank_case_ids",
        sum(
            1
            for row in registry
            if not norm(row["case_id"])
        ) == 0,
        sum(
            1
            for row in registry
            if not norm(row["case_id"])
        ),
        0,
    )

    check(
        "blank_pdf_provenance",
        sum(
            1
            for row in registry
            if (
                not norm(row["pdf_page"])
                or not norm(row["pdf_line_number"])
                or not norm(row["source_line_raw"])
            )
        ) == 0,
        sum(
            1
            for row in registry
            if (
                not norm(row["pdf_page"])
                or not norm(row["pdf_line_number"])
                or not norm(row["source_line_raw"])
            )
        ),
        0,
    )

    check(
        "blank_raw_labels",
        sum(
            1
            for row in registry
            if not norm(row["field_label_raw"])
        ) == 0,
        sum(
            1
            for row in registry
            if not norm(row["field_label_raw"])
        ),
        0,
    )

    out.mkdir(parents=True, exist_ok=True)

    write_csv(
        out / "technical_registry.csv",
        registry,
        [
            "group6_technical_id",
            "source_candidate_id",
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "source_format",
            "source_path",
            "pdf_page",
            "pdf_line_number",
            "source_line_raw",
            "family",
            "field_label_raw",
            "field_value_raw",
            "raw_unit",
            "semantic_normalization_status",
            "unit_conversion_status",
        ],
    )

    write_csv(
        out / "technical_values.csv",
        values,
        [
            "group6_technical_id",
            "field_value_raw",
            "numeric_value",
            "raw_unit",
            "value_parse_status",
            "missing_or_unavailable",
        ],
    )

    write_csv(
        out / "extraction_failures.csv",
        failures,
        [
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "group6_candidate_id",
            "pdf_page",
            "pdf_line_number",
            "field_label_raw",
            "field_value_raw",
            "error_type",
            "error",
        ],
    )

    write_csv(
        out / "family_summary.csv",
        [
            {
                "family": family,
                "technical_field_count": count,
            }
            for family, count in family_counts.most_common()
        ],
        [
            "family",
            "technical_field_count",
        ],
    )

    write_csv(
        out / "validation_checks.csv",
        checks,
        [
            "check",
            "status",
            "severity",
            "observed",
            "expected",
            "note",
        ],
    )

    hard_failures = sum(
        1
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"] == "hard"
        )
    )

    warning_failures = sum(
        1
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"] == "warning"
        )
    )

    metadata = {
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 6 - Other structured technical and investigation information",

        "stage":
            "PDF-only structured extraction",

        "input_accepted_fields":
            len(accepted),

        "structured_technical_count":
            len(registry),

        "technical_value_count":
            len(values),

        "extraction_failure_count":
            len(failures),

        "reports_with_structured_technical_fields":
            len(reports),

        "cases_with_structured_technical_fields":
            len(cases),

        "family_counts":
            dict(family_counts),

        "value_parse_status_counts":
            dict(parse_status_counts),

        "numeric_value_count":
            parse_status_counts.get(
                "numeric_scalar",
                0,
            ),

        "missing_or_unavailable_count":
            parse_status_counts.get(
                "missing_or_unavailable",
                0,
            ),

        "textual_or_identifier_count":
            parse_status_counts.get(
                "textual_or_identifier",
                0,
            ),

        "validation_checks":
            len(checks),

        "hard_validation_failures":
            hard_failures,

        "warning_validation_failures":
            warning_failures,

        "scope":
            (
                "Structured extraction of the fully resolved Group 6 "
                "PDF-only population. One accepted PDF source observation "
                "is preserved as one structured technical/readout record. "
                "PDF page, line number, source line, raw label, raw value, "
                "family, report/case provenance, and source path are retained. "
                "Numeric parsing is conservative. Identifiers and textual "
                "technical values remain raw. No OCR, semantic normalization, "
                "unit conversion, fuzzy inference, or source mutation is performed."
            ),
    }

    (out / "metadata.json").write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(f"Outputs: {out}")

    if hard_failures:
        print()
        print(
            "GROUP 6 PDF STRUCTURED EXTRACTION HAS HARD VALIDATION FAILURES."
        )
        raise SystemExit(1)

    print()
    print("GROUP 6 PDF STRUCTURED EXTRACTION COMPLETE.")


if __name__ == "__main__":
    main()
