"""
Validate and freeze the structured Group 5 CSV package.

Input
-----
data/processed/edr/group5_csv_structured_v1/

    measurement_registry.csv
    measurement_values.csv
    companion_context.csv
    extraction_failures.csv
    validation_report.csv
    metadata.json

Output
------
data/processed/edr/group5_csv_validation_v1/

    validation_checks.csv
    suspicious_measurements.csv
    duplicate_source_observations.csv
    family_value_audit.csv
    unit_audit.csv
    metadata.json

If all hard checks pass, also creates:

data/processed/edr/group5_csv_final_v1/

    measurement_registry.csv
    measurement_values.csv
    companion_context.csv
    extraction_failures.csv
    validation_report.csv
    source_validation/
        validation_checks.csv
        suspicious_measurements.csv
        duplicate_source_observations.csv
        family_value_audit.csv
        unit_audit.csv
        metadata.json
    freeze_manifest.json

Validation goals
----------------
- preserve exact source-field accounting
- verify registry/value consistency
- verify ID uniqueness
- inspect duplicate source observations
- audit numeric parsing consistency
- audit unit/family consistency
- surface suspicious textual/non-numeric values
- verify provenance/event-hint fields remain intact
- preserve review evidence rather than force-resolving it

No semantic normalization, unit conversion, or fuzzy event linking is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
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


def file_sha256(path: Path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


# ============================================================
# Helpers
# ============================================================

def norm(value):
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").strip(),
    )


def norm_key(value):
    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            norm(value).casefold(),
        )
    )


def is_truthy_text(value):
    return norm(value).casefold() in {
        "true",
        "1",
        "yes",
    }


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


NUMERIC_PATTERN = re.compile(
    r"[-+]?"
    r"(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?"
)


def safely_numeric_like(value):
    """
    Independent validator for whether a raw value appears to contain one scalar number.
    Used only to compare against field_value_numeric.
    """

    text = norm(value)

    if not text or is_missing_or_na(text):
        return False

    cleaned = text.replace(",", "")

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

    return bool(
        re.fullmatch(
            NUMERIC_PATTERN,
            cleaned,
        )
    )


# ============================================================
# Expected family/unit behavior
# ============================================================

TIME_FAMILIES = {
    "delta_v_timing",
    "acceleration_peak_timing",
    "trigger_relative_timing",
    "delta_v_duration",
    "range_clipping_timing",
    "delta_v_time_zero_offset",
    "roll_time_zero_offset",
    "precrash_time_alignment",
    "sensor_loss_timing",
    "delta_v_integration_time",
}

VELOCITY_CHANGE_FAMILIES = {
    "delta_v_summary",
    "delta_v_component_at_maximum",
}

ANGLE_FAMILIES = {
    "roll_peak",
    "roll_at_trigger",
}

ACCELERATION_FAMILIES = {
    "acceleration_peak",
}

TEXT_FAMILIES = {
    "direction_summary",
}


def unit_class(unit):
    u = norm(unit).casefold()

    if not u:
        return "blank"

    if re.search(
        r"\b(?:ms|msec|millisecond|milliseconds|sec|seconds|s)\b",
        u,
        re.I,
    ):
        return "time"

    if re.search(
        r"\b(?:mph|km/h|kph|m/s)\b",
        u,
        re.I,
    ):
        return "velocity"

    if re.search(
        r"\b(?:g|m/s\^?2|m/s²|ft/s\^?2|ft/s²)\b",
        u,
        re.I,
    ):
        return "acceleration"

    if re.search(
        r"\b(?:deg|degree|degrees)\b",
        u,
        re.I,
    ):
        return "angle"

    if re.search(
        r"\b(?:deg/s|rad/s)\b",
        u,
        re.I,
    ):
        return "angular_rate"

    if "%" in u or "percent" in u:
        return "percent"

    return "other"


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--structured-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_structured_v1"
        ),
    )

    parser.add_argument(
        "--validation-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_validation_v1"
        ),
    )

    parser.add_argument(
        "--final-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_final_v1"
        ),
    )

    args = parser.parse_args()

    src = args.structured_directory
    val_out = args.validation_directory
    final_out = args.final_directory

    required = {
        "registry": src / "measurement_registry.csv",
        "values": src / "measurement_values.csv",
        "companion": src / "companion_context.csv",
        "failures": src / "extraction_failures.csv",
        "validation_report": src / "validation_report.csv",
        "metadata": src / "metadata.json",
    }

    for name, path in required.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {name}: {path}"
            )

    registry = read_csv(required["registry"])
    values = read_csv(required["values"])
    companion = read_csv(required["companion"])
    failures = read_csv(required["failures"])

    source_validation_report = read_csv(
        required["validation_report"]
    )

    source_metadata = json.loads(
        required["metadata"].read_text(
            encoding="utf-8"
        )
    )

    # ========================================================
    # Validation check framework
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
            "status":
                "PASS"
                if condition
                else "FAIL",
            "severity": severity,
            "observed": str(observed),
            "expected": str(expected),
            "note": note,
        })

    # ========================================================
    # Basic accounting
    # ========================================================

    check(
        "registry_expected_count",
        len(registry) == 10595,
        len(registry),
        10595,
        severity="warning",
    )

    check(
        "values_expected_count",
        len(values) == 10595,
        len(values),
        10595,
        severity="warning",
    )

    check(
        "companion_expected_count",
        len(companion) == 1166,
        len(companion),
        1166,
        severity="warning",
    )

    check(
        "extraction_failures_zero",
        len(failures) == 0,
        len(failures),
        0,
    )

    check(
        "registry_values_same_row_count",
        len(registry) == len(values),
        len(registry),
        len(values),
    )

    # ========================================================
    # ID integrity
    # ========================================================

    registry_ids = [
        norm(row.get("measurement_id", ""))
        for row in registry
    ]

    value_ids = [
        norm(row.get("measurement_id", ""))
        for row in values
    ]

    blank_measurement_ids = sum(
        1
        for value in registry_ids
        if not value
    )

    duplicate_measurement_ids = (
        len(registry_ids)
        - len(set(registry_ids))
    )

    check(
        "blank_measurement_ids",
        blank_measurement_ids == 0,
        blank_measurement_ids,
        0,
    )

    check(
        "duplicate_measurement_ids",
        duplicate_measurement_ids == 0,
        duplicate_measurement_ids,
        0,
    )

    check(
        "registry_values_measurement_id_sets_equal",
        set(registry_ids) == set(value_ids),
        len(set(registry_ids) ^ set(value_ids)),
        0,
    )

    candidate_ids = [
        norm(row.get("group5_candidate_id", ""))
        for row in registry
    ]

    blank_candidate_ids = sum(
        1
        for value in candidate_ids
        if not value
    )

    duplicate_candidate_ids = (
        len(candidate_ids)
        - len(set(candidate_ids))
    )

    check(
        "blank_candidate_ids",
        blank_candidate_ids == 0,
        blank_candidate_ids,
        0,
    )

    check(
        "duplicate_candidate_ids",
        duplicate_candidate_ids == 0,
        duplicate_candidate_ids,
        0,
    )

    # ========================================================
    # Registry/value consistency
    # ========================================================

    registry_by_id = {
        row["measurement_id"]: row
        for row in registry
    }

    value_by_id = {
        row["measurement_id"]: row
        for row in values
    }

    comparison_fields = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
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
    ]

    mismatches = 0

    for measurement_id in (
        set(registry_by_id)
        & set(value_by_id)
    ):
        left = registry_by_id[
            measurement_id
        ]
        right = value_by_id[
            measurement_id
        ]

        for field in comparison_fields:
            if norm(left.get(field, "")) != norm(right.get(field, "")):
                mismatches += 1

    check(
        "registry_values_field_mismatches",
        mismatches == 0,
        mismatches,
        0,
    )

    # ========================================================
    # Required provenance fields
    # ========================================================

    required_provenance = [
        "report_id",
        "case_id",
        "vehicle_number",
        "export_basename",
        "source_path",
        "source_record_index",
        "field_label_raw",
        "family",
    ]

    blank_provenance = Counter()

    for row in registry:
        for field in required_provenance:
            if not norm(row.get(field, "")):
                blank_provenance[field] += 1

    total_blank_provenance = sum(
        blank_provenance.values()
    )

    check(
        "required_provenance_blank_cells",
        total_blank_provenance == 0,
        total_blank_provenance,
        0,
        note=json.dumps(
            dict(blank_provenance),
            ensure_ascii=False,
        ),
    )

    # ========================================================
    # Numeric parse audit
    # ========================================================

    numeric_parse_disagreements = []

    for row in registry:
        raw = row.get(
            "field_value_raw",
            ""
        )

        parsed = norm(
            row.get(
                "field_value_numeric",
                ""
            )
        )

        should_parse = safely_numeric_like(
            raw
        )

        did_parse = bool(parsed)

        if should_parse != did_parse:
            numeric_parse_disagreements.append({
                "report_id":
                    row.get("report_id", ""),
                "case_id":
                    row.get("case_id", ""),
                "vehicle_number":
                    row.get("vehicle_number", ""),
                "export_basename":
                    row.get("export_basename", ""),
                "measurement_id":
                    row.get("measurement_id", ""),
                "family":
                    row.get("family", ""),
                "field_label_raw":
                    row.get("field_label_raw", ""),
                "field_value_raw":
                    raw,
                "field_value_numeric":
                    parsed,
                "unit_raw":
                    row.get("unit_raw", ""),
                "issue":
                    (
                        "numeric_like_but_not_parsed"
                        if should_parse
                        else "parsed_but_validator_not_numeric_like"
                    ),
            })

    check(
        "numeric_parse_disagreements",
        len(numeric_parse_disagreements) == 0,
        len(numeric_parse_disagreements),
        0,
        severity="warning",
    )

    # ========================================================
    # Missing/NA consistency
    # ========================================================

    missing_flag_disagreements = 0

    for row in registry:
        expected = is_missing_or_na(
            row.get(
                "field_value_raw",
                ""
            )
        )

        observed = is_truthy_text(
            row.get(
                "field_value_is_missing_or_na",
                ""
            )
        )

        if expected != observed:
            missing_flag_disagreements += 1

    check(
        "missing_value_flag_disagreements",
        missing_flag_disagreements == 0,
        missing_flag_disagreements,
        0,
    )

    # ========================================================
    # Family/unit audit
    # ========================================================

    family_value_audit = []
    unit_audit_rows = []
    suspicious_measurements = list(
        numeric_parse_disagreements
    )

    family_counts = Counter()
    family_numeric = Counter()
    family_missing = Counter()
    family_text = Counter()
    family_units = defaultdict(Counter)

    for row in registry:
        family = norm(
            row.get(
                "family",
                ""
            )
        )

        raw_value = norm(
            row.get(
                "field_value_raw",
                ""
            )
        )

        parsed = norm(
            row.get(
                "field_value_numeric",
                ""
            )
        )

        unit = norm(
            row.get(
                "unit_raw",
                ""
            )
        )

        family_counts[family] += 1

        if parsed:
            family_numeric[family] += 1

        elif is_missing_or_na(
            raw_value
        ):
            family_missing[family] += 1

        else:
            family_text[family] += 1

        family_units[family][
            unit_class(unit)
        ] += 1

        uclass = unit_class(unit)

        expected_classes = set()

        if family in TIME_FAMILIES:
            expected_classes = {
                "time",
                "blank",
            }

        elif family in VELOCITY_CHANGE_FAMILIES:
            expected_classes = {
                "velocity",
                "blank",
            }

        elif family in ANGLE_FAMILIES:
            expected_classes = {
                "angle",
                "blank",
            }

        elif family in ACCELERATION_FAMILIES:
            expected_classes = {
                "acceleration",
                "blank",
            }

        elif family in TEXT_FAMILIES:
            expected_classes = {
                "blank",
                "angle",
                "other",
            }

        if (
            expected_classes
            and uclass not in expected_classes
        ):
            unit_audit_rows.append({
                "report_id":
                    row.get("report_id", ""),
                "case_id":
                    row.get("case_id", ""),
                "vehicle_number":
                    row.get("vehicle_number", ""),
                "export_basename":
                    row.get("export_basename", ""),
                "measurement_id":
                    row.get("measurement_id", ""),
                "family":
                    family,
                "field_label_raw":
                    row.get("field_label_raw", ""),
                "field_value_raw":
                    raw_value,
                "unit_raw":
                    unit,
                "unit_class":
                    uclass,
                "expected_unit_classes":
                    "|".join(
                        sorted(expected_classes)
                    ),
                "issue":
                    "unexpected_unit_class_for_family",
            })

    for family, count in (
        family_counts.most_common()
    ):
        family_value_audit.append({
            "family":
                family,

            "measurement_count":
                count,

            "numeric_value_count":
                family_numeric[
                    family
                ],

            "missing_or_na_count":
                family_missing[
                    family
                ],

            "non_numeric_text_count":
                family_text[
                    family
                ],

            "unit_class_counts_json":
                json.dumps(
                    dict(
                        family_units[
                            family
                        ]
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
        })

    check(
        "unexpected_unit_family_rows",
        len(unit_audit_rows) == 0,
        len(unit_audit_rows),
        0,
        severity="warning",
    )

    # ========================================================
    # Suspicious textual values
    # ========================================================

    for row in registry:
        family = norm(
            row.get(
                "family",
                ""
            )
        )

        raw = norm(
            row.get(
                "field_value_raw",
                ""
            )
        )

        parsed = norm(
            row.get(
                "field_value_numeric",
                ""
            )
        )

        if (
            family not in TEXT_FAMILIES
            and raw
            and not parsed
            and not is_missing_or_na(raw)
        ):
            suspicious_measurements.append({
                "report_id":
                    row.get("report_id", ""),
                "case_id":
                    row.get("case_id", ""),
                "vehicle_number":
                    row.get("vehicle_number", ""),
                "export_basename":
                    row.get("export_basename", ""),
                "measurement_id":
                    row.get("measurement_id", ""),
                "family":
                    family,
                "field_label_raw":
                    row.get("field_label_raw", ""),
                "field_value_raw":
                    raw,
                "field_value_numeric":
                    parsed,
                "unit_raw":
                    row.get("unit_raw", ""),
                "issue":
                    "non_numeric_text_in_numeric_or_timing_family",
            })

    # Deduplicate suspicion rows.
    suspicion_keyed = {}

    for row in suspicious_measurements:
        key = (
            row.get("measurement_id", ""),
            row.get("issue", ""),
        )
        suspicion_keyed[key] = row

    suspicious_measurements = list(
        suspicion_keyed.values()
    )

    check(
        "suspicious_measurement_rows",
        len(suspicious_measurements) == 0,
        len(suspicious_measurements),
        0,
        severity="warning",
        note=(
            "Review evidence only; does not automatically invalidate "
            "the package."
        ),
    )

    # ========================================================
    # Duplicate source observation audit
    # ========================================================

    source_groups = defaultdict(list)

    for row in registry:
        key = (
            norm(row.get("source_path", "")),
            norm(row.get("source_record_index", "")),
            norm_key(row.get("field_label_raw", "")),
            norm(row.get("field_value_raw", "")),
        )

        source_groups[key].append(row)

    duplicate_source_observations = []

    for key, rows in source_groups.items():
        if len(rows) <= 1:
            continue

        for row in rows:
            duplicate_source_observations.append({
                "report_id":
                    row.get("report_id", ""),
                "case_id":
                    row.get("case_id", ""),
                "vehicle_number":
                    row.get("vehicle_number", ""),
                "export_basename":
                    row.get("export_basename", ""),
                "measurement_id":
                    row.get("measurement_id", ""),
                "source_path":
                    row.get("source_path", ""),
                "source_record_index":
                    row.get(
                        "source_record_index",
                        "",
                    ),
                "family":
                    row.get("family", ""),
                "field_label_raw":
                    row.get(
                        "field_label_raw",
                        "",
                    ),
                "field_value_raw":
                    row.get(
                        "field_value_raw",
                        "",
                    ),
                "duplicate_group_size":
                    len(rows),
            })

    check(
        "duplicate_source_observation_rows",
        len(duplicate_source_observations) == 0,
        len(duplicate_source_observations),
        0,
        severity="warning",
    )

    # ========================================================
    # Event hint / provenance sanity
    # ========================================================

    event_hint_count = sum(
        1
        for row in registry
        if norm(
            row.get(
                "event_hint",
                ""
            )
        )
    )

    linked_exact_count = sum(
        1
        for row in registry
        if norm(
            row.get(
                "event_link_status",
                ""
            )
        ).casefold()
        not in {
            "",
            "not_linked",
            "source_hint_only",
        }
    )

    check(
        "no_fuzzy_or_semantic_event_linking",
        linked_exact_count == 0,
        linked_exact_count,
        0,
    )

    source_path_missing = sum(
        1
        for row in registry
        if not norm(
            row.get(
                "source_path",
                ""
            )
        )
    )

    check(
        "source_path_present",
        source_path_missing == 0,
        source_path_missing,
        0,
    )

    # ========================================================
    # Source extraction validation inheritance
    # ========================================================

    inherited_hard_failures = sum(
        1
        for row in source_validation_report
        if (
            norm(row.get("status", "")).upper()
            == "FAIL"
            and norm(
                row.get(
                    "severity",
                    ""
                )
            ).casefold()
            == "hard"
        )
    )

    check(
        "source_structural_validation_hard_failures",
        inherited_hard_failures == 0,
        inherited_hard_failures,
        0,
    )

    # ========================================================
    # Write validation outputs
    # ========================================================

    val_out.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_csv(
        val_out / "validation_checks.csv",
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

    write_csv(
        val_out / "suspicious_measurements.csv",
        suspicious_measurements,
        [
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "measurement_id",
            "family",
            "field_label_raw",
            "field_value_raw",
            "field_value_numeric",
            "unit_raw",
            "issue",
        ],
    )

    write_csv(
        val_out
        / "duplicate_source_observations.csv",
        duplicate_source_observations,
        [
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "measurement_id",
            "source_path",
            "source_record_index",
            "family",
            "field_label_raw",
            "field_value_raw",
            "duplicate_group_size",
        ],
    )

    write_csv(
        val_out / "family_value_audit.csv",
        family_value_audit,
        [
            "family",
            "measurement_count",
            "numeric_value_count",
            "missing_or_na_count",
            "non_numeric_text_count",
            "unit_class_counts_json",
        ],
    )

    write_csv(
        val_out / "unit_audit.csv",
        unit_audit_rows,
        [
            "report_id",
            "case_id",
            "vehicle_number",
            "export_basename",
            "measurement_id",
            "family",
            "field_label_raw",
            "field_value_raw",
            "unit_raw",
            "unit_class",
            "expected_unit_classes",
            "issue",
        ],
    )

    hard_failures = [
        row
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"]
            == "hard"
        )
    ]

    warning_failures = [
        row
        for row in checks
        if (
            row["status"] == "FAIL"
            and row["severity"]
            == "warning"
        )
    ]

    validation_metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "CSV validation",

        "registry_rows":
            len(registry),

        "value_rows":
            len(values),

        "companion_context_rows":
            len(companion),

        "extraction_failure_rows":
            len(failures),

        "reports_with_measurements":
            len({
                norm(row.get("report_id", ""))
                for row in registry
                if norm(row.get("report_id", ""))
            }),

        "cases_with_measurements":
            len({
                norm(row.get("case_id", ""))
                for row in registry
                if norm(row.get("case_id", ""))
            }),

        "event_hint_rows":
            event_hint_count,

        "numeric_parse_disagreement_rows":
            len(
                numeric_parse_disagreements
            ),

        "suspicious_measurement_rows":
            len(
                suspicious_measurements
            ),

        "unit_audit_rows":
            len(
                unit_audit_rows
            ),

        "duplicate_source_observation_rows":
            len(
                duplicate_source_observations
            ),

        "validation_checks":
            len(checks),

        "validation_failures":
            sum(
                1
                for row in checks
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

        "validation_status":
            (
                "validated_ready_for_freeze"
                if not hard_failures
                else "validation_failed"
            ),

        "scope":
            (
                "Validation of the structured Group 5 CSV scalar "
                "measurement package. Checks include row accounting, "
                "registry/value consistency, identifier uniqueness, "
                "required provenance, independent numeric parsing, "
                "missing-value flags, family/unit compatibility, "
                "duplicate source observations, suspicious textual "
                "values, and preservation of non-fuzzy event linkage. "
                "Warnings are preserved as explicit review evidence "
                "and do not mutate source measurements."
            ),
    }

    tmp = val_out / "metadata.json.part"

    tmp.write_text(
        json.dumps(
            validation_metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        val_out / "metadata.json"
    )

    print()
    print(
        json.dumps(
            validation_metadata,
            indent=2,
            ensure_ascii=False,
        )
    )

    if hard_failures:
        print()
        print(
            "GROUP 5 CSV VALIDATION FAILED. "
            "Final package was NOT frozen."
        )

        for row in hard_failures:
            print(
                f"- {row['check']}: "
                f"observed={row['observed']} "
                f"expected={row['expected']}"
            )

        raise SystemExit(1)

    # ========================================================
    # Freeze validated package
    # ========================================================

    if final_out.exists():
        shutil.rmtree(final_out)

    final_out.mkdir(
        parents=True,
        exist_ok=True,
    )

    core_files = [
        "measurement_registry.csv",
        "measurement_values.csv",
        "companion_context.csv",
        "extraction_failures.csv",
        "validation_report.csv",
        "metadata.json",
    ]

    for filename in core_files:
        shutil.copy2(
            src / filename,
            final_out / filename,
        )

    review_dir = (
        final_out
        / "source_validation"
    )

    review_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    validation_files = [
        "validation_checks.csv",
        "suspicious_measurements.csv",
        "duplicate_source_observations.csv",
        "family_value_audit.csv",
        "unit_audit.csv",
        "metadata.json",
    ]

    for filename in validation_files:
        shutil.copy2(
            val_out / filename,
            review_dir / filename,
        )

    frozen_files = []

    for path in sorted(
        final_out.rglob("*")
    ):
        if path.is_file():
            frozen_files.append({
                "relative_path":
                    str(
                        path.relative_to(
                            final_out
                        )
                    ),
                "size_bytes":
                    path.stat().st_size,
                "sha256":
                    file_sha256(path),
            })

    freeze_manifest = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "source_package":
            str(src),

        "validation_package":
            str(val_out),

        "freeze_status":
            "frozen_validated_with_explicit_review_evidence",

        "registry_rows":
            len(registry),

        "value_rows":
            len(values),

        "companion_context_rows":
            len(companion),

        "extraction_failures":
            len(failures),

        "hard_validation_failures":
            len(hard_failures),

        "warning_validation_failures":
            len(warning_failures),

        "suspicious_measurement_rows":
            len(suspicious_measurements),

        "unit_audit_rows":
            len(unit_audit_rows),

        "duplicate_source_observation_rows":
            len(
                duplicate_source_observations
            ),

        "immutable_intent":
            (
                "This package is the frozen validated Group 5 CSV source "
                "package. Do not modify unless a concrete validation or "
                "source-extraction error is demonstrated."
            ),

        "files":
            frozen_files,
    }

    (final_out / "freeze_manifest.json").write_text(
        json.dumps(
            freeze_manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(
        json.dumps(
            freeze_manifest,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        f"Validation outputs: {val_out}"
    )

    print(
        f"Frozen package: {final_out}"
    )

    print()
    print(
        "GROUP 5 CSV VALIDATION AND FREEZE COMPLETE."
    )


if __name__ == "__main__":
    main()
