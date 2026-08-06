"""
Create a comprehensive data audit for one CISS case.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import json
import re
import zipfile

from openpyxl import load_workbook
from src.audit.entity_registry import (
    EntityRegistryBuilder,
)
from src.audit.research_labels import (
    ResearchLabelBuilder,
)

from src.audit.audit_rules import (
    AUDIT_SCHEMA_VERSION,
    CORE_SHEETS,
    IMPORTANT_VARIABLES,
    NUMERIC_SENTINEL_VALUES,
    PRIMARY_KEYS,
    SENTINEL_TEXT_PATTERNS,
    VARIABLE_CATEGORY_DEFAULTS,
    VARIABLE_ENTITY_BY_SHEET,
    VARIABLE_METADATA_OVERRIDES,
    VARIABLE_REGISTRY_VERSION,
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

    @staticmethod
    def _numeric_sentinel_category(
        sheet_name: str | None,
        field: str,
        value: Any,
    ) -> str | None:
        """Return a source-specific numeric sentinel category."""

        if not sheet_name:
            return None

        registry_id = f"{sheet_name}.{field}"
        sentinel_rules = NUMERIC_SENTINEL_VALUES.get(
            registry_id,
            {},
        )

        numeric_value = CaseAuditor._coerce_numeric_value(
            value
        )

        if numeric_value is None:
            return None

        for sentinel_value, category in sentinel_rules.items():
            if numeric_value == float(sentinel_value):
                return category

        return None

    def _record_sentinel_category(
        self,
        record: dict[str, Any],
        field: str,
        sheet_name: str | None = None,
    ) -> str | None:
        """Resolve text and numeric sentinel representations."""

        text_category = self._sentinel_category(
            record.get(f"{field}TEXT")
        )

        if text_category:
            return text_category

        return self._numeric_sentinel_category(
            sheet_name=sheet_name,
            field=field,
            value=record.get(field),
        )

    def _is_usable(
        self,
        record,
        field,
        sheet_name=None,
    ):
        value = record.get(field)

        if value is None or value == "":
            return False

        return (
            self._record_sentinel_category(
                record=record,
                field=field,
                sheet_name=sheet_name,
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
                    sheet_name="OCC",
                )
                else None
            )

            mais = (
                record.get("MAIS")
                if self._is_usable(
                    record,
                    "MAIS",
                    sheet_name="OCC",
                )
                else None
            )

            iss = (
                record.get("ISS")
                if self._is_usable(
                    record,
                    "ISS",
                    sheet_name="OCC",
                )
                else None
            )

            injstatus = (
                record.get("INJSTATUS")
                if self._is_usable(
                    record,
                    "INJSTATUS",
                    sheet_name="OCC",
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

    def _final_label_readiness(
        self,
        injury_audit: dict[str, Any],
    ) -> dict[str, Any]:
        """Summarize which occupant outcomes can supervise ML training."""

        occupants = injury_audit.get(
            "occupants",
            [],
        )

        occupant_records = [
            {
                "case_id": occupant.get("case_id"),
                "vehicle_number": occupant.get(
                    "vehicle_number"
                ),
                "occupant_number": occupant.get(
                    "occupant_number"
                ),
                "label_state": occupant.get(
                    "label_state"
                ),
                "training_eligible": bool(
                    occupant.get("label_available")
                ),
                "exclusion_reason": (
                    None
                    if occupant.get("label_available")
                    else "unknown_or_insufficient_injury_outcome"
                ),
            }
            for occupant in occupants
        ]

        total_occupants = len(occupant_records)
        eligible_occupants = sum(
            record["training_eligible"]
            for record in occupant_records
        )
        excluded_occupants = total_occupants - eligible_occupants

        if total_occupants == 0:
            status = "not_available"
            reason = "No occupant records are available."
        elif eligible_occupants == 0:
            status = "not_ready"
            reason = (
                "No occupants have reliable positive or explicit "
                "negative injury outcomes."
            )
        elif eligible_occupants == total_occupants:
            status = "ready"
            reason = (
                "All occupants have reliable positive or explicit "
                "negative injury outcomes."
            )
        else:
            status = "partially_ready"
            reason = (
                "Only a subset of occupants has reliable injury "
                "outcomes; row-level filtering is required."
            )

        return {
            "status": status,
            "count_unit": "occupant_records",
            "total_occupants": total_occupants,
            "eligible_occupants": eligible_occupants,
            "excluded_occupants": excluded_occupants,
            "label_state_counts": injury_audit.get(
                "state_counts",
                {},
            ),
            "reason": reason,
            "occupants": occupant_records,
        }

    @staticmethod
    def _apply_final_label_readiness(
        variable_registry: dict[str, Any],
        final_label_readiness: dict[str, Any],
    ) -> None:
        """Apply occupant-level label validation to registry metadata."""

        readiness_status = final_label_readiness.get("status")
        variables = variable_registry.get("variables", {})

        for entry in variables.values():
            if "final_label" not in entry.get("training_roles", []):
                continue
            if entry.get("availability") != "available":
                continue

            if readiness_status == "ready":
                entry["training_usability"] = "training_ready"
                entry["label_validation_status"] = (
                    "validated_at_occupant_level"
                )
            elif readiness_status == "partially_ready":
                entry["training_usability"] = (
                    "partially_training_ready_requires_row_filtering"
                )
                entry["label_validation_status"] = (
                    "partially_validated_at_occupant_level"
                )
            else:
                entry["training_usability"] = (
                    "not_training_ready_no_reliable_labels"
                )
                entry["label_validation_status"] = (
                    "rejected_at_occupant_level"
                )

        training_usability_counts = Counter(
            entry.get("training_usability")
            for entry in variables.values()
        )

        ready_final_label_variables = sorted(
            registry_id
            for registry_id, entry in variables.items()
            if (
                "final_label" in entry.get("training_roles", [])
                and entry.get("training_usability") == "training_ready"
            )
        )

        variable_registry["training_usability_counts"] = dict(
            sorted(training_usability_counts.items())
        )
        variable_registry[
            "training_ready_final_label_variable_count"
        ] = len(ready_final_label_variables)
        variable_registry[
            "training_ready_final_label_variables"
        ] = ready_final_label_variables





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
                sheet_name="EDREVENT",
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
                sheet_name="EDREVENT",
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
                    sheet_name=sheet_name,
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
                                sheet_name=sheet_name,
                            )
                            else None
                        ),
                        "lateral_delta_v": (
                            record.get("DVLAT")
                            if self._is_usable(
                                record,
                                "DVLAT",
                                sheet_name=sheet_name,
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
                    sheet_name="EDREVENT",
                )
                else None
            )

            lateral = (
                record.get("MAXDVLAT")
                if self._is_usable(
                    record,
                    "MAXDVLAT",
                    sheet_name="EDREVENT",
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
        sheet_name,
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
                self._record_sentinel_category(
                    record=record,
                    field=field,
                    sheet_name=sheet_name,
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
                            sheet_name,
                            sheet,
                            field,
                        )
                    )
                    for field in fields
                }

        return result

    @staticmethod
    def _coerce_numeric_value(
        value: Any,
    ) -> float | None:
        """
        Convert a value to float when possible.

        Boolean values are rejected because Python treats bool as int.
        """

        if value is None or value == "":
            return None

        if isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")

            if not cleaned:
                return None

            try:
                return float(cleaned)
            except ValueError:
                return None

        return None

    def _range_validation(
        self,
        sheet_name: str,
        sheet: dict[str, Any],
        field: str,
        expected_range: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Validate all usable numeric values against an expected range.

        Sentinel-coded records are excluded using the companion TEXT
        variable when available.
        """

        if not expected_range:
            return {
                "status": "not_defined",
                "minimum": None,
                "maximum": None,
                "numeric_value_count": 0,
                "non_numeric_value_count": 0,
                "out_of_range_count": 0,
                "out_of_range_samples": [],
            }

        minimum = expected_range.get("minimum")
        maximum = expected_range.get("maximum")

        numeric_values: list[float] = []
        non_numeric_count = 0
        out_of_range_values: list[Any] = []

        for record in sheet.get("records", []):
            value = record.get(field)

            if value is None or value == "":
                continue

            sentinel_category = self._record_sentinel_category(
                record=record,
                field=field,
                sheet_name=sheet_name,
            )

            if sentinel_category:
                continue

            numeric_value = self._coerce_numeric_value(value)

            if numeric_value is None:
                non_numeric_count += 1
                continue

            numeric_values.append(numeric_value)

            below_minimum = (
                minimum is not None
                and numeric_value < minimum
            )

            above_maximum = (
                maximum is not None
                and numeric_value > maximum
            )

            if below_minimum or above_maximum:
                if value not in out_of_range_values:
                    out_of_range_values.append(value)

        if not numeric_values and non_numeric_count == 0:
            status = "not_evaluated_no_values"

        elif out_of_range_values:
            status = "failed"

        elif non_numeric_count:
            status = "passed_with_non_numeric_values"

        else:
            status = "passed"

        return {
            "status": status,
            "minimum": minimum,
            "maximum": maximum,
            "numeric_value_count": len(numeric_values),
            "non_numeric_value_count": non_numeric_count,
            "out_of_range_count": len(out_of_range_values),
            "out_of_range_samples": out_of_range_values[:5],
        }
    # ------------------------------------------------------------------
    # Variable registry
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_metadata_age(
        value: Any,
    ) -> dict[str, Any] | None:
        """Parse API age strings such as ``42 years`` or ``18 months``."""

        if not isinstance(value, str):
            return None

        match = re.fullmatch(
            r"\s*(\d+(?:\.\d+)?)\s*(years?|months?)\s*",
            value,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        amount = float(match.group(1))
        reported_unit = match.group(2).lower()

        if reported_unit.startswith("month"):
            age_years = amount / 12.0
            age_months = amount
        else:
            age_years = amount
            age_months = amount * 12.0

        return {
            "reported_value": amount,
            "reported_unit": reported_unit,
            "age_years": age_years,
            "age_months": age_months,
        }

    def _audit_occupant_age(
        self,
        sheets: dict[str, Any],
        metadata: Any,
    ) -> dict[str, Any]:
        """
        Reconcile OCC.AGE with the API occupant profile.

        The Crash Viewer Excel endpoint can expose adult ages as a
        month-like count even though the analytical CISS AGE variable is
        defined in years.  This method documents a normalization candidate;
        it never mutates the raw workbook value.
        """

        profiles = (
            metadata.get("occupantProfiles", [])
            if isinstance(metadata, dict)
            else []
        )

        profile_index = {
            (
                profile.get("caseId"),
                profile.get("vehicleNumber"),
                profile.get("occupantNumber"),
            ): profile
            for profile in profiles
            if isinstance(profile, dict)
        }

        results = []

        for record in self._records(sheets, "OCC"):
            raw_age = record.get("AGE")

            key = (
                record.get("CASEID"),
                record.get("VEHNO"),
                record.get("OCCNO"),
            )

            profile = profile_index.get(key)
            metadata_age_text = (
                profile.get("age")
                if profile
                else None
            )
            parsed_metadata_age = (
                self._parse_metadata_age(
                    metadata_age_text
                )
            )

            raw_numeric = self._coerce_numeric_value(
                raw_age
            )

            if not self._is_usable(
                record,
                "AGE",
                sheet_name="OCC",
            ):
                reconciliation = "raw_age_not_usable"
                canonical_age = None
                normalization = None

            elif parsed_metadata_age is None:
                reconciliation = "metadata_age_unavailable"
                canonical_age = None
                normalization = None

            elif raw_numeric is None:
                reconciliation = "raw_age_not_numeric"
                canonical_age = None
                normalization = None

            else:
                metadata_years = parsed_metadata_age[
                    "age_years"
                ]

                direct_match = abs(
                    raw_numeric - metadata_years
                ) < 1e-9

                month_encoded_match = (
                    raw_numeric > 120
                    and abs(
                        raw_numeric / 12.0
                        - metadata_years
                    )
                    < 1e-9
                )

                if direct_match:
                    reconciliation = "direct_year_match"
                    canonical_age = metadata_years
                    normalization = None

                elif month_encoded_match:
                    reconciliation = (
                        "month_encoded_value_confirmed"
                    )
                    canonical_age = metadata_years
                    normalization = {
                        "operation": "divide",
                        "factor": 12,
                        "from_unit": "month_like_count",
                        "to_unit": "year",
                        "apply_in_stage": 3,
                        "applied_during_audit": False,
                    }

                else:
                    reconciliation = "cross_source_mismatch"
                    canonical_age = None
                    normalization = None

            results.append(
                {
                    "case_id": key[0],
                    "vehicle_number": key[1],
                    "occupant_number": key[2],
                    "raw_excel_age": raw_age,
                    "raw_excel_age_text": record.get(
                        "AGETEXT"
                    ),
                    "metadata_age_text": metadata_age_text,
                    "parsed_metadata_age": parsed_metadata_age,
                    "reconciliation": reconciliation,
                    "canonical_age_years_candidate": (
                        canonical_age
                    ),
                    "normalization_candidate": normalization,
                }
            )

        reconciled_states = {
            "direct_year_match",
            "month_encoded_value_confirmed",
        }

        reconciled_count = sum(
            result["reconciliation"] in reconciled_states
            for result in results
        )
        month_encoded_count = sum(
            result["reconciliation"]
            == "month_encoded_value_confirmed"
            for result in results
        )
        unresolved_count = sum(
            result["reconciliation"]
            not in reconciled_states
            for result in results
        )

        if not results:
            status = "not_available"
        elif unresolved_count == 0:
            status = "reconciled"
        elif reconciled_count:
            status = "partially_reconciled"
        else:
            status = "unresolved"

        return {
            "status": status,
            "source_variable": "OCC.AGE",
            "canonical_unit": "year",
            "record_count": len(results),
            "reconciled_count": reconciled_count,
            "month_encoded_count": month_encoded_count,
            "unresolved_count": unresolved_count,
            "normalization_required": month_encoded_count > 0,
            "raw_values_preserved": True,
            "normalization_stage": 3,
            "records": results,
        }

    def _variable_registry_entry(
        self,
        domain: str,
        sheet_name: str,
        field: str,
        profile: dict[str, Any],
        sheet: dict[str, Any],
        occupant_age_audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Build one source-specific variable metadata record.
        """

        registry_id = f"{sheet_name}.{field}"

        defaults = VARIABLE_CATEGORY_DEFAULTS.get(
            domain,
            {
                "training_roles": (
                    "observed_input",
                ),
                "downstream_stages": (3,),
            },
        )

        override = VARIABLE_METADATA_OVERRIDES.get(
            registry_id,
            {},
        )

        present = bool(profile.get("present"))

        record_count = int(
            profile.get("record_count", 0) or 0
        )

        usable_count = int(
            profile.get("usable_count", 0) or 0
        )

        # ----------------------------------------------------------
        # Source availability
        # ----------------------------------------------------------

        if not present:
            availability = "unavailable"
            raw_usability = "unavailable"
            confidence = None

        elif record_count == 0:
            availability = "source_present_no_records"
            raw_usability = "not_usable"
            confidence = None

        elif usable_count == 0:
            availability = "present_without_usable_values"
            raw_usability = "not_usable"
            confidence = None

        else:
            availability = "available"
            raw_usability = "usable"
            confidence = "reported"

        expected_range = override.get(
            "expected_range"
        )

        range_validation = self._range_validation(
            sheet_name=sheet_name,
            sheet=sheet,
            field=field,
            expected_range=expected_range,
        )

        range_status = range_validation["status"]

        if range_status == "failed":
            raw_usability = "requires_validation"
            confidence = "questionable"

        semantic_reconciliation = None
        normalization_candidate = None
        raw_unit = override.get("unit")

        if (
            registry_id == "OCC.AGE"
            and occupant_age_audit
        ):
            semantic_reconciliation = {
                "status": occupant_age_audit.get("status"),
                "reconciled_count": occupant_age_audit.get(
                    "reconciled_count",
                    0,
                ),
                "unresolved_count": occupant_age_audit.get(
                    "unresolved_count",
                    0,
                ),
                "month_encoded_count": occupant_age_audit.get(
                    "month_encoded_count",
                    0,
                ),
            }

            if (
                occupant_age_audit.get("status") == "reconciled"
                and occupant_age_audit.get(
                    "normalization_required"
                )
            ):
                range_status = "raw_encoding_reconciled"
                range_validation["status"] = range_status
                raw_usability = "requires_standardization"
                confidence = "cross_source_confirmed"
                raw_unit = "month_like_count"
                normalization_candidate = {
                    "operation": "divide",
                    "factor": 12,
                    "from_unit": "month_like_count",
                    "to_unit": "year",
                    "apply_in_stage": 3,
                    "applied_during_audit": False,
                }

        training_roles = list(
            override.get(
                "training_roles",
                defaults["training_roles"],
            )
        )

        downstream_stages = list(
            override.get(
                "downstream_stages",
                defaults["downstream_stages"],
            )
        )

        # ----------------------------------------------------------
        # Training usability
        # ----------------------------------------------------------

        if availability != "available":
            training_usability = "not_usable"

        elif range_status == "failed":
            training_usability = (
                "not_usable_until_range_issue_resolved"
            )

        elif range_status == "raw_encoding_reconciled":
            training_usability = "requires_standardization"

        elif "final_label" in training_roles:
            training_usability = (
                "requires_research_label_validation"
            )

        else:
            training_usability = "candidate"

        text_companion = (
            f"{field}TEXT"
            if f"{field}TEXT"
            in sheet.get("headers", [])
            else None
        )

        return {
            "registry_id": registry_id,
            "canonical_name": override.get(
                "canonical_name",
                field.lower(),
            ),
            "raw_name": field,
            "entity_type": VARIABLE_ENTITY_BY_SHEET.get(
                sheet_name,
                "unknown",
            ),
            "category": domain,
            "worksheet": sheet_name,
            "source": "CISS Excel export",
            "source_reference": registry_id,
            "text_companion": text_companion,
            "unit": override.get("unit"),
            "raw_unit": raw_unit,
            "unit_status": override.get(
                "unit_status",
                "not_defined",
            ),
            "expected_range": expected_range,
            "range_status": range_status,
            "range_validation": range_validation,
            "semantic_reconciliation": semantic_reconciliation,
            "normalization_candidate": normalization_candidate,
            "availability": availability,

            # Retained for backward compatibility.
            "usability": raw_usability,

            "raw_usability": raw_usability,
            "training_usability": training_usability,
            "confidence": confidence,
            "training_roles": training_roles,
            "downstream_stages": downstream_stages,
            "case_profile": profile,
        }

    def _variable_registry(
        self,
        sheets: dict[str, Any],
        important_variable_profile: dict[str, Any],
        occupant_age_audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Convert the legacy important-variable profile into the
        Stage-2 variable registry.

        The old profile remains in the audit document for backward
        compatibility.
        """

        variables: dict[str, dict[str, Any]] = {}

        for domain, sheet_rules in IMPORTANT_VARIABLES.items():
            for sheet_name, fields in sheet_rules.items():
                sheet = sheets.get(
                    sheet_name,
                    {
                        "headers": [],
                        "records": [],
                    },
                )

                profiles = (
                    important_variable_profile
                    .get(domain, {})
                    .get(sheet_name, {})
                )

                for field in fields:
                    profile = profiles.get(
                        field,
                        {
                            "present": False,
                        },
                    )

                    entry = self._variable_registry_entry(
                        domain=domain,
                        sheet_name=sheet_name,
                        field=field,
                        profile=profile,
                        sheet=sheet,
                        occupant_age_audit=occupant_age_audit,
                    )

                    variables[entry["registry_id"]] = entry

        availability_counts = Counter(
            entry["availability"]
            for entry in variables.values()
        )

        range_status_counts = Counter(
            entry["range_status"]
            for entry in variables.values()
        )

        raw_usability_counts = Counter(
            entry["raw_usability"]
            for entry in variables.values()
        )

        training_usability_counts = Counter(
            entry["training_usability"]
            for entry in variables.values()
        )

        defined_role_counts = Counter(
            role
            for entry in variables.values()
            for role in entry["training_roles"]
        )

        available_role_counts = Counter(
            role
            for entry in variables.values()
            if entry["availability"] == "available"
            for role in entry["training_roles"]
        )

        range_violation_variables = [
            registry_id
            for registry_id, entry in variables.items()
            if entry["range_status"] == "failed"
        ]

        return {
            "registry_version": VARIABLE_REGISTRY_VERSION,
            "registry_id_format": "WORKSHEET.FIELD",
            "variable_count": len(variables),
            "availability_counts": dict(
                sorted(availability_counts.items())
            ),
            "range_status_counts": dict(
                sorted(range_status_counts.items())
            ),
            "raw_usability_counts": dict(
                sorted(raw_usability_counts.items())
            ),
            "training_usability_counts": dict(
                sorted(training_usability_counts.items())
            ),

            # Retained for backward compatibility.
            "training_role_counts": dict(
                sorted(defined_role_counts.items())
            ),

            "defined_training_role_counts": dict(
                sorted(defined_role_counts.items())
            ),
            "available_training_role_counts": dict(
                sorted(available_role_counts.items())
            ),
            "range_violation_count": len(
                range_violation_variables
            ),
            "range_violation_variables": (
                range_violation_variables
            ),
            "variables": variables,
        }
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
                sheet_name="CDC",
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
    def audit_case(
        self,
        case_id: int,
    ) -> dict[str, Any]:
        """
        Create the comprehensive Stage-2 audit for one CISS case.

        Parameters
        ----------
        case_id:
            CISS case identifier.

        Returns
        -------
        dict[str, Any]
            Complete case audit document.
        """

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

        # ----------------------------------------------------------
        # Input paths
        # ----------------------------------------------------------

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

        # ----------------------------------------------------------
        # Load Phase-1 inputs
        # ----------------------------------------------------------

        metadata = self._load_json(
            paths["metadata"]
        )

        navigation_tree = self._load_json(
            paths["navigation_tree"]
        )

        asset_registry = self._load_json(
            paths["asset_registry"]
        )

        # The manifest is optional because older Phase-1 cases may
        # have been created before manifest generation was added.
        manifest = self._load_json(
            paths["manifest"],
            required=False,
        )

        sheets = self._read_workbook(
            paths["excel_export"]
        )
        entity_registry = (
            EntityRegistryBuilder().build(
                case_id=case_id,
                sheets=sheets,
                asset_registry=asset_registry,
            )
        )
        # ----------------------------------------------------------
        # Variable metadata
        # ----------------------------------------------------------

        # Preserve the original variable profile for backward
        # compatibility.
        important_variable_profile = (
            self._important_variable_profile(
                sheets
            )
        )

        occupant_age_audit = (
            self._audit_occupant_age(
                sheets=sheets,
                metadata=metadata,
            )
        )

        # Create the enriched Stage-2 variable registry.
        variable_registry = (
            self._variable_registry(
                sheets=sheets,
                important_variable_profile=(
                    important_variable_profile
                ),
                occupant_age_audit=(
                    occupant_age_audit
                ),
            )
        )

        # ----------------------------------------------------------
        # Core audits
        # ----------------------------------------------------------

        workbook_audit = self._audit_workbook(
            sheets
        )

        relational_audit = (
            self._audit_relationships(
                sheets
            )
        )

        injury_audit = (
            self._audit_injury_outcomes(
                sheets
            )
        )

        final_label_readiness = (
            self._final_label_readiness(
                injury_audit
            )
        )

        self._apply_final_label_readiness(
            variable_registry,
            final_label_readiness,
        )

        edr_audit = self._audit_edr(
            sheets
        )
        # ----------------------------------------------------------
        # Research label registry
        # ----------------------------------------------------------

        research_labels = (
            ResearchLabelBuilder().build(
                case_id=case_id,
                sheets=sheets,
                entity_registry=entity_registry,
                final_label_readiness=(
                    final_label_readiness
                ),
                edr_audit=edr_audit,
            )
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

        # ----------------------------------------------------------
        # Domain availability and task eligibility
        # ----------------------------------------------------------

        domains = self._domain_availability(
            sheets,
            asset_registry,
            injury_audit,
            edr_audit,
            mechanics_audit,
        )

        eligibility = self._task_eligibility(
            domains,
            injury_audit,
            edr_audit,
            mechanics_audit,
            contradiction_audit,
        )

        # ----------------------------------------------------------
        # Errors and warnings
        # ----------------------------------------------------------

        errors: list[str] = []
        warnings: list[str] = []
        unresolved_entity_references = (
            entity_registry.get(
                "summary",
                {},
            ).get(
                "unresolved_reference_count",
                0,
            )
        )

        if unresolved_entity_references:
            warnings.append(
                "Entity registry contains "
                f"{unresolved_entity_references} "
                "unresolved reference(s); "
                "downstream joins require review."
            )
        required_files = {
            "metadata",
            "navigation_tree",
            "asset_registry",
            "excel_export",
        }
        unresolved_research_labels = (
            research_labels.get(
                "summary",
                {},
            ).get(
                "unresolved_label_count",
                0,
            )
        )

        if unresolved_research_labels:
            warnings.append(
                "Research label registry contains "
                f"{unresolved_research_labels} "
                "unresolved label reference(s); "
                "downstream supervision joins "
                "require review."
            )
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

        missing_core_sheets = (
            workbook_audit.get(
                "missing_core_sheets",
                [],
            )
        )

        if missing_core_sheets:
            errors.append(
                "Core workbook sheets are missing: "
                + ", ".join(
                    missing_core_sheets
                )
            )

        errors.extend(
            relational_audit.get(
                "errors",
                [],
            )
        )

        # ----------------------------------------------------------
        # Variable registry warnings
        # ----------------------------------------------------------

        range_violation_variables = (
            variable_registry.get(
                "range_violation_variables",
                [],
            )
        )

        if range_violation_variables:
            warnings.append(
                "Variables contain values outside their "
                "documented ranges: "
                + ", ".join(
                    range_violation_variables
                )
            )

        if occupant_age_audit.get(
            "normalization_required",
            False,
        ):
            if (
                occupant_age_audit.get("status")
                == "reconciled"
            ):
                warnings.append(
                    "OCC.AGE uses a month-like encoding in the "
                    "Crash Viewer Excel export. The values were "
                    "cross-source reconciled with metadata.json; "
                    "raw values were preserved and conversion to "
                    "years was deferred to Stage 3."
                )
            else:
                warnings.append(
                    "OCC.AGE contains a suspected month-like "
                    "encoding that could not be fully reconciled "
                    "with metadata.json."
                )

        # ----------------------------------------------------------
        # Injury-label warnings
        # ----------------------------------------------------------

        if (
            injury_audit.get(
                "labeled_occupant_count",
                0,
            )
            == 0
        ):
            warnings.append(
                "No reliable occupant injury labels "
                "were identified. Missing injury rows "
                "must not be interpreted as no injury."
            )

        # ----------------------------------------------------------
        # EDR warnings
        # ----------------------------------------------------------

        if not edr_audit.get(
            "edr_obtained",
            False,
        ):
            warnings.append(
                "No EDR data were found."
            )

        elif not edr_audit.get(
            "applicable_event_identified",
            False,
        ):
            warnings.append(
                "EDR collection information exists, "
                "but no EDR event records are available."
            )

        else:
            if edr_audit.get(
                "unit_validation_required",
                False,
            ):
                warnings.append(
                    "The applicable EDR event contains "
                    "a Delta-V history, but its unit is "
                    "not explicit in the exported signal "
                    "description. Validate the unit before "
                    "biomechanical calculations."
                )

            delta_v_history_available = (
                edr_audit.get(
                    "delta_v_history_available",
                    False,
                )
            )

            direct_acceleration_available = (
                edr_audit.get(
                    "direct_acceleration_"
                    "history_available",
                    False,
                )
            )

            if (
                delta_v_history_available
                and not direct_acceleration_available
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
                delta_v_history_available
                or direct_acceleration_available
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
            agreement.get(
                "available",
                False,
            )
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

        # ----------------------------------------------------------
        # Contradiction warnings
        # ----------------------------------------------------------

        contradiction_count = (
            contradiction_audit.get(
                "contradiction_count",
                0,
            )
        )

        if contradiction_count:
            warnings.append(
                "Cross-source contradictions require "
                "manual review."
            )

        # ----------------------------------------------------------
        # Overall audit status
        # ----------------------------------------------------------

        if errors:
            status = "audit_failed"

        elif warnings:
            status = (
                "audit_passed_with_warnings"
            )

        else:
            status = "audit_passed"

        # ----------------------------------------------------------
        # Final audit document
        # ----------------------------------------------------------

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
                    asset_registry
                )
            ),
            "workbook": workbook_audit,
            # Legacy entity count summary retained for
            # backward compatibility.
            "entities": (
                self._entity_summary(
                    sheets
                )
            ),

            "entity_registry": (
                entity_registry
            ),

            "research_labels": (
                research_labels
            ),

            "relational_integrity": (
                relational_audit
            ),

            # Legacy variable output retained temporarily.
            "important_variable_profile": (
                important_variable_profile
            ),

            # New Stage-2 metadata contract.
            "variable_registry": (
                variable_registry
            ),
            "occupant_age_audit": (
                occupant_age_audit
            ),
            "final_label_readiness": (
                final_label_readiness
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

        # ----------------------------------------------------------
        # Save and report
        # ----------------------------------------------------------

        self._save_json(
            audit,
            output_path,
        )

        print(
            "Case audit created: "
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
   
