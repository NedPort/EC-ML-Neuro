"""
Create a human-readable data dictionary for case_index.parquet.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


DATA_ROOT = Path("data")
INPUT_PATH = (
    DATA_ROOT
    / "processed"
    / "linked_tables"
    / "case_index.parquet"
)
OUTPUT_PATH = (
    DATA_ROOT
    / "processed"
    / "linked_tables"
    / "case_index_data_dictionary.csv"
)


SPECIAL_DEFINITIONS = {
    "case_id": (
        "Unique CISS crash-case identifier.",
        "Case package and audit",
        "Primary key",
    ),
    "audit_status": (
        "Overall result of the Stage 2 case audit.",
        "case_audit.json",
        "Audit quality status",
    ),
    "case_index_version": (
        "Schema version of the case-index builder.",
        "Case-index builder",
        "Provenance",
    ),
    "source_case_id_agreement": (
        "Whether the audit, metadata JSON, and CRASH worksheet "
        "identify the same case ID.",
        "Cross-source validation",
        "Quality-control result",
    ),
    "case_number": (
        "Full readable CISS case number.",
        "CRASH.CASENUMBER",
        "Case identifier",
    ),
    "case_number_raw": (
        "Numeric case number within the CISS PSU/year record.",
        "CRASH.CASENO",
        "Raw source value",
    ),
    "psu": (
        "Primary Sampling Unit code.",
        "CRASH.PSU",
        "Sampling-design metadata",
    ),
    "domain": (
        "CISS case-domain code.",
        "CRASH.CATEGORY",
        "Case classification",
    ),
    "crash_configuration_code": (
        "Raw code for the overall crash configuration.",
        "CRASH.CONFIG",
        "Raw source value",
    ),
    "crash_configuration_text": (
        "Human-readable overall crash configuration.",
        "CRASH.CONFIGTEXT",
        "Case-level crash context",
    ),
    "crash_event_count_raw": (
        "Number of crash events coded in the original CRASH sheet.",
        "CRASH.EVENTS",
        "Raw source value",
    ),
    "case_crash_event_count": (
        "Number of crash events reconstructed by the audit.",
        "case_audit.json / entities.crash_events",
        "Audit-derived validation value",
    ),
    "vehicle_count_raw": (
        "Number of vehicles coded in the original CRASH sheet.",
        "CRASH.VEHICLES",
        "Raw source value",
    ),
    "case_vehicle_count": (
        "Number of CISS vehicles reconstructed by the audit.",
        "case_audit.json / collision_context",
        "Audit-derived validation value",
    ),
    "manner_of_collision_raw": (
        "Raw broad CISS manner-of-collision code.",
        "CRASH.MANCOLL",
        "Raw source value",
    ),
    "manner_of_collision_text": (
        "Human-readable broad CISS manner-of-collision classification.",
        "CRASH.MANCOLLTEXT",
        "Case-level crash context",
    ),
    "case_ais_raw": (
        "Raw case-level AIS or injury-severity classification code.",
        "CRASH.CAIS",
        "Post-crash outcome",
    ),
    "case_ais_text": (
        "Text description of the case-level injury-severity classification.",
        "CRASH.CAISTEXT",
        "Post-crash outcome",
    ),
    "case_iss_raw": (
        "Raw case-level injury severity score field.",
        "CRASH.CISS",
        "Post-crash outcome",
    ),
    "case_injured_raw": (
        "Raw case-level injured-person indicator or count field.",
        "CRASH.CINJURED",
        "Post-crash outcome",
    ),
    "case_injury_severity_raw": (
        "Raw case-level injury-severity field.",
        "CRASH.CINJSEV",
        "Post-crash outcome",
    ),
    "case_treatment_raw": (
        "Raw case-level medical treatment or disposition code.",
        "CRASH.CTREAT",
        "Post-crash outcome",
    ),
    "case_treatment_text": (
        "Text description of case-level medical treatment or disposition.",
        "CRASH.CTREATTEXT",
        "Post-crash outcome",
    ),
    "alcohol_involvement_raw": (
        "Raw case-level alcohol-involvement code.",
        "CRASH.ALCINV",
        "Case context",
    ),
    "drug_involvement_raw": (
        "Raw case-level drug-involvement code.",
        "CRASH.DRGINV",
        "Case context",
    ),
    "case_weight": (
        "CISS sampling weight for population-level estimation.",
        "CRASH.CASEWGT",
        "Survey-design metadata",
    ),
    "psu_stratum": (
        "Primary Sampling Unit stratum for the sampling design.",
        "CRASH.PSUSTRAT",
        "Survey-design metadata",
    ),
    "source_version": (
        "CISS export/version field from the CRASH record.",
        "CRASH.VERSION",
        "Provenance",
    ),
    "edr_summary_count": (
        "Number of EDR summary records identified by the audit.",
        "case_audit.json / entities.edr_summaries",
        "Audit-derived availability",
    ),
    "edr_event_count": (
        "Number of EDR event records identified by the audit.",
        "case_audit.json / entities.edr_events",
        "Audit-derived availability",
    ),
    "image_count": (
        "Number of registered image assets in the case package.",
        "case_audit.json / asset_inventory",
        "Evidence availability",
    ),
    "sketch_count": (
        "Number of registered sketch assets in the case package.",
        "case_audit.json / asset_inventory",
        "Evidence availability",
    ),
    "document_count": (
        "Number of registered document assets in the case package.",
        "case_audit.json / asset_inventory",
        "Evidence availability",
    ),
    "cross_source_contradiction_count": (
        "Number of unresolved cross-source contradictions found by the audit.",
        "case_audit.json",
        "Quality-control result",
    ),
    "package_validation_passed": (
        "Whether the downloaded case package passed file-level validation.",
        "manifest.json / case audit",
        "Package quality status",
    ),
}


def infer_definition(column: str) -> tuple[str, str, str]:
    """Return description, source, and role for a case-index column."""

    if column in SPECIAL_DEFINITIONS:
        return SPECIAL_DEFINITIONS[column]

    if column.startswith("metadata_"):
        label = column.removeprefix("metadata_").replace("_", " ")
        return (
            f"Companion metadata JSON value: {label}.",
            "metadata.json / crashSummary",
            "Companion source and provenance",
        )

    if column.endswith("_source_path"):
        return (
            "Path to the original input file used to construct the row.",
            "Case package",
            "Provenance",
        )

    if column.endswith("_available"):
        return (
            "Whether the corresponding source file or domain is available.",
            "Case audit or case package",
            "Availability flag",
        )

    if column.endswith("_domain_status"):
        return (
            "Audited availability status for this data domain.",
            "case_audit.json / domain_availability",
            "Quality and availability",
        )

    if column.startswith("audit_"):
        return (
            "Case-audit summary value.",
            "case_audit.json / audit_summary",
            "Quality-control result",
        )

    if column in {"asset_count", "package_status"}:
        return (
            column.replace("_", " ").capitalize() + ".",
            "case_audit.json",
            "Audit-derived availability",
        )

    return (
        column.replace("_", " ").capitalize() + ".",
        "See case_index builder and source audit.",
        "Documented field",
    )


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"case_index was not found: {INPUT_PATH}"
        )

    frame = pd.read_parquet(INPUT_PATH)

    rows = []

    for column in frame.columns:
        meaning, source, role = infer_definition(column)

        rows.append(
            {
                "column_name": column,
                "meaning": meaning,
                "source": source,
                "entity_level": "case",
                "data_type": str(frame[column].dtype),
                "role": role,
                "observed_non_null_count": int(
                    frame[column].notna().sum()
                ),
                "observed_missing_count": int(
                    frame[column].isna().sum()
                ),
            }
        )

    dictionary = pd.DataFrame(rows)

    dictionary.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print("Case-index data dictionary completed.")
    print(f"Rows: {len(dictionary)}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()