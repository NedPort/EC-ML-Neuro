"""Run resumable sequential acquisition and auditing for a CISS pilot cohort."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Callable


PILOT_MANIFEST_VERSION = "1.0"
PILOT_SUMMARY_VERSION = "1.0"


class PilotRunner:
    """Process a manifest of CISS cases sequentially and resumably."""

    def __init__(
        self,
        data_root: str | Path = "data",
        manifest_path: str | Path | None = None,
        api_factory: Callable[..., Any] | None = None,
        processor_factory: Callable[..., Any] | None = None,
        auditor_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path is not None
            else self.data_root / "manifests" / "pilot_cases.json"
        )
        self.summary_path = (
            self.data_root
            / "processed"
            / "pilot"
            / "pilot_audit_summary.json"
        )
        self._api_factory = api_factory
        self._processor_factory = processor_factory
        self._auditor_factory = auditor_factory

    def initialize_manifest(
        self,
        case_ids: list[int] | None = None,
        target_case_count: int = 20,
    ) -> dict[str, Any]:
        """Create the pilot manifest if it does not already exist."""

        if self.manifest_path.exists():
            return self.load_manifest()

        normalized_ids = self._normalize_case_ids(case_ids or [6028, 7009])
        now = self._utc_now()
        manifest = {
            "schema_version": PILOT_MANIFEST_VERSION,
            "pilot_id": "ciss_stage2_pilot_v1",
            "created_at": now,
            "updated_at": now,
            "target_case_count": int(target_case_count),
            "processing_policy": {
                "sequential_processing": True,
                "continue_after_case_failure": True,
                "cleanup_requires_successful_contract": True,
                "temporary_cleanup_default": False,
            },
            "cases": [
                self._new_case_record(case_id, "development_case")
                for case_id in normalized_ids
            ],
        }
        self._validate_manifest(manifest)
        self._save_json(manifest, self.manifest_path)
        return manifest

    def add_cases(self, case_ids: list[int]) -> dict[str, Any]:
        """Add unique case IDs without changing existing case state."""

        manifest = self.initialize_manifest()
        existing = {int(item["case_id"]) for item in manifest["cases"]}
        for case_id in self._normalize_case_ids(case_ids):
            if case_id not in existing:
                manifest["cases"].append(
                    self._new_case_record(case_id, "pilot_candidate")
                )
                existing.add(case_id)
        manifest["updated_at"] = self._utc_now()
        self._validate_manifest(manifest)
        self._save_json(manifest, self.manifest_path)
        return manifest

    def load_manifest(self) -> dict[str, Any]:
        """Load and validate the current pilot manifest."""

        if not self.manifest_path.exists():
            raise FileNotFoundError(
                f"Pilot manifest does not exist: {self.manifest_path}"
            )
        with self.manifest_path.open("r", encoding="utf-8") as input_file:
            manifest = json.load(input_file)
        self._validate_manifest(manifest)
        return manifest

    def run(
        self,
        headless: bool = False,
        cleanup_temp: bool = False,
        retry_failed: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Acquire and audit selected cases, saving progress after every case."""

        manifest = self.initialize_manifest()
        candidates = [
            item
            for item in manifest["cases"]
            if self._should_process(item, retry_failed=retry_failed)
        ]
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be a positive integer")
            candidates = candidates[:limit]

        if not candidates:
            summary = self.build_summary(manifest)
            self._save_json(summary, self.summary_path)
            print("No pending pilot cases were found.")
            return summary

        api_factory, processor_factory, auditor_factory = self._factories()
        api = api_factory(headless=headless)
        try:
            processor = processor_factory(api=api, data_root=self.data_root)
            auditor = auditor_factory(data_root=self.data_root)

            for index, case_record in enumerate(candidates, start=1):
                case_id = int(case_record["case_id"])
                print()
                print(
                    f"Pilot case {index}/{len(candidates)}: CISS {case_id}"
                )
                self._mark_started(case_record)
                self._save_progress(manifest)

                try:
                    acquisition = processor.process_case(case_id)
                    case_record["acquisition_status"] = acquisition.get(
                        "status", "completed"
                    )
                    case_record["acquisition_validation_passed"] = bool(
                        acquisition.get("validation", {}).get("passed", False)
                    )

                    audit = auditor.audit_case(case_id)
                    self._apply_audit_result(case_record, audit)

                    if cleanup_temp:
                        self._cleanup_case_temp(case_record, audit)
                except Exception as error:  # isolate failures by case
                    case_record["processing_status"] = "failed"
                    case_record["completed_at"] = self._utc_now()
                    case_record["last_error"] = {
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                    print(
                        f"Pilot case {case_id} failed: "
                        f"{type(error).__name__}: {error}"
                    )
                finally:
                    self._save_progress(manifest)
        finally:
            api.close()

        summary = self.build_summary(manifest)
        self._save_json(summary, self.summary_path)
        self._print_summary(summary)
        return summary

    def build_summary(
        self, manifest: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build a dataset-level summary from current pilot case records."""

        manifest = manifest or self.load_manifest()
        records = manifest["cases"]
        processing_counts = Counter(
            item.get("processing_status", "unknown") for item in records
        )
        warning_frequencies = Counter(
            warning
            for item in records
            for warning in item.get("audit_warnings", [])
        )
        stage_status_counts: dict[str, Counter[str]] = {}
        for item in records:
            for stage, status in item.get("stage_statuses", {}).items():
                stage_status_counts.setdefault(stage, Counter())[status] += 1

        contract_failures = [
            {
                "case_id": item["case_id"],
                "errors": item.get("contract_errors", []),
            }
            for item in records
            if item.get("contract_passed") is False
        ]
        processing_failures = [
            {
                "case_id": item["case_id"],
                "error": item.get("last_error"),
            }
            for item in records
            if item.get("processing_status") == "failed"
        ]
        profile_counts = Counter(
            reason
            for item in records
            for reason in item.get("observed_profile", [])
        )

        return {
            "summary_version": PILOT_SUMMARY_VERSION,
            "pilot_id": manifest["pilot_id"],
            "created_at": self._utc_now(),
            "target_case_count": manifest["target_case_count"],
            "registered_case_count": len(records),
            "processing_status_counts": dict(sorted(processing_counts.items())),
            "contract_pass_count": sum(
                item.get("contract_passed") is True for item in records
            ),
            "contract_failure_count": len(contract_failures),
            "contract_failures": contract_failures,
            "processing_failures": processing_failures,
            "warning_frequencies": dict(
                sorted(warning_frequencies.items(), key=lambda pair: (-pair[1], pair[0]))
            ),
            "stage_status_counts": {
                stage: dict(sorted(counts.items()))
                for stage, counts in sorted(stage_status_counts.items())
            },
            "observed_profile_counts": dict(sorted(profile_counts.items())),
            "cases": [
                {
                    "case_id": item["case_id"],
                    "processing_status": item.get("processing_status"),
                    "contract_passed": item.get("contract_passed"),
                    "observed_profile": item.get("observed_profile", []),
                    "last_error": item.get("last_error"),
                }
                for item in records
            ],
        }

    def save_summary(self) -> dict[str, Any]:
        """Rebuild and persist the pilot summary without processing cases."""

        summary = self.build_summary()
        self._save_json(summary, self.summary_path)
        return summary

    def _apply_audit_result(
        self, case_record: dict[str, Any], audit: dict[str, Any]
    ) -> None:
        contract = audit.get("audit_contract", {})
        stages = audit.get("stage_eligibility", {}).get("stages", {})
        case_record.update(
            {
                "processing_status": (
                    "completed"
                    if contract.get("passed") is True
                    else "contract_failed"
                ),
                "audit_status": audit.get("status"),
                "audit_schema_version": audit.get("schema_version"),
                "contract_passed": contract.get("passed"),
                "contract_error_count": contract.get("error_count", 0),
                "contract_errors": contract.get("errors", []),
                "audit_warning_count": audit.get("audit_summary", {}).get(
                    "warning_count", 0
                ),
                "audit_warnings": audit.get("audit_summary", {}).get(
                    "warnings", []
                ),
                "stage_statuses": {
                    name: stage.get("status")
                    for name, stage in stages.items()
                    if isinstance(stage, dict)
                },
                "observed_profile": self._observed_profile(audit),
                "completed_at": self._utc_now(),
                "last_error": None,
            }
        )

    @staticmethod
    def _observed_profile(audit: dict[str, Any]) -> list[str]:
        profile: set[str] = set()
        entities = audit.get("entity_registry", {}).get("summary", {}).get(
            "entities_by_type", {}
        )
        vehicle_count = int(entities.get("vehicle", 0) or 0)
        occupant_count = int(entities.get("occupant", 0) or 0)
        profile.add("multi_vehicle" if vehicle_count > 1 else "single_vehicle")
        profile.add("multiple_occupants" if occupant_count > 1 else "single_occupant")

        edr = audit.get("edr_quality_audit", {})
        profile.add(
            "edr_pulse_candidate"
            if edr.get("pulse_candidate_available")
            else "no_edr_pulse_candidate"
        )
        labels = audit.get("research_labels", {}).get("summary", {})
        usable_final = labels.get("training_usable_by_role", {}).get(
            "final_label", 0
        )
        profile.add(
            "reliable_final_labels"
            if usable_final
            else "no_reliable_final_labels"
        )
        return sorted(profile)

    def _cleanup_case_temp(
        self, case_record: dict[str, Any], audit: dict[str, Any]
    ) -> None:
        if audit.get("audit_contract", {}).get("passed") is not True:
            case_record["temporary_cleanup_status"] = (
                "skipped_contract_not_passed"
            )
            return
        case_id = int(case_record["case_id"])
        temporary_directory = self.data_root / "temp" / str(case_id)
        expected_parent = (self.data_root / "temp").resolve()
        resolved_target = temporary_directory.resolve()
        if resolved_target.parent != expected_parent:
            raise RuntimeError(
                f"Refusing unsafe temporary cleanup target: {resolved_target}"
            )
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)
            case_record["temporary_cleanup_status"] = "removed"
        else:
            case_record["temporary_cleanup_status"] = "already_absent"

    def _save_progress(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = self._utc_now()
        self._validate_manifest(manifest)
        self._save_json(manifest, self.manifest_path)
        summary = self.build_summary(manifest)
        self._save_json(summary, self.summary_path)

    @staticmethod
    def _should_process(
        record: dict[str, Any], retry_failed: bool
    ) -> bool:
        if record.get("selection_status") != "selected":
            return False
        status = record.get("processing_status", "pending")
        if status in {"completed", "contract_failed"}:
            return False
        if status == "failed":
            return retry_failed
        return True

    @staticmethod
    def _mark_started(record: dict[str, Any]) -> None:
        record["processing_status"] = "in_progress"
        record["attempt_count"] = int(record.get("attempt_count", 0)) + 1
        record["last_attempt_at"] = PilotRunner._utc_now()
        record["last_error"] = None

    @staticmethod
    def _new_case_record(case_id: int, selection_reason: str) -> dict[str, Any]:
        return {
            "case_id": int(case_id),
            "selection_status": "selected",
            "selection_reasons": [selection_reason],
            "processing_status": "pending",
            "acquisition_status": "pending",
            "audit_status": "pending",
            "attempt_count": 0,
        }

    @staticmethod
    def _normalize_case_ids(case_ids: list[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for value in case_ids:
            case_id = int(value)
            if case_id <= 0:
                raise ValueError("Every CISS case ID must be positive.")
            if case_id not in seen:
                normalized.append(case_id)
                seen.add(case_id)
        return normalized

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        if manifest.get("schema_version") != PILOT_MANIFEST_VERSION:
            raise ValueError("Unsupported pilot manifest schema version.")
        if not isinstance(manifest.get("cases"), list):
            raise ValueError("Pilot manifest cases must be a list.")
        case_ids = [int(item["case_id"]) for item in manifest["cases"]]
        if any(case_id <= 0 for case_id in case_ids):
            raise ValueError("Pilot manifest contains a non-positive case ID.")
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Pilot manifest contains duplicate case IDs.")
        if int(manifest.get("target_case_count", 0)) < 1:
            raise ValueError("target_case_count must be positive.")

    def _factories(
        self,
    ) -> tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any]]:
        if all(
            factory is not None
            for factory in (
                self._api_factory,
                self._processor_factory,
                self._auditor_factory,
            )
        ):
            return (
                self._api_factory,
                self._processor_factory,
                self._auditor_factory,
            )
        from src.api.client import CISSApi
        from src.audit.case_auditor import CaseAuditor
        from src.pipeline.case_processor import CaseProcessor

        return (
            self._api_factory or CISSApi,
            self._processor_factory or CaseProcessor,
            self._auditor_factory or CaseAuditor,
        )

    @staticmethod
    def _save_json(data: dict[str, Any], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as output_file:
            json.dump(data, output_file, indent=2, ensure_ascii=False)
            output_file.write("\n")
        temporary_path.replace(output_path)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _print_summary(summary: dict[str, Any]) -> None:
        print()
        print("Pilot processing summary")
        print("=" * 50)
        print(f"Registered cases: {summary['registered_case_count']}")
        print(f"Contract passes: {summary['contract_pass_count']}")
        print(f"Contract failures: {summary['contract_failure_count']}")
        print(
            "Processing statuses: "
            f"{summary['processing_status_counts']}"
        )
