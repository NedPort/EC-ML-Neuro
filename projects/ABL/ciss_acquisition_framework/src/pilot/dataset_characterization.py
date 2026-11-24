"""Build the final Stage-2 characterization report for a CISS pilot."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


CHARACTERIZATION_SCHEMA_VERSION = "1.0"
MINIMUM_SUMMARY_VERSION = (2, 1)


IMPORTANT_VARIABLE_GROUPS: dict[str, tuple[str, ...]] = {
    "crash_mechanics": (
        "GV.DVTOTAL",
        "CDC.DVTOTAL",
        "CDC.PDOF",
        "EDREVENT.MAXDVLONG",
        "EDREVENT.MAXDVLAT",
        "EDREVENT.MAXDVRESTIME",
    ),
    "occupant_characteristics": (
        "OCC.AGE",
        "OCC.HEIGHT",
        "OCC.WEIGHT",
        "OCC.SEATLOC",
    ),
    "restraint_and_protection": (
        "OCC.BELTUSE",
        "OCC.PARAIRBAG",
    ),
    "injury_labels": (
        "OCC.MAIS",
        "OCC.AIS",
        "INJURY.AIS",
    ),
}


class DatasetCharacterizer:
    """Convert the Stage-2 pilot summary into research-facing metadata."""

    def __init__(
        self,
        data_root: str | Path = "data",
        summary_path: str | Path | None = None,
        output_path: str | Path | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.summary_path = (
            Path(summary_path)
            if summary_path is not None
            else self.data_root
            / "processed"
            / "pilot"
            / "pilot_audit_summary.json"
        )
        self.output_path = (
            Path(output_path)
            if output_path is not None
            else self.data_root
            / "processed"
            / "pilot"
            / "dataset_characterization.json"
        )
        self.markdown_path = self.output_path.with_suffix(".md")

    def build_and_save(self) -> dict[str, Any]:
        """Load the pilot summary, build both reports, and save them."""

        summary = self._load_json(self.summary_path)
        report = self.build(summary)
        self._save_json(report, self.output_path)
        self._save_text(
            self._to_markdown(report),
            self.markdown_path,
        )

        print(
            "Dataset characterization created: "
            f"{self.output_path}"
        )
        print(
            "Readable characterization created: "
            f"{self.markdown_path}"
        )
        print(f"Status: {report['stage_2_completion']['status']}")
        return report

    def build(self, summary: dict[str, Any]) -> dict[str, Any]:
        """Build a deterministic characterization from summary version 2.1+."""

        self._validate_summary(summary)
        registered_count = int(
            summary.get("registered_case_count", 0) or 0
        )
        variable_summary = summary[
            "variable_availability_summary"
        ]
        variables = variable_summary.get("variables", {})

        important_variables = {
            group: {
                variable_id: self._variable_characterization(
                    variable_id,
                    variables.get(variable_id),
                    registered_count,
                )
                for variable_id in variable_ids
            }
            for group, variable_ids in IMPORTANT_VARIABLE_GROUPS.items()
        }

        age = self._age_characterization(
            summary,
            variables.get("OCC.AGE", {}),
        )
        missingness = self._missingness_characterization(
            variables,
            registered_count,
        )
        completion = self._completion_assessment(
            summary,
            age,
        )

        return {
            "schema_version": CHARACTERIZATION_SCHEMA_VERSION,
            "created_at": self._utc_now(),
            "source": {
                "pilot_id": summary.get("pilot_id"),
                "pilot_summary_version": summary.get(
                    "summary_version"
                ),
                "pilot_summary_path": self.summary_path.as_posix(),
            },
            "dataset_inventory": {
                "registered_case_count": registered_count,
                "processing_status_counts": summary.get(
                    "processing_status_counts",
                    {},
                ),
                "contract_pass_count": int(
                    summary.get("contract_pass_count", 0) or 0
                ),
                "contract_failure_count": int(
                    summary.get("contract_failure_count", 0) or 0
                ),
                "audited_variable_count": int(
                    variable_summary.get("variable_count", 0) or 0
                ),
            },
            "integrity": {
                "processing_failures": summary.get(
                    "processing_failures",
                    [],
                ),
                "contract_failures": summary.get(
                    "contract_failures",
                    [],
                ),
                "contradictions": summary.get(
                    "contradiction_summary",
                    {},
                ),
                "warning_details": summary.get(
                    "warning_details",
                    [],
                ),
            },
            "important_variable_availability": important_variables,
            "missingness_characterization": missingness,
            "age_standardization": age,
            "physics_readiness": summary.get(
                "physics_readiness_summary",
                {},
            ),
            "stage_eligibility": {
                "status_counts": summary.get(
                    "stage_status_counts",
                    {},
                ),
                "status_details": summary.get(
                    "stage_status_details",
                    {},
                ),
            },
            "research_cohorts": summary.get(
                "research_cohorts",
                {},
            ),
            "label_readiness": summary.get(
                "label_readiness_summary",
                {},
            ),
            "stage_2_completion": completion,
        }

    @staticmethod
    def _variable_characterization(
        variable_id: str,
        detail: Any,
        registered_count: int,
    ) -> dict[str, Any]:
        if not isinstance(detail, dict):
            return {
                "variable_id": variable_id,
                "registry_status": "not_registered",
                "availability_tier": "absent",
                "available_case_count": 0,
                "registered_case_count": registered_count,
                "availability_rate": 0.0,
                "availability_percent": 0.0,
                "availability_status_counts": {},
                "training_usability_counts": {},
                "available_case_ids": [],
            }

        rate = float(detail.get("availability_rate", 0.0) or 0.0)
        return {
            "variable_id": variable_id,
            "registry_status": "registered",
            "availability_tier": DatasetCharacterizer._availability_tier(
                rate
            ),
            "available_case_count": int(
                detail.get("available_case_count", 0) or 0
            ),
            "registered_case_count": registered_count,
            "availability_rate": rate,
            "availability_percent": round(rate * 100.0, 2),
            "availability_status_counts": detail.get(
                "availability_status_counts",
                {},
            ),
            "training_usability_counts": detail.get(
                "training_usability_counts",
                {},
            ),
            "available_case_ids": detail.get(
                "available_case_ids",
                [],
            ),
        }

    @staticmethod
    def _missingness_characterization(
        variables: dict[str, Any],
        registered_count: int,
    ) -> dict[str, Any]:
        tiers: dict[str, list[str]] = {
            "high": [],
            "moderate": [],
            "low": [],
            "absent": [],
        }

        for variable_id, detail in variables.items():
            if not isinstance(detail, dict):
                continue
            rate = float(detail.get("availability_rate", 0.0) or 0.0)
            tiers[
                DatasetCharacterizer._availability_tier(rate)
            ].append(variable_id)

        for tier in tiers:
            tiers[tier] = sorted(tiers[tier])

        return {
            "availability_tier_thresholds": {
                "high": "rate >= 0.80",
                "moderate": "0.50 <= rate < 0.80",
                "low": "0 < rate < 0.50",
                "absent": "rate = 0",
            },
            "variable_counts_by_tier": {
                tier: len(variable_ids)
                for tier, variable_ids in tiers.items()
            },
            "variables_by_tier": tiers,
            "interpretation": (
                "Availability describes whether usable values were "
                "found in the audited source. It does not imply that "
                "the variable is standardized or training-ready."
            ),
        }

    @staticmethod
    def _age_characterization(
        summary: dict[str, Any],
        age_detail: dict[str, Any],
    ) -> dict[str, Any]:
        reconciled: set[int] = set()
        unresolved: set[int] = set()

        for warning in summary.get("warning_details", []):
            if not isinstance(warning, dict):
                continue
            message = str(warning.get("warning", "")).lower()
            case_ids = {
                int(case_id)
                for case_id in warning.get("case_ids", [])
            }
            if "cross-source reconciled" in message:
                reconciled.update(case_ids)
            if "could not be fully reconciled" in message:
                unresolved.update(case_ids)

        return {
            "available_case_count": int(
                age_detail.get("available_case_count", 0) or 0
            ),
            "availability_rate": float(
                age_detail.get("availability_rate", 0.0) or 0.0
            ),
            "reconciled_requires_standardization": {
                "count": len(reconciled),
                "case_ids": sorted(reconciled),
            },
            "unresolved_not_training_ready": {
                "count": len(unresolved),
                "case_ids": sorted(unresolved),
            },
            "stage_3_policy": {
                "preserve_raw_value": True,
                "create_standardized_years_field": True,
                "exclude_unresolved_values_until_reviewed": True,
                "do_not_interpret_sentinel_as_age": True,
            },
        }

    @staticmethod
    def _completion_assessment(
        summary: dict[str, Any],
        age: dict[str, Any],
    ) -> dict[str, Any]:
        registered = int(summary.get("registered_case_count", 0) or 0)
        completed = int(
            summary.get("processing_status_counts", {}).get(
                "completed",
                0,
            )
            or 0
        )
        contract_failures = int(
            summary.get("contract_failure_count", 0) or 0
        )
        processing_failures = len(
            summary.get("processing_failures", [])
        )
        contradictions = int(
            summary.get("contradiction_summary", {}).get(
                "contradiction_count",
                0,
            )
            or 0
        )

        blockers: list[str] = []
        if completed != registered:
            blockers.append("not_all_registered_cases_completed")
        if contract_failures:
            blockers.append("audit_contract_failures_present")
        if processing_failures:
            blockers.append("processing_failures_present")
        if contradictions:
            blockers.append("unresolved_cross_source_contradictions")

        actions: list[str] = []
        if age["reconciled_requires_standardization"]["count"]:
            actions.append("standardize_reconciled_occupant_age_values")
        if age["unresolved_not_training_ready"]["count"]:
            actions.append("review_unresolved_occupant_age_values")
        if summary.get("physics_readiness_summary", {}).get(
            "pulse_candidate_requires_validation",
            {},
        ).get("count", 0):
            actions.append("validate_edr_pulse_candidates")

        return {
            "audit_integrity_passed": not blockers,
            "status": (
                "ready_for_stage_3_with_actions"
                if not blockers
                else "stage_2_blocked"
            ),
            "blockers": blockers,
            "required_next_actions": actions,
            "decision": (
                "Stage 2 has established dataset integrity and "
                "research cohorts. Stage 3 may begin while listed "
                "standardization and validation actions are tracked."
                if not blockers
                else "Resolve Stage-2 blockers before Stage 3."
            ),
        }

    @staticmethod
    def _availability_tier(rate: float) -> str:
        if rate >= 0.80:
            return "high"
        if rate >= 0.50:
            return "moderate"
        if rate > 0.0:
            return "low"
        return "absent"

    def _validate_summary(self, summary: dict[str, Any]) -> None:
        required = {
            "summary_version",
            "registered_case_count",
            "variable_availability_summary",
            "physics_readiness_summary",
            "research_cohorts",
        }
        missing = sorted(required.difference(summary))
        if missing:
            raise ValueError(
                "Pilot summary is missing required fields: "
                + ", ".join(missing)
            )

        version = self._parse_version(summary["summary_version"])
        if version < MINIMUM_SUMMARY_VERSION:
            raise ValueError(
                "Dataset characterization requires pilot summary "
                "version 2.1 or newer."
            )

    @staticmethod
    def _parse_version(value: Any) -> tuple[int, int]:
        try:
            parts = str(value).split(".")
            return int(parts[0]), int(parts[1])
        except (IndexError, TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid pilot summary version: {value!r}"
            ) from error

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Pilot summary not found: {path}")
        with path.open("r", encoding="utf-8") as input_file:
            data = json.load(input_file)
        if not isinstance(data, dict):
            raise ValueError("Pilot summary must contain a JSON object.")
        return data

    @staticmethod
    def _save_json(data: dict[str, Any], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as output_file:
            json.dump(data, output_file, indent=2, ensure_ascii=False)
            output_file.write("\n")
        temporary.replace(path)

    @staticmethod
    def _save_text(text: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as output_file:
            output_file.write(text)
        temporary.replace(path)

    @staticmethod
    def _to_markdown(report: dict[str, Any]) -> str:
        inventory = report["dataset_inventory"]
        completion = report["stage_2_completion"]
        physics = report["physics_readiness"]
        cohorts = report["research_cohorts"]
        age = report["age_standardization"]

        lines = [
            "# CISS Stage 2 Dataset Characterization",
            "",
            f"Generated: {report['created_at']}",
            "",
            "## Completion decision",
            "",
            f"**Status:** `{completion['status']}`",
            "",
            completion["decision"],
            "",
            "## Dataset inventory",
            "",
            f"- Registered cases: {inventory['registered_case_count']}",
            f"- Audit contract passes: {inventory['contract_pass_count']}",
            f"- Audit contract failures: {inventory['contract_failure_count']}",
            f"- Audited variables: {inventory['audited_variable_count']}",
            "",
            "## Physics readiness",
            "",
        ]

        for key in (
            "full_pulse_driven",
            "pulse_candidate_requires_validation",
            "simplified_parameter_based",
            "insufficient",
        ):
            detail = physics.get(key, {})
            lines.append(
                f"- {key}: {detail.get('count', 0)} cases "
                f"{detail.get('case_ids', [])}"
            )

        lines.extend(
            [
                "",
                "## Research cohorts",
                "",
            ]
        )
        for name, detail in cohorts.items():
            lines.append(
                f"- {name}: {detail.get('count', 0)} cases "
                f"{detail.get('case_ids', [])}"
            )

        lines.extend(
            [
                "",
                "## Occupant age",
                "",
                "- Reconciled and requiring Stage 3 standardization: "
                f"{age['reconciled_requires_standardization']['count']}",
                "- Unresolved and not training-ready: "
                f"{age['unresolved_not_training_ready']['count']} "
                f"{age['unresolved_not_training_ready']['case_ids']}",
                "",
                "## Required next actions",
                "",
            ]
        )
        for action in completion["required_next_actions"]:
            lines.append(f"- {action}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
