"""
Build structured Group 5 CSV scalar crash/event measurement datasets.

Input
-----
data/processed/edr/group5_csv_resolved_v1/
    accepted_group5_fields.csv
    companion_group5_context.csv

Output
------
data/processed/edr/group5_csv_structured_v1/

    measurement_registry.csv
    measurement_values.csv
    companion_context.csv
    extraction_audit.csv
    extraction_failures.csv
    validation_report.csv
    metadata.json

Purpose
-------
Convert the resolved Group 5 CSV field population into a structured scalar
measurement package while preserving the original labels, values, units,
source rows, report/case/vehicle linkage, section context, and event hints.

Important rules
---------------
- One accepted source field becomes one measurement record.
- Raw labels and raw values are preserved exactly as extracted.
- Parsed numeric values are added only when safely recoverable.
- Raw units are inferred conservatively from the label/value.
- No semantic normalization is performed.
- No unit conversion is performed.
- No fuzzy event identity inference is performed.
- Event hints remain source hints only.
- Companion/context fields remain separate from primary measurements.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

csv.field_size_limit(100_000_000)

BASE = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


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


def write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".part"
    )

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
        str(
            value
            if value is not None
            else ""
        ).strip(),
    )


def norm_key(value):
    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            norm(value).casefold(),
        )
    )


def identifier(*parts):
    text = "|".join(
        norm(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:24]


MISSING_VALUES = {
    "",
    "n/a",
    "na",
    "sna",
    "not available",
    "data not available",
    "not applicable",
    "unknown",
    "invalid",
    "not recorded",
}


def is_missing_or_na(value):
    return norm(value).casefold() in MISSING_VALUES


# ============================================================
# Unit parsing
# ============================================================

UNIT_PATTERNS = [
    ("mph", r"\bmph\b"),
    ("km/h", r"\bkm/h\b|\bkph\b"),
    ("m/s", r"\bm/s\b"),
    ("g", r"(?<![a-z])g(?![a-z])"),
    ("m/s^2", r"\bm/s(?:\^?2|²)\b"),
    ("ft/s^2", r"\bft/s(?:\^?2|²)\b"),
    ("ms", r"\bmsec\b|\bmilliseconds?\b|\bms\b"),
    ("s", r"\bseconds?\b|\bsec\b"),
    ("deg", r"\bdegrees?\b|\bdeg\b"),
    ("deg/s", r"\bdeg/s\b|\bdegrees?/sec\b"),
    ("rad/s", r"\brad/s\b"),
    ("%", r"%|\bpercent\b"),
]


def extract_unit(label, value):
    """
    Conservative raw-unit extraction.

    Prefer units embedded in the field label. If absent, inspect the raw value.
    """

    label_text = norm(label)
    value_text = norm(value)

    # Parenthesized units in labels are strongest evidence.
    for content in reversed(
        re.findall(
            r"\(([^()]*)\)",
            label_text,
        )
    ):
        candidate = norm(content)

        for canonical, pattern in UNIT_PATTERNS:
            if re.search(
                pattern,
                candidate,
                re.I,
            ):
                return candidate

    # Otherwise search label for known unit tokens.
    for canonical, pattern in UNIT_PATTERNS:
        match = re.search(
            pattern,
            label_text,
            re.I,
        )

        if match:
            return norm(
                match.group(0)
            )

    # Finally inspect the raw value suffix.
    for canonical, pattern in UNIT_PATTERNS:
        match = re.search(
            pattern,
            value_text,
            re.I,
        )

        if match:
            return norm(
                match.group(0)
            )

    return ""


# ============================================================
# Numeric parsing
# ============================================================

NUMERIC_PATTERN = re.compile(
    r"[-+]?"
    r"(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?"
)


def parse_numeric(value):
    """
    Parse only if the source value is safely interpretable as one scalar number.

    Examples accepted:
        -20.26
        117.5
        -5.35 MPH
        150 msec

    Examples not forced:
        Left
        Yes
        10-20
        3/4
    """

    text = norm(value)

    if not text:
        return ""

    if is_missing_or_na(text):
        return ""

    cleaned = text.replace(
        ",",
        "",
    )

    # Remove common unit suffixes.
    cleaned = re.sub(
        r"\s*(?:"
        r"mph|km/h|kph|m/s|m/s\^?2|m/s²|"
        r"ft/s\^?2|ft/s²|"
        r"g|ms|msec|milliseconds?|"
        r"sec|seconds?|"
        r"deg|degrees?|deg/s|rad/s|"
        r"%|percent"
        r")\s*$",
        "",
        cleaned,
        flags=re.I,
    )

    cleaned = norm(cleaned)

    if not re.fullmatch(
        NUMERIC_PATTERN,
        cleaned,
    ):
        return ""

    try:
        number = float(cleaned)

        if math.isfinite(number):
            return number

    except ValueError:
        pass

    return ""


# ============================================================
# Measurement records
# ============================================================

def build_measurement(source):
    candidate_id = norm(
        source.get(
            "group5_candidate_id",
            ""
        )
    )

    if not candidate_id:
        raise ValueError(
            "Missing group5_candidate_id."
        )

    label = norm(
        source.get(
            "field_label_raw",
            ""
        )
    )

    if not label:
        raise ValueError(
            "Missing field_label_raw."
        )

    raw_value = norm(
        source.get(
            "field_value_raw",
            ""
        )
    )

    measurement_id = (
        "g5csvmeas_"
        + identifier(
            source.get(
                "report_id",
                ""
            ),
            candidate_id,
            source.get(
                "source_record_index",
                ""
            ),
            label,
        )
    )

    unit = extract_unit(
        label,
        raw_value,
    )

    numeric = parse_numeric(
        raw_value
    )

    return {
        **{
            key:
                source.get(
                    key,
                    ""
                )
            for key in BASE
        },

        "measurement_id":
            measurement_id,

        "group5_candidate_id":
            candidate_id,

        "source_format":
            "csv",

        "source_path":
            source.get(
                "source_path",
                "",
            ),

        "source_record_index":
            source.get(
                "source_record_index",
                "",
            ),

        "source_section_heading":
            source.get(
                "source_section_heading",
                "",
            ),

        "event_hint":
            source.get(
                "event_hint",
                "",
            ),

        "event_link_status":
            source.get(
                "event_link_status",
                "",
            )
            or "not_linked",

        "family":
            source.get(
                "audited_family",
                "",
            ),

        "field_label_raw":
            label,

        "field_value_raw":
            raw_value,

        "field_value_numeric":
            numeric,

        "field_value_is_missing_or_na":
            is_missing_or_na(
                raw_value
            ),

        "unit_raw":
            unit,

        "source_row_json":
            source.get(
                "source_row_json",
                "",
            ),

        "source_value_column_index":
            source.get(
                "value_column_index",
                "",
            ),

        "group4_companion_support_count":
            source.get(
                "group4_companion_support_count",
                "",
            ),

        "processing_status":
            "structured_extracted",

        "semantic_normalization_status":
            "not_normalized",

        "unit_conversion_status":
            "not_converted",
    }


def build_companion(source):
    candidate_id = norm(
        source.get(
            "group5_candidate_id",
            ""
        )
    )

    companion_id = (
        "g5csvctx_"
        + identifier(
            source.get(
                "report_id",
                ""
            ),
            candidate_id,
            source.get(
                "source_record_index",
                ""
            ),
            source.get(
                "field_label_raw",
                ""
            ),
        )
    )

    return {
        **{
            key:
                source.get(
                    key,
                    ""
                )
            for key in BASE
        },

        "companion_context_id":
            companion_id,

        "group5_candidate_id":
            candidate_id,

        "source_format":
            "csv",

        "source_path":
            source.get(
                "source_path",
                "",
            ),

        "source_record_index":
            source.get(
                "source_record_index",
                "",
            ),

        "source_section_heading":
            source.get(
                "source_section_heading",
                "",
            ),

        "event_hint":
            source.get(
                "event_hint",
                "",
            ),

        "field_label_raw":
            source.get(
                "field_label_raw",
                "",
            ),

        "field_value_raw":
            source.get(
                "field_value_raw",
                "",
            ),

        "audited_family":
            source.get(
                "audited_family",
                "",
            ),

        "audit_reason":
            source.get(
                "audit_reason",
                "",
            ),

        "source_row_json":
            source.get(
                "source_row_json",
                "",
            ),

        "processing_status":
            "preserved_group5_companion_context",
    }


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--resolved-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_resolved_v1"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_structured_v1"
        ),
    )

    args = parser.parse_args()

    accepted_path = (
        args.resolved_directory
        / "accepted_group5_fields.csv"
    )

    companion_path = (
        args.resolved_directory
        / "companion_group5_context.csv"
    )

    if not accepted_path.exists():
        raise FileNotFoundError(
            accepted_path
        )

    if not companion_path.exists():
        raise FileNotFoundError(
            companion_path
        )

    accepted = read_csv(
        accepted_path
    )

    companion_input = read_csv(
        companion_path
    )

    measurements = []
    companion_rows = []
    audit_rows = []
    failures = []

    # ========================================================
    # Primary measurement extraction
    # ========================================================

    for index, source in enumerate(
        accepted,
        1,
    ):
        try:
            record = build_measurement(
                source
            )

            measurements.append(
                record
            )

            audit_rows.append({
                **{
                    key:
                        source.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "group5_candidate_id":
                    source.get(
                        "group5_candidate_id",
                        "",
                    ),

                "measurement_id":
                    record[
                        "measurement_id"
                    ],

                "family":
                    record[
                        "family"
                    ],

                "field_label_raw":
                    record[
                        "field_label_raw"
                    ],

                "field_value_raw":
                    record[
                        "field_value_raw"
                    ],

                "field_value_numeric":
                    record[
                        "field_value_numeric"
                    ],

                "unit_raw":
                    record[
                        "unit_raw"
                    ],

                "status":
                    "success",

                "issue":
                    "",
            })

        except Exception as exc:
            failures.append({
                **{
                    key:
                        source.get(
                            key,
                            ""
                        )
                    for key in BASE
                },

                "group5_candidate_id":
                    source.get(
                        "group5_candidate_id",
                        "",
                    ),

                "field_label_raw":
                    source.get(
                        "field_label_raw",
                        "",
                    ),

                "field_value_raw":
                    source.get(
                        "field_value_raw",
                        "",
                    ),

                "error_type":
                    type(exc).__name__,

                "error":
                    str(exc),
            })

        if (
            index % 1000 == 0
            or index
            == len(accepted)
        ):
            print(
                "Structured Group 5 CSV "
                f"{index}/{len(accepted)} fields...",
                flush=True,
            )

    # ========================================================
    # Companion/context extraction
    # ========================================================

    for source in companion_input:
        companion_rows.append(
            build_companion(
                source
            )
        )

    # ========================================================
    # Validation
    # ========================================================

    validation = []

    def check(
        name,
        condition,
        observed,
        expected,
        severity="hard",
        note="",
    ):
        validation.append({
            "check":
                name,

            "status":
                (
                    "PASS"
                    if condition
                    else "FAIL"
                ),

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
        "accepted_fields_accounted_for",
        (
            len(measurements)
            + len(failures)
            == len(accepted)
        ),
        (
            len(measurements)
            + len(failures)
        ),
        len(accepted),
    )

    check(
        "expected_input_accepted_count",
        len(accepted) == 10595,
        len(accepted),
        10595,
        severity="warning",
    )

    check(
        "expected_companion_count",
        len(companion_rows) == 1166,
        len(companion_rows),
        1166,
        severity="warning",
    )

    measurement_ids = [
        row["measurement_id"]
        for row in measurements
    ]

    duplicate_measurement_ids = (
        len(measurement_ids)
        - len(
            set(
                measurement_ids
            )
        )
    )

    check(
        "measurement_ids_unique",
        duplicate_measurement_ids == 0,
        duplicate_measurement_ids,
        0,
    )

    candidate_ids = [
        row["group5_candidate_id"]
        for row in measurements
    ]

    duplicate_candidate_ids = (
        len(candidate_ids)
        - len(
            set(
                candidate_ids
            )
        )
    )

    check(
        "candidate_ids_unique_in_measurements",
        duplicate_candidate_ids == 0,
        duplicate_candidate_ids,
        0,
    )

    blank_labels = sum(
        1
        for row in measurements
        if not norm(
            row["field_label_raw"]
        )
    )

    check(
        "blank_field_labels",
        blank_labels == 0,
        blank_labels,
        0,
    )

    blank_families = sum(
        1
        for row in measurements
        if not norm(
            row["family"]
        )
    )

    check(
        "blank_measurement_families",
        blank_families == 0,
        blank_families,
        0,
    )

    source_format_errors = sum(
        1
        for row in measurements
        if row[
            "source_format"
        ] != "csv"
    )

    check(
        "source_format_is_csv",
        source_format_errors == 0,
        source_format_errors,
        0,
    )

    numeric_value_count = sum(
        1
        for row in measurements
        if row[
            "field_value_numeric"
        ] != ""
    )

    missing_value_count = sum(
        1
        for row in measurements
        if row[
            "field_value_is_missing_or_na"
        ]
    )

    raw_unit_count = sum(
        1
        for row in measurements
        if norm(
            row["unit_raw"]
        )
    )

    # Families should be one of the resolved audit families.
    family_counts = Counter(
        row["family"]
        for row in measurements
    )

    expected_families = {
        "delta_v_summary",
        "delta_v_timing",
        "acceleration_peak",
        "acceleration_peak_timing",
        "trigger_relative_timing",
        "delta_v_duration",
        "range_clipping_timing",
        "delta_v_time_zero_offset",
        "direction_summary",
        "roll_peak",
        "delta_v_component_at_maximum",
        "roll_time_zero_offset",
        "roll_at_trigger",
        "precrash_time_alignment",
        "sensor_loss_timing",
        "delta_v_integration_time",
    }

    unexpected_families = sorted(
        family
        for family in family_counts
        if family
        not in expected_families
    )

    check(
        "unexpected_family_count",
        len(
            unexpected_families
        )
        == 0,
        len(
            unexpected_families
        ),
        0,
        severity="warning",
        note=json.dumps(
            unexpected_families,
            ensure_ascii=False,
        ),
    )

    # ========================================================
    # Write outputs
    # ========================================================

    out = args.output_directory
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        out
        / "measurement_registry.csv",
        measurements,
        [
            *BASE,
            "measurement_id",
            "group5_candidate_id",
            "source_format",
            "source_path",
            "source_record_index",
            "source_section_heading",
            "event_hint",
            "event_link_status",
            "family",
            "field_label_raw",
            "field_value_raw",
            "field_value_numeric",
            "field_value_is_missing_or_na",
            "unit_raw",
            "source_row_json",
            "source_value_column_index",
            "group4_companion_support_count",
            "processing_status",
            "semantic_normalization_status",
            "unit_conversion_status",
        ],
    )

    # Alias with a value-centric name for downstream convenience.
    write_csv(
        out
        / "measurement_values.csv",
        measurements,
        [
            *BASE,
            "measurement_id",
            "group5_candidate_id",
            "event_hint",
            "event_link_status",
            "family",
            "field_label_raw",
            "field_value_raw",
            "field_value_numeric",
            "field_value_is_missing_or_na",
            "unit_raw",
            "source_path",
            "source_record_index",
            "source_section_heading",
            "source_row_json",
            "processing_status",
            "semantic_normalization_status",
            "unit_conversion_status",
        ],
    )

    write_csv(
        out
        / "companion_context.csv",
        companion_rows,
        [
            *BASE,
            "companion_context_id",
            "group5_candidate_id",
            "source_format",
            "source_path",
            "source_record_index",
            "source_section_heading",
            "event_hint",
            "field_label_raw",
            "field_value_raw",
            "audited_family",
            "audit_reason",
            "source_row_json",
            "processing_status",
        ],
    )

    write_csv(
        out
        / "extraction_audit.csv",
        audit_rows,
        [
            *BASE,
            "group5_candidate_id",
            "measurement_id",
            "family",
            "field_label_raw",
            "field_value_raw",
            "field_value_numeric",
            "unit_raw",
            "status",
            "issue",
        ],
    )

    write_csv(
        out
        / "extraction_failures.csv",
        failures,
        [
            *BASE,
            "group5_candidate_id",
            "field_label_raw",
            "field_value_raw",
            "error_type",
            "error",
        ],
    )

    write_csv(
        out
        / "validation_report.csv",
        validation,
        [
            "check",
            "status",
            "severity",
            "observed",
            "expected",
            "note",
        ],
    )

    # ========================================================
    # Metadata
    # ========================================================

    reports_with_measurements = {
        row["report_id"]
        for row in measurements
        if norm(
            row["report_id"]
        )
    }

    cases_with_measurements = {
        row["case_id"]
        for row in measurements
        if norm(
            row["case_id"]
        )
    }

    hard_failures = [
        row
        for row in validation
        if (
            row["status"]
            == "FAIL"
            and row["severity"]
            == "hard"
        )
    ]

    warning_failures = [
        row
        for row in validation
        if (
            row["status"]
            == "FAIL"
            and row["severity"]
            == "warning"
        )
    ]

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "CSV structural extraction",

        "input_accepted_fields":
            len(accepted),

        "structured_measurement_count":
            len(measurements),

        "companion_context_count":
            len(companion_rows),

        "extraction_failure_count":
            len(failures),

        "reports_with_structured_measurements":
            len(
                reports_with_measurements
            ),

        "cases_with_structured_measurements":
            len(
                cases_with_measurements
            ),

        "family_counts":
            dict(
                family_counts
            ),

        "numeric_value_count":
            numeric_value_count,

        "missing_or_unavailable_value_count":
            missing_value_count,

        "measurement_rows_with_raw_unit":
            raw_unit_count,

        "unique_raw_field_labels":
            len(
                {
                    row["field_label_raw"]
                    for row in measurements
                }
            ),

        "validation_checks":
            len(validation),

        "validation_failures":
            sum(
                1
                for row in validation
                if row["status"]
                == "FAIL"
            ),

        "hard_validation_failures":
            len(
                hard_failures
            ),

        "warning_validation_failures":
            len(
                warning_failures
            ),

        "scope":
            (
                "Structural extraction of resolved Group 5 CSV scalar "
                "crash/event measurements. Each accepted source field is "
                "preserved as one structured measurement with report, case, "
                "vehicle, source row, section, event hint, raw label, raw "
                "value, conservatively parsed numeric value, and raw unit. "
                "Companion/context fields remain separate. No semantic "
                "normalization, unit conversion, fuzzy event identity "
                "inference, PDF processing, or CSV/PDF integration is "
                "performed."
            ),
    }

    tmp = (
        out
        / "metadata.json.part"
    )

    tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        out
        / "metadata.json"
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
    print(
        f"Outputs: {out}"
    )

    if hard_failures:
        print()
        print(
            "GROUP 5 CSV STRUCTURAL EXTRACTION "
            "HAS HARD VALIDATION FAILURES."
        )

        for row in hard_failures:
            print(
                f"- {row['check']}: "
                f"observed={row['observed']} "
                f"expected={row['expected']}"
            )

        raise SystemExit(1)

    print()
    print(
        "GROUP 5 CSV STRUCTURAL EXTRACTION COMPLETE."
    )


if __name__ == "__main__":
    main()
