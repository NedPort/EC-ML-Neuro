from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Model1FeatureRegistryPaths:
    csv: Path


class Model1FeatureRegistryBuilder:
    """
    Creates a transparent feature-decision registry for the Model 1 flat table.

    This does not delete or alter model1_delta_v_pdof_candidate_flat.parquet.
    It documents what each column means for Model 1 Delta-V/PDOF prediction.
    """

    VERSION = "1.0"

    TARGET_COLUMNS = {
        "total_delta_v_kmh",
        "longitudinal_delta_v_kmh",
        "lateral_delta_v_kmh",
        "pdof_degrees",
    }

    TARGET_PROVENANCE_COLUMNS = {
        "delta_v_unit",
        "delta_v_source",
        "delta_v_source_priority",
        "delta_v_internal_consistency",
        "delta_v_training_usable",
        "delta_v_exclusion_reason",
        "delta_v_scope",
        "delta_v_event_linked",
        "pdof_unit",
        "pdof_source_variable",
        "pdof_training_usable",
        "pdof_exclusion_reason",
        "pdof_event_linked",
    }

    DIRECT_RECONSTRUCTION_COLUMNS = {
        "excel_cdc_total_delta_v_raw",
        "excel_cdc_longitudinal_delta_v_raw",
        "excel_cdc_lateral_delta_v_raw",
        "excel_cdc_heading_angle",
    }

    IDENTIFIER_COLUMNS = {
        "case_id",
        "vehicle_id",
        "vehicle_number",
        "event_number",
        "vehicle_event_id",
        "case_number",
        "case_number_raw",
        "metadata_case_id",
        "metadata_case_number",
        "excel_case_id",
        "metadata_vin_masked",
        "psu",
        "domain",
        "metadata_psu",
        "metadata_domain",
    }

    PATH_OR_VERSION_COLUMNS = {
        "source_audit_file",
        "metadata_source_path",
        "excel_source_path",
        "audit_source_path",
        "asset_source_path",
        "tree_source_path",
        "standardization_version",
        "evidence_enrichment_version",
        "vehicle_event_index_version",
        "case_index_version",
        "vehicle_index_version",
        "case_vehicle_reconciliation_version",
        "model1_candidate_flat_version",
        "source_version",
    }

    QUALITY_OR_AUDIT_COLUMNS = {
        "audit_status",
        "audit_case_status",
        "audit_passed",
        "audit_warning_count",
        "audit_error_count",
        "cross_source_contradiction_count",
        "audit_cross_source_contradiction_count",
        "audit_cross_source_contextual_difference_count",
        "metadata_available",
        "metadata_read_error",
        "excel_available",
        "excel_read_error",
        "tree_available",
        "package_status",
        "package_validation_passed",
        "crash_domain_status",
        "vehicle_domain_status",
        "edr_domain_status",
        "visual_assets_domain_status",
        "source_case_id_agreement",
        "metadata_vehicle_match_status",
        "metadata_event_match_status",
        "metadata_edr_match_status",
        "excel_gv_match_status",
        "excel_vehicle_spec_match_status",
        "excel_vehicle_measurement_match_status",
        "excel_cdc_match_status",
        "excel_event_match_status",
        "excel_edr_collect_match_status",
        "excel_edr_summary_match_status",
        "collision_context_source",
        "collision_context_status",
    }

    POSTCRASH_OUTCOME_COLUMNS = {
        "case_ais_raw",
        "case_ais_text",
        "case_iss_raw",
        "case_injured_raw",
        "case_injury_severity_raw",
        "case_treatment_raw",
        "case_treatment_text",
    }

    DAMAGE_COLUMNS = {
        "metadata_damage_plane",
        "metadata_damage_severity",
        "event_focal_damage_area",
        "event_partner_damage_area",
        "metadata_event_area_damage_code",
        "metadata_event_area_damage_description",
        "metadata_event_vehicle_contact_damage",
        "metadata_event_vehicle_contact_damage_description",
        "excel_measure_front_bumper_raw",
        "excel_measure_rear_bumper_raw",
        "excel_measure_front_track_raw",
        "excel_measure_rear_track_raw",
        "excel_measure_front_hood_raw",
        "excel_measure_side_door_raw",
        "excel_event_general_area_damage_1",
        "excel_event_general_area_damage_1_text",
        "excel_event_general_area_damage_2",
        "excel_event_general_area_damage_2_text",
        "excel_cdc_code",
        "excel_cdc_plane",
        "excel_cdc_plane_text",
        "excel_cdc_extent",
        "excel_cdc_extent_text",
        "excel_cdc_end_shift",
        "excel_cdc_end_shift_text",
        "excel_cdc_overlap_under_ride",
        "excel_cdc_max_crush_raw",
    }

    ROADWAY_AND_PRECRASH_COLUMNS = {
        "crash_configuration_code",
        "crash_configuration_text",
        "manner_of_collision_raw",
        "manner_of_collision_text",
        "excel_gv_speed_limit_raw",
        "excel_gv_speed_limit_text",
        "excel_gv_traffic_flow",
        "excel_gv_road_lane_count",
        "excel_gv_initial_lane",
        "excel_gv_surface_type",
        "excel_gv_surface_condition",
        "excel_gv_alignment",
        "excel_gv_profile",
        "excel_gv_light_condition",
        "excel_gv_weather",
        "excel_gv_traffic_device",
        "excel_gv_precrash_heading",
        "excel_gv_precrash_movement",
        "excel_precrash_record_count",
        "excel_precrash_sequences",
        "excel_precrash_events",
        "excel_precrash_event_texts",
    }

    EVENT_SEQUENCE_COLUMNS = {
        "event_audit_case_vehicle_count",
        "case_crash_event_count",
        "is_multi_vehicle_case",
        "is_multi_event_case",
        "event_sequence_position",
        "prior_event_count",
        "vehicle_count_raw",
        "case_vehicle_count",
        "linked_vehicle_count",
        "vehicle_count_reconciliation_status",
        "crash_event_count_raw",
    }

    PARTNER_COLUMNS = {
        "collision_partner_class",
        "collision_partner_vehicle_number",
        "collision_partner_raw_code",
        "collision_partner_text",
        "event_partner_class_text",
        "metadata_event_vehicle_class",
        "metadata_event_vehicle_class_description",
        "metadata_event_object_contact_class",
        "metadata_event_object_contact_class_description",
        "metadata_event_object_contact_code",
        "metadata_event_object_contact_description",
        "metadata_event_vehicle_contact_class",
        "metadata_event_vehicle_contact_class_description",
        "excel_event_class_2",
        "excel_event_class_2_text",
        "excel_event_object_contact",
        "excel_event_object_contact_text",
    }

    EDR_COLUMNS = {
        "edr_available",
        "edr_event_number",
        "edr_event_description",
        "edr_related_to_investigated_crash",
        "crash_pulse_status",
        "crash_pulse_candidate_available",
        "crash_pulse_unit_validation_required",
        "metadata_edr_obtained",
        "metadata_edr_imaging_method",
        "metadata_edr_event_total",
        "metadata_edr_module_type",
        "metadata_edr_ignition_cycle_download",
        "metadata_cdr_version_collected",
        "metadata_cdr_version_reported",
        "metadata_cdr_file_count",
        "metadata_cdr_file_available",
        "metadata_cdr_file_names",
        "metadata_cdr_file_descriptions",
        "metadata_cdr_object_ids",
        "excel_edr_obtained",
        "excel_edr_obtained_text",
        "excel_edr_method",
        "excel_edr_method_text",
        "excel_edr_summary_number",
        "excel_edr_number_of_events",
        "excel_edr_cdr_version_collected",
        "excel_edr_cdr_version_reported",
        "excel_edr_module_type",
        "excel_edr_module_type_text",
        "excel_edr_ignition_cycle_download",
        "audit_edr_status",
        "audit_edr_obtained",
        "audit_edr_summary_records_available",
        "audit_edr_event_records_available",
        "audit_edr_applicable_event_identified",
        "audit_edr_delta_v_history_available",
        "audit_edr_direct_acceleration_history_available",
        "audit_edr_pulse_candidate_available",
        "edr_summary_count",
        "edr_event_count",
        "asset_vehicle_cdrx_count",
        "asset_vehicle_blz_count",
        "asset_vehicle_nik_count",
        "asset_has_cdrx_file",
    }

    VISUAL_COLUMNS = {
        "image_count",
        "document_count",
        "sketch_count",
        "has_vehicle_damage_images",
        "has_sketches",
        "visual_semantics_available",
        "vlm_damage_location",
        "vlm_damage_severity",
        "vlm_vehicle_orientation",
        "vlm_intrusion_evidence",
        "vlm_collision_partner_evidence",
        "vlm_scene_geometry",
        "vlm_semantic_version",
        "asset_case_total_count",
        "asset_vehicle_total_count",
        "asset_vehicle_image_count",
        "asset_vehicle_document_count",
        "asset_vehicle_sketch_count",
        "asset_vehicle_csv_count",
        "asset_vehicle_pdf_count",
        "asset_has_vehicle_images",
        "asset_has_sketches",
        "asset_has_scene_diagram_document",
        "tree_node_count",
        "tree_has_scene_diagram",
        "tree_has_edr_section",
        "tree_vehicle_image_category_present",
        "tree_vehicle_front_image_category_present",
        "tree_vehicle_side_image_category_present",
        "tree_vehicle_rear_image_category_present",
        "tree_vehicle_interior_image_category_present",
        "audit_visual_assets_status",
    }

    def __init__(self, flat_table_path: Path) -> None:
        self.flat_table_path = flat_table_path

    def build(self, output_directory: Path) -> Model1FeatureRegistryPaths:
        frame = pd.read_parquet(self.flat_table_path)

        rows = [
            self._build_registry_row(frame, column)
            for column in frame.columns
        ]

        registry = pd.DataFrame(rows)
        registry = registry.sort_values(
            ["feature_group", "model1_decision", "column_name"]
        )

        output_directory.mkdir(parents=True, exist_ok=True)

        csv_path = (
            output_directory / "model1_feature_registry.csv"
        )
        registry.to_csv(csv_path, index=False)

        return Model1FeatureRegistryPaths(csv=csv_path)

    def _build_registry_row(
        self,
        frame: pd.DataFrame,
        column: str,
    ) -> dict[str, object]:
        decision = self._classify(column)

        present_count = int(frame[column].notna().sum())
        row_count = len(frame)

        return {
            "column_name": column,
            "data_type": str(frame[column].dtype),
            "non_null_count": present_count,
            "missing_count": int(row_count - present_count),
            "coverage_percent": round(
                100 * present_count / row_count,
                2,
            ) if row_count else None,
            **decision,
            "registry_version": self.VERSION,
        }

    def _classify(self, column: str) -> dict[str, str]:
        if column in self.TARGET_COLUMNS:
            return {
                "feature_group": "target_labels",
                "reason_code": "target_label",
                "model1_decision": "target_only",
                "decision_explanation": (
                    "Event-specific reconstruction target. "
                    "Use as the prediction outcome, never as an input."
                ),
            }

        if (
            column in self.TARGET_PROVENANCE_COLUMNS
            or column in self.DIRECT_RECONSTRUCTION_COLUMNS
            or column.startswith("excel_cdc_delta_v_")
        ):
            return {
                "feature_group": "target_labels",
                "reason_code": "target_derived_leakage",
                "model1_decision": "exclude_leakage",
                "decision_explanation": (
                    "Directly contains, identifies, validates, or closely "
                    "encodes a Delta-V or PDOF reconstruction result."
                ),
            }

        if column in self.IDENTIFIER_COLUMNS:
            return {
                "feature_group": "administrative",
                "reason_code": "identifier_privacy_or_provenance",
                "model1_decision": "exclude_identifier",
                "decision_explanation": (
                    "Identifier or sampling code used for linkage, traceability, "
                    "and case-level train/test splitting; not crash mechanics."
                ),
            }

        if (
            column in self.PATH_OR_VERSION_COLUMNS
            or column in self.QUALITY_OR_AUDIT_COLUMNS
        ):
            return {
                "feature_group": "administrative",
                "reason_code": "identifier_privacy_or_provenance",
                "model1_decision": "retain_provenance",
                "decision_explanation": (
                    "Source, extraction, audit, or quality-control information. "
                    "Retain for reproducibility and filtering, not as a predictor."
                ),
            }

        if column in self.POSTCRASH_OUTCOME_COLUMNS:
            return {
                "feature_group": "post_crash_outcomes",
                "reason_code": "postcrash_outcome",
                "model1_decision": "exclude_outcome",
                "decision_explanation": (
                    "Injury or treatment outcome observed after the crash. "
                    "Not an input to the crash-mechanics prediction model."
                ),
            }

        if column in self.DAMAGE_COLUMNS:
            return {
                "feature_group": "post_crash_damage_and_crush",
                "reason_code": "postcrash_physical_evidence",
                "model1_decision": "include_expanded_evidence",
                "decision_explanation": (
                    "Post-crash deformation, crush, overlap, or damage geometry. "
                    "Candidate only for the expanded evidence-based model."
                ),
            }

        if column in self.ROADWAY_AND_PRECRASH_COLUMNS:
            return {
                "feature_group": "preimpact_motion_and_roadway",
                "reason_code": "roadway_or_preimpact_context",
                "model1_decision": "include_context",
                "decision_explanation": (
                    "Crash configuration, roadway, environment, or pre-impact "
                    "motion context available before reconstruction."
                ),
            }

        if column in self.EVENT_SEQUENCE_COLUMNS:
            return {
                "feature_group": "event_sequence_and_complexity",
                "reason_code": "event_sequence_complexity",
                "model1_decision": "include_context",
                "decision_explanation": (
                    "Describes event order or case complexity and helps distinguish "
                    "single-impact from multi-impact crash circumstances."
                ),
            }

        if column in self.PARTNER_COLUMNS:
            if column == "collision_partner_vehicle_number":
                return {
                    "feature_group": "collision_partner_information",
                    "reason_code": "partner_linkage_key",
                    "model1_decision": "retain_for_feature_engineering",
                    "decision_explanation": (
                        "Link key for deriving the collision partner's mass, "
                        "class, and geometry from vehicle_index. Do not model "
                        "the vehicle number itself."
                    ),
                }

            return {
                "feature_group": "collision_partner_information",
                "reason_code": "collision_configuration",
                "model1_decision": "include_context",
                "decision_explanation": (
                    "Describes the contacted vehicle or fixed object and the "
                    "collision configuration."
                ),
            }

        if column in self.EDR_COLUMNS:
            return {
                "feature_group": "edr_evidence",
                "reason_code": "unavailable_or_insufficient_coverage",
                "model1_decision": "defer_pending_validation",
                "decision_explanation": (
                    "EDR/CDR availability, file, or linkage evidence. Preserve "
                    "for future validated EDR extraction; do not use as a "
                    "routine predictor at this stage."
                ),
            }

        if column in self.VISUAL_COLUMNS:
            return {
                "feature_group": "scene_image_sketch_evidence",
                "reason_code": "unavailable_or_insufficient_coverage",
                "model1_decision": "defer_pending_validation",
                "decision_explanation": (
                    "Image, sketch, asset, tree, or VLM-semantic evidence. "
                    "Preserve for later validated visual feature extraction."
                ),
            }

        if (
            column.startswith("metadata_")
            or column.startswith("excel_gv_")
            or column.startswith("excel_vehspec_")
            or column == "excel_gv_towed_status"
        ):
            return {
                "feature_group": "subject_vehicle_information",
                "reason_code": "intrinsic_vehicle_characteristic",
                "model1_decision": "include_context",
                "decision_explanation": (
                    "Intrinsic subject-vehicle identity, mass, geometry, "
                    "powertrain, use, or modification characteristic."
                ),
            }

        if column in {
            "analysis_cohort",
            "audit_crash_mechanics_status",
            "audit_crash_reconstruction_eligibility",
            "audit_multimodal_learning_eligibility",
        }:
            return {
                "feature_group": "administrative",
                "reason_code": "analysis_cohort_or_eligibility",
                "model1_decision": "retain_provenance",
                "decision_explanation": (
                    "Cohort or audit eligibility indicator. Use for transparent "
                    "filtering and reporting, not as a predictive feature."
                ),
            }

        if column in {
            "crash_year",
            "crash_month",
            "crash_month_text",
            "day_of_week",
            "day_of_week_code",
            "crash_time_raw",
            "metadata_crash_date_raw",
            "metadata_crash_time_raw",
            "metadata_crash_year",
            "metadata_day_of_week",
        }:
            return {
                "feature_group": "temporal_context",
                "reason_code": "roadway_or_preimpact_context",
                "model1_decision": "defer_pending_review",
                "decision_explanation": (
                    "Temporal crash context. Retain for review; include only "
                    "if its interpretation and possible sampling effects are justified."
                ),
            }

        if column in {
            "crash_summary",
            "metadata_crash_summary",
            "metadata_event_description",
        }:
            return {
                "feature_group": "narrative_text",
                "reason_code": "narrative_requires_leakage_review",
                "model1_decision": "exclude_baseline",
                "decision_explanation": (
                    "Free text may describe damage, reconstruction findings, or "
                    "outcomes. Reserve for a separate NLP study after leakage review."
                ),
            }

        return {
            "feature_group": "manual_review",
            "reason_code": "manual_review_required",
            "model1_decision": "defer_pending_review",
            "decision_explanation": (
                "Column was retained in the rich flat table but needs an explicit "
                "expert decision before use in Model 1."
            ),
        }