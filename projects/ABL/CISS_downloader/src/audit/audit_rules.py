"""
Definitions used by the CISS case auditor.
"""

AUDIT_SCHEMA_VERSION = "2.1"

VARIABLE_REGISTRY_VERSION = "1.1"


CORE_SHEETS = {
    "CRASH",
    "GV",
    "OCC",
    "EVENT",
    "CDC",
    "INJURY",
}


SENTINEL_TEXT_PATTERNS = {
    "unknown": (
        "unknown",
        "unk if",
        "unspecified",
    ),
    "not_reported": (
        "not reported",
        "not recorded",
    ),
    "not_applicable": (
        "not applicable",
        "no rollover",
        "no ejection",
    ),
    "not_available": (
        "not available",
        "not collected",
        "not obtained",
    ),
    "not_performed": (
        "not made",
        "not given",
        "no specimen",
        "none given",
    ),
}


# Candidate column-name patterns for EDR signal detection.
EDR_TIME_PATTERNS = (
    "TIME",
    "TIMESTAMP",
    "MSEC",
    "MILLISECOND",
)

EDR_LONGITUDINAL_PATTERNS = (
    "DVLONG",
    "LONGDV",
    "LONGITUDINAL",
    "ACCELX",
    "XACCEL",
)

EDR_LATERAL_PATTERNS = (
    "DVLAT",
    "LATDV",
    "LATERAL",
    "ACCELY",
    "YACCEL",
)


IMPORTANT_VARIABLES = {
    "crash": {
        "CRASH": (
            "CRASHYEAR",
            "CRASHMONTH",
            "DAYOFWEEK",
            "CRASHTIME",
            "CONFIG",
            "EVENTS",
            "VEHICLES",
            "SUMMARY",
        ),
    },

    "vehicle": {
        "GV": (
            "VEHNO",
            "MAKE",
            "MODEL",
            "MODELYR",
            "BODYTYPE",
            "VEHCLASS",
            "CURBWT",
            "DAMPLANE",
            "DAMSEV",
        ),
    },

    "crash_mechanics": {
        "GV": (
            "DVEVENT",
            "DVBASIS",
            "DVTOTAL",
            "DVLONG",
            "DVLAT",
            "DVENERGY",
            "DVSPEED",
            "DVMOMENT",
            "DVBES",
            "DVCONF",
        ),
        "CDC": (
            "EVENTNO",
            "PDOF",
            "OCLOCK",
            "CDC",
            "DVTOTAL",
            "DVLONG",
            "DVLAT",
            "DVENERGY",
            "DVBARRIER",
            "CMAX",
            "DIRECTD",
            "DIRECTWIDTH",
            "FIELDL",
        ),
        "EVENT": (
            "EVENTNO",
            "VEHNUM",
            "OBJCONT",
            "GAD1",
        ),
    },

    "occupant": {
        "OCC": (
            "VEHNO",
            "OCCNO",
            "SEATLOC",
            "ROLE",
            "AGE",
            "SEX",
            "HEIGHT",
            "WEIGHT",
            "BMI",
            "POSTURE",
            "ENTRAP",
        ),
    },

    "restraint_and_airbag": {
        "OCC": (
            "VEHNO",
            "OCCNO",
            "BELTAVAIL",
            "BELTUSE",
            "BELTMALF",
            "PARAIRBAG",
        ),
        "AIRBAG": (
            "VEHNO",
            "BAGNO",
            "BAGLOCATION",
            "BAGSTATUS",
            "BAGDEPLOY",
            "DEPLOYEVENT",
        ),
        "SEAT": (
            "VEHNO",
            "SEATLOC",
            "SEATTYPE",
            "ORIENTATION",
            "TRACK",
            "PERFORMANCE",
            "BELTUSEINSP",
            "BELTPRETENSIONINSP",
        ),
    },

    "occupant_contact_and_intrusion": {
        "OCCONTACT": (
            "VEHNO",
            "OCCNO",
            "CONTACT",
            "CONTAREA",
            "CONTCOMP",
            "BODYREGION",
            "EVIDENCE",
            "CONFIDENCE",
        ),
        "INTRUSION": (
            "VEHNO",
            "INTRUNO",
            "INTRUSION",
        ),
        "INTEGRITY": (
            "VEHNO",
            "INTEGRITY",
        ),
        "INTERIOR": (
            "VEHNO",
            "POSTINTEGLOSS",
            "GLAZINGCONT",
        ),
    },

    "injury_outcomes": {
        "OCC": (
            "VEHNO",
            "OCCNO",
            "INJSTATUS",
            "INJNUM",
            "MAIS",
            "ISS",
            "TREATMENT",
            "MORTALITY",
        ),
        "INJURY": (
            "VEHNO",
            "OCCNO",
            "INJNO",
            "AISCODE",
            "INJLEVEL",
            "AIS",
            "INJURYNOTE",
        ),
    },

    "edr": {
        "EDRCOLLECT": (
            "VEHNO",
            "EDROBTAINED",
            "EDRMETHOD",
        ),
        "EDRSUMM": (
            "VEHNO",
            "NUMEVENTS",
            "MODTYPE",
            "CDRVERCOLL",
        ),
        "EDREVENT": (
            "VEHNO",
            "EDREVENTNO",
            "EVENTDESC",
            "MAXDVLONG",
            "MAXDVLAT",
            "MAXDVRESTIME",
        ),
        "EDRPRECRASH": (
            "VEHNO",
            "EDREVENTNO",
        ),
        "EDRPOSTCRASH": (
            "VEHNO",
            "EDREVENTNO",
        ),
        "EDRREST": (
            "VEHNO",
            "EDREVENTNO",
            "LFBELT",
            "RFBELT",
        ),
    },
}



# ------------------------------------------------------------------
# Variable Registry Rules
# ------------------------------------------------------------------

VARIABLE_ENTITY_BY_SHEET = {
    "CRASH": "case",
    "GV": "vehicle",
    "CDC": "vehicle_event",
    "EVENT": "crash_event",
    "OCC": "occupant",
    "AIRBAG": "airbag",
    "SEAT": "seat",
    "OCCONTACT": "occupant_contact",
    "INTRUSION": "vehicle_intrusion",
    "INTEGRITY": "vehicle_integrity",
    "INTERIOR": "vehicle_interior",
    "INJURY": "occupant_injury",
    "EDRCOLLECT": "edr_collection",
    "EDRSUMM": "edr_summary",
    "EDREVENT": "edr_event",
    "EDRPRECRASH": "edr_signal",
    "EDRPOSTCRASH": "edr_signal",
    "EDRREST": "edr_restraint",
}


VARIABLE_CATEGORY_DEFAULTS = {
    "crash": {
        "training_roles": (
            "observed_input",
        ),
        "downstream_stages": (
            3,
            4,
            8,
        ),
    },
    "vehicle": {
        "training_roles": (
            "observed_input",
        ),
        "downstream_stages": (
            3,
            4,
            5,
            8,
        ),
    },
    "crash_mechanics": {
        "training_roles": (
            "observed_input",
        ),
        "downstream_stages": (
            3,
            4,
            5,
            8,
        ),
    },
    "occupant": {
        "training_roles": (
            "observed_input",
        ),
        "downstream_stages": (
            3,
            5,
            8,
        ),
    },
    "restraint_and_airbag": {
        "training_roles": (
            "observed_input",
        ),
        "downstream_stages": (
            3,
            5,
            8,
        ),
    },
    "occupant_contact_and_intrusion": {
        "training_roles": (
            "observed_input",
        ),
        "downstream_stages": (
            3,
            5,
            8,
            9,
        ),
    },
    "injury_outcomes": {
        "training_roles": (
            "final_label",
        ),
        "downstream_stages": (
            3,
            8,
            9,
        ),
    },
    "edr": {
        "training_roles": (
            "observed_input",
        ),
        "downstream_stages": (
            3,
            4,
            5,
            6,
            7,
        ),
    },
}


VARIABLE_METADATA_OVERRIDES = {
    # --------------------------------------------------------------
    # Identifiers
    # --------------------------------------------------------------

    "GV.VEHNO": {
        "canonical_name": "vehicle_number",
        "training_roles": ("identifier",),
        "downstream_stages": (3, 4, 5, 8, 9),
    },

    "OCC.VEHNO": {
        "canonical_name": "vehicle_number",
        "training_roles": ("identifier",),
        "downstream_stages": (3, 4, 5, 8, 9),
    },

    "OCC.OCCNO": {
        "canonical_name": "occupant_number",
        "training_roles": ("identifier",),
        "downstream_stages": (3, 5, 8, 9),
    },

    # --------------------------------------------------------------
    # Crash mechanics
    # --------------------------------------------------------------

    "GV.DVTOTAL": {
        "canonical_name": "delta_v_total",
        "unit": "km/h",
        "unit_status": "verified_from_ciss_manual",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    "CDC.DVTOTAL": {
        "canonical_name": "delta_v_total",
        "unit": "km/h",
        "unit_status": "verified_from_ciss_manual",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    "GV.DVLONG": {
        "canonical_name": "delta_v_longitudinal",
        "unit": "km/h",
        "unit_status": "verified_from_ciss_manual",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    "CDC.DVLONG": {
        "canonical_name": "delta_v_longitudinal",
        "unit": "km/h",
        "unit_status": "verified_from_ciss_manual",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    "GV.DVLAT": {
        "canonical_name": "delta_v_lateral",
        "unit": "km/h",
        "unit_status": "verified_from_ciss_manual",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    "CDC.DVLAT": {
        "canonical_name": "delta_v_lateral",
        "unit": "km/h",
        "unit_status": "verified_from_ciss_manual",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    "CDC.PDOF": {
        "canonical_name": "principal_direction_of_force",
        "unit": "degree",
        "unit_status": "verified_from_ciss_manual",
        "expected_range": {
            "minimum": 0,
            "maximum": 360,
        },
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    # --------------------------------------------------------------
    # Occupant attributes
    # --------------------------------------------------------------

    "OCC.AGE": {
        "canonical_name": "occupant_age",
        "unit": "year",
        "unit_status": "verified_from_ciss_manual",
        "expected_range": {
            "minimum": 0,
            "maximum": 120,
        },
    },

    "OCC.HEIGHT": {
        "canonical_name": "occupant_height",
        "unit": "cm",
        "unit_status": "verified_from_ciss_manual",
        "expected_range": {
            "minimum": 30,
            "maximum": 220,
        },
    },

    "OCC.WEIGHT": {
        "canonical_name": "occupant_weight",
        "unit": "kg",
        "unit_status": "verified_from_ciss_manual",
        "expected_range": {
            "minimum": 2,
            "maximum": 275,
        },
    },

    "OCC.BMI": {
        "canonical_name": "occupant_bmi",
        "unit": "kg/m^2",
        "unit_status": "declared_by_variable_definition",
    },

    # --------------------------------------------------------------
    # Injury labels
    # --------------------------------------------------------------

    "OCC.AIS": {
        "canonical_name": "ais",
        "expected_range": {
            "minimum": 0,
            "maximum": 6,
        },
        "training_roles": ("final_label",),
        "downstream_stages": (8, 9),
    },

    "INJURY.AIS": {
        "canonical_name": "ais",
        "expected_range": {
            "minimum": 0,
            "maximum": 6,
        },
        "training_roles": ("final_label",),
        "downstream_stages": (8, 9),
    },

    "OCC.MAIS": {
        "canonical_name": "mais",
        "expected_range": {
            "minimum": 0,
            "maximum": 6,
        },
        "training_roles": ("final_label",),
        "downstream_stages": (8, 9),
    },

    "OCC.ISS": {
        "canonical_name": "iss",
        "expected_range": {
            "minimum": 0,
            "maximum": 75,
        },
        "training_roles": ("final_label",),
        "downstream_stages": (8, 9),
    },

    # --------------------------------------------------------------
    # EDR
    # --------------------------------------------------------------

    "EDREVENT.MAXDVLONG": {
        "canonical_name": "edr_max_delta_v_longitudinal",
        "unit": None,
        "unit_status": "requires_source_verification",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },

    "EDREVENT.MAXDVLAT": {
        "canonical_name": "edr_max_delta_v_lateral",
        "unit": None,
        "unit_status": "requires_source_verification",
        "training_roles": (
            "intermediate_label",
            "physics_parameter",
        ),
        "downstream_stages": (3, 4, 5),
    },
}


PRIMARY_KEYS = {
    "CRASH": (
        "CASEID",
    ),
    "GV": (
        "CASEID",
        "VEHNO",
    ),
    "OCC": (
        "CASEID",
        "VEHNO",
        "OCCNO",
    ),
    "EVENT": (
        "CASEID",
        "EVENTNO",
    ),
    "CDC": (
        "CASEID",
        "VEHNO",
        "EVENTNO",
    ),
    "INJURY": (
        "CASEID",
        "VEHNO",
        "OCCNO",
        "INJNO",
    ),
    "EDREVENT": (
        "CASEID",
        "VEHNO",
        "EDREVENTNO",
    ),
}