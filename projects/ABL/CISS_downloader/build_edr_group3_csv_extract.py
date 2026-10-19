"""
Build structured Group 3 CSV package from the fully resolved audit output.

Input
-----
data/processed/edr/group3_csv_resolved_v1/
    accepted_group3_fields.csv
    companion_group3_context.csv
    excluded_non_group3_fields.csv
    remaining_review_fields.csv

Output
------
data/processed/edr/group3_csv_structured_v1/
    condition_registry.csv
    condition_values.csv
    companion_context.csv
    extraction_failures.csv
    family_summary.csv
    validation_checks.csv
    metadata.json

Rules
-----
- One accepted source observation becomes one Group 3 structured record.
- Preserve raw label, raw value, source section, source row, event hint,
  source path, and source-format provenance.
- Parse a numeric value only when the raw value is safely representable as
  one scalar number, optionally followed by a simple unit.
- Preserve textual states such as Yes/No, Deployed/Not Deployed, ON/OFF,
  SNA, N/A, Active/Inactive, Buckled/Unbuckled exactly as raw values.
- No semantic normalization.
- No unit conversion.
- No fuzzy event linking.
- No mutation of source files.
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


# ============================================================
# I/O
# ============================================================

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


# ============================================================
# Helpers
# ============================================================

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


def is_missing_like(value):
    return norm(value).casefold() in MISSING_VALUES


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
        mph
        |
        km/h
        |
        kph
        |
        m/s
        |
        m/s\^2
        |
        m/s2
        |
        g
        |
        ms
        |
        msec
        |
        milliseconds?
        |
        sec
        |
        seconds?
        |
        s
        |
        V
        |
        volts?
        |
        cycles?
        |
        min
        |
        minutes?
        |
        deg
        |
        degrees?
    )?
    \s*$
    """,
    re.I | re.X,
)


def parse_numeric_scalar(value):
    text = norm(value)

    if not text or is_missing_like(text):
        return None, "", "missing_or_unavailable"

    cleaned = text.replace(",", "")

    match = NUMERIC_RE.fullmatch(cleaned)

    if not match:
        return None, "", "textual_or_non_scalar"

    try:
        number = float(match.group("num"))
    except Exception:
        return None, "", "numeric_parse_failed"

    unit = norm(match.group("unit") or "")

    return number, unit, "numeric_scalar"


def raw_unit_from_label(label):
    text = norm(label)

    patterns = [
        r"\(([^()]*)\)\s*$",
        r",\s*([^,]+)\s*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            candidate = norm(match.group(1))

            if re.fullmatch(
                r"(?:"
                r"ms|msec|milliseconds?|"
                r"sec|seconds?|s|"
                r"V|volts?|"
                r"cycles?|"
                r"min|minutes?|"
                r"%|mph|km/h|kph|"
                r"deg|degrees?"
                r")",
                candidate,
                flags=re.I,
            ):
                return candidate

    return ""


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--resolved-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_csv_resolved_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group3_csv_structured_v1"
        ),
    )

    args = parser.parse_args()

    src = args.resolved_directory
    out = args.output_directory

    accepted_path = src / "accepted_group3_fields.csv"
    companion_path = src / "companion_group3_context.csv"
    unresolved_path = src / "remaining_review_fields.csv"

    if not accepted_path.exists():
        raise FileNotFoundError(accepted_path)

    if not companion_path.exists():
        raise FileNotFoundError(companion_path)

    if not unresolved_path.exists():
        raise FileNotFoundError(unresolved_path)

    accepted = read_csv(accepted_path)
    companion = read_csv(companion_path)
    unresolved = read_csv(unresolved_path)

    if unresolved:
        raise RuntimeError(
            f"Refusing extraction: {len(unresolved)} unresolved review rows remain."
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
            source_index = norm(row.get("source_record_index", ""))
            section = norm(row.get("source_section_heading", ""))
            event_hint = norm(row.get("event_hint", ""))
            raw_label = norm(row.get("field_label_raw", ""))
            raw_value = norm(row.get("field_value_raw", ""))
            family = norm(row.get("audited_family", ""))

            if not raw_label:
                raise ValueError("blank field_label_raw")

            if not family:
                raise ValueError("blank audited_family")

            source_candidate_id = norm(
                row.get("group3_candidate_id", "")
            )

            condition_id = (
                "g3csv_"
                + stable_id(
                    report_id,
                    case_id,
                    vehicle_number,
                    export_basename,
                    source_path,
                    source_index,
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
                "group3_condition_id": condition_id,
                "source_candidate_id": source_candidate_id,
                "report_id": report_id,
                "case_id": case_id,
                "vehicle_number": vehicle_number,
                "export_basename": export_basename,
                "source_format": "csv",
                "source_path": source_path,
                "source_record_index": source_index,
                "source_section_heading": section,
                "event_hint": event_hint,
                "family": family,
                "field_label_raw": raw_label,
                "field_value_raw": raw_value,
                "raw_unit": raw_unit,
                "event_link_status":
                    norm(row.get("event_link_status", ""))
                    or (
                        "source_hint_only"
                        if event_hint
                        else "not_linked"
                    ),
                "semantic_normalization_status": "not_normalized",
                "unit_conversion_status": "not_converted",
            })

            values.append({
                "group3_condition_id": condition_id,
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
                "group3_candidate_id":
                    norm(row.get("group3_candidate_id", "")),
                "field_label_raw":
                    norm(row.get("field_label_raw", "")),
                "field_value_raw":
                    norm(row.get("field_value_raw", "")),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    # ========================================================
    # Validation
    # ========================================================

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
        len(accepted) == 37065,
        len(accepted),
        37065,
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
        row["group3_condition_id"]
        for row in registry
    ]

    duplicate_ids = len(ids) - len(set(ids))

    check(
        "duplicate_condition_ids",
        duplicate_ids == 0,
        duplicate_ids,
        0,
    )

    value_ids = {
        row["group3_condition_id"]
        for row in values
    }

    check(
        "registry_value_id_sets_equal",
        set(ids) == value_ids,
        len(set(ids) ^ value_ids),
        0,
    )

    blank_report_ids = sum(
        1
        for row in registry
        if not norm(row["report_id"])
    )

    check(
        "blank_report_ids",
        blank_report_ids == 0,
        blank_report_ids,
        0,
    )

    blank_case_ids = sum(
        1
        for row in registry
        if not norm(row["case_id"])
    )

    check(
        "blank_case_ids",
        blank_case_ids == 0,
        blank_case_ids,
        0,
    )

    blank_labels = sum(
        1
        for row in registry
        if not norm(row["field_label_raw"])
    )

    check(
        "blank_raw_labels",
        blank_labels == 0,
        blank_labels,
        0,
    )

    blank_family = sum(
        1
        for row in registry
        if not norm(row["family"])
    )

    check(
        "blank_family",
        blank_family == 0,
        blank_family,
        0,
    )

    # ========================================================
    # Write
    # ========================================================

    out.mkdir(parents=True, exist_ok=True)

    write_csv(
        out / "condition_registry.csv",
        registry,
        [
            "group3_condition_id",
            "source_candidate_id",
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "source_format",
            "source_path",
            "source_record_index",
            "source_section_heading",
            "event_hint",
            "family",
            "field_label_raw",
            "field_value_raw",
            "raw_unit",
            "event_link_status",
            "semantic_normalization_status",
            "unit_conversion_status",
        ],
    )

    write_csv(
        out / "condition_values.csv",
        values,
        [
            "group3_condition_id",
            "field_value_raw",
            "numeric_value",
            "raw_unit",
            "value_parse_status",
            "missing_or_unavailable",
        ],
    )

    # Preserve companion context even though currently empty.
    companion_columns = (
        list(companion[0].keys())
        if companion
        else [
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "field_label_raw",
            "field_value_raw",
        ]
    )

    write_csv(
        out / "companion_context.csv",
        companion,
        companion_columns,
    )

    write_csv(
        out / "extraction_failures.csv",
        failures,
        [
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "group3_candidate_id",
            "field_label_raw",
            "field_value_raw",
            "error_type",
            "error",
        ],
    )

    family_summary = [
        {
            "family": family,
            "condition_count": count,
        }
        for family, count
        in family_counts.most_common()
    ]

    write_csv(
        out / "family_summary.csv",
        family_summary,
        [
            "family",
            "condition_count",
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
            "Group 3 - Event conditions, deployment, and status information",

        "stage":
            "CSV structured extraction",

        "input_accepted_fields":
            len(accepted),

        "structured_condition_count":
            len(registry),

        "condition_value_count":
            len(values),

        "companion_context_count":
            len(companion),

        "extraction_failure_count":
            len(failures),

        "reports_with_structured_conditions":
            len(reports),

        "cases_with_structured_conditions":
            len(cases),

        "family_counts":
            dict(family_counts),

        "value_parse_status_counts":
            dict(parse_status_counts),

        "numeric_value_count":
            parse_status_counts.get("numeric_scalar", 0),

        "missing_or_unavailable_count":
            parse_status_counts.get("missing_or_unavailable", 0),

        "textual_or_non_scalar_count":
            parse_status_counts.get("textual_or_non_scalar", 0),

        "validation_checks":
            len(checks),

        "hard_validation_failures":
            hard_failures,

        "warning_validation_failures":
            warning_failures,

        "scope":
            (
                "Structured extraction of the fully resolved Group 3 CSV "
                "population. One accepted source observation is preserved as "
                "one structured event-condition record. Raw labels, raw values, "
                "units, section headings, event hints, source rows, source paths, "
                "and provenance are retained. Numeric parsing is conservative "
                "and limited to unambiguous scalar values. Textual states remain "
                "raw. No semantic normalization, unit conversion, fuzzy event "
                "linking, PDF processing, or source mutation is performed."
            ),
    }

    tmp = out / "metadata.json.part"
    tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(out / "metadata.json")

    print()
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print()
    print(f"Outputs: {out}")

    if hard_failures:
        print()
        print("GROUP 3 CSV STRUCTURED EXTRACTION HAS HARD FAILURES.")
        raise SystemExit(1)

    print()
    print("GROUP 3 CSV STRUCTURED EXTRACTION COMPLETE.")


if __name__ == "__main__":
    main()
