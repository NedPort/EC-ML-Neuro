from pathlib import Path
import re

import pandas as pd


INPUT_PATH = Path(
    "data/processed/linked_tables/vehicle_event_index.parquet"
)

OUTPUT_PATH = Path(
    "data/processed/linked_tables/"
    "vehicle_event_index_data_dictionary.csv"
)


EXACT_MEANINGS = {
    "case_id": "CISS crash-case identifier.",
    "vehicle_id": (
        "Unique linked-table vehicle identifier in the form "
        "<case_id>-V<vehicle_number>."
    ),
    "vehicle_number": (
        "CISS vehicle number within the crash case. Used to join vehicle-"
        "level records."
    ),
    "event_number": (
        "CISS crash-event number for this vehicle. Used with vehicle_number "
        "to identify one specific impact event."
    ),
    "vehicle_event_id": (
        "Unique vehicle-event identifier in the form "
        "<case_id>-V<vehicle_number>-E<event_number>."
    ),
    "event_audit_case_vehicle_count": (
        "Original audit-derived count of vehicles in the case, retained as "
        "provenance and not used as the authoritative linked count."
    ),
    "linked_vehicle_count": (
        "Verified number of distinct vehicle records linked to this case "
        "from vehicle_index."
    ),
    "vehicle_count_reconciliation_status": (
        "Whether the original audit vehicle count agrees with the verified "
        "linked_vehicle_count."
    ),
    "total_delta_v_kmh": (
        "Audited total vehicle Delta-V for this event, in km/h. This is a "
        "prediction target and must not be used as a Model 1 input."
    ),
    "longitudinal_delta_v_kmh": (
        "Audited longitudinal Delta-V component for this event, in km/h. "
        "This is a prediction target, not a model input."
    ),
    "lateral_delta_v_kmh": (
        "Audited lateral Delta-V component for this event, in km/h. This "
        "is a prediction target, not a model input."
    ),
    "pdof_degrees": (
        "Audited principal direction of force for this vehicle-event, in "
        "degrees. This is a prediction target, not a model input."
    ),
    "collision_partner_class": (
        "Normalized class of the collision partner, such as vehicle, fixed "
        "object, pedestrian/cyclist, animal, or unknown."
    ),
    "collision_partner_vehicle_number": (
        "CISS vehicle number of the collision partner when it is another "
        "vehicle in the same case. Supports a later partner-vehicle join."
    ),
    "collision_partner_text": (
        "Human-readable description of the collision partner."
    ),
    "event_focal_damage_area": (
        "Primary damage area associated with this vehicle-event."
    ),
    "event_partner_damage_area": (
        "Damage-area description for the collision partner in this event."
    ),
    "analysis_cohort": (
        "Descriptive collision cohort, such as vehicle_to_vehicle or "
        "vehicle_to_fixed_object. It is not an ML eligibility decision."
    ),
    "event_sequence_position": (
        "Position of this event within the vehicle's recorded crash-event "
        "sequence."
    ),
    "prior_event_count": (
        "Number of recorded vehicle events preceding this event."
    ),
    "is_multi_vehicle_case": (
        "Whether the case contains more than one verified vehicle."
    ),
    "is_multi_event_case": (
        "Whether the case contains more than one recorded crash event."
    ),
    "edr_available": (
        "Whether an applicable audited EDR event record was linked to this "
        "vehicle-event."
    ),
    "crash_pulse_candidate_available": (
        "Whether audit evidence indicates a candidate crash-pulse record "
        "may be available. It is not a validated pulse measurement."
    ),
    "asset_has_cdrx_file": (
        "Whether the asset inventory lists a vehicle-associated .cdrx file. "
        "This indicates availability only; the file has not been parsed."
    ),
    "asset_vehicle_nik_count": (
        "Number of vehicle-associated Nikon .nik evidence files listed in "
        "the asset inventory. It indicates availability only."
    ),
    "asset_vehicle_blz_count": (
        "Number of vehicle-associated .blz evidence files listed in the "
        "asset inventory. It indicates availability only."
    ),
    "visual_semantics_available": (
        "Whether validated visual-semantic extraction has been incorporated "
        "for this row. Current false values do not mean images are absent."
    ),
}


def humanize(column: str) -> str:
    """Convert a snake_case source name into readable field text."""

    text = column.replace("_", " ")
    text = re.sub(r"\bcdc\b", "CDC", text)
    text = re.sub(r"\bedr\b", "EDR", text)
    text = re.sub(r"\bpdof\b", "PDOF", text)
    text = re.sub(r"\bvlm\b", "VLM", text)
    text = re.sub(r"\bcdrx\b", "CDRX", text)
    return text.capitalize()


def describe(column: str) -> str:
    """Return a curated source-aware meaning for every table column."""

    if column in EXACT_MEANINGS:
        return EXACT_MEANINGS[column]

    if column.startswith("metadata_event_"):
        return (
            f"Event-specific value from metadata.json: {humanize(column)}. "
            "Joined using vehicle_number and event_number."
        )

    if column.startswith("metadata_"):
        return (
            f"Vehicle- or case-level value from metadata.json: "
            f"{humanize(column)}. Preserved from the original CISS metadata."
        )

    if column.startswith("excel_event_"):
        return (
            f"Event-specific value from the export.xlsx EVENT worksheet: "
            f"{humanize(column)}. Joined using VEHNUM and EVENTNO."
        )

    if column.startswith("excel_cdc_"):
        return (
            f"Raw crash-damage-code evidence from the export.xlsx CDC "
            f"worksheet: {humanize(column)}. It must not overwrite audited "
            "Delta-V or PDOF targets."
        )

    if column.startswith("excel_gv_"):
        return (
            f"Vehicle, roadway, environment, or pre-impact context from the "
            f"export.xlsx GV worksheet: {humanize(column)}."
        )

    if column.startswith("excel_vehspec_"):
        return (
            f"Vehicle specification from the export.xlsx VEHSPEC worksheet: "
            f"{humanize(column)}."
        )

    if column.startswith("excel_measure_"):
        return (
            f"Vehicle measurement from the export.xlsx VEH_MEAS worksheet: "
            f"{humanize(column)}."
        )

    if column.startswith("excel_precrash_"):
        return (
            f"Vehicle-level aggregated pre-crash evidence from the "
            f"export.xlsx PRE_FHE worksheet: {humanize(column)}."
        )

    if column.startswith("excel_edr_"):
        return (
            f"Vehicle-level EDR collection or summary evidence from "
            f"export.xlsx: {humanize(column)}. It is not automatically "
            "linked to a specific crash event."
        )

    if column.startswith("audit_"):
        return (
            f"Audit quality, availability, or eligibility field: "
            f"{humanize(column)}."
        )

    if column.startswith("asset_"):
        return (
            f"Asset-inventory availability or count field: "
            f"{humanize(column)}."
        )

    if column.startswith("tree_"):
        return (
            f"Navigation-tree evidence availability field: "
            f"{humanize(column)}."
        )

    if column.startswith("vlm_"):
        return (
            f"Reserved field for validated visual-language-model evidence: "
            f"{humanize(column)}. It is not currently a confirmed source "
            "measurement."
        )

    if column.startswith("delta_v_"):
        return (
            f"Delta-V target provenance, quality, or eligibility field: "
            f"{humanize(column)}."
        )

    if column.startswith("pdof_"):
        return (
            f"PDOF target provenance, quality, or eligibility field: "
            f"{humanize(column)}."
        )

    return f"Linked vehicle-event field: {humanize(column)}."


def source_and_join(column: str) -> tuple[str, str, str]:
    """Return source, entity level, and join key."""

    if column in {
        "case_id",
        "vehicle_id",
        "vehicle_number",
        "event_number",
        "vehicle_event_id",
    }:
        return "linked-table identifier", "vehicle-event", "primary key"

    if column.startswith("metadata_event_"):
        return (
            "metadata.json: events",
            "vehicle-event",
            "vehicleNumber + eventNumber",
        )

    if column.startswith("metadata_"):
        return "metadata.json", "case or vehicle", "case_id or vehicle_number"

    if column.startswith("excel_event_"):
        return "export.xlsx: EVENT", "vehicle-event", "VEHNUM + EVENTNO"

    if column.startswith("excel_cdc_"):
        return "export.xlsx: CDC", "vehicle-event", "VEHNO + EVENTNO"

    if column.startswith("excel_gv_"):
        return "export.xlsx: GV", "vehicle", "VEHNO"

    if column.startswith("excel_vehspec_"):
        return "export.xlsx: VEHSPEC", "vehicle", "VEHNO"

    if column.startswith("excel_measure_"):
        return "export.xlsx: VEH_MEAS", "vehicle", "VEHNO"

    if column.startswith("excel_precrash_"):
        return "export.xlsx: PRE_FHE", "vehicle", "VEHNO"

    if column.startswith("excel_edr_"):
        return "export.xlsx: EDRCOLLECT / EDRSUMM", "vehicle", "VEHNO"

    if column.startswith(("audit_", "asset_", "tree_")):
        return "case_audit.json / assets.json / navigation_tree.json", "case or vehicle", "case_id / vehicle_number"

    if column.startswith("vlm_"):
        return "future validated visual-semantic extraction", "vehicle-event", "vehicle_event_id"

    return "vehicle_event_index build", "vehicle-event", "vehicle_event_id"


def role_and_ml_use(column: str) -> tuple[str, str]:
    """Classify data use and prevent label leakage."""

    if column in {
        "total_delta_v_kmh",
        "longitudinal_delta_v_kmh",
        "lateral_delta_v_kmh",
        "pdof_degrees",
    }:
        return "target_label", "target_only_not_model_input"

    if (
        column.startswith("delta_v_")
        or column.startswith("pdof_")
        or column.startswith("excel_cdc_delta_v_")
        or column == "excel_cdc_heading_angle"
    ):
        return "target_provenance_or_leakage_risk", "exclude_from_model_inputs"

    if (
        column.endswith("_status")
        or column.endswith("_available")
        or column.endswith("_eligibility")
        or column.endswith("_usable")
        or column.endswith("_match_status")
    ):
        return "quality_or_availability_flag", "analysis_filter_or_quality_control"

    if column in {
        "case_id",
        "vehicle_id",
        "vehicle_number",
        "event_number",
        "vehicle_event_id",
    }:
        return "identifier", "join_only_not_model_input"

    return "source_evidence_or_candidate_feature", "task_dependent"


def main() -> None:
    df = pd.read_parquet(INPUT_PATH)

    rows = []

    for column in df.columns:
        source, entity_level, join_key = source_and_join(column)
        role, ml_use = role_and_ml_use(column)

        non_null_count = int(df[column].notna().sum())

        rows.append(
            {
                "column_name": column,
                "meaning": describe(column),
                "source_file": source,
                "entity_level": entity_level,
                "join_key": join_key,
                "data_type": str(df[column].dtype),
                "role": role,
                "ML_use": ml_use,
                "non_null_count": non_null_count,
                "missing_count": int(len(df) - non_null_count),
                "coverage_percent": round(
                    100 * non_null_count / len(df),
                    2,
                ),
            }
        )

    dictionary_df = pd.DataFrame(rows)

    dictionary_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Created: {OUTPUT_PATH}")
    print(f"Documented columns: {len(dictionary_df)}")


if __name__ == "__main__":
    main()