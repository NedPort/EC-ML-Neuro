"""Build downstream-stage eligibility metadata for one audited CISS case."""

from __future__ import annotations

from collections import Counter
from typing import Any

from src.audit.audit_rules import STAGE_ELIGIBILITY_REGISTRY_VERSION


class StageEligibilityBuilder:
    """Translate Stage-2 metadata into conservative downstream decisions.

    Eligibility means that the currently audited evidence satisfies a stage's
    entry requirements. Conditional eligibility is reported separately when a
    stage may become eligible after validation, standardization, uncertainty
    modeling, or completion of an upstream stage.
    """

    def build(
        self,
        case_id: int,
        entity_registry: dict[str, Any],
        variable_registry: dict[str, Any],
        research_labels: dict[str, Any],
        physics_readiness: dict[str, Any],
    ) -> dict[str, Any]:
        """Return case-level and pair-level eligibility for Stages 3--9."""

        case_id = int(case_id)
        pairs = physics_readiness.get("occupant_vehicle_pairs", [])
        pair_assessments = [self._assess_pair(pair) for pair in pairs]

        entity_unresolved = self._summary_count(
            entity_registry, "unresolved_reference_count"
        )
        label_unresolved = self._summary_count(
            research_labels, "unresolved_label_count"
        )
        physics_unresolved = self._summary_count(
            physics_readiness, "unresolved_entity_count"
        )

        variables = variable_registry.get("variables", {})
        variable_count = int(variable_registry.get("variable_count", 0) or 0)
        if variable_count == 0 and isinstance(variables, (dict, list)):
            variable_count = len(variables)
        entity_count = self._summary_count(entity_registry, "entity_count")
        if entity_count == 0:
            entities = entity_registry.get("entities", [])
            entity_count = len(entities) if isinstance(entities, list) else 0

        usable_labels = [
            label
            for label in research_labels.get("labels", [])
            if isinstance(label, dict) and label.get("training_usable") is True
        ]
        usable_final_labels = [
            label
            for label in usable_labels
            if label.get("training_role") == "final_label"
        ]
        usable_intermediate_labels = [
            label
            for label in usable_labels
            if label.get("training_role") == "intermediate_label"
        ]

        integrity_blockers = []
        if entity_unresolved:
            integrity_blockers.append("unresolved_entity_references")
        if label_unresolved:
            integrity_blockers.append("unresolved_research_labels")
        if physics_unresolved:
            integrity_blockers.append("unresolved_physics_entities")
        if not entity_count:
            integrity_blockers.append("entity_registry_empty")
        if not variable_count:
            integrity_blockers.append("variable_registry_empty")

        stage3_ready = not integrity_blockers
        stage4_ready_pairs = self._pair_ids(pair_assessments, 4, "eligible")
        stage4_conditional_pairs = self._pair_ids(
            pair_assessments, 4, "conditionally_eligible"
        )
        stage5_ready_pairs = self._pair_ids(pair_assessments, 5, "eligible")
        stage5_conditional_pairs = self._pair_ids(
            pair_assessments, 5, "conditionally_eligible"
        )

        stages: dict[str, dict[str, Any]] = {}
        stages["stage_3_data_standardization"] = self._stage(
            stage=3,
            eligible=stage3_ready,
            conditional=False,
            status="eligible" if stage3_ready else "blocked",
            blockers=integrity_blockers,
            prerequisites=[],
            evidence={
                "entity_count": entity_count,
                "variable_count": variable_count,
                "unresolved_entity_references": entity_unresolved,
                "unresolved_research_labels": label_unresolved,
            },
            next_actions=(
                ["standardize_units_codes_and_missing_value_semantics"]
                if stage3_ready
                else ["resolve_stage2_integrity_blockers"]
            ),
        )

        stage4_eligible = bool(stage4_ready_pairs) and stage3_ready
        stage4_conditional = bool(stage4_conditional_pairs) and stage3_ready
        stage4_blockers = []
        if not pairs:
            stage4_blockers.append("no_resolved_occupant_vehicle_pairs")
        if not stage3_ready:
            stage4_blockers.append("stage_3_not_eligible")
        if pairs and not stage4_ready_pairs and not stage4_conditional_pairs:
            stage4_blockers.append("delta_v_or_pdof_unavailable")
        stages["stage_4_physics_parameter_construction"] = self._stage(
            stage=4,
            eligible=stage4_eligible,
            conditional=stage4_conditional,
            status=self._status(stage4_eligible, stage4_conditional),
            blockers=stage4_blockers,
            prerequisites=["stage_3_data_standardization"],
            evidence={
                "pair_count": len(pairs),
                "eligible_pair_ids": stage4_ready_pairs,
                "conditionally_eligible_pair_ids": stage4_conditional_pairs,
                "usable_intermediate_label_count": len(
                    usable_intermediate_labels
                ),
            },
            next_actions=["construct_pair_specific_physics_parameters"],
        )

        stage5_eligible = bool(stage5_ready_pairs) and stage4_eligible
        stage5_conditional = (
            bool(stage5_conditional_pairs)
            and (stage4_eligible or stage4_conditional)
        )
        stage5_blockers = self._collect_pair_blockers(pair_assessments, 5)
        if not pairs:
            stage5_blockers.append("no_resolved_occupant_vehicle_pairs")
        if not stage4_eligible and not stage4_conditional:
            stage5_blockers.append("stage_4_not_eligible")
        stages["stage_5_physics_based_occupant_simulation"] = self._stage(
            stage=5,
            eligible=stage5_eligible,
            conditional=stage5_conditional,
            status=self._status(stage5_eligible, stage5_conditional),
            blockers=stage5_blockers,
            prerequisites=["stage_4_physics_parameter_construction"],
            evidence={
                "execution_ready_pair_ids": stage5_ready_pairs,
                "conditionally_eligible_pair_ids": stage5_conditional_pairs,
                "simulation_executed": bool(
                    physics_readiness.get("policy", {}).get(
                        "simulation_executed", False
                    )
                ),
            },
            next_actions=[
                "validate_or_construct_crash_pulse",
                "define_parameter_distributions",
                "propagate_parameter_uncertainty",
            ],
        )

        # Stages 6 and 7 require outputs that Stage 2 intentionally does not
        # create. They may be conditionally reachable, but are not executable.
        stage6_conditional = stage5_eligible or stage5_conditional
        stages["stage_6_latent_biomechanical_variables"] = self._stage(
            stage=6,
            eligible=False,
            conditional=stage6_conditional,
            status="pending_upstream_output" if stage6_conditional else "blocked",
            blockers=["stage_5_simulation_outputs_not_generated"],
            prerequisites=["stage_5_physics_based_occupant_simulation"],
            evidence={"latent_biomechanical_records_available": False},
            next_actions=["run_validated_occupant_model_and_store_time_histories"],
        )

        stages["stage_7_injury_criterion_computation"] = self._stage(
            stage=7,
            eligible=False,
            conditional=stage6_conditional,
            status="pending_upstream_output" if stage6_conditional else "blocked",
            blockers=["stage_6_latent_variables_not_generated"],
            prerequisites=["stage_6_latent_biomechanical_variables"],
            evidence={"injury_criterion_records_available": False},
            next_actions=[
                "select_body_region_criteria_matching_available_signals"
            ],
        )

        stage8_blockers = ["stage_7_injury_criteria_not_generated"]
        if not usable_final_labels:
            stage8_blockers.append("reliable_final_injury_labels_unavailable")
        stage8_conditional = bool(usable_final_labels) and stage6_conditional
        stages["stage_8_physics_informed_machine_learning"] = self._stage(
            stage=8,
            eligible=False,
            conditional=stage8_conditional,
            status="pending_upstream_output" if stage8_conditional else "blocked",
            blockers=stage8_blockers,
            prerequisites=[
                "stage_7_injury_criterion_computation",
                "reliable_final_injury_labels",
                "cohort_level_dataset",
            ],
            evidence={
                "usable_final_label_count": len(usable_final_labels),
                "usable_intermediate_label_count": len(
                    usable_intermediate_labels
                ),
            },
            next_actions=[
                "assemble_leakage_safe_case_occupant_training_table",
                "define_grouped_train_validation_test_splits",
            ],
        )

        stages["stage_9_model_validation"] = self._stage(
            stage=9,
            eligible=False,
            conditional=stage8_conditional,
            status="pending_upstream_output" if stage8_conditional else "blocked",
            blockers=[
                "trained_stage_8_model_unavailable",
                "held_out_validation_cohort_unavailable",
            ],
            prerequisites=["stage_8_physics_informed_machine_learning"],
            evidence={"validation_executed": False},
            next_actions=[
                "validate_discrimination_calibration_and_uncertainty"
            ],
        )

        status_counts = Counter(item["status"] for item in stages.values())
        return {
            "registry_version": STAGE_ELIGIBILITY_REGISTRY_VERSION,
            "case_id": case_id,
            "assessment_scope": "case_and_vehicle_occupant_pair",
            "policy": {
                "eligibility_is_not_execution": True,
                "conditional_eligibility_is_not_ready": True,
                "downstream_outputs_are_not_inferred": True,
                "single_arbitrary_imputation_allowed": False,
            },
            "summary": {
                "stage_count": len(stages),
                "status_counts": dict(sorted(status_counts.items())),
                "highest_currently_eligible_stage": self._highest_eligible(stages),
                "pair_assessment_count": len(pair_assessments),
            },
            "stages": stages,
            "occupant_vehicle_pairs": pair_assessments,
        }

    def _assess_pair(self, pair: dict[str, Any]) -> dict[str, Any]:
        pair_id = self._pair_id(pair)
        capabilities = pair.get("capabilities", {})
        blockers = list(pair.get("blocking_reasons", []))

        stage4_ready = bool(capabilities.get("stage4_parameter_construction"))
        stage4 = {
            "eligible": stage4_ready,
            "conditionally_eligible": False,
            "status": "eligible" if stage4_ready else "blocked",
            "blocking_reasons": (
                []
                if stage4_ready
                else sorted(
                    reason
                    for reason in blockers
                    if reason
                    in {"usable_delta_v_unavailable", "usable_pdof_unavailable"}
                )
            ),
        }

        pulse_ready = bool(capabilities.get("pulse_based_occupant_model"))
        analytical_ready = bool(capabilities.get("simplified_occupant_model"))
        stage5_conditional = analytical_ready and not pulse_ready
        simulation_blockers = sorted(
            reason
            for reason in blockers
            if reason.startswith("crash_pulse_")
            or "distribution" in reason
            or "external_model" in reason
        )
        stage5 = {
            "eligible": pulse_ready,
            "conditionally_eligible": stage5_conditional,
            "status": self._status(pulse_ready, stage5_conditional),
            "supported_model_path": (
                "pulse_based"
                if pulse_ready
                else "simplified_analytical_with_uncertainty"
                if stage5_conditional
                else None
            ),
            "blocking_reasons": simulation_blockers,
        }

        return {
            "pair_id": pair_id,
            "occupant_entity_id": pair.get("occupant_entity_id"),
            "vehicle_entity_id": pair.get("vehicle_entity_id"),
            "stage_4": stage4,
            "stage_5": stage5,
        }

    @staticmethod
    def _stage(
        stage: int,
        eligible: bool,
        conditional: bool,
        status: str,
        blockers: list[str],
        prerequisites: list[str],
        evidence: dict[str, Any],
        next_actions: list[str],
    ) -> dict[str, Any]:
        return {
            "stage_number": stage,
            "eligible": bool(eligible),
            "conditionally_eligible": bool(conditional),
            "status": status,
            "blocking_reasons": sorted(set(blockers)),
            "prerequisites": prerequisites,
            "evidence": evidence,
            "next_actions": next_actions,
        }

    @staticmethod
    def _status(eligible: bool, conditional: bool) -> str:
        if eligible:
            return "eligible"
        if conditional:
            return "conditionally_eligible"
        return "blocked"

    @staticmethod
    def _summary_count(registry: dict[str, Any], key: str) -> int:
        value = registry.get("summary", {}).get(key, 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _pair_id(pair: dict[str, Any]) -> str:
        occupant_id = pair.get("occupant_entity_id") or "UNKNOWN-OCCUPANT"
        vehicle_id = pair.get("vehicle_entity_id") or "UNKNOWN-VEHICLE"
        return f"{vehicle_id}::{occupant_id}"

    @staticmethod
    def _pair_ids(
        pair_assessments: list[dict[str, Any]], stage: int, field: str
    ) -> list[str]:
        key = f"stage_{stage}"
        return [
            item["pair_id"]
            for item in pair_assessments
            if item.get(key, {}).get(field) is True
        ]

    @staticmethod
    def _collect_pair_blockers(
        pair_assessments: list[dict[str, Any]], stage: int
    ) -> list[str]:
        key = f"stage_{stage}"
        return sorted(
            {
                reason
                for item in pair_assessments
                for reason in item.get(key, {}).get("blocking_reasons", [])
            }
        )

    @staticmethod
    def _highest_eligible(stages: dict[str, dict[str, Any]]) -> int | None:
        eligible = [
            item["stage_number"]
            for item in stages.values()
            if item.get("eligible") is True
        ]
        return max(eligible) if eligible else None
