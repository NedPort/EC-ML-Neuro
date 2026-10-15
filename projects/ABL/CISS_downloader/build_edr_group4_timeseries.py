"""
Build Group 4 time-series working datasets from PCM EDR tables.

Current scope:
- PCM EDR tables previously quarantined during Group 2 processing
- preserve original row evidence
- identify units rows
- preserve buffer ordering
- parse relative time when available
- produce registry, wide-sample, and long-value datasets

No semantic filtering of individual PCM signals is performed here.
"""

import argparse
import csv
import json
import hashlib
import re

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter


csv.field_size_limit(10000000)


BASE = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


# ============================================================
# I/O
# ============================================================

def read(path):
    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def write(path, rows, columns):
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
        )

        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


# ============================================================
# Helpers
# ============================================================

def normalize_space(value):
    return re.sub(
        r"\s+",
        " ",
        (value or "").strip(),
    )


def safe_json_list(value):
    try:
        result = json.loads(value)

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return []

    if not isinstance(result, list):
        return []

    return result


def parse_float(value):
    value = normalize_space(value)

    if not value:
        return None

    if value.lower() in {
        "n/a",
        "na",
        "not available",
        "not reported",
    }:
        return None

    try:
        return float(value)

    except ValueError:
        return None


def make_series_id(
    report_id,
    section_id,
):
    token = hashlib.sha256(
        (
            report_id
            + "|"
            + section_id
        ).encode()
    ).hexdigest()[:24]

    return (
        "g4ts_"
        + token
    )


def make_sample_id(
    series_id,
    source_record,
):
    token = hashlib.sha256(
        (
            series_id
            + "|"
            + source_record
        ).encode()
    ).hexdigest()[:24]

    return (
        "g4sample_"
        + token
    )


def is_pcm_units_row(
    header,
    values,
):
    """
    Detect the PCM units/encoding-definition row.

    Expected beginning:
        Buffer Address -> Hex
        Relative Time  -> Seconds
    """

    if len(values) < 2:
        return False

    first = normalize_space(
        values[0]
    ).lower()

    second = normalize_space(
        values[1]
    ).lower()

    return (
        first == "hex"
        and second == "seconds"
    )


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input-file",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group2_working_v1/"
            "pcm_buffer_rows.csv"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group4_timeseries_v1"
        ),
    )

    args = parser.parse_args()

    rows = read(
        args.input_file
    )

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # Group rows by PCM section
    # ========================================================

    by_section = {}

    for row in rows:

        section_id = row[
            "section_id"
        ]

        by_section.setdefault(
            section_id,
            [],
        ).append(
            row
        )

    # ========================================================
    # Outputs
    # ========================================================

    registry = []

    samples_wide = []

    values_long = []

    audit_rows = []

    # ========================================================
    # Process each PCM section
    # ========================================================

    for section_id, section_rows in by_section.items():

        first_row = (
            section_rows[0]
        )

        report_id = (
            first_row[
                "report_id"
            ]
        )

        series_id = make_series_id(
            report_id,
            section_id,
        )

        # ----------------------------------------------------
        # Establish header
        # ----------------------------------------------------

        header = []

        for row in section_rows:

            candidate_header = safe_json_list(
                row[
                    "source_header_json"
                ]
            )

            if candidate_header:
                header = candidate_header
                break

        if not header:

            audit_rows.append({
                **{
                    key:
                        first_row.get(
                            key,
                            "",
                        )
                    for key in BASE
                },

                "section_id":
                    section_id,

                "series_id":
                    series_id,

                "issue":
                    "missing_header",

                "details":
                    "No valid source_header_json found.",
            })

            continue

        # ----------------------------------------------------
        # Find unit row and measurement rows
        # ----------------------------------------------------

        unit_values = None

        measurement_rows = []

        header_candidate_rows = 0

        for row in section_rows:

            if (
                row[
                    "row_role"
                ]
                == "header_candidate"
            ):
                header_candidate_rows += 1
                continue

            values = safe_json_list(
                row[
                    "source_row_json"
                ]
            )

            if not values:
                continue

            if (
                unit_values is None
                and is_pcm_units_row(
                    header,
                    values,
                )
            ):

                unit_values = values

                continue

            measurement_rows.append(
                row
            )

        # ----------------------------------------------------
        # Normalize units to header length
        # ----------------------------------------------------

        if unit_values is None:
            unit_values = [
                ""
                for _ in header
            ]

        if len(unit_values) < len(header):
            unit_values = (
                unit_values
                + [""]
                * (
                    len(header)
                    - len(unit_values)
                )
            )

        unit_values = (
            unit_values[
                :len(header)
            ]
        )

        # ----------------------------------------------------
        # Examine time axis
        # ----------------------------------------------------

        relative_times = []

        for row in measurement_rows:

            values = safe_json_list(
                row[
                    "source_row_json"
                ]
            )

            if len(values) > 1:

                relative_times.append(
                    parse_float(
                        values[1]
                    )
                )

            else:

                relative_times.append(
                    None
                )

        numeric_times = [
            value
            for value in relative_times
            if value is not None
        ]

        if (
            measurement_rows
            and len(numeric_times)
            == len(measurement_rows)
        ):

            time_axis_status = (
                "relative_time_available"
            )

        elif numeric_times:

            time_axis_status = (
                "relative_time_partial"
            )

        else:

            time_axis_status = (
                "buffer_order_only"
            )

        # ----------------------------------------------------
        # Registry entry
        # ----------------------------------------------------

        registry.append({

            **{
                key:
                    first_row.get(
                        key,
                        "",
                    )
                for key in BASE
            },

            "series_id":
                series_id,

            "section_id":
                section_id,

            "source_module":
                "PCM",

            "source_scope_candidate":
                first_row.get(
                    "scope_candidate",
                    "",
                ),

            "time_axis_field":
                (
                    header[1]
                    if len(header) > 1
                    else ""
                ),

            "time_axis_unit":
                (
                    unit_values[1]
                    if len(unit_values) > 1
                    else ""
                ),

            "time_axis_status":
                time_axis_status,

            "sample_count":
                len(
                    measurement_rows
                ),

            "signal_column_count":
                max(
                    len(header) - 2,
                    0,
                ),

            "column_count":
                len(header),

            "time_min":
                (
                    min(numeric_times)
                    if numeric_times
                    else ""
                ),

            "time_max":
                (
                    max(numeric_times)
                    if numeric_times
                    else ""
                ),

            "header_json":
                json.dumps(
                    header,
                    ensure_ascii=False,
                ),

            "units_json":
                json.dumps(
                    unit_values,
                    ensure_ascii=False,
                ),

            "record_candidate_id":
                first_row.get(
                    "record_candidate_id",
                    "",
                ),

            "record_link_status":
                (
                    "linked"
                    if first_row.get(
                        "record_candidate_id",
                        "",
                    )
                    else "not_linked"
                ),

            "requires_review":
                (
                    time_axis_status
                    != "relative_time_available"
                ),
        })

        # ----------------------------------------------------
        # Measurement rows
        # ----------------------------------------------------

        for sample_index, row in enumerate(
            measurement_rows
        ):

            values = safe_json_list(
                row[
                    "source_row_json"
                ]
            )

            # Preserve extra source values explicitly.
            extra_values = []

            if len(values) > len(header):

                extra_values = (
                    values[
                        len(header):
                    ]
                )

            # Pad short rows for indexing.
            padded = (
                values
                + [""] * len(header)
            )[:len(header)]

            sample_id = make_sample_id(
                series_id,
                row[
                    "source_record"
                ],
            )

            buffer_address = (
                padded[0]
                if len(padded) > 0
                else ""
            )

            relative_time_raw = (
                padded[1]
                if len(padded) > 1
                else ""
            )

            relative_time_numeric = (
                parse_float(
                    relative_time_raw
                )
            )

            # =================================================
            # Wide sample row
            # =================================================

            wide_row = {

                **{
                    key:
                        row.get(
                            key,
                            "",
                        )
                    for key in BASE
                },

                "series_id":
                    series_id,

                "sample_id":
                    sample_id,

                "section_id":
                    section_id,

                "source_record":
                    row[
                        "source_record"
                    ],

                "sample_index":
                    sample_index,

                "buffer_address":
                    buffer_address,

                "relative_time_raw":
                    relative_time_raw,

                "relative_time_numeric":
                    (
                        relative_time_numeric
                        if relative_time_numeric
                        is not None
                        else ""
                    ),

                "time_axis_status":
                    time_axis_status,

                "extra_source_values_json":
                    json.dumps(
                        extra_values,
                        ensure_ascii=False,
                    ),

                "source_row_json":
                    row[
                        "source_row_json"
                    ],

                "requires_review":
                    (
                        relative_time_numeric
                        is None
                    ),
            }

            # Add original signal columns to wide row.
            for column_index, column_name in enumerate(
                header
            ):

                key_name = (
                    f"signal_{column_index + 1:02d}"
                )

                wide_row[
                    key_name
                ] = padded[
                    column_index
                ]

            samples_wide.append(
                wide_row
            )

            # =================================================
            # Long-form signal values
            # =================================================

            for column_index, column_name in enumerate(
                header
            ):

                value_raw = (
                    padded[
                        column_index
                    ]
                )

                unit = (
                    unit_values[
                        column_index
                    ]
                    if column_index
                    < len(unit_values)
                    else ""
                )

                # Buffer address and relative time remain
                # structural axes and are not duplicated as
                # signal observations.
                if column_index in {
                    0,
                    1,
                }:
                    continue

                value_numeric = (
                    parse_float(
                        value_raw
                    )
                )

                values_long.append({

                    **{
                        key:
                            row.get(
                                key,
                                "",
                            )
                        for key in BASE
                    },

                    "series_id":
                        series_id,

                    "sample_id":
                        sample_id,

                    "section_id":
                        section_id,

                    "source_record":
                        row[
                            "source_record"
                        ],

                    "sample_index":
                        sample_index,

                    "buffer_address":
                        buffer_address,

                    "relative_time_raw":
                        relative_time_raw,

                    "relative_time_numeric":
                        (
                            relative_time_numeric
                            if relative_time_numeric
                            is not None
                            else ""
                        ),

                    "signal_index":
                        column_index + 1,

                    "signal_name_raw":
                        column_name,

                    "value_raw":
                        value_raw,

                    "value_numeric":
                        (
                            value_numeric
                            if value_numeric
                            is not None
                            else ""
                        ),

                    "unit_raw":
                        unit,

                    "source_module":
                        "PCM",

                    "time_axis_status":
                        time_axis_status,

                    "requires_review":
                        False,
                })

    # ========================================================
    # Wide output columns
    # ========================================================

    if samples_wide:

        wide_columns = list(
            samples_wide[0]
        )

    else:

        wide_columns = BASE + [
            "series_id",
            "sample_id",
        ]

    # ========================================================
    # Write outputs
    # ========================================================

    write(
        out
        / "timeseries_registry.csv",

        registry,

        list(registry[0])
        if registry
        else BASE + ["series_id"],
    )

    write(
        out
        / "timeseries_samples_wide.csv",

        samples_wide,

        wide_columns,
    )

    write(
        out
        / "timeseries_values_long.csv",

        values_long,

        list(values_long[0])
        if values_long
        else BASE + ["series_id"],
    )

    write(
        out
        / "timeseries_audit.csv",

        audit_rows,

        list(audit_rows[0])
        if audit_rows
        else BASE
        + [
            "section_id",
            "series_id",
            "issue",
            "details",
        ],
    )

    # ========================================================
    # Statistics
    # ========================================================

    time_axis_counts = Counter(
        row[
            "time_axis_status"
        ]
        for row
        in registry
    )

    total_samples = sum(
        int(
            row[
                "sample_count"
            ]
        )
        for row
        in registry
    )

    # ========================================================
    # Metadata
    # ========================================================

    metadata = {

        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "input_file":
            str(
                args.input_file
            ),

        "source_pcm_rows":
            len(rows),

        "series_count":
            len(registry),

        "sample_count":
            total_samples,

        "long_value_rows":
            len(values_long),

        "time_axis_status_counts":
            dict(
                time_axis_counts
            ),

        "audit_issue_count":
            len(audit_rows),

        "scope":
            (
                "Initial Group 4 time-series working extraction "
                "from PCM EDR tables. Header and units evidence "
                "are preserved. Buffer address and relative time "
                "are treated as structural axes. Signals are "
                "available in both wide and long representations. "
                "No semantic filtering or record identity is "
                "inferred. Sections without numeric relative time "
                "are retained as ordered buffer sequences."
            ),
    }

    metadata_tmp = (
        out
        / "metadata.json.part"
    )

    metadata_tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
        ),
        encoding="utf-8",
    )

    metadata_tmp.replace(
        out
        / "metadata.json"
    )

    print(
        json.dumps(
            metadata,
            indent=2,
        )
    )

    print(
        f"Outputs: {out}"
    )


if __name__ == "__main__":
    main()