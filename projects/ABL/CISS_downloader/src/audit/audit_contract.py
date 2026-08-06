"""Validate the internal contract of a completed Stage-2 case audit."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.audit.audit_rules import (
    AUDIT_CONTRACT_VERSION,
    AUDIT_SCHEMA_VERSION,
    ENTITY_REGISTRY_VERSION,
    PHYSICS_READINESS_REGISTRY_VERSION,
    RESEARCH_LABEL_REGISTRY_VERSION,
    STAGE_ELIGIBILITY_REGISTRY_VERSION,
    VARIABLE_REGISTRY_VERSION,
)


class AuditContractValidator:
    """Check registry contracts, counts, references, and stage consistency."""

    REQUIRED_SECTIONS = (
        "entity_registry",
        "variable_registry",
        "research_labels",
        "physics_readiness",
        "stage_eligibility",
    )
    DEPRECATED_SECTIONS = {
        "important_variable_profile": "variable_registry",
        "task_eligibility": "stage_eligibility",
    }
    ALLOWED_STAGE_STATUSES = {
        "eligible",
        "conditionally_eligible",
        "pending_upstream_output",
        "blocked",
    }
    EXPECTED_STAGE_NUMBERS = set(range(3, 10))

    def validate(self, audit: dict[str, Any]) -> dict[str, Any]:
        """Return a non-mutating validation report for one audit document."""

        errors: list[str] = []
        warnings: list[str] = []
        checks: list[dict[str, Any]] = []

        self._check(
            checks,
            errors,
            "audit_schema_version",
            audit.get("schema_version") == AUDIT_SCHEMA_VERSION,
            (
                "Audit schema version is unsupported: "
                f"{audit.get('schema_version')!r}; expected "
                f"{AUDIT_SCHEMA_VERSION!r}."
            ),
        )

        for section in self.REQUIRED_SECTIONS:
            self._check(
                checks,
                errors,
                f"required_section:{section}",
                isinstance(audit.get(section), dict),
                f"Required audit section is missing or invalid: {section}.",
            )

        if errors:
            return self._report(audit, checks, errors, warnings)

        entity_registry = audit["entity_registry"]
        variable_registry = audit["variable_registry"]
        research_labels = audit["research_labels"]
        physics_readiness = audit["physics_readiness"]
        stage_eligibility = audit["stage_eligibility"]

        expected_versions = {
            "entity_registry": ENTITY_REGISTRY_VERSION,
            "variable_registry": VARIABLE_REGISTRY_VERSION,
            "research_labels": RESEARCH_LABEL_REGISTRY_VERSION,
            "physics_readiness": PHYSICS_READINESS_REGISTRY_VERSION,
            "stage_eligibility": STAGE_ELIGIBILITY_REGISTRY_VERSION,
        }
        registries = {
            "entity_registry": entity_registry,
            "variable_registry": variable_registry,
            "research_labels": research_labels,
            "physics_readiness": physics_readiness,
            "stage_eligibility": stage_eligibility,
        }
        for name, expected in expected_versions.items():
            actual = registries[name].get("registry_version")
            self._check(
                checks,
                errors,
                f"registry_version:{name}",
                actual == expected,
                (
                    f"{name} version {actual!r} is unsupported; "
                    f"expected {expected!r}."
                ),
            )

        case_id = self._case_id(audit.get("case_id"))
        self._check(
            checks,
            errors,
            "case_id",
            case_id is not None,
            "Audit case_id must be a positive integer.",
        )
        for name, registry in registries.items():
            registry_case = self._case_id(registry.get("case_id"))
            if registry_case is not None:
                self._check(
                    checks,
                    errors,
                    f"case_id_consistency:{name}",
                    registry_case == case_id,
                    f"{name} case_id does not match the audit case_id.",
                )

        entities = self._dict_records(entity_registry.get("entities"))
        relationships = self._dict_records(entity_registry.get("relationships"))
        entity_ids = [item.get("entity_id") for item in entities]
        entity_id_set = {item for item in entity_ids if item}
        self._unique_check(
            checks, errors, "entity_ids_unique", entity_ids, "entity_id"
        )
        self._count_check(
            checks,
            errors,
            "entity_count",
            entity_registry.get("summary", {}).get("entity_count"),
            len(entities),
        )
        self._count_check(
            checks,
            errors,
            "relationship_count",
            entity_registry.get("summary", {}).get("relationship_count"),
            len(relationships),
        )
        for index, relationship in enumerate(relationships):
            for field in ("source_entity_id", "target_entity_id"):
                reference = relationship.get(field)
                if reference not in entity_id_set:
                    errors.append(
                        f"Relationship {index} has unresolved {field}: "
                        f"{reference!r}."
                    )

        variables = variable_registry.get("variables", {})
        actual_variable_count = (
            len(variables) if isinstance(variables, (dict, list)) else 0
        )
        self._count_check(
            checks,
            errors,
            "variable_count",
            variable_registry.get("variable_count"),
            actual_variable_count,
        )

        labels = self._dict_records(research_labels.get("labels"))
        label_ids = [item.get("label_id") for item in labels]
        label_id_set = {item for item in label_ids if item}
        self._unique_check(
            checks, errors, "label_ids_unique", label_ids, "label_id"
        )
        self._count_check(
            checks,
            errors,
            "research_label_count",
            research_labels.get("summary", {}).get("total_label_records"),
            len(labels),
        )
        usable_count = sum(
            item.get("training_usable") is True for item in labels
        )
        self._count_check(
            checks,
            errors,
            "training_usable_label_count",
            research_labels.get("summary", {}).get(
                "training_usable_label_count"
            ),
            usable_count,
        )
        for label in labels:
            if label.get("entity_id") not in entity_id_set:
                errors.append(
                    f"Label {label.get('label_id')!r} references an unknown "
                    f"entity: {label.get('entity_id')!r}."
                )

        physics_pairs = self._dict_records(
            physics_readiness.get("occupant_vehicle_pairs")
        )
        self._count_check(
            checks,
            errors,
            "physics_pair_count",
            physics_readiness.get("summary", {}).get("pair_count"),
            len(physics_pairs),
        )
        for index, pair in enumerate(physics_pairs):
            self._validate_pair_entities(
                errors, pair, index, entity_id_set, "Physics readiness"
            )
            mechanics = pair.get("inputs", {}).get("crash_mechanics", {})
            for input_name in ("delta_v", "pdof"):
                label_id = mechanics.get(input_name, {}).get("label_id")
                if label_id and label_id not in label_id_set:
                    errors.append(
                        f"Physics pair {index} references unknown {input_name} "
                        f"label_id: {label_id!r}."
                    )

        stages = stage_eligibility.get("stages", {})
        if not isinstance(stages, dict):
            stages = {}
        stage_numbers = {
            item.get("stage_number")
            for item in stages.values()
            if isinstance(item, dict)
        }
        self._check(
            checks,
            errors,
            "stage_numbers",
            stage_numbers == self.EXPECTED_STAGE_NUMBERS,
            (
                "Stage eligibility must contain exactly Stages 3 through 9; "
                f"found {sorted(x for x in stage_numbers if x is not None)}."
            ),
        )
        self._count_check(
            checks,
            errors,
            "stage_count",
            stage_eligibility.get("summary", {}).get("stage_count"),
            len(stages),
        )
        actual_status_counts = Counter()
        for name, stage in stages.items():
            if not isinstance(stage, dict):
                errors.append(f"Stage record {name!r} must be an object.")
                continue
            status = stage.get("status")
            actual_status_counts[status] += 1
            if status not in self.ALLOWED_STAGE_STATUSES:
                errors.append(f"Stage {name!r} has invalid status: {status!r}.")
            eligible = stage.get("eligible") is True
            conditional = stage.get("conditionally_eligible") is True
            if eligible and conditional:
                errors.append(
                    f"Stage {name!r} cannot be both eligible and conditional."
                )
            if eligible and status != "eligible":
                errors.append(
                    f"Stage {name!r} is eligible but status is {status!r}."
                )
            if eligible and stage.get("blocking_reasons"):
                errors.append(
                    f"Stage {name!r} is eligible but still has blockers."
                )
            if conditional and status not in {
                "conditionally_eligible",
                "pending_upstream_output",
            }:
                errors.append(
                    f"Stage {name!r} is conditional but status is {status!r}."
                )

        recorded_status_counts = stage_eligibility.get("summary", {}).get(
            "status_counts", {}
        )
        self._check(
            checks,
            errors,
            "stage_status_counts",
            dict(sorted(actual_status_counts.items()))
            == dict(sorted(recorded_status_counts.items())),
            "Stage status summary does not match the stage records.",
        )

        stage_pairs = self._dict_records(
            stage_eligibility.get("occupant_vehicle_pairs")
        )
        self._count_check(
            checks,
            errors,
            "stage_pair_count",
            stage_eligibility.get("summary", {}).get(
                "pair_assessment_count"
            ),
            len(stage_pairs),
        )
        pair_ids = [item.get("pair_id") for item in stage_pairs]
        self._unique_check(
            checks, errors, "stage_pair_ids_unique", pair_ids, "pair_id"
        )
        for index, pair in enumerate(stage_pairs):
            self._validate_pair_entities(
                errors, pair, index, entity_id_set, "Stage eligibility"
            )
            expected_pair_id = (
                f"{pair.get('vehicle_entity_id')}::"
                f"{pair.get('occupant_entity_id')}"
            )
            if pair.get("pair_id") != expected_pair_id:
                errors.append(
                    f"Stage pair {index} violates the pair_id contract."
                )

        return self._report(audit, checks, errors, warnings)

    @classmethod
    def _report(
        cls,
        audit: dict[str, Any],
        checks: list[dict[str, Any]],
        errors: list[str],
        warnings: list[str],
    ) -> dict[str, Any]:
        deprecated = [
            {
                "section": section,
                "replacement": replacement,
                "present": section in audit,
                "removal_policy": "retain_until_major_schema_migration",
            }
            for section, replacement in cls.DEPRECATED_SECTIONS.items()
        ]
        passed_checks = sum(item.get("passed") is True for item in checks)
        failed_checks = len(errors)
        return {
            "contract_version": AUDIT_CONTRACT_VERSION,
            "passed": not errors,
            "check_count": passed_checks + failed_checks,
            "passed_check_count": passed_checks,
            "failed_check_count": failed_checks,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "deprecated_sections": deprecated,
            "checks": checks,
        }

    @staticmethod
    def _check(
        checks: list[dict[str, Any]],
        errors: list[str],
        name: str,
        passed: bool,
        message: str,
    ) -> None:
        checks.append({"name": name, "passed": bool(passed)})
        if not passed:
            errors.append(message)

    @classmethod
    def _count_check(
        cls,
        checks: list[dict[str, Any]],
        errors: list[str],
        name: str,
        recorded: Any,
        actual: int,
    ) -> None:
        cls._check(
            checks,
            errors,
            name,
            recorded == actual,
            f"{name} mismatch: recorded={recorded!r}, actual={actual}.",
        )

    @classmethod
    def _unique_check(
        cls,
        checks: list[dict[str, Any]],
        errors: list[str],
        name: str,
        values: list[Any],
        field: str,
    ) -> None:
        nonempty = [value for value in values if value]
        passed = len(nonempty) == len(values) == len(set(nonempty))
        cls._check(
            checks,
            errors,
            name,
            passed,
            f"{field} values must be present and unique.",
        )

    @staticmethod
    def _validate_pair_entities(
        errors: list[str],
        pair: dict[str, Any],
        index: int,
        entity_ids: set[Any],
        section: str,
    ) -> None:
        for field in ("occupant_entity_id", "vehicle_entity_id"):
            if pair.get(field) not in entity_ids:
                errors.append(
                    f"{section} pair {index} references unknown {field}: "
                    f"{pair.get(field)!r}."
                )

    @staticmethod
    def _dict_records(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _case_id(value: Any) -> int | None:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if result > 0 else None
