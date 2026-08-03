"""
Definitions used by the CISS case auditor.
"""

AUDIT_SCHEMA_VERSION = "2.0"


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