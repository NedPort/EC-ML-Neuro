"""
JSON schema for evidence extracted from one crash photograph.

This schema is limited to directly visible evidence. Physical
interpretations and crash-reconstruction conclusions belong in
separate expert schemas.
"""


VISUAL_EVIDENCE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CISS Individual Image Visual Evidence",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "analysis_type",
        "case_id",
        "asset_id",
        "source",
        "image_quality",
        "viewpoint",
        "vehicle_observations",
        "damage_observations",
        "safety_observations",
        "scene_observations",
        "evidence_summary",
        "uncertainties",
    ],
    "properties": {
        "schema_version": {
            "type": "string",
            "const": "1.0",
        },
        "analysis_type": {
            "type": "string",
            "const": "individual_image_visual_evidence",
        },
        "case_id": {
            "type": "integer",
        },
        "asset_id": {
            "type": "string",
            "minLength": 1,
        },
        "source": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "relative_path",
                "vehicle_number",
                "ciss_category",
                "normalized_category",
            ],
            "properties": {
                "relative_path": {
                    "type": "string",
                },
                "vehicle_number": {
                    "type": ["integer", "null"],
                },
                "ciss_category": {
                    "type": "string",
                },
                "normalized_category": {
                    "type": "string",
                },
            },
        },
        "model_provenance": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": [
                "provider",
                "model",
                "prompt_version",
                "processed_at",
            ],
            "properties": {
                "provider": {
                    "type": "string",
                },
                "model": {
                    "type": "string",
                },
                "model_version": {
                    "type": ["string", "null"],
                },
                "prompt_version": {
                    "type": "string",
                },
                "processed_at": {
                    "type": "string",
                },
            },
        },
        "image_quality": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "usable",
                "overall_quality",
                "blur",
                "lighting",
                "occlusion",
                "resolution_sufficient",
                "limitations",
            ],
            "properties": {
                "usable": {
                    "type": "boolean",
                },
                "overall_quality": {
                    "type": "string",
                    "enum": [
                        "high",
                        "medium",
                        "low",
                        "unusable",
                    ],
                },
                "blur": {
                    "type": "string",
                    "enum": [
                        "none",
                        "minor",
                        "moderate",
                        "severe",
                    ],
                },
                "lighting": {
                    "type": "string",
                    "enum": [
                        "adequate",
                        "underexposed",
                        "overexposed",
                        "uneven",
                        "uncertain",
                    ],
                },
                "occlusion": {
                    "type": "string",
                    "enum": [
                        "none",
                        "minor",
                        "moderate",
                        "major",
                    ],
                },
                "resolution_sufficient": {
                    "type": "boolean",
                },
                "limitations": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
        },
        "viewpoint": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "observed_view",
                "camera_distance",
                "vehicle_regions_visible",
                "view_matches_ciss_category",
            ],
            "properties": {
                "observed_view": {
                    "type": "string",
                    "enum": [
                        "front",
                        "front_left_oblique",
                        "front_right_oblique",
                        "left",
                        "right",
                        "rear",
                        "rear_left_oblique",
                        "rear_right_oblique",
                        "top",
                        "interior_first_row",
                        "interior_second_row",
                        "detail_closeup",
                        "crash_scene",
                        "other",
                        "uncertain",
                    ],
                },
                "camera_distance": {
                    "type": "string",
                    "enum": [
                        "close_up",
                        "medium",
                        "wide",
                        "uncertain",
                    ],
                },
                "vehicle_regions_visible": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "view_matches_ciss_category": {
                    "type": "string",
                    "enum": [
                        "yes",
                        "partially",
                        "no",
                        "uncertain",
                    ],
                },
            },
        },
        "vehicle_observations": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "vehicle_visible",
                "number_of_vehicles_visible",
                "body_type",
                "orientation",
                "identifying_details",
                "inspection_state",
                "inspection_artifacts",
            ],
            "properties": {
                "vehicle_visible": {
                    "type": "boolean",
                },
                "number_of_vehicles_visible": {
                    "type": "integer",
                    "minimum": 0,
                },
                "body_type": {
                    "type": [
                        "string",
                        "null",
                    ],
                },
                "orientation": {
                    "type": [
                        "string",
                        "null",
                    ],
                },
                "identifying_details": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
                "inspection_state": {
                    "type": "string",
                    "enum": [
                        "as_found",
                        "partially_disassembled",
                        "extensively_disassembled",
                        "reassembled",
                        "uncertain",
                    ],
                },
                "inspection_artifacts": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "measurement_gauge",
                            "measurement_targets",
                            "evidence_labels",
                            "protective_covering",
                            "component_markings",
                            "license_plate_covering",
                            "other",
                        ],
                    },
                },
            },
        },
        "damage_observations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "observation_id",
                    "vehicle_region",
                    "laterality",
                    "component",
                    "damage_types",
                    "visible_severity",
                    "description",
                    "confidence",
                ],
                "properties": {
                    "observation_id": {
                        "type": "string",
                    },
                    "vehicle_region": {
                        "type": "string",
                        "enum": [
                            "front",
                            "rear",
                            "left_side",
                            "right_side",
                            "roof",
                            "underbody",
                            "interior",
                            "wheel_area",
                            "glass_area",
                            "other",
                            "uncertain",
                        ],
                    },
                    "laterality": {
                        "type": "string",
                        "enum": [
                            "left",
                            "right",
                            "center",
                            "bilateral",
                            "not_applicable",
                            "uncertain",
                        ],
                    },
                    "component": {
                        "type": "string",
                    },
                    "damage_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "dent",
                                "crack",
                                "tear",
                                "scratch",
                                "buckling",
                                "crushing",
                                "fracture",
                                "displacement",
                                "separation",
                                "detachment",
                                "glass_breakage",
                                "lamp_breakage",
                                "tire_damage",
                                "wheel_displacement",
                                "intrusion",
                                "fluid_leak_evidence",
                                "burning_or_heat_damage",
                                "other",
                                "uncertain",
                            ],
                        },
                    },
                    "visible_severity": {
                        "type": "string",
                        "enum": [
                            "none",
                            "minor",
                            "moderate",
                            "severe",
                            "uncertain",
                        ],
                    },
                    "description": {
                        "type": "string",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
            },
        },
        "safety_observations": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "airbag_status",
                "restraint_status",
                "glazing_damage",
                "occupant_compartment_intrusion",
                "observations",
            ],
            "properties": {
                "airbag_status": {
                    "$ref": "#/$defs/visibility_status",
                },
                "restraint_status": {
                    "$ref": "#/$defs/visibility_status",
                },
                "glazing_damage": {
                    "$ref": "#/$defs/visibility_status",
                },
                "occupant_compartment_intrusion": {
                    "$ref": "#/$defs/visibility_status",
                },
                "observations": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
        },
        "scene_observations": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "roadway_visible",
                "environment_visible",
                "vehicle_position_visible",
                "debris_visible",
                "observations",
            ],
            "properties": {
                "roadway_visible": {
                    "type": "boolean",
                },
                "environment_visible": {
                    "type": "boolean",
                },
                "vehicle_position_visible": {
                    "type": "boolean",
                },
                "debris_visible": {
                    "type": "boolean",
                },
                "observations": {
                    "type": "array",
                    "items": {
                        "type": "string",
                    },
                },
            },
        },
        "evidence_summary": {
            "type": "string",
            "description": (
                "A concise summary containing only directly "
                "visible evidence."
            ),
        },
        "uncertainties": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "field",
                    "reason",
                ],
                "properties": {
                    "field": {
                        "type": "string",
                    },
                    "reason": {
                        "type": "string",
                    },
                },
            },
        },
    },
    "$defs": {
        "visibility_status": {
            "type": "string",
            "enum": [
                "visible_present",
                "visible_absent",
                "not_visible",
                "uncertain",
            ],
        },
    },
}
