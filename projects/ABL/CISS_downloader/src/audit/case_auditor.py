"""
Create a comprehensive data audit for one CISS case.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import json
import zipfile

from openpyxl import load_workbook

from src.audit.audit_rules import (
    AUDIT_SCHEMA_VERSION,
    CORE_SHEETS,
    IMPORTANT_VARIABLES,
    PRIMARY_KEYS,
    SENTINEL_TEXT_PATTERNS,
)


class CaseAuditor:
    """
    Audit the files created during Phase 1.

    Input:
        data/raw/<case_id>/

    Output:
        data/processed/<case_id>/audit/case_audit.json
    """

    def __init__(self, data_root="data"):
        self.data_root = Path(data_root)

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    def _load_json(self, file_path, required=True):
        file_path = Path(file_path)

        if not file_path.exists():
            if required:
                raise FileNotFoundError(
                    f"Required file is missing: {file_path}"
                )

            return None

        try:
            with file_path.open(
                "r",
                encoding="utf-8",
            ) as input_file:
                return json.load(input_file)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Invalid JSON file: {file_path}"
            ) from error

    def _save_json(self, data, output_path):
        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = output_path.with_suffix(
            output_path.suffix + ".part"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                data,
                output_file,
                indent=2,
                ensure_ascii=False,
            )

        temporary_path.replace(output_path)

    # ------------------------------------------------------------------
    # Workbook loading
    # ------------------------------------------------------------------

    def _read_workbook(self, workbook_path):
        workbook_path = Path(workbook_path)

        if not workbook_path.exists():
            raise FileNotFoundError(
                f"Excel export is missing: {workbook_path}"
            )

        if not zipfile.is_zipfile(workbook_path):
            raise RuntimeError(
                f"Invalid XLSX workbook: {workbook_path}"
            )

        workbook = load_workbook(
            workbook_path,
            read_only=True,
            data_only=True,
        )

        sheets = {}

        for worksheet in workbook.worksheets:
            rows = list(
                worksheet.iter_rows(
                    values_only=True,
                )
            )

            if not rows:
                sheets[worksheet.title] = {
                    "headers": [],
                    "records": [],
                }
                continue

            headers = [
                str(value).strip()
                if value is not None
                else ""
                for value in rows[0]
            ]

            records = [
                dict(zip(headers, row))
                for row in rows[1:]
            ]

            sheets[worksheet.title] = {
                "headers": headers,
                "records": records,
            }

        workbook.close()

        return sheets

    def _records(self, sheets, sheet_name):
        return sheets.get(
            sheet_name,
            {},
        ).get(
            "records",
            [],
        )

    # ------------------------------------------------------------------
    # Missing and sentinel values
    # ------------------------------------------------------------------

    def _sentinel_category(self, value):
        if not isinstance(value, str):
            return None

        normalized = " ".join(
            value.lower().split()
        )

        for category, patterns in (
            SENTINEL_TEXT_PATTERNS.items()
        ):
            if any(
                pattern in normalized
                for pattern in patterns
            ):
                return category

        return None

    def _is_usable(self, record, field):
        value = record.get(field)

        if value is None or value == "":
            return False

        paired_text = record.get(
            f"{field}TEXT"
        )

        return (
            self._sentinel_category(
                paired_text
            )
            is None
        )

    # ------------------------------------------------------------------
    # Workbook summary
    # ------------------------------------------------------------------

    def _audit_workbook(self, sheets):
        summaries = {}

        for sheet_name, sheet in sheets.items():
            headers = sheet["headers"]
            records = sheet["records"]

            total_cells = (
                len(headers)
                * len(records)
            )

            blank_cells = sum(
                value is None or value == ""
                for record in records
                for value in record.values()
            )

            sentinel_counts = Counter()

            for record in records:
                for field, value in record.items():
                    if not field.endswith("TEXT"):
                        continue

                    category = self._sentinel_category(
                        value
                    )

                    if category:
                        sentinel_counts[
                            category
                        ] += 1

            duplicate_headers = [
                header
                for header, count
                in Counter(headers).items()
                if header and count > 1
            ]

            completeness = None

            if total_cells:
                completeness = round(
                    100
                    * (
                        total_cells
                        - blank_cells
                    )
                    / total_cells,
                    2,
                )

            summaries[sheet_name] = {
                "record_count": len(records),
                "column_count": len(headers),
                "blank_cell_count": blank_cells,
                "cell_completeness_percent": (
                    completeness
                ),
                "sentinel_text_counts": dict(
                    sorted(
                        sentinel_counts.items()
                    )
                ),
                "duplicate_headers": sorted(
                    duplicate_headers
                ),
            }

        return {
            "sheet_count": len(sheets),
            "nonempty_sheet_count": sum(
                bool(sheet["records"])
                for sheet in sheets.values()
            ),
            "empty_sheet_count": sum(
                not sheet["records"]
                for sheet in sheets.values()
            ),
            "missing_core_sheets": sorted(
                CORE_SHEETS - set(sheets)
            ),
            "sheets": summaries,
        }

    # ------------------------------------------------------------------
    # Entity counts
    # ------------------------------------------------------------------

    def _entity_summary(self, sheets):
        def count(sheet_name):
            return len(
                self._records(
                    sheets,
                    sheet_name,
                )
            )

        return {
            "crashes": count("CRASH"),
            "vehicles": count("GV"),
            "occupants": count("OCC"),
            "crash_events": count("EVENT"),
            "damage_events": count("CDC"),
            "injuries": count("INJURY"),
            "occupant_contacts": count(
                "OCCONTACT"
            ),
            "airbags": count("AIRBAG"),
            "edr_summaries": count(
                "EDRSUMM"
            ),
            "edr_events": count(
                "EDREVENT"
            ),
            "edr_precrash_rows": count(
                "EDRPRECRASH"
            ),
            "edr_postcrash_rows": count(
                "EDRPOSTCRASH"
            ),
        }

    # ------------------------------------------------------------------
    # Relational integrity
    # ------------------------------------------------------------------

    def _audit_relationships(self, sheets):
        errors = []

        vehicles = {
            (
                record.get("CASEID"),
                record.get("VEHNO"),
            )
            for record in self._records(
                sheets,
                "GV",
            )
        }

        occupants = {
            (
                record.get("CASEID"),
                record.get("VEHNO"),
                record.get("OCCNO"),
            )
            for record in self._records(
                sheets,
                "OCC",
            )
        }

        vehicle_orphans = []
        occupant_orphans = []

        for sheet_name, sheet in sheets.items():
            headers = set(sheet["headers"])

            for row_number, record in enumerate(
                sheet["records"],
                start=2,
            ):
                if {
                    "CASEID",
                    "VEHNO",
                } <= headers:
                    key = (
                        record.get("CASEID"),
                        record.get("VEHNO"),
                    )

                    if key not in vehicles:
                        vehicle_orphans.append(
                            {
                                "sheet": sheet_name,
                                "row": row_number,
                                "key": key,
                            }
                        )

                if {
                    "CASEID",
                    "VEHNO",
                    "OCCNO",
                } <= headers:
                    key = (
                        record.get("CASEID"),
                        record.get("VEHNO"),
                        record.get("OCCNO"),
                    )

                    if key not in occupants:
                        occupant_orphans.append(
                            {
                                "sheet": sheet_name,
                                "row": row_number,
                                "key": key,
                            }
                        )

        duplicate_keys = []

        for sheet_name, key_fields in (
            PRIMARY_KEYS.items()
        ):
            keys = [
                tuple(
                    record.get(field)
                    for field in key_fields
                )
                for record in self._records(
                    sheets,
                    sheet_name,
                )
            ]

            duplicates = [
                key
                for key, count
                in Counter(keys).items()
                if count > 1
            ]

            if duplicates:
                duplicate_keys.append(
                    {
                        "sheet": sheet_name,
                        "key_fields": list(
                            key_fields
                        ),
                        "duplicates": duplicates,
                    }
                )

        if vehicle_orphans:
            errors.append(
                f"{len(vehicle_orphans)} "
                "orphan vehicle references found."
            )

        if occupant_orphans:
            errors.append(
                f"{len(occupant_orphans)} "
                "orphan occupant references found."
            )

        if duplicate_keys:
            errors.append(
                "Duplicate primary keys found."
            )

        return {
            "passed": not errors,
            "errors": errors,
            "checks": {
                "vehicle_orphans": (
                    vehicle_orphans
                ),
                "occupant_orphans": (
                    occupant_orphans
                ),
                "duplicate_keys": (
                    duplicate_keys
                ),
            },
        }

    # ------------------------------------------------------------------
    # Injury outcomes
    # ------------------------------------------------------------------

    def _audit_injury_outcomes(self, sheets):
        injury_rows = self._records(
            sheets,
            "INJURY",
        )

        injuries_by_occupant = Counter(
            (
                record.get("CASEID"),
                record.get("VEHNO"),
                record.get("OCCNO"),
            )
            for record in injury_rows
        )

        occupants = []
        state_counts = Counter()

        for record in self._records(
            sheets,
            "OCC",
        ):
            key = (
                record.get("CASEID"),
                record.get("VEHNO"),
                record.get("OCCNO"),
            )

            detailed_count = (
                injuries_by_occupant[key]
            )

            injnum = (
                record.get("INJNUM")
                if self._is_usable(
                    record,
                    "INJNUM",
                )
                else None
            )

            mais = (
                record.get("MAIS")
                if self._is_usable(
                    record,
                    "MAIS",
                )
                else None
            )

            iss = (
                record.get("ISS")
                if self._is_usable(
                    record,
                    "ISS",
                )
                else None
            )

            injstatus = (
                record.get("INJSTATUS")
                if self._is_usable(
                    record,
                    "INJSTATUS",
                )
                else None
            )

            positive = (
                detailed_count > 0
                or (
                    isinstance(
                        injnum,
                        (int, float),
                    )
                    and injnum > 0
                )
                or (
                    isinstance(
                        mais,
                        (int, float),
                    )
                    and mais > 0
                )
            )

            explicit_negative = (
                detailed_count == 0
                and injnum == 0
                and mais == 0
                and iss == 0
                and injstatus == 0
            )

            if positive:
                state = "positive"

            elif explicit_negative:
                state = "negative"

            else:
                state = "unknown"

            state_counts[state] += 1

            occupants.append(
                {
                    "case_id": key[0],
                    "vehicle_number": key[1],
                    "occupant_number": key[2],
                    "label_state": state,
                    "label_available": (
                        state
                        in {
                            "positive",
                            "negative",
                        }
                    ),
                    "injury_present": (
                        True
                        if state == "positive"
                        else False
                        if state == "negative"
                        else None
                    ),
                    "injury_count_reported": (
                        injnum
                    ),
                    "detailed_injury_rows": (
                        detailed_count
                    ),
                    "mais": mais,
                    "iss": iss,
                    "evidence": {
                        "INJSTATUS": record.get(
                            "INJSTATUS"
                        ),
                        "INJSTATUSTEXT": record.get(
                            "INJSTATUSTEXT"
                        ),
                        "INJNUM": record.get(
                            "INJNUM"
                        ),
                        "MAIS": record.get(
                            "MAIS"
                        ),
                        "MAISTEXT": record.get(
                            "MAISTEXT"
                        ),
                        "ISS": record.get(
                            "ISS"
                        ),
                    },
                }
            )

        labeled_count = (
            state_counts["positive"]
            + state_counts["negative"]
        )

        return {
            "status": (
                "available"
                if labeled_count
                else "unavailable"
            ),
            "occupant_count": len(
                occupants
            ),
            "labeled_occupant_count": (
                labeled_count
            ),
            "state_counts": dict(
                sorted(
                    state_counts.items()
                )
            ),
            "detailed_injury_rows": len(
                injury_rows
            ),
            "occupants": occupants,
        }





    # ------------------------------------------------------------------
    # EDR signal interpretation
    # ------------------------------------------------------------------

    def _classify_edr_signal(self, pcode, description):
        """
        Convert a CISS EDR signal description into a stable category.
        Unknown signals are retained instead of being discarded.
        """
        normalized = " ".join(
            str(description or "").lower().split()
        )

        if (
            pcode == 2010
            or (
                "delta-v" in normalized
                and "longitudinal" in normalized
            )
        ):
            return "longitudinal_delta_v"

        if (
            "delta-v" in normalized
            and "lateral" in normalized
        ):
            return "lateral_delta_v"

        if (
            "acceleration" in normalized
            and "accelerator pedal" not in normalized
        ):
            if any(
                term in normalized
                for term in (
                    "longitudinal",
                    "x-axis",
                    "x axis",
                )
            ):
                return "longitudinal_acceleration"

            if any(
                term in normalized
                for term in (
                    "lateral",
                    "y-axis",
                    "y axis",
                )
            ):
                return "lateral_acceleration"

            return "acceleration"

        if (
            pcode == 1010
            or "vehicle speed" in normalized
        ):
            return "vehicle_speed"

        if (
            pcode == 1020
            or "engine throttle" in normalized
        ):
            return "engine_throttle"

        if (
            pcode == 1030
            or "accelerator pedal" in normalized
        ):
            return "accelerator_pedal"

        if (
            pcode == 1040
            or "service brake" in normalized
        ):
            return "service_brake"

        if (
            pcode == 1050
            or "engine rpm" in normalized
        ):
            return "engine_rpm"

        if (
            pcode == 1080
            or "steering input" in normalized
        ):
            return "steering_input"

        return "unclassified"

    def _infer_edr_unit(
        self,
        description,
        signal_type,
    ):
        """
        Return a unit only when it is explicitly stated.

        Delta-V units must not be assumed when they are absent from
        PCODETEXT.
        """
        normalized = str(
            description or ""
        ).lower()

        if "kmph" in normalized:
            return "km/h"

        if "km/h" in normalized:
            return "km/h"

        if "mph" in normalized:
            return "mph"

        if "rpm" in normalized:
            return "rpm"

        if "% full" in normalized:
            return "percent"

        if "(deg)" in normalized:
            return "degree"

        if signal_type in {
            "longitudinal_delta_v",
            "lateral_delta_v",
        }:
            return None

        return None

    def _is_unrelated_edr_event(
        self,
        event_record,
    ):
        relation_code = event_record.get(
            "CDCEVENT"
        )

        relation_text = str(
            event_record.get(
                "CDCEVENTTEXT"
            )
            or ""
        ).lower()

        return (
            relation_code == 97
            or "not related to this crash"
            in relation_text
        )

    def _select_applicable_edr_event(
        self,
        event_records,
    ):
        """
        Select an EDR event only when CISS explicitly associates one
        event with the investigated crash.
        """
        candidates = []

        for record in event_records:
            if self._is_unrelated_edr_event(
                record
            ):
                continue

            cdc_event = record.get(
                "CDCEVENT"
            )

            explicitly_linked = (
                isinstance(
                    cdc_event,
                    (int, float),
                )
                and cdc_event > 0
                and cdc_event != 97
            )

            if not explicitly_linked:
                continue

            candidates.append(
                {
                    "case_id": record.get(
                        "CASEID"
                    ),
                    "vehicle_number": record.get(
                        "VEHNO"
                    ),
                    "edr_event_number": record.get(
                        "EDREVENTNO"
                    ),
                    "event_description": record.get(
                        "EVENTDESC"
                    ),
                    "cdc_event": cdc_event,
                    "cdc_event_text": record.get(
                        "CDCEVENTTEXT"
                    ),
                    "selection_evidence": (
                        "EDREVENT.CDCEVENT"
                    ),
                }
            )

        if len(candidates) == 1:
            return {
                "identified": True,
                "selection_status": "selected",
                "selection_method": (
                    "EDREVENT.CDCEVENT"
                ),
                "confidence": "explicit",
                "event": candidates[0],
                "candidates": candidates,
            }

        if not candidates:
            return {
                "identified": False,
                "selection_status": (
                    "no_explicit_match"
                ),
                "selection_method": (
                    "EDREVENT.CDCEVENT"
                ),
                "confidence": None,
                "event": None,
                "candidates": [],
            }

        return {
            "identified": False,
            "selection_status": (
                "multiple_explicit_matches"
            ),
            "selection_method": (
                "EDREVENT.CDCEVENT"
            ),
            "confidence": None,
            "event": None,
            "candidates": candidates,
        }

    def _audit_edr_signal_group(
        self,
        rows,
        applicable_event_number,
    ):
        """
        Audit one long-format EDR signal.

        Grouping key:
            CASEID + VEHNO + EDREVENTNO + PCODE
        """
        first = rows[0]

        pcode = first.get("PCODE")
        description = first.get(
            "PCODETEXT"
        )

        signal_type = (
            self._classify_edr_signal(
                pcode,
                description,
            )
        )

        unit = self._infer_edr_unit(
            description,
            signal_type,
        )

        numeric_rows = [
            row
            for row in rows
            if isinstance(
                row.get("PTIME"),
                (int, float),
            )
            and isinstance(
                row.get("PVALUE"),
                (int, float),
            )
        ]

        numeric_rows.sort(
            key=lambda row: row["PTIME"]
        )

        times = [
            row["PTIME"]
            for row in numeric_rows
        ]

        values = [
            row["PVALUE"]
            for row in numeric_rows
        ]

        duplicate_time_count = (
            len(times)
            - len(set(times))
        )

        time_intervals = [
            right - left
            for left, right in zip(
                times,
                times[1:],
            )
        ]

        time_axis_increasing = (
            len(times) >= 2
            and all(
                right > left
                for left, right in zip(
                    times,
                    times[1:],
                )
            )
        )

        median_interval = (
            median(time_intervals)
            if time_intervals
            else None
        )

        irregular_sampling = None

        if (
            time_intervals
            and median_interval is not None
        ):
            tolerance = max(
                abs(median_interval) * 0.01,
                1e-9,
            )

            irregular_sampling = any(
                abs(
                    interval
                    - median_interval
                )
                > tolerance
                for interval in time_intervals
            )

        missing_time_count = sum(
            row.get("PTIME") in (
                None,
                "",
            )
            for row in rows
        )

        missing_value_count = sum(
            row.get("PVALUE") in (
                None,
                "",
            )
            for row in rows
        )

        sentinel_time_count = sum(
            self._sentinel_category(
                row.get("PTIMETEXT")
            )
            is not None
            for row in rows
        )

        sentinel_value_count = sum(
            self._sentinel_category(
                row.get("PVALUETEXT")
            )
            is not None
            for row in rows
        )

        event_number = first.get(
            "EDREVENTNO"
        )

        related_to_crash = (
            applicable_event_number
            is not None
            and event_number
            == applicable_event_number
        )

        delta_v_history = (
            signal_type
            in {
                "longitudinal_delta_v",
                "lateral_delta_v",
            }
            and len(numeric_rows) >= 2
            and time_axis_increasing
        )

        direct_acceleration_history = (
            signal_type
            in {
                "acceleration",
                "longitudinal_acceleration",
                "lateral_acceleration",
            }
            and len(numeric_rows) >= 2
            and time_axis_increasing
        )

        return {
            "case_id": first.get(
                "CASEID"
            ),
            "vehicle_number": first.get(
                "VEHNO"
            ),
            "edr_event_number": (
                event_number
            ),
            "related_to_investigated_crash": (
                related_to_crash
            ),
            "pcode": pcode,
            "description": description,
            "signal_type": signal_type,
            "unit": unit,
            "unit_explicitly_available": (
                unit is not None
            ),
            "sample_count": len(rows),
            "numeric_sample_count": len(
                numeric_rows
            ),
            "missing_time_count": (
                missing_time_count
            ),
            "missing_value_count": (
                missing_value_count
            ),
            "sentinel_time_count": (
                sentinel_time_count
            ),
            "sentinel_value_count": (
                sentinel_value_count
            ),
            "duplicate_time_count": (
                duplicate_time_count
            ),
            "time_axis_valid": (
                time_axis_increasing
                and duplicate_time_count == 0
            ),
            "time_min": (
                min(times)
                if times
                else None
            ),
            "time_max": (
                max(times)
                if times
                else None
            ),
            "median_time_interval": (
                median_interval
            ),
            "irregular_sampling": (
                irregular_sampling
            ),
            "value_min": (
                min(values)
                if values
                else None
            ),
            "value_max": (
                max(values)
                if values
                else None
            ),
            "initial_value": (
                values[0]
                if values
                else None
            ),
            "final_value": (
                values[-1]
                if values
                else None
            ),
            "delta_v_history": (
                delta_v_history
            ),
            "direct_acceleration_history": (
                direct_acceleration_history
            ),
            "raw_fields": {
                "signal_code": "PCODE",
                "signal_description": (
                    "PCODETEXT"
                ),
                "time": "PTIME",
                "value": "PVALUE",
            },
        }

    def _compare_edr_summary_to_history(
        self,
        event_records,
        signals,
        applicable_event_number,
    ):
        """
        Compare the EDREVENT maximum longitudinal Delta-V with the
        final value of the applicable longitudinal Delta-V history.
        """
        if applicable_event_number is None:
            return {
                "available": False,
                "reason": (
                    "Applicable event not identified."
                ),
            }

        event_record = next(
            (
                record
                for record in event_records
                if record.get(
                    "EDREVENTNO"
                )
                == applicable_event_number
            ),
            None,
        )

        if event_record is None:
            return {
                "available": False,
                "reason": (
                    "Applicable event record "
                    "not found."
                ),
            }

        longitudinal_signal = next(
            (
                signal
                for signal in signals
                if (
                    signal[
                        "edr_event_number"
                    ]
                    == applicable_event_number
                    and signal[
                        "signal_type"
                    ]
                    == (
                        "longitudinal_delta_v"
                    )
                )
            ),
            None,
        )

        reported_value = (
            event_record.get(
                "MAXDVLONG"
            )
            if self._is_usable(
                event_record,
                "MAXDVLONG",
            )
            else None
        )

        reported_time = (
            event_record.get(
                "MAXDVLONGTIME"
            )
            if self._is_usable(
                event_record,
                "MAXDVLONGTIME",
            )
            else None
        )

        if (
            longitudinal_signal is None
            or reported_value is None
        ):
            return {
                "available": False,
                "reported_value": (
                    reported_value
                ),
                "history_available": (
                    longitudinal_signal
                    is not None
                ),
                "reason": (
                    "Summary or longitudinal "
                    "history is unavailable."
                ),
            }

        final_value = longitudinal_signal[
            "final_value"
        ]

        difference = (
            abs(
                reported_value
                - final_value
            )
            if final_value is not None
            else None
        )

        reporting_tolerance = 0.5

        agreement_status = (
            "close"
            if (
                difference is not None
                and difference
                <= reporting_tolerance
            )
            else "requires_review"
        )

        return {
            "available": True,
            "reported_max_longitudinal_delta_v": (
                reported_value
            ),
            "reported_max_time": (
                reported_time
            ),
            "history_final_longitudinal_delta_v": (
                final_value
            ),
            "history_final_time": (
                longitudinal_signal[
                    "time_max"
                ]
            ),
            "absolute_difference": (
                difference
            ),
            "reporting_tolerance": (
                reporting_tolerance
            ),
            "agreement_status": (
                agreement_status
            ),
        }

    def _audit_edr(self, sheets):
        """
        Audit the actual long-format CISS EDR tables.
        """
        collection_rows = self._records(
            sheets,
            "EDRCOLLECT",
        )

        summary_rows = self._records(
            sheets,
            "EDRSUMM",
        )

        event_rows = self._records(
            sheets,
            "EDREVENT",
        )

        precrash_rows = self._records(
            sheets,
            "EDRPRECRASH",
        )

        postcrash_rows = self._records(
            sheets,
            "EDRPOSTCRASH",
        )

        event_selection = (
            self._select_applicable_edr_event(
                event_rows
            )
        )

        applicable_event_number = None

        if event_selection["identified"]:
            applicable_event_number = (
                event_selection[
                    "event"
                ]["edr_event_number"]
            )

        grouped_rows = defaultdict(list)

        for table_name, records in (
            (
                "EDRPRECRASH",
                precrash_rows,
            ),
            (
                "EDRPOSTCRASH",
                postcrash_rows,
            ),
        ):
            for record in records:
                key = (
                    table_name,
                    record.get("CASEID"),
                    record.get("VEHNO"),
                    record.get(
                        "EDREVENTNO"
                    ),
                    record.get("PCODE"),
                    record.get(
                        "PCODETEXT"
                    ),
                )

                grouped_rows[key].append(
                    record
                )

        signals = []

        for key, rows in sorted(
            grouped_rows.items(),
            key=lambda item: str(
                item[0]
            ),
        ):
            signal = (
                self._audit_edr_signal_group(
                    rows,
                    applicable_event_number,
                )
            )

            signal["source_table"] = key[0]

            signals.append(signal)

        applicable_signals = [
            signal
            for signal in signals
            if signal[
                "related_to_investigated_crash"
            ]
        ]

        longitudinal_delta_v = [
            signal
            for signal in applicable_signals
            if (
                signal["signal_type"]
                == "longitudinal_delta_v"
                and signal[
                    "delta_v_history"
                ]
            )
        ]

        lateral_delta_v = [
            signal
            for signal in applicable_signals
            if (
                signal["signal_type"]
                == "lateral_delta_v"
                and signal[
                    "delta_v_history"
                ]
            )
        ]

        acceleration_signals = [
            signal
            for signal in applicable_signals
            if signal[
                "direct_acceleration_history"
            ]
        ]

        delta_v_history_available = bool(
            longitudinal_delta_v
            or lateral_delta_v
        )

        direct_acceleration_available = bool(
            acceleration_signals
        )

        acceleration_derivable = (
            delta_v_history_available
            and not direct_acceleration_available
        )

        delta_v_units_available = all(
            signal[
                "unit_explicitly_available"
            ]
            for signal in (
                longitudinal_delta_v
                + lateral_delta_v
            )
        )

        unit_validation_required = (
            delta_v_history_available
            and not delta_v_units_available
        )

        agreement = (
            self._compare_edr_summary_to_history(
                event_rows,
                signals,
                applicable_event_number,
            )
        )

        declared_event_count = sum(
            record.get("NUMEVENTS") or 0
            for record in summary_rows
            if isinstance(
                record.get("NUMEVENTS"),
                (int, float),
            )
        )

        direct_acceleration_ready = any(
            signal[
                "direct_acceleration_history"
            ]
            and signal[
                "time_axis_valid"
            ]
            and signal[
                "unit_explicitly_available"
            ]
            for signal in acceleration_signals
        )

        return {
            "edr_obtained": bool(
                collection_rows
                or summary_rows
            ),
            "declared_event_count": (
                declared_event_count
            ),
            "event_record_count": len(
                event_rows
            ),
            "event_selection": (
                event_selection
            ),
            "applicable_event_identified": (
                event_selection[
                    "identified"
                ]
            ),
            "applicable_event_number": (
                applicable_event_number
            ),
            "precrash_row_count": len(
                precrash_rows
            ),
            "postcrash_row_count": len(
                postcrash_rows
            ),
            "signal_count": len(signals),
            "signals": signals,
            "applicable_event_signals": (
                applicable_signals
            ),
            "delta_v_history_available": (
                delta_v_history_available
            ),
            "longitudinal_delta_v_history_available": (
                bool(longitudinal_delta_v)
            ),
            "lateral_delta_v_history_available": (
                bool(lateral_delta_v)
            ),
            "direct_acceleration_history_available": (
                direct_acceleration_available
            ),
            "acceleration_derivable": (
                acceleration_derivable
            ),
            "unit_validation_required": (
                unit_validation_required
            ),
            "summary_history_agreement": (
                agreement
            ),
            "direct_acceleration_ready_for_simulation": (
                direct_acceleration_ready
            ),
            "pulse_candidate_available": (
                delta_v_history_available
                or direct_acceleration_available
            ),
            "pulse_ready_for_simulation": (
                direct_acceleration_ready
            ),
        }

    # ------------------------------------------------------------------
    # Crash-mechanics sources
    # ------------------------------------------------------------------

    def _audit_crash_mechanics(
        self,
        sheets,
        edr_audit,
    ):
        """
        Reconcile reconstructed and EDR Delta-V evidence.

        An EDR longitudinal or lateral component is never incorrectly
        relabeled as total Delta-V.
        """
        reconstructed = []

        for sheet_name in (
            "GV",
            "CDC",
        ):
            for record in self._records(
                sheets,
                sheet_name,
            ):
                if not self._is_usable(
                    record,
                    "DVTOTAL",
                ):
                    continue

                reconstructed.append(
                    {
                        "source": sheet_name,
                        "case_id": record.get(
                            "CASEID"
                        ),
                        "vehicle_number": (
                            record.get("VEHNO")
                        ),
                        "event_number": (
                            record.get("EVENTNO")
                            or record.get(
                                "DVEVENT"
                            )
                        ),
                        "total_delta_v": (
                            record.get("DVTOTAL")
                        ),
                        "longitudinal_delta_v": (
                            record.get("DVLONG")
                            if self._is_usable(
                                record,
                                "DVLONG",
                            )
                            else None
                        ),
                        "lateral_delta_v": (
                            record.get("DVLAT")
                            if self._is_usable(
                                record,
                                "DVLAT",
                            )
                            else None
                        ),
                    }
                )

        applicable_event_number = (
            edr_audit.get(
                "applicable_event_number"
            )
        )

        edr_values = []

        for record in self._records(
            sheets,
            "EDREVENT",
        ):
            longitudinal = (
                record.get("MAXDVLONG")
                if self._is_usable(
                    record,
                    "MAXDVLONG",
                )
                else None
            )

            lateral = (
                record.get("MAXDVLAT")
                if self._is_usable(
                    record,
                    "MAXDVLAT",
                )
                else None
            )

            if (
                longitudinal is None
                and lateral is None
            ):
                continue

            event_number = record.get(
                "EDREVENTNO"
            )

            edr_values.append(
                {
                    "source": "EDREVENT",
                    "case_id": record.get(
                        "CASEID"
                    ),
                    "vehicle_number": (
                        record.get("VEHNO")
                    ),
                    "edr_event_number": (
                        event_number
                    ),
                    "event_description": (
                        record.get("EVENTDESC")
                    ),
                    "longitudinal_delta_v": (
                        longitudinal
                    ),
                    "lateral_delta_v": (
                        lateral
                    ),
                    "related_to_investigated_crash": (
                        applicable_event_number
                        is not None
                        and event_number
                        == applicable_event_number
                    ),
                }
            )

        reconstructed_values = {
            observation[
                "total_delta_v"
            ]
            for observation in reconstructed
        }

        applicable_edr_values = [
            observation
            for observation in edr_values
            if observation[
                "related_to_investigated_crash"
            ]
        ]

        preferred_total = None
        preferred_source = None
        selected_observation = None
        selection_status = "unavailable"

        if (
            reconstructed
            and len(
                reconstructed_values
            )
            == 1
        ):
            preferred_total = next(
                iter(
                    reconstructed_values
                )
            )

            preferred_source = (
                "reconstruction"
            )

            selected_observation = (
                reconstructed[0]
            )

            selection_status = "selected"

        elif reconstructed:
            selection_status = (
                "conflicting_reconstruction_values"
            )

        elif (
            len(applicable_edr_values)
            == 1
        ):
            selected_observation = (
                applicable_edr_values[0]
            )

            preferred_source = (
                "edr_applicable_event"
            )

            selection_status = (
                "selected_component_values"
            )

        elif edr_values:
            selection_status = (
                "requires_edr_event_matching"
            )

        return {
            "reconstruction": {
                "available": bool(
                    reconstructed
                ),
                "observations": (
                    reconstructed
                ),
            },
            "edr": {
                "available": bool(
                    edr_values
                ),
                "observations": (
                    edr_values
                ),
                "applicable_event_observations": (
                    applicable_edr_values
                ),
                "applicable_event_identified": (
                    edr_audit[
                        "applicable_event_identified"
                    ]
                ),
            },
            "preferred_total_delta_v": (
                preferred_total
            ),
            "preferred_longitudinal_delta_v": (
                selected_observation.get(
                    "longitudinal_delta_v"
                )
                if selected_observation
                else None
            ),
            "preferred_lateral_delta_v": (
                selected_observation.get(
                    "lateral_delta_v"
                )
                if selected_observation
                else None
            ),
            "preferred_source": (
                preferred_source
            ),
            "selected_observation": (
                selected_observation
            ),
            "selection_status": (
                selection_status
            ),
        }







    # ------------------------------------------------------------------
    # Cross-source contradictions
    # ------------------------------------------------------------------

    def _belt_state(self, value, text_value):
        text = str(
            text_value or ""
        ).lower()

        if (
            "unknown" in text
            or "not reported" in text
        ):
            return "unknown"

        if (
            "not used" in text
            or "unbelted" in text
        ):
            return "unbelted"

        if (
            "belt" in text
            and "no belt" not in text
        ):
            return "belted"

        return "unknown"

    def _direction(self, value, text_value):
        text = (
            f"{value or ''} "
            f"{text_value or ''}"
        ).lower()

        mappings = {
            "front": (
                "front",
                " f ",
            ),
            "rear": (
                "rear",
                "back",
                " b ",
            ),
            "left": (
                "left",
                " l ",
            ),
            "right": (
                "right",
                " r ",
            ),
        }

        padded = f" {text} "

        for direction, terms in (
            mappings.items()
        ):
            if any(
                term in padded
                for term in terms
            ):
                return direction

        return "unknown"

    def _audit_contradictions(
        self,
        sheets,
        injury_audit,
        mechanics_audit,
    ):
        contradictions = []

        # Belt-use consistency
        belt_by_vehicle = defaultdict(list)

        for record in self._records(
            sheets,
            "OCC",
        ):
            key = (
                record.get("CASEID"),
                record.get("VEHNO"),
            )

            belt_by_vehicle[key].append(
                {
                    "source": "OCC.BELTUSE",
                    "value": self._belt_state(
                        record.get("BELTUSE"),
                        record.get(
                            "BELTUSETEXT"
                        ),
                    ),
                    "occupant_number": (
                        record.get("OCCNO")
                    ),
                }
            )

        for record in self._records(
            sheets,
            "SEAT",
        ):
            key = (
                record.get("CASEID"),
                record.get("VEHNO"),
            )

            belt_by_vehicle[key].append(
                {
                    "source": (
                        "SEAT.BELTUSEINSP"
                    ),
                    "value": self._belt_state(
                        record.get(
                            "BELTUSEINSP"
                        ),
                        record.get(
                            "BELTUSEINSPTEXT"
                        ),
                    ),
                    "seat_location": (
                        record.get("SEATLOC")
                    ),
                }
            )

        for key, observations in (
            belt_by_vehicle.items()
        ):
            usable_states = {
                observation["value"]
                for observation
                in observations
                if observation["value"]
                != "unknown"
            }

            if len(usable_states) > 1:
                contradictions.append(
                    {
                        "variable": "belt_use",
                        "entity": {
                            "case_id": key[0],
                            "vehicle_number": (
                                key[1]
                            ),
                        },
                        "status": "conflicting",
                        "observations": (
                            observations
                        ),
                        "resolution": (
                            "unresolved"
                        ),
                    }
                )

        # Reconstruction Delta-V consistency
        if (
            mechanics_audit[
                "selection_status"
            ]
            == (
                "conflicting_"
                "reconstruction_values"
            )
        ):
            contradictions.append(
                {
                    "variable": "delta_v",
                    "status": "conflicting",
                    "observations": (
                        mechanics_audit[
                            "reconstruction"
                        ]["observations"]
                    ),
                    "resolution": (
                        "unresolved"
                    ),
                }
            )

        # Damage-direction consistency
        gv_directions = {}

        for record in self._records(
            sheets,
            "GV",
        ):
            key = (
                record.get("CASEID"),
                record.get("VEHNO"),
            )

            gv_directions[key] = (
                self._direction(
                    record.get("DAMPLANE"),
                    record.get(
                        "DAMPLANETEXT"
                    ),
                )
            )

        for record in self._records(
            sheets,
            "CDC",
        ):
            key = (
                record.get("CASEID"),
                record.get("VEHNO"),
            )

            cdc_direction = (
                self._direction(
                    record.get("CDCPLANE"),
                    record.get(
                        "CDCPLANETEXT"
                    ),
                )
            )

            gv_direction = (
                gv_directions.get(
                    key,
                    "unknown",
                )
            )

            if (
                gv_direction != "unknown"
                and cdc_direction
                != "unknown"
                and gv_direction
                != cdc_direction
            ):
                contradictions.append(
                    {
                        "variable": (
                            "damage_direction"
                        ),
                        "entity": {
                            "case_id": key[0],
                            "vehicle_number": (
                                key[1]
                            ),
                        },
                        "status": "conflicting",
                        "observations": [
                            {
                                "source": (
                                    "GV.DAMPLANE"
                                ),
                                "value": (
                                    gv_direction
                                ),
                            },
                            {
                                "source": (
                                    "CDC.CDCPLANE"
                                ),
                                "value": (
                                    cdc_direction
                                ),
                            },
                        ],
                        "resolution": (
                            "unresolved"
                        ),
                    }
                )

        # Injury-label consistency
        inconsistent_injuries = []

        for occupant in injury_audit[
            "occupants"
        ]:
            if (
                occupant["label_state"]
                == "positive"
                and occupant["mais"] == 0
            ):
                inconsistent_injuries.append(
                    occupant
                )

        if inconsistent_injuries:
            contradictions.append(
                {
                    "variable": (
                        "injury_outcome"
                    ),
                    "status": "conflicting",
                    "observations": (
                        inconsistent_injuries
                    ),
                    "resolution": (
                        "unresolved"
                    ),
                }
            )

        return {
            "passed": not contradictions,
            "contradiction_count": len(
                contradictions
            ),
            "contradictions": (
                contradictions
            ),
        }

    # ------------------------------------------------------------------
    # Important-variable profiles
    # ------------------------------------------------------------------

    def _profile_variable(
        self,
        sheet,
        field,
    ):
        if field not in sheet["headers"]:
            return {
                "present": False,
            }

        blank_count = 0
        usable_values = []
        sentinel_counts = Counter()

        for record in sheet["records"]:
            value = record.get(field)

            if value is None or value == "":
                blank_count += 1
                continue

            category = (
                self._sentinel_category(
                    record.get(
                        f"{field}TEXT"
                    )
                )
            )

            if category:
                sentinel_counts[
                    category
                ] += 1
            else:
                usable_values.append(value)

        samples = []

        for value in usable_values:
            if value not in samples:
                samples.append(value)

            if len(samples) == 5:
                break

        return {
            "present": True,
            "record_count": len(
                sheet["records"]
            ),
            "usable_count": len(
                usable_values
            ),
            "blank_count": blank_count,
            "sentinel_counts": dict(
                sorted(
                    sentinel_counts.items()
                )
            ),
            "sample_values": samples,
        }

    def _important_variable_profile(
        self,
        sheets,
    ):
        result = {}

        for domain, sheet_rules in (
            IMPORTANT_VARIABLES.items()
        ):
            result[domain] = {}

            for sheet_name, fields in (
                sheet_rules.items()
            ):
                sheet = sheets.get(
                    sheet_name,
                    {
                        "headers": [],
                        "records": [],
                    },
                )

                result[domain][sheet_name] = {
                    field: (
                        self._profile_variable(
                            sheet,
                            field,
                        )
                    )
                    for field in fields
                }

        return result

    # ------------------------------------------------------------------
    # Asset inventory
    # ------------------------------------------------------------------

    def _asset_summary(self, registry):
        assets = registry.get(
            "assets",
            [],
        )

        type_counts = Counter(
            asset.get(
                "asset_type",
                "unknown",
            )
            for asset in assets
        )

        extension_counts = Counter(
            asset.get(
                "extension",
                "",
            )
            for asset in assets
        )

        return {
            "total_assets": len(assets),
            "total_bytes": sum(
                asset.get(
                    "size_bytes",
                    0,
                )
                or 0
                for asset in assets
            ),
            "assets_by_type": dict(
                sorted(
                    type_counts.items()
                )
            ),
            "assets_by_extension": dict(
                sorted(
                    extension_counts.items()
                )
            ),
            "missing_object_ids": sum(
                not asset.get("object_id")
                for asset in assets
            ),
            "missing_checksums": sum(
                not asset.get("sha256")
                for asset in assets
            ),
        }

    # ------------------------------------------------------------------
    # Domain availability
    # ------------------------------------------------------------------

    def _domain_availability(
        self,
        sheets,
        registry,
        injury_audit,
        edr_audit,
        mechanics_audit,
    ):
        def row_count(sheet_name):
            return len(
                self._records(
                    sheets,
                    sheet_name,
                )
            )

        asset_types = Counter(
            asset.get("asset_type")
            for asset in registry.get(
                "assets",
                [],
            )
        )

        pdof_available = any(
            self._is_usable(
                record,
                "PDOF",
            )
            for record in self._records(
                sheets,
                "CDC",
            )
        )

        delta_v_candidate = (
            mechanics_audit[
                "reconstruction"
            ]["available"]
            or mechanics_audit[
                "edr"
            ]["available"]
        )

        delta_v_component_selected = (
            mechanics_audit[
                "preferred_longitudinal_delta_v"
            ]
            is not None
            or mechanics_audit[
                "preferred_lateral_delta_v"
            ]
            is not None
        )

        return {
            "crash": {
                "status": (
                    "available"
                    if row_count("CRASH")
                    else "unavailable"
                ),
            },
            "vehicle": {
                "status": (
                    "available"
                    if row_count("GV")
                    else "unavailable"
                ),
            },
            "occupant": {
                "status": (
                    "available"
                    if row_count("OCC")
                    else "unavailable"
                ),
            },
            "crash_mechanics": {
                "status": (
                    "available"
                    if row_count("CDC")
                    else "partial"
                    if row_count("GV")
                    else "unavailable"
                ),
                "delta_v_candidate_available": (
                    delta_v_candidate
                ),
                "total_delta_v_selected": (
                    mechanics_audit[
                        "preferred_total_delta_v"
                    ]
                    is not None
                ),
                "delta_v_component_selected": (
                    delta_v_component_selected
                ),
                "delta_v_selection_status": (
                    mechanics_audit[
                        "selection_status"
                    ]
                ),
                "pdof_available": (
                    pdof_available
                ),
            },
            "restraint_and_airbag": {
                "status": (
                    "available"
                    if (
                        row_count("OCC")
                        and row_count("AIRBAG")
                    )
                    else "partial"
                    if row_count("OCC")
                    else "unavailable"
                ),
            },
            "injury_outcomes": {
                "status": (
                    injury_audit["status"]
                ),
                "labeled_occupant_count": (
                    injury_audit[
                        "labeled_occupant_count"
                    ]
                ),
                "state_counts": (
                    injury_audit[
                        "state_counts"
                    ]
                ),
            },
            "edr": {
                "status": (
                    "available"
                    if edr_audit[
                        "pulse_ready_for_simulation"
                    ]
                    else "partial"
                    if edr_audit[
                        "edr_obtained"
                    ]
                    else "unavailable"
                ),
                "summary_available": (
                    edr_audit[
                        "edr_obtained"
                    ]
                ),
                "applicable_event_identified": (
                    edr_audit[
                        "applicable_event_identified"
                    ]
                ),
                "delta_v_history_available": (
                    edr_audit[
                        "delta_v_history_available"
                    ]
                ),
                "direct_acceleration_available": (
                    edr_audit[
                        "direct_acceleration_"
                        "history_available"
                    ]
                ),
                "acceleration_derivable": (
                    edr_audit[
                        "acceleration_derivable"
                    ]
                ),
                "unit_validation_required": (
                    edr_audit[
                        "unit_validation_required"
                    ]
                ),
                "pulse_candidate_available": (
                    edr_audit[
                        "pulse_candidate_available"
                    ]
                ),
                "pulse_ready_for_simulation": (
                    edr_audit[
                        "pulse_ready_for_simulation"
                    ]
                ),
            },
            "visual_assets": {
                "status": (
                    "available"
                    if asset_types["image"]
                    else "unavailable"
                ),
                "image_count": (
                    asset_types["image"]
                ),
                "sketch_count": (
                    asset_types["sketch"]
                ),
            },
            "documents": {
                "status": (
                    "available"
                    if asset_types["document"]
                    else "unavailable"
                ),
                "document_count": (
                    asset_types["document"]
                ),
            },
        }

    # ------------------------------------------------------------------
    # Task eligibility
    # ------------------------------------------------------------------

    def _task_eligibility(
        self,
        domains,
        injury_audit,
        edr_audit,
        mechanics_audit,
        contradiction_audit,
    ):
        mechanics = domains[
            "crash_mechanics"
        ]

        images = domains[
            "visual_assets"
        ]

        simulation_base = (
            domains["occupant"]["status"]
            == "available"
            and domains[
                "restraint_and_airbag"
            ]["status"]
            in {
                "available",
                "partial",
            }
            and mechanics[
                "pdof_available"
            ]
            and mechanics[
                "delta_v_candidate_available"
            ]
        )

        if (
            simulation_base
            and edr_audit[
                "pulse_ready_for_simulation"
            ]
        ):
            simulation_status = (
                "simulation_ready"
            )

        elif (
            simulation_base
            and edr_audit[
                "pulse_candidate_available"
            ]
        ):
            simulation_status = (
                "requires_pulse_preprocessing"
            )

        elif simulation_base:
            simulation_status = (
                "parameterizable"
            )

        elif (
            domains["occupant"]["status"]
            == "available"
        ):
            simulation_status = "limited"

        else:
            simulation_status = (
                "not_eligible"
            )

        if (
            mechanics_audit[
                "preferred_total_delta_v"
            ]
            is not None
            and mechanics[
                "pdof_available"
            ]
        ):
            reconstruction_status = (
                "eligible"
            )

        elif (
            mechanics_audit[
                "preferred_longitudinal_delta_v"
            ]
            is not None
            or mechanics_audit[
                "preferred_lateral_delta_v"
            ]
            is not None
        ):
            reconstruction_status = (
                "partial"
            )

        elif (
            mechanics_audit[
                "reconstruction"
            ]["available"]
            or mechanics_audit[
                "edr"
            ]["available"]
        ):
            reconstruction_status = (
                "partial"
            )

        else:
            reconstruction_status = (
                "not_eligible"
            )

        return {
            "image_analysis": {
                "status": (
                    "eligible"
                    if images["image_count"]
                    else "not_eligible"
                ),
                "reason": (
                    f"{images['image_count']} "
                    "image assets registered."
                ),
            },
            "crash_reconstruction": {
                "status": (
                    reconstruction_status
                ),
                "reason": (
                    mechanics_audit[
                        "selection_status"
                    ]
                ),
            },
            "edr_pulse_modeling": {
                "status": (
                    "eligible"
                    if edr_audit[
                        "pulse_ready_for_simulation"
                    ]
                    else "requires_validation"
                    if edr_audit[
                        "pulse_candidate_available"
                    ]
                    else "not_eligible"
                ),
                "reason": (
                    "A Delta-V history is not the "
                    "same as direct acceleration. "
                    "Units and time axes must be "
                    "validated before differentiation."
                ),
            },
            "occupant_simulation": {
                "status": (
                    simulation_status
                ),
                "reason": (
                    "Readiness depends on occupant, "
                    "restraint, PDOF, Delta-V, and "
                    "crash-pulse availability."
                ),
            },
            "supervised_injury_prediction": {
                "status": (
                    "eligible"
                    if injury_audit[
                        "labeled_occupant_count"
                    ]
                    else "not_eligible"
                ),
                "reason": (
                    "Positive injuries and explicit "
                    "no-injury outcomes are valid "
                    "supervised labels; unknown "
                    "outcomes are not labels."
                ),
                "label_state_counts": (
                    injury_audit[
                        "state_counts"
                    ]
                ),
            },
            "multimodal_learning": {
                "status": (
                    "eligible"
                    if (
                        images["image_count"]
                        and domains["crash"][
                            "status"
                        ]
                        == "available"
                    )
                    else "not_eligible"
                ),
                "reason": (
                    "Requires structured crash data "
                    "and registered visual assets."
                ),
            },
            "unresolved_contradictions": {
                "status": (
                    "review_required"
                    if contradiction_audit[
                        "contradiction_count"
                    ]
                    else "clear"
                ),
                "count": (
                    contradiction_audit[
                        "contradiction_count"
                    ]
                ),
            },
        }

    # ------------------------------------------------------------------
    # Main audit
    # ------------------------------------------------------------------

    def audit_case(self, case_id):
        case_id = int(case_id)

        raw_directory = (
            self.data_root
            / "raw"
            / str(case_id)
        )

        output_path = (
            self.data_root
            / "processed"
            / str(case_id)
            / "audit"
            / "case_audit.json"
        )

        paths = {
            "manifest": (
                raw_directory
                / "manifest.json"
            ),
            "metadata": (
                raw_directory
                / "metadata.json"
            ),
            "navigation_tree": (
                raw_directory
                / "navigation_tree.json"
            ),
            "asset_registry": (
                raw_directory
                / "assets.json"
            ),
            "excel_export": (
                raw_directory
                / "export.xlsx"
            ),
        }

        input_files = {
            name: {
                "path": path.as_posix(),
                "exists": path.exists(),
                "size_bytes": (
                    path.stat().st_size
                    if path.exists()
                    else None
                ),
            }
            for name, path in paths.items()
        }

        # Required structured inputs
        metadata = self._load_json(
            paths["metadata"]
        )

        navigation_tree = self._load_json(
            paths["navigation_tree"]
        )

        registry = self._load_json(
            paths["asset_registry"]
        )

        # Manifest remains optional because older Phase-1 cases may
        # predate manifest generation.
        manifest = self._load_json(
            paths["manifest"],
            required=False,
        )

        sheets = self._read_workbook(
            paths["excel_export"]
        )

        workbook_audit = (
            self._audit_workbook(sheets)
        )

        relational_audit = (
            self._audit_relationships(sheets)
        )

        injury_audit = (
            self._audit_injury_outcomes(
                sheets
            )
        )

        edr_audit = self._audit_edr(
            sheets
        )

        mechanics_audit = (
            self._audit_crash_mechanics(
                sheets,
                edr_audit,
            )
        )

        contradiction_audit = (
            self._audit_contradictions(
                sheets,
                injury_audit,
                mechanics_audit,
            )
        )

        domains = (
            self._domain_availability(
                sheets,
                registry,
                injury_audit,
                edr_audit,
                mechanics_audit,
            )
        )

        eligibility = (
            self._task_eligibility(
                domains,
                injury_audit,
                edr_audit,
                mechanics_audit,
                contradiction_audit,
            )
        )

        errors = []
        warnings = []

        required_files = {
            "metadata",
            "navigation_tree",
            "asset_registry",
            "excel_export",
        }

        missing_files = [
            name
            for name, information
            in input_files.items()
            if (
                name in required_files
                and not information["exists"]
            )
        ]

        if missing_files:
            errors.append(
                "Missing required files: "
                + ", ".join(
                    missing_files
                )
            )

        if workbook_audit[
            "missing_core_sheets"
        ]:
            errors.append(
                "Core workbook sheets are missing: "
                + ", ".join(
                    workbook_audit[
                        "missing_core_sheets"
                    ]
                )
            )

        errors.extend(
            relational_audit["errors"]
        )

        if (
            injury_audit[
                "labeled_occupant_count"
            ]
            == 0
        ):
            warnings.append(
                "No reliable occupant injury labels "
                "were identified. Missing injury rows "
                "must not be interpreted as no injury."
            )

        if not edr_audit[
            "edr_obtained"
        ]:
            warnings.append(
                "No EDR data were found."
            )

        elif not edr_audit[
            "applicable_event_identified"
        ]:
            warnings.append(
                "EDR collection information exists,"
                 " but no EDR event records are available."
            )

        else:
            if edr_audit[
                "unit_validation_required"
            ]:
                warnings.append(
                    "The applicable EDR event contains "
                    "a Delta-V history, but its unit is "
                    "not explicit in the exported signal "
                    "description. Validate the unit before "
                    "biomechanical calculations."
                )

            if (
                edr_audit[
                    "delta_v_history_available"
                ]
                and not edr_audit[
                    "direct_acceleration_"
                    "history_available"
                ]
            ):
                warnings.append(
                    "A Delta-V time history is available, "
                    "but direct acceleration is unavailable. "
                    "Acceleration may be derived only after "
                    "validating the time and Delta-V units "
                    "and applying an appropriate numerical "
                    "differentiation method."
                )

            elif not (
                edr_audit[
                    "delta_v_history_available"
                ]
                or edr_audit[
                    "direct_acceleration_"
                    "history_available"
                ]
            ):
                warnings.append(
                    "The applicable EDR event does not "
                    "contain a usable Delta-V or direct "
                    "acceleration history."
                )

        agreement = edr_audit.get(
            "summary_history_agreement",
            {},
        )

        if (
            agreement.get("available")
            and agreement.get(
                "agreement_status"
            )
            == "requires_review"
        ):
            warnings.append(
                "The EDR summary Delta-V and the "
                "final Delta-V history sample differ "
                "by more than the audit tolerance."
            )

        if contradiction_audit[
            "contradiction_count"
        ]:
            warnings.append(
                "Cross-source contradictions require "
                "manual review."
            )

        if errors:
            status = "audit_failed"

        elif warnings:
            status = (
                "audit_passed_with_warnings"
            )

        else:
            status = "audit_passed"

        audit = {
            "schema_version": (
                AUDIT_SCHEMA_VERSION
            ),
            "case_id": case_id,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": status,
            "provenance": {
                "source": (
                    "NHTSA CISS Crash Viewer"
                ),
                "audit_component": (
                    "CaseAuditor"
                ),
                "manifest_schema_version": (
                    manifest.get(
                        "schema_version"
                    )
                    if manifest
                    else None
                ),
                "raw_data_preserved": True,
                "notes": (
                    "Eligibility represents data "
                    "availability and quality. It "
                    "does not guarantee biomechanical "
                    "validity or prediction accuracy."
                ),
            },
            "input_files": input_files,
            "package_manifest": {
                "available": (
                    manifest is not None
                ),
                "status": (
                    manifest.get("status")
                    if manifest
                    else None
                ),
                "validation_passed": (
                    manifest.get(
                        "validation",
                        {},
                    ).get(
                        "passed"
                    )
                    if manifest
                    else None
                ),
            },
            "metadata": {
                "available": bool(
                    metadata
                ),
                "top_level_keys": (
                    sorted(
                        metadata.keys()
                    )
                    if isinstance(
                        metadata,
                        dict,
                    )
                    else None
                ),
            },
            "navigation_tree": {
                "available": bool(
                    navigation_tree
                ),
                "node_count": (
                    len(navigation_tree)
                    if isinstance(
                        navigation_tree,
                        list,
                    )
                    else None
                ),
            },
            "asset_inventory": (
                self._asset_summary(
                    registry
                )
            ),
            "workbook": (
                workbook_audit
            ),
            "entities": (
                self._entity_summary(
                    sheets
                )
            ),
            "relational_integrity": (
                relational_audit
            ),
            "important_variable_profile": (
                self._important_variable_profile(
                    sheets
                )
            ),
            "injury_outcome_audit": (
                injury_audit
            ),
            "edr_quality_audit": (
                edr_audit
            ),
            "crash_mechanics_sources": (
                mechanics_audit
            ),
            "cross_source_contradictions": (
                contradiction_audit
            ),
            "domain_availability": (
                domains
            ),
            "task_eligibility": (
                eligibility
            ),
            "audit_summary": {
                "passed": not errors,
                "error_count": len(
                    errors
                ),
                "warning_count": len(
                    warnings
                ),
                "errors": errors,
                "warnings": warnings,
            },
        }

        self._save_json(
            audit,
            output_path,
        )

        print(
            f"Case audit created: "
            f"{output_path}"
        )

        print(
            f"Status: {status}"
        )

        print(
            "Workbook sheets audited: "
            f"{workbook_audit['sheet_count']}"
        )

        print(
            f"Audit errors: {len(errors)}; "
            f"warnings: {len(warnings)}"
        )

        return audit