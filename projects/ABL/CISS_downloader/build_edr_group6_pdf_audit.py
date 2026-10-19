"""
Audit and reconstruct Group 6 fields from PDF-only reports.

Why this stage exists
---------------------
The first PDF discovery found zero candidates because the PDF text layout
does not reliably preserve "label : value" delimiters. A second-pass
diagnostic found many Group 6 keyword-bearing lines. This audit therefore
rescans the original PDF-only reports and accepts only exact, structurally
recognizable Group 6 field patterns.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Output
------
data/processed/edr/group6_pdf_audit_v1/

    accepted_group6_pdf_fields.csv
    excluded_keyword_noise.csv
    remaining_review_fields.csv
    family_summary.csv
    report_coverage.csv
    validation_checks.csv
    metadata.json

Principles
----------
- original PDFs are authoritative
- PDF-only population only
- no OCR
- exact/anchored parsing only
- preserve page, line number, source line, raw label/value
- no semantic normalization
- no unit conversion
- no fuzzy inference
- no source mutation
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

import pdfplumber

csv.field_size_limit(100_000_000)

BASE = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


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
    with tmp.open("w", encoding="utf-8-sig", newline="") as f:
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
    text = "|".join(norm(x) for x in parts)
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:24]


def resolve_pdf_path(row: dict, source_root: Path):
    raw = norm(row.get("pdf_path", ""))

    if raw:
        p = Path(raw)

        if p.exists():
            return p

        basename = PureWindowsPath(raw).name
        case_id = norm(row.get("case_id", ""))

        if case_id and basename:
            case_root = source_root / case_id

            if case_root.exists():
                matches = list(case_root.rglob(basename))

                if matches:
                    return matches[0]

    basename = norm(row.get("export_basename", ""))
    case_id = norm(row.get("case_id", ""))

    if basename and case_id:
        case_root = source_root / case_id

        if case_root.exists():
            matches = list(case_root.rglob(basename + ".pdf"))

            if not matches:
                matches = list(case_root.rglob(basename + ".PDF"))

            if matches:
                return matches[0]

    return None


# ------------------------------------------------------------------
# Exact accepted Group 6 field patterns observed in the diagnostic
# population. Each pattern must capture LABEL and VALUE.
# ------------------------------------------------------------------

ACCEPT_RULES = [
    (
        "ignition_cycle_readout",
        re.compile(
            r"^(Ignition Cycles At Investigation)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "ignition_cycle_readout",
        re.compile(
            r"^(Ignition Cycle at Download \(Cycles\))\s+(.+)$",
            re.I,
        ),
    ),
    (
        "ignition_cycle_readout",
        re.compile(
            r"^(Ignition Cycle, Download "
            r"\(Ignition Cycles at Investigation\))\s+(.+)$",
            re.I,
        ),
    ),

    (
        "part_serial_identifier",
        re.compile(
            r"^(End Model Part Number)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "part_serial_identifier",
        re.compile(
            r"^(ESS # \d+ Traceability Data, "
            r"Part Number/Broadcast Code)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "part_serial_identifier",
        re.compile(
            r"^(Part Number, ACM)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "part_serial_identifier",
        re.compile(
            r"^(ECU Part Number)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "part_serial_identifier",
        re.compile(
            r"^(Module Serial Number)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "part_serial_identifier",
        re.compile(
            r"^(Restraints Control Module Part Number)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "part_serial_identifier",
        re.compile(
            r"^(Ford Part Number Prefix)\s+(.+)$",
            re.I,
        ),
    ),

    (
        "module_supplier",
        re.compile(
            r"^(ESS # \d+ Traceability Data, Supplier Code)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "module_supplier",
        re.compile(
            r"^(Supplier ID, ACM)\s+(.+)$",
            re.I,
        ),
    ),

    (
        "production_manufacture_date",
        re.compile(
            r"^(Production Date, ACM)\s+(.+)$",
            re.I,
        ),
    ),

    (
        "operating_time",
        re.compile(
            r"^(Operating Time \(min\))\s+(.+)$",
            re.I,
        ),
    ),

    (
        "odometer_mileage",
        re.compile(
            r"^(Vehicle Mileage \(km\))\s+(.+)$",
            re.I,
        ),
    ),
    (
        "odometer_mileage",
        re.compile(
            r"^(Odometer signal \(miles \[km\]\))\s+(.+)$",
            re.I,
        ),
    ),

    (
        "software_calibration_version",
        re.compile(
            r"^(Software Module Identifier \d+)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "software_calibration_version",
        re.compile(
            r"^(Restraints Control Module "
            r"Software Version Number)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "software_calibration_version",
        re.compile(
            r"^(Restraints Control Module Software Date)\s+(.+)$",
            re.I,
        ),
    ),

    (
        "vehicle_identifier_technical",
        re.compile(
            r"^(Vehicle Identification Number \(VIN\))\s+(.+)$",
            re.I,
        ),
    ),
    (
        "vehicle_identifier_technical",
        re.compile(
            r"^(Vehicle Identification Number)\s+(.+)$",
            re.I,
        ),
    ),

    # Additional exact technical fields exposed by neighboring lines
    # in the diagnostic population.
    (
        "traceability_identifier",
        re.compile(
            r"^(ESS # \d+ Traceability Data, "
            r"Component Identifier)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "traceability_identifier",
        re.compile(
            r"^(ESS # \d+ Traceability Data, "
            r"Traceability Number)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "traceability_identifier",
        re.compile(
            r"^(Manufacturing Traceability Data, LineID)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "traceability_identifier",
        re.compile(
            r"^(Manufacturing Traceability Data, ShiftID)\s+(.+)$",
            re.I,
        ),
    ),

    (
        "system_type",
        re.compile(
            r"^(System Type)\s+(.+)$",
            re.I,
        ),
    ),
    (
        "edr_generation",
        re.compile(
            r"^(EDR Generation)\s+(.+)$",
            re.I,
        ),
    ),
]


# Broad keyword detector used only to retain rejected/noise evidence.
KEYWORD_RE = re.compile(
    r"\b(?:"
    r"ignition cycles?|power[- ]on cycles?|"
    r"part number|serial number|supplier|"
    r"software|calibration|firmware|"
    r"vehicle identification number|vin|"
    r"configuration|odometer|mileage|"
    r"operating time|production date|"
    r"manufacture date|traceability|"
    r"module identifier|system type|edr generation"
    r")\b",
    re.I,
)


# Explicit known cross-group / documentation exclusions.
def exclusion_reason(line: str):
    text = norm(line)

    if re.search(r"^User Entered VIN\b", text, re.I):
        return "group1_user_entered_vin"

    if re.search(r"\bVIN sequence number\b", text, re.I):
        return "documentation_or_record_structure"

    if re.search(
        r"\bCRC Check Failed - Saved Without VIN Sequence Number\b",
        text,
        re.I,
    ):
        return "group2_record_structure"

    if re.search(
        r"\bIgnition Cycle(?:s)? at Event\b",
        text,
        re.I,
    ):
        return "group3_event_condition"

    if re.search(
        r"\bIgnition Cycle, Crash\b",
        text,
        re.I,
    ):
        return "group3_event_condition"

    if re.search(
        r"\bSIR Warning Lamp\b",
        text,
        re.I,
    ):
        return "group3_warning_lamp"

    if re.search(
        r"\bIgnition Cycles Since DTCs? Were Last Cleared\b",
        text,
        re.I,
    ):
        return "diagnostic_event_status_not_group6_readout"

    if re.search(
        r"\bIgnition Cycle Since DTC was Set\b",
        text,
        re.I,
    ):
        return "diagnostic_event_status_not_group6_readout"

    if re.search(
        r"\b(?:latest production release|CDR software|"
        r"software when viewing|software and/or data|"
        r"software or use thereof)\b",
        text,
        re.I,
    ):
        return "documentation_software_notice"

    if re.search(
        r"\bvehicle configuration\b",
        text,
        re.I,
    ) and len(text) > 100:
        return "documentation_configuration_statement"

    if re.search(
        r"\bpart number\b",
        text,
        re.I,
    ) and len(text) > 100:
        return "documentation_part_number_statement"

    return ""


def parse_accepted(line: str):
    text = norm(line)

    for family, pattern in ACCEPT_RULES:
        match = pattern.fullmatch(text)

        if match:
            label = norm(match.group(1))
            value = norm(match.group(2))

            if label and value:
                return family, label, value

    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--report-index",
        type=Path,
        default=Path(
            "data/processed/edr/group1_v4/report_index.csv"
        ),
    )

    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("data/temp"),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/group6_pdf_audit_v1"
        ),
    )

    args = parser.parse_args()

    report_index = read_csv(args.report_index)
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)

    accepted = []
    excluded = []
    remaining_review = []
    coverage = []
    errors = []

    family_counts = Counter()

    selected = 0
    processed = 0

    reports_with_accepted = set()
    cases_with_accepted = set()

    for row in report_index:
        has_csv = bool(norm(row.get("csv_path", "")))
        has_pdf = bool(norm(row.get("pdf_path", "")))

        if has_csv or not has_pdf:
            continue

        selected += 1

        pdf_path = resolve_pdf_path(
            row,
            args.source_root,
        )

        if pdf_path is None or not pdf_path.exists():
            errors.append({
                **{
                    k: row.get(k, "")
                    for k in BASE
                },
                "error_type": "pdf_source_not_found",
                "pdf_path": norm(row.get("pdf_path", "")),
                "error": "Could not resolve PDF path.",
            })
            continue

        report_accept = 0
        report_excluded = 0
        report_review = 0

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_no, page in enumerate(
                    pdf.pages,
                    start=1,
                ):
                    text = page.extract_text() or ""

                    for line_no, raw_line in enumerate(
                        text.splitlines(),
                        start=1,
                    ):
                        line = norm(raw_line)

                        if not line:
                            continue

                        parsed = parse_accepted(line)

                        if parsed is not None:
                            family, label, value = parsed

                            candidate_id = (
                                "g6pdf_"
                                + stable_id(
                                    row.get("report_id", ""),
                                    page_no,
                                    line_no,
                                    label,
                                    value,
                                )
                            )

                            accepted.append({
                                **{
                                    k: row.get(k, "")
                                    for k in BASE
                                },
                                "group6_candidate_id":
                                    candidate_id,
                                "source_format":
                                    "pdf",
                                "source_path":
                                    str(pdf_path),
                                "pdf_page":
                                    page_no,
                                "pdf_line_number":
                                    line_no,
                                "source_line_raw":
                                    line,
                                "field_label_raw":
                                    label,
                                "field_value_raw":
                                    value,
                                "audited_family":
                                    family,
                                "audit_decision":
                                    "accept",
                                "audit_reason":
                                    "exact_anchored_pdf_field_pattern",
                                "semantic_normalization_status":
                                    "not_normalized",
                                "unit_conversion_status":
                                    "not_converted",
                            })

                            family_counts[family] += 1
                            report_accept += 1
                            reports_with_accepted.add(
                                row.get("report_id", "")
                            )
                            cases_with_accepted.add(
                                row.get("case_id", "")
                            )
                            continue

                        if not KEYWORD_RE.search(line):
                            continue

                        reason = exclusion_reason(line)

                        evidence = {
                            **{
                                k: row.get(k, "")
                                for k in BASE
                            },
                            "source_format":
                                "pdf",
                            "source_path":
                                str(pdf_path),
                            "pdf_page":
                                page_no,
                            "pdf_line_number":
                                line_no,
                            "source_line_raw":
                                line,
                        }

                        if reason:
                            excluded.append({
                                **evidence,
                                "audit_decision":
                                    "exclude",
                                "audit_reason":
                                    reason,
                            })
                            report_excluded += 1

                        else:
                            remaining_review.append({
                                **evidence,
                                "audit_decision":
                                    "review",
                                "audit_reason":
                                    "group6_keyword_but_no_exact_accepted_pattern",
                            })
                            report_review += 1

            processed += 1

        except Exception as exc:
            errors.append({
                **{
                    k: row.get(k, "")
                    for k in BASE
                },
                "error_type":
                    type(exc).__name__,
                "pdf_path":
                    str(pdf_path),
                "error":
                    str(exc),
            })
            continue

        coverage.append({
            **{
                k: row.get(k, "")
                for k in BASE
            },
            "pdf_path":
                str(pdf_path),
            "accepted_count":
                report_accept,
            "excluded_keyword_noise_count":
                report_excluded,
            "remaining_review_count":
                report_review,
        })

        if processed % 25 == 0 or processed == selected:
            print(
                f"Audited Group 6 PDF {processed}/{selected} reports...",
                flush=True,
            )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

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
            "check":
                name,
            "status":
                "PASS" if condition else "FAIL",
            "severity":
                severity,
            "observed":
                str(observed),
            "expected":
                str(expected),
            "note":
                note,
        })

    check(
        "pdf_only_reports_selected",
        selected == 181,
        selected,
        181,
    )

    check(
        "pdf_only_reports_processed",
        processed == selected,
        processed,
        selected,
    )

    check(
        "source_errors_zero",
        len(errors) == 0,
        len(errors),
        0,
    )

    ids = [
        norm(row.get("group6_candidate_id", ""))
        for row in accepted
    ]

    check(
        "accepted_ids_unique",
        len(ids) == len(set(ids)),
        len(ids) - len(set(ids)),
        0,
    )

    check(
        "accepted_labels_nonblank",
        all(
            norm(row.get("field_label_raw", ""))
            for row in accepted
        ),
        sum(
            1
            for row in accepted
            if not norm(row.get("field_label_raw", ""))
        ),
        0,
    )

    check(
        "accepted_values_nonblank",
        all(
            norm(row.get("field_value_raw", ""))
            for row in accepted
        ),
        sum(
            1
            for row in accepted
            if not norm(row.get("field_value_raw", ""))
        ),
        0,
    )

    check(
        "accepted_family_accounting",
        sum(family_counts.values()) == len(accepted),
        sum(family_counts.values()),
        len(accepted),
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

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    accepted_cols = [
        *BASE,
        "group6_candidate_id",
        "source_format",
        "source_path",
        "pdf_page",
        "pdf_line_number",
        "source_line_raw",
        "field_label_raw",
        "field_value_raw",
        "audited_family",
        "audit_decision",
        "audit_reason",
        "semantic_normalization_status",
        "unit_conversion_status",
    ]

    evidence_cols = [
        *BASE,
        "source_format",
        "source_path",
        "pdf_page",
        "pdf_line_number",
        "source_line_raw",
        "audit_decision",
        "audit_reason",
    ]

    write_csv(
        out / "accepted_group6_pdf_fields.csv",
        accepted,
        accepted_cols,
    )

    write_csv(
        out / "excluded_keyword_noise.csv",
        excluded,
        evidence_cols,
    )

    write_csv(
        out / "remaining_review_fields.csv",
        remaining_review,
        evidence_cols,
    )

    write_csv(
        out / "family_summary.csv",
        [
            {
                "audited_family": family,
                "field_count": count,
            }
            for family, count
            in family_counts.most_common()
        ],
        [
            "audited_family",
            "field_count",
        ],
    )

    write_csv(
        out / "report_coverage.csv",
        coverage,
        [
            *BASE,
            "pdf_path",
            "accepted_count",
            "excluded_keyword_noise_count",
            "remaining_review_count",
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

    metadata = {
        "created_at":
            datetime.now(timezone.utc).isoformat(),

        "group":
            "Group 6 - Other structured technical and investigation information",

        "stage":
            "PDF-only exact-pattern audit",

        "pdf_only_reports_selected":
            selected,

        "pdf_only_reports_processed":
            processed,

        "accepted_group6_fields":
            len(accepted),

        "excluded_keyword_noise":
            len(excluded),

        "remaining_review_fields":
            len(remaining_review),

        "reports_with_accepted_group6_fields":
            len(reports_with_accepted),

        "cases_with_accepted_group6_fields":
            len(cases_with_accepted),

        "accepted_family_counts":
            dict(family_counts),

        "source_errors":
            len(errors),

        "ocr_used":
            False,

        "validation_checks":
            len(checks),

        "hard_validation_failures":
            hard_failures,

        "warning_validation_failures":
            warning_failures,

        "scope":
            (
                "Exact-pattern audit and reconstruction of Group 6 fields "
                "from the original PDF-only report population after the "
                "diagnostic pass showed that generic label/value parsing "
                "missed technical fields. Only anchored field patterns are "
                "accepted. Documentation text, event-condition fields, "
                "record-structure text, and other keyword-bearing noise are "
                "excluded or retained for explicit review. No OCR, semantic "
                "normalization, unit conversion, fuzzy inference, or source "
                "mutation is performed."
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
        print("GROUP 6 PDF AUDIT HAS HARD VALIDATION FAILURES.")
        raise SystemExit(1)

    print()
    print("GROUP 6 PDF AUDIT COMPLETE.")


if __name__ == "__main__":
    main()
