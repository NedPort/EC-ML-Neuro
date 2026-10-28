from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

import pdfplumber

GROUP_NAME = "group3"
RULE_VERSION = "2.3"


@dataclass
class Group3ExtractionResult:
    source_format: str
    source_path: str
    conditions: list[dict[str, Any]]
    values: list[dict[str, Any]]
    explicit_review_evidence: list[dict[str, Any]]
    excluded: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    issues: list[str]

    @property
    def requires_review(self) -> bool:
        return bool(self.unresolved or self.issues)

    def audit_record(self, identity: dict[str, Any]) -> dict[str, Any]:
        return {
            **identity,
            "source_format": self.source_format,
            "source_path": self.source_path,
            "condition_count": len(self.conditions),
            "value_count": len(self.values),
            "explicit_review_evidence_count": len(self.explicit_review_evidence),
            "excluded_count": len(self.excluded),
            "unresolved_count": len(self.unresolved),
            "issue": "|".join(self.issues),
            "rule_version": RULE_VERSION,
        }

BASE = [
    "report_id",
    "case_id",
    "vehicle_number",
    "export_basename",
]


# ============================================================
# I/O
# ============================================================

def read_csv_dict(path: Path):
    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        return list(csv.DictReader(f))


def read_raw_csv(path: Path):
    rows = []

    with path.open(
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:
        reader = csv.reader(f)

        for index, row in enumerate(reader):
            rows.append(
                (
                    index,
                    [clean_cell(cell) for cell in row],
                )
            )

    return rows


def write_csv(
    path: Path,
    rows: list[dict],
    columns: list[str],
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".part"
    )

    with tmp.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)

    tmp.replace(path)


# ============================================================
# Helpers
# ============================================================

def clean_cell(value):
    text = str(
        value
        if value is not None
        else ""
    )

    text = text.replace(
        "\r",
        " ",
    ).replace(
        "\n",
        " ",
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def norm(value):
    return re.sub(
        r"\s+",
        " ",
        clean_cell(value),
    )


def norm_key(value):
    return norm(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            norm(value).casefold(),
        )
    )


def identifier(*parts):
    text = "|".join(
        norm(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode(
            "utf-8"
        )
    ).hexdigest()[:24]


def populated(row):
    return [
        value
        for value in row
        if norm(value)
    ]


def first_populated_with_index(row):
    for index, value in enumerate(row):
        value = norm(value)

        if value:
            return index, value

    return None, ""


def looks_status_value(value):
    text = norm(value).casefold()

    return text in {
        "yes",
        "no",
        "on",
        "off",
        "active",
        "inactive",
        "enabled",
        "disabled",
        "deployed",
        "not deployed",
        "deployment",
        "non-deployment",
        "buckled",
        "unbuckled",
        "present",
        "not present",
        "forward",
        "rearward",
        "valid",
        "invalid",
        "data valid",
        "data invalid",
        "sna",
        "n/a",
        "na",
        "unknown",
    }


def looks_numeric(value):
    text = norm(value)

    if not text:
        return False

    text = text.replace(
        ",",
        "",
    )

    text = re.sub(
        r"\s*(?:"
        r"mph|km/h|kph|m/s|m/s\^2|g|"
        r"ms|msec|milliseconds?|"
        r"sec|seconds?|"
        r"deg|degrees?|deg/s|rad/s|"
        r"%|percent|cycles?"
        r")\s*$",
        "",
        text,
        flags=re.I,
    )

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def looks_value_like(value):
    text = norm(value)

    if not text:
        return False

    if looks_numeric(text):
        return True

    if text.casefold() in {
        "yes",
        "no",
        "on",
        "off",
        "active",
        "inactive",
        "enabled",
        "disabled",
        "buckled",
        "unbuckled",
        "forward",
        "rearward",
        "present",
        "not present",
        "deployed",
        "not deployed",
        "deployment",
        "non-deployment",
        "pretensioner only",
        "n/a",
        "na",
        "sna",
        "unknown",
        "invalid",
        "data invalid",
        "data valid",
    }:
        return True

    return False


# ============================================================
# Source path resolution
# ============================================================

def resolve_csv_path(
    index_row: dict,
    source_root: Path,
):
    raw = norm(
        index_row.get(
            "csv_path",
            ""
        )
    )

    if raw:
        direct = Path(raw)

        if direct.exists():
            return direct

        basename = PureWindowsPath(
            raw
        ).name

        case_id = norm(
            index_row.get(
                "case_id",
                ""
            )
        )

        if case_id and basename:
            case_root = (
                source_root
                / case_id
            )

            if case_root.exists():
                matches = list(
                    case_root.rglob(
                        basename
                    )
                )

                if len(matches) == 1:
                    return matches[0]

                if len(matches) > 1:
                    preferred = [
                        path
                        for path in matches
                        if "cdr_exports"
                        in str(path).casefold()
                    ]

                    if len(preferred) == 1:
                        return preferred[0]

                    return matches[0]

    basename = norm(
        index_row.get(
            "export_basename",
            ""
        )
    )

    case_id = norm(
        index_row.get(
            "case_id",
            ""
        )
    )

    if basename and case_id:
        case_root = (
            source_root
            / case_id
        )

        if case_root.exists():
            matches = list(
                case_root.rglob(
                    basename + ".CSV"
                )
            )

            if not matches:
                matches = list(
                    case_root.rglob(
                        basename + ".csv"
                    )
                )

            if matches:
                return matches[0]

    return None


# ============================================================
# Section detection
# ============================================================

def is_heading_row(row):
    values = populated(row)

    if len(values) != 1:
        return False

    text = values[0]

    if not text:
        return False

    if looks_numeric(text):
        return False

    if len(text) > 220:
        return False

    alpha = [
        char
        for char in text
        if char.isalpha()
    ]

    if alpha:
        uppercase_ratio = (
            sum(
                1
                for char in alpha
                if char.isupper()
            )
            / len(alpha)
        )
    else:
        uppercase_ratio = 0.0

    heading_terms = bool(
        re.search(
            r"\b(?:"
            r"status|deployment|"
            r"non[- ]deployment|"
            r"system|event|restraint|"
            r"occupant|passenger|driver|"
            r"airbag|air bag|pretensioner|"
            r"warning|configuration|"
            r"multiple event|crash"
            r")\b",
            text,
            re.I,
        )
    )

    return (
        uppercase_ratio >= 0.70
        or heading_terms
    )


# ============================================================
# Event hint extraction
# ============================================================

EVENT_PATTERNS = [
    r"\bevent record\s*#?\s*\d+\b",
    r"\bevent\s*#\s*\d+\b",
    r"\bdeployment event\s*#?\s*\d*\b",
    r"\bnon[- ]deployment event\b",
    r"\bmost recent event\b",
    r"\b\d+(?:st|nd|rd|th)\s+prior event\b",
    r"\btrg\s*\d+\b",
]


def extract_event_hint(*texts):
    combined = " | ".join(
        norm(text)
        for text in texts
        if norm(text)
    )

    hints = []

    for pattern in EVENT_PATTERNS:
        for match in re.findall(
            pattern,
            combined,
            flags=re.I,
        ):
            cleaned = norm(match)

            if cleaned.casefold() not in {
                item.casefold()
                for item in hints
            }:
                hints.append(
                    cleaned
                )

    return " | ".join(hints)


# ============================================================
# Group 3 families
# ============================================================

FAMILY_RULES = [
    (
        "deployment_timing",
        [
            r"\btime\b.*\bdeployment command\b",
            r"\btime from algorithm enable\b.*\bdeployment\b",
            r"\bdeployment command criteria met\b.*\b(?:msec|ms|time)\b",
            r"\b1st stage time\b",
            r"\b2nd stage time\b",
            r"\bstage time from algorithm enable\b",
            r"\btime to deploy\b",
        ],
    ),
    (
        "deployment_status",
        [
            r"\bair ?bag\b.*\b(?:deployed|deployment|commanded|status)\b",
            r"\bdeployment\b.*\b(?:status|level|commanded|occurred)\b",
            r"\bfrontal deployment\b",
            r"\bside deployment\b",
            r"\bknee deployment\b",
            r"\bcurtain deployment\b",
            r"\brollover deployment\b",
            r"\bdeployment level\b",
        ],
    ),
    (
        "pretensioner_status",
        [
            r"\bpretensioner\b",
        ],
    ),
    (
        "restraint_status",
        [
            r"\bbelt switch\b",
            r"\bsafety belt\b",
            r"\bseat belt\b",
            r"\brestraint\b",
            r"\bbuckled\b",
            r"\bunbuckled\b",
        ],
    ),
    (
        "occupant_status",
        [
            r"\boccupant\b",
            r"\bpassenger classification\b",
            r"\bpassenger presence\b",
            r"\bseat occupancy\b",
            r"\boccupancy\b",
            r"\bpassenger seat position\b",
            r"\bseat position switch\b",
        ],
    ),
    (
        "event_severity_status",
        [
            r"\bevent severity\b",
            r"\bseverity status\b",
            r"\bcrash severity\b",
        ],
    ),
    (
        "warning_lamp_status",
        [
            r"\bwarning lamp\b",
            r"\bsir warning lamp\b",
            r"\bair ?bag warning\b",
            r"\bmalfunction indicator\b",
        ],
    ),
    (
        "power_event_condition",
        [
            r"\bpower loss\b.*\bevent\b",
            r"\bpower supply status\b",
            r"\bvehicle power mode status\b",
            r"\brun/crank\b",
            r"\bremote start status\b",
        ],
    ),
    (
        "high_voltage_status",
        [
            r"\bhigh voltage disable\b",
            r"\bhigh voltage\b.*\bnotification\b",
        ],
    ),
    (
        "algorithm_status",
        [
            r"\balgorithm active\b",
            r"\balgorithm status\b",
            r"\btime from time zero to algorithm start\b",
            r"\btime from time zero to algorithm reset\b",
            r"\balgorithm enable status\b",
        ],
    ),
    (
        "sensor_validity_status",
        [
            r"\bdata validity\b",
            r"\belectronic data validity\b",
            r"\bvalidity check status\b",
            r"\bdata valid\b",
            r"\bdata invalid\b",
        ],
    ),
    (
        "other_event_condition",
        [
            r"\brsca disable\b",
            r"\bonstar\b.*\b(?:sent|deployment|status)\b",
            r"\bevent condition\b",
        ],
    ),
]


def classify_family(label):
    text = norm(label)

    for family, patterns in FAMILY_RULES:
        if any(
            re.search(
                pattern,
                text,
                re.I,
            )
            for pattern in patterns
        ):
            return family

    return ""


# ============================================================
# Strong exclusions
# ============================================================

GROUP2_PATTERNS = [
    r"\bevent recording complete\b",
    r"\bcrash record locked\b",
    r"\brecording complete\b",
    r"\bmultiple events?\b",
    r"\bevent counter\b",
    r"\brecord status\b",
    r"\bretrieval status\b",
    r"\bassociated events?\b",
    r"\bevents? not recorded\b",
    r"\btime between\b.*\bevents?\b",
    r"\bprevious crash type\b",
    r"\bevent record type\b",
    r"\btrg count\b",
    r"\btrip count\b",
]

GROUP5_PATTERNS = [
    r"\bmaximum\b.*\bdelta[- ]?v\b",
    r"\bmax(?:imum)?\b.*\bvelocity change\b",
    r"\bmaximum\b.*\brecorded vehicle velocity change\b",
    r"\bmaximum\b.*\brecorded velocity change\b",
    r"\btime\b.*\bmaximum\b.*\bdelta[- ]?v\b",
    r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
    r"\bmaximum acceleration\b",
    r"\btime\b.*\bmaximum acceleration\b",
    r"\broll angle peak\b",
    r"\bmaximum\b.*\broll angle\b",
    r"\btime from time zero to trg\b",
    r"\blength of delta[- ]?v\b",
    r"\bclipping time\b",
    r"\baccelerometer range exceeded\b",
    r"\bsensor design range exceeded\b",
    r"\brecorded side\b",
    r"\bpdof\b",
]

GROUP6_PATTERNS = [
    r"\bignition cycles? at investigation\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bsupplier id\b",
    r"\bproduction date\b",
    r"\bmodule\b.*\b(?:id|identifier|number|version)\b",
    r"\bconfiguration\b",
    r"\bconfigured for\b",
    r"\bodometer\b",
    r"\bvehicle mileage\b",
    r"\boperating time\b",
    r"\bdownload\b",
    r"\binvestigation\b",
    r"\bvin\b",
]

GROUP1_PATTERNS = [
    r"\bfilename\b",
    r"\bsaved on\b",
    r"\bimaged with\b",
    r"\breported with\b",
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
    r"\buser entered vin\b",
    r"\bdevice type\b",
]

TIMESERIES_AXIS_PATTERNS = [
    r"^\s*time\s*(?:\([^)]*\))?\s*$",
    r"^\s*times\s*(?:\([^)]*\))?\s*$",
    r"^\s*seconds?\s+before\b",
    r"^\s*seconds?\s+after\b",
    r"^\s*sample\s+count\b",
    r"^\s*buffer address\b",
]


def matches_any(
    text,
    patterns,
):
    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in patterns
    )


def looks_like_timeseries_axis(label):
    text = norm(label)

    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in TIMESERIES_AXIS_PATTERNS
    )


# ============================================================
# Optional Group 5 handoff support
# ============================================================

def load_group5_handoff(path: Path):
    """
    Extract labels that Group 5 explicitly routed to Group 3.

    The handoff is support only; original CSV source remains authoritative.
    """

    support = Counter()

    if not path.exists():
        return support

    for row in read_csv_dict(path):
        label = norm(
            row.get(
                "field_label_raw",
                "",
            )
        )

        if not label:
            continue

        destination = norm(
            row.get(
                "resolution_destination",
                "",
            )
        ).casefold()

        audit_family = norm(
            row.get(
                "audited_family",
                "",
            )
        ).casefold()

        audit_reason = norm(
            row.get(
                "audit_reason",
                "",
            )
        ).casefold()

        if (
            "group3"
            in destination
            or "group3"
            in audit_family
            or any(
                term in audit_reason
                for term in [
                    "deployment",
                    "restraint",
                    "event_status",
                    "event_condition",
                    "algorithm_state",
                ]
            )
        ):
            support[
                norm_key(
                    label
                )
            ] += 1

    return support


# ============================================================
# Scalar field parsing
# ============================================================

def parse_scalar_observation(row):
    nonblank = [
        (
            index,
            norm(value),
        )
        for index, value in enumerate(
            row
        )
        if norm(value)
    ]

    if len(nonblank) < 2:
        return None

    label_index, label = (
        nonblank[0]
    )

    if looks_numeric(
        label
    ):
        return None

    if len(nonblank) > 4:
        return None

    value_index, value = (
        nonblank[-1]
    )

    if value_index == label_index:
        return None

    return {
        "label_index":
            label_index,

        "label":
            label,

        "value_index":
            value_index,

        "value":
            value,

        "populated_cell_count":
            len(nonblank),
    }


# ============================================================
# Candidate scoring
# ============================================================

def score_field(
    label,
    value,
    section_heading,
    handoff_support,
):
    label_text = norm(
        label
    )

    section_text = norm(
        section_heading
    )

    family = classify_family(
        label_text
    )

    score = 0
    evidence = []
    exclusions = []

    if family:
        score += 6
        evidence.append(
            f"family:{family}"
        )

    if looks_value_like(
        value
    ):
        score += 1
        evidence.append(
            "status_or_scalar_value_like"
        )

    if re.search(
        r"\b(?:"
        r"status|deployment|pretensioner|"
        r"belt|restraint|occupant|"
        r"warning|severity|power|"
        r"high voltage|algorithm|validity"
        r")\b",
        label_text,
        re.I,
    ):
        score += 1
        evidence.append(
            "group3_terms"
        )

    if re.search(
        r"\b(?:"
        r"system status|deployment|"
        r"non[- ]deployment|restraint|"
        r"occupant|event status"
        r")\b",
        section_text,
        re.I,
    ):
        score += 1
        evidence.append(
            "group3_section_context"
        )

    support_count = handoff_support.get(
        norm_key(
            label_text
        ),
        0,
    )

    if support_count:
        score += 3
        evidence.append(
            "group5_to_group3_handoff_support"
        )

    # Explicit exclusions
    if looks_like_timeseries_axis(
        label_text
    ):
        exclusions.append(
            "group4_timeseries_axis"
        )

    if matches_any(
        label_text,
        GROUP2_PATTERNS,
    ):
        exclusions.append(
            "group2_record_structure"
        )

    if matches_any(
        label_text,
        GROUP5_PATTERNS,
    ):
        exclusions.append(
            "group5_crash_measurement"
        )

    if matches_any(
        label_text,
        GROUP6_PATTERNS,
    ):
        exclusions.append(
            "group6_technical_or_investigation"
        )

    if matches_any(
        label_text,
        GROUP1_PATTERNS,
    ):
        exclusions.append(
            "group1_report_metadata"
        )

    if exclusions:
        decision = "excluded_overlap"

    elif score >= 6:
        decision = "candidate"

    elif score >= 3:
        decision = "review"

    else:
        decision = "not_group3"

    return {
        "family":
            family
            or "other_event_condition",

        "score":
            score,

        "decision":
            decision,

        "evidence":
            evidence,

        "exclusions":
            exclusions,

        "handoff_support_count":
            support_count,
    }



def has(text, pattern):
    return bool(
        re.search(
            pattern,
            norm(text),
            re.I,
        )
    )

def refine_candidate_family(label, old_family):
    text = norm(label)

    # --------------------------------------------------------
    # Group 5 companion overlap: keep outside Group 3
    # --------------------------------------------------------

    if has(
        text,
        r"\bpower supply status\b.*\bmax(?:imum)?\.?\s*(?:delta[- ]?v|velocity change)\b",
    ):
        return (
            "exclude",
            "group5_measurement_context",
            "excluded_non_group3",
            "power_status_is_context_for_group5_maximum_delta_v",
        )

    # --------------------------------------------------------
    # Record structure overlap
    # --------------------------------------------------------

    if has(
        text,
        r"\brecording status\b",
    ):
        return (
            "exclude",
            "group2_record_structure",
            "excluded_non_group3",
            "recording_status_belongs_to_group2",
        )

    # --------------------------------------------------------
    # Technical/readout overlap
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"power[- ]on cycle at reading|"
        r"ignition cycles? at investigation|"
        r"supplier id|production date|"
        r"serial number|part number|"
        r"software version"
        r")\b",
    ):
        return (
            "exclude",
            "group6_technical",
            "excluded_non_group3",
            "technical_or_readout_metadata",
        )

    # --------------------------------------------------------
    # Pretensioner timing before generic pretensioner status
    # --------------------------------------------------------

    if (
        has(text, r"\bpretensioner\b")
        and has(
            text,
            r"\b(?:time|time to|time from|fire|deployment loop command criteria met)\b",
        )
    ):
        return (
            "accept",
            "pretensioner_timing",
            "accepted_group3_candidate",
            "pretensioner_activation_or_deployment_timing",
        )

    # --------------------------------------------------------
    # Other restraint-device timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:"
            r"belt[- ]load limiter|"
            r"adaptive load limiter|"
            r"active head ?rest(?:raint)?|"
            r"inflatable knee bolster|"
            r"knee bolster|"
            r"inflatable seatbelt|"
            r"adaptive steering column|"
            r"can(?:n)?ister vent|"
            r"battery disconnect|"
            r"rollover protection system"
            r")\b",
        )
        and has(
            text,
            r"\b(?:time|time to|time from|fire|deploy|deployment)\b",
        )
    ):
        return (
            "accept",
            "restraint_deployment_timing",
            "accepted_group3_candidate",
            "restraint_or_protection_device_activation_timing",
        )

    # --------------------------------------------------------
    # General deployment timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:deployment|deploy|air ?bag)\b",
        )
        and has(
            text,
            r"\b(?:"
            r"time|time to|time from|"
            r"criteria met|1st stage time|2nd stage time"
            r")\b",
        )
    ):
        return (
            "accept",
            "deployment_timing",
            "accepted_group3_candidate",
            "deployment_command_or_stage_timing",
        )

    # Event-severity timing should not remain generic severity status.
    if (
        has(
            text,
            r"\bevent severity\b",
        )
        and has(
            text,
            r"\btime\b",
        )
    ):
        return (
            "accept",
            "event_severity_timing",
            "accepted_group3_candidate",
            "event_severity_threshold_timing",
        )

    # Warning lamp timing/history remains Group 3, but distinguish it.
    if (
        has(
            text,
            r"\bwarning lamp\b|\bmalfunction indicator lamp\b|\bMIL\b",
        )
        and has(
            text,
            r"\b(?:time|minutes?|seconds?|cycles?)\b",
        )
    ):
        return (
            "accept",
            "warning_lamp_history",
            "accepted_group3_candidate",
            "warning_lamp_time_or_cycle_history",
        )

    # Configuration of restraint hardware is not event state.
    if has(
        text,
        r"\bconfigured\b.*\b(?:belt|restraint|head restraint|pretensioner)\b",
    ):
        return (
            "exclude",
            "group6_configuration",
            "excluded_non_group3",
            "hardware_configuration_not_event_state",
        )

    # Default: preserve discovery family.
    return (
        "accept",
        norm(old_family) or "other_event_condition",
        "accepted_group3_candidate",
        "strong_group3_discovery_pattern",
    )

def classify_review(label):
    text = norm(label)

    # --------------------------------------------------------
    # Group 2 exclusions
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"complete status of event data record|"
        r"recording status|"
        r"deployment command counter|"
        r"event counter|"
        r"record complete|"
        r"recording complete"
        r")\b",
    ):
        return (
            "exclude",
            "group2_record_structure",
            "excluded_non_group3",
            "record_or_counter_structure",
        )

    # --------------------------------------------------------
    # Group 6 exclusions
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"power[- ]on cycle at reading|"
        r"lifetime operating timer|"
        r"production date|supplier id|"
        r"part number|serial number|"
        r"software version"
        r")\b",
    ):
        return (
            "exclude",
            "group6_technical",
            "excluded_non_group3",
            "technical_or_readout_metadata",
        )

    # --------------------------------------------------------
    # Seat-track status
    # --------------------------------------------------------

    if has(
        text,
        r"\bseat track\b.*\b(?:position|forward|foremost|status|fault)\b",
    ):
        return (
            "accept",
            "seat_track_status",
            "recovered_group3_measurement",
            "seat_track_event_state",
        )

    # --------------------------------------------------------
    # Sensor deployment discrimination/safing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:"
            r"discriminating deployment|"
            r"safing deployment"
            r")\b",
        )
    ):
        return (
            "accept",
            "deployment_sensor_status",
            "recovered_group3_measurement",
            "sensor_discriminating_or_safing_deployment_state",
        )

    # --------------------------------------------------------
    # Device deployment/status/timing
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:"
            r"belt[- ]load limiter|"
            r"adaptive load limiter|"
            r"active head ?rest(?:raint)?|"
            r"inflatable knee bolster|"
            r"knee bolster|"
            r"inflatable seatbelt|"
            r"adaptive steering column|"
            r"battery disconnect|"
            r"rollover protection system|"
            r"can(?:n)?ister vent|"
            r"side seat airbag|"
            r"active glove box"
            r")\b",
        )
    ):
        if has(
            text,
            r"\b(?:time|fire|deploy|deployment)\b",
        ):
            return (
                "accept",
                "restraint_deployment_timing",
                "recovered_group3_measurement",
                "protection_device_activation_or_deployment",
            )

        return (
            "accept",
            "restraint_activation_status",
            "recovered_group3_measurement",
            "protection_device_activation_state",
        )

    # --------------------------------------------------------
    # Algorithm timing/status
    # --------------------------------------------------------

    if has(
        text,
        r"\btime\b.*\balgorithm\b.*\b(?:reset|wake[- ]?up|start)\b",
    ):
        return (
            "accept",
            "algorithm_timing",
            "recovered_group3_measurement",
            "algorithm_event_timing",
        )

    # --------------------------------------------------------
    # Sensor faults/state at algorithm wake-up
    # --------------------------------------------------------

    if (
        has(
            text,
            r"\b(?:sensor|seat track)\b.*\bfault\b.*\balgorithm wake[- ]?up\b",
        )
    ):
        return (
            "accept",
            "sensor_fault_status",
            "recovered_group3_measurement",
            "sensor_fault_state_at_algorithm_wakeup",
        )

    # --------------------------------------------------------
    # Event electrical state at algorithm wake-up
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"key on timer|"
        r"battery voltage|"
        r"energy reserve voltage"
        r")\b.*\balgorithm wake[- ]?up\b",
    ):
        return (
            "accept",
            "algorithm_wakeup_condition",
            "recovered_group3_measurement",
            "event_electrical_state_at_algorithm_wakeup",
        )

    # --------------------------------------------------------
    # Explicit seat/restraint/occupant status
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:"
        r"seat track position switch|"
        r"occupancy status|"
        r"occupant classification|"
        r"passenger classification|"
        r"belt switch|safety belt"
        r")\b",
    ):
        return (
            "accept",
            "occupant_restraint_status",
            "recovered_group3_measurement",
            "occupant_or_restraint_event_state",
        )

    # --------------------------------------------------------
    # Warning/brake status
    # --------------------------------------------------------

    if has(
        text,
        r"\b(?:warning status|warning lamp|brake system warning)\b",
    ):
        return (
            "accept",
            "warning_lamp_status",
            "recovered_group3_measurement",
            "warning_state",
        )

    # --------------------------------------------------------
    # Fuel cutoff event decision timing
    # --------------------------------------------------------

    if has(
        text,
        r"\bfuel cutoff algorithm decision time\b",
    ):
        return (
            "accept",
            "algorithm_timing",
            "recovered_group3_measurement",
            "fuel_cutoff_algorithm_event_timing",
        )

    # --------------------------------------------------------
    # Freeze signal factors are potentially meaningful event conditions
    # but model-specific; preserve for explicit review.
    # --------------------------------------------------------

    if has(
        text,
        r"\bfreeze signal factor\b",
    ):
        return (
            "review",
            "other_event_condition",
            "remaining_review",
            "manufacturer_specific_freeze_signal_factor",
        )

    return (
        "review",
        "unresolved_review",
        "remaining_review",
        "no_safe_group3_resolution_rule",
    )


def resolve_row(row):
    label = norm(row.get("field_label_raw", ""))

    # Direct deployment-state fields.
    if re.fullmatch(
        r"Side Seat Airbags Deployment, (?:Left|Right)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_status",
            "explicit_side_airbag_deployment_state",
        )

    # Manufacturer-specific freeze-signal factors are event-state variables.
    # They are tied to deployment discriminators/CSA logic and appear under
    # SYSTEM STATUS AT EVENT. Preserve the raw OFF value exactly.
    if re.fullmatch(
        r"Freeze Signal Factor, Side CSA Deployment, "
        r"(?:Left|Right) Side",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_sensor_status",
            "deployment_freeze_signal_factor_at_event",
        )

    if re.fullmatch(
        r"Freeze Signal Factor, Rollover CSA Deployment",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_sensor_status",
            "rollover_deployment_freeze_signal_factor_at_event",
        )

    # High-voltage battery deactivation command is event/deployment behavior.
    # Even when raw value is "Not Deployed", preserve it as a timing/status
    # observation rather than forcing a numeric value.
    if re.fullmatch(
        r"High-Voltage Battery Deactivation, Time to Deployment \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "high_voltage_deactivation_timing",
            "high_voltage_battery_deactivation_deployment_timing",
        )

    if re.fullmatch(
        r"Belt tensioner deployment, time to 1st stage, driver \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "pretensioner_timing",
            "belt_tensioner_first_stage_deployment_timing",
        )

    if re.fullmatch(
        r"Driver Center Inboard Time From Time Zero to "
        r"Deployment Loop Command Criteria Met \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_timing",
            "deployment_loop_command_criteria_timing",
        )

    if re.fullmatch(
        r"Time From Time Zero to Deployment \(Rollover\) \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "deployment_timing",
            "rollover_deployment_timing",
        )

    if re.fullmatch(
        r"Active Head-Rest, Time to Deployment, "
        r"Front (?:Passenger|Driver) \(ms\)",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "restraint_deployment_timing",
            "active_head_restraint_deployment_timing",
        )

    if re.fullmatch(
        r"Tire Pressure Monitoring System Warning Light Status",
        label,
        flags=re.I,
    ):
        return (
            "accept",
            "warning_lamp_status",
            "event_warning_light_state",
        )

    return (
        "review",
        "unresolved_review",
        "no_explicit_resolution_rule",
    )



# Reviewed Group-5 -> Group-3 handoff labels from the validated historical workflow.
# These are label-level rules, not report IDs or dataset-specific record IDs.
VALIDATED_G3_HANDOFF_LABELS = {
    'algorithm active frontal',
    'algorithm active rear',
    'algorithm active rollover',
    'algorithm active side',
    'driver knee deployment loop commanded',
    'event severity status frontal stage 1',
    'event severity status frontal stage 2',
    'event severity status left side',
    'event severity status rear',
    'event severity status right side',
    'event severity status rollover',
    'onstar deployment status data sent',
    'onstar sdm recorded vehicle velocity change data sent',
    'passenger knee deployment loop commanded',
    'passenger seat occupancy status',
    'roll angle rollover deployment deg',
    'rsca disable switch',
    'safety belt status driver',
    'safety belt status front passenger',
    'time from time zero to algorithm reset front ms',
    'time from time zero to algorithm reset rear ms',
    'time from time zero to algorithm reset rollover ms',
    'time from time zero to algorithm reset side ms',
    'time from time zero to algorithm start front ms',
    'time from time zero to algorithm start rear ms',
    'time from time zero to algorithm start side ms',
}

def _validated_handoff_counter():
    return Counter({label: 1 for label in VALIDATED_G3_HANDOFF_LABELS})


stable_id = identifier

PDF_SEPARATOR_PATTERNS = [
    r"^(?P<label>.+?)\s*[:=]\s*(?P<value>.+?)$",
    r"^(?P<label>.+?)\s{2,}(?P<value>\S.+?)$",
]

PDF_UNIT_OR_VALUE_RE = re.compile(
    r"""
    (?:
        [-+]?\d+(?:\.\d+)?
        (?:\s*(?:ms|msec|sec|s|V|volts?|cycles?|%|mph|km/h|kph))?
        |
        Yes|No|ON|OFF|Active|Inactive|Enabled|Disabled|
        Deployed|Not\ Deployed|Deployment|Non-Deployment|
        Buckled|Unbuckled|Present|Not\ Present|
        Forward|Rearward|Valid|Invalid|SNA|N/A|NA|Unknown
    )
    """,
    re.I | re.X,
)


def pdf_split_line(line):
    text = norm(line)

    if not text:
        return None

    for pattern in PDF_SEPARATOR_PATTERNS:
        match = re.match(pattern, text, flags=re.I)

        if match:
            label = norm(match.group("label"))
            value = norm(match.group("value"))

            if label and value and len(label) <= 260:
                return label, value, "separator"

    # Conservative fallback:
    # split at final recognizable scalar/status token only.
    matches = list(PDF_UNIT_OR_VALUE_RE.finditer(text))

    if not matches:
        return None

    final = matches[-1]

    if final.end() != len(text):
        return None

    label = norm(text[:final.start()])
    value = norm(final.group(0))

    if not label or not value:
        return None

    if len(label) > 260:
        return None

    return label, value, "terminal_value"


# ============================================================
# Event hints / section context
# ============================================================

PDF_EVENT_PATTERNS = [
    r"\bevent record\s*#?\s*\d+\b",
    r"\bevent\s*#\s*\d+\b",
    r"\bdeployment event\s*#?\s*\d*\b",
    r"\bnon[- ]deployment event\b",
    r"\bmost recent event\b",
    r"\b\d+(?:st|nd|rd|th)\s+prior event\b",
]


def pdf_extract_event_hint(*texts):
    combined = " | ".join(
        norm(x)
        for x in texts
        if norm(x)
    )

    hints = []

    for pattern in PDF_EVENT_PATTERNS:
        for match in re.findall(pattern, combined, flags=re.I):
            cleaned = norm(match)

            if cleaned.casefold() not in {
                x.casefold()
                for x in hints
            }:
                hints.append(cleaned)

    return " | ".join(hints)


def pdf_looks_heading(line):
    text = norm(line)

    if not text:
        return False

    if len(text) > 180:
        return False

    if ":" in text or "=" in text:
        return False

    if looks_numeric(text):
        return False

    alpha = [c for c in text if c.isalpha()]

    if not alpha:
        return False

    upper_ratio = sum(c.isupper() for c in alpha) / len(alpha)

    return (
        upper_ratio >= 0.70
        or bool(
            re.search(
                r"\b(?:"
                r"system status|deployment|non[- ]deployment|"
                r"restraint|occupant|air ?bag|pretensioner|"
                r"warning|event data|crash event"
                r")\b",
                text,
                re.I,
            )
        )
    )


# ============================================================
# Group 3 classification
# ============================================================

PDF_FAMILY_RULES = [
    (
        "pretensioner_timing",
        [
            r"\bpretensioner\b.*\b(?:time|fire|deployment)\b",
            r"\bbelt tensioner\b.*\btime\b",
        ],
    ),
    (
        "restraint_deployment_timing",
        [
            r"\b(?:"
            r"load limiter|head[- ]?rest|knee bolster|"
            r"inflatable seatbelt|adaptive steering column|"
            r"battery disconnect|rollover protection system"
            r")\b.*\b(?:time|deploy|deployment|fire)\b",
        ],
    ),
    (
        "deployment_timing",
        [
            r"\bdeployment\b.*\b(?:time|criteria met)\b",
            r"\btime\b.*\bdeployment\b",
            r"\b1st stage time\b",
            r"\b2nd stage time\b",
        ],
    ),
    (
        "pretensioner_status",
        [
            r"\bpretensioner\b",
            r"\bbelt tensioner\b",
        ],
    ),
    (
        "deployment_status",
        [
            r"\bair ?bag\b.*\b(?:deployed|deployment|status|commanded)\b",
            r"\bdeployment\b.*\b(?:status|level|commanded|occurred)\b",
            r"\bside seat airbags? deployment\b",
            r"\bfrontal deployment\b",
            r"\brollover deployment\b",
        ],
    ),
    (
        "restraint_status",
        [
            r"\bseat belt\b",
            r"\bsafety belt\b",
            r"\bbelt switch\b",
            r"\brestraint\b",
            r"\bbuckled\b",
            r"\bunbuckled\b",
        ],
    ),
    (
        "occupant_status",
        [
            r"\boccupant\b",
            r"\bpassenger classification\b",
            r"\bpassenger presence\b",
            r"\boccupancy\b",
            r"\bseat track\b",
            r"\bseat position\b",
        ],
    ),
    (
        "warning_lamp_status",
        [
            r"\bwarning lamp\b",
            r"\bwarning light\b",
            r"\bmalfunction indicator\b",
        ],
    ),
    (
        "event_severity_status",
        [
            r"\bevent severity\b",
            r"\bseverity status\b",
            r"\bcrash severity\b",
        ],
    ),
    (
        "high_voltage_status",
        [
            r"\bhigh[- ]?voltage\b",
            r"\bhigh voltage disable\b",
        ],
    ),
    (
        "power_event_condition",
        [
            r"\bpower loss\b",
            r"\bpower supply status\b",
            r"\bvehicle power mode\b",
            r"\bbattery voltage\b.*\balgorithm wake[- ]?up\b",
            r"\benergy reserve voltage\b.*\balgorithm wake[- ]?up\b",
        ],
    ),
    (
        "algorithm_timing",
        [
            r"\btime\b.*\balgorithm\b.*\b(?:wake[- ]?up|reset|start|decision)\b",
            r"\bfuel cutoff algorithm decision time\b",
        ],
    ),
    (
        "algorithm_status",
        [
            r"\balgorithm active\b",
            r"\balgorithm status\b",
            r"\balgorithm enable\b",
        ],
    ),
    (
        "deployment_sensor_status",
        [
            r"\b(?:discriminating deployment|safing deployment)\b",
            r"\bfreeze signal factor\b.*\bdeployment\b",
        ],
    ),
    (
        "sensor_fault_status",
        [
            r"\bsensor\b.*\bfault\b",
        ],
    ),
    (
        "other_event_condition",
        [
            r"\bevent condition\b",
            r"\brsca disable\b",
            r"\bonstar\b.*\bstatus\b",
        ],
    ),
]


PDF_GROUP2_PATTERNS = [
    r"\bevent recording complete\b",
    r"\brecording status\b",
    r"\bcrash record locked\b",
    r"\brecord complete\b",
    r"\bevent counter\b",
    r"\bdeployment command counter\b",
    r"\bretrieval status\b",
    r"\bmultiple events?\b",
    r"\btime between\b.*\bevents?\b",
]

PDF_GROUP5_PATTERNS = [
    r"\bmaximum\b.*\bdelta[- ]?v\b",
    r"\bmax(?:imum)?\b.*\bvelocity change\b",
    r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
    r"\bmaximum acceleration\b",
    r"\btime\b.*\bmaximum acceleration\b",
    r"\broll angle peak\b",
    r"\blength of delta[- ]?v\b",
    r"\bclipping time\b",
    r"\baccelerometer range exceeded\b",
    r"\bsensor design range exceeded\b",
    r"\bpdof\b",
]

PDF_GROUP6_PATTERNS = [
    r"\bignition cycles? at investigation\b",
    r"\bpower[- ]on cycle at reading\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bsupplier id\b",
    r"\bproduction date\b",
    r"\bmodule\b.*\b(?:id|identifier|number|version)\b",
    r"\bodometer\b",
    r"\bvehicle mileage\b",
    r"\boperating time\b",
    r"\binvestigation\b",
    r"\bvin\b",
]

PDF_GROUP1_PATTERNS = [
    r"\bfilename\b",
    r"\bsaved on\b",
    r"\bimaged with\b",
    r"\breported with\b",
    r"\bcrash date\b",
    r"\bedr data imaging date\b",
]


def pdf_classify_family(label):
    text = norm(label)

    for family, patterns in PDF_FAMILY_RULES:
        if any(
            re.search(pattern, text, re.I)
            for pattern in patterns
        ):
            return family

    return ""


def pdf_score_field(label, value, section):
    family = pdf_classify_family(label)
    score = 0
    evidence = []
    exclusions = []

    if family:
        score += 6
        evidence.append(f"family:{family}")

    if looks_status_value(value):
        score += 1
        evidence.append("status_value")

    elif looks_numeric(value):
        score += 1
        evidence.append("scalar_value")

    if re.search(
        r"\b(?:"
        r"deployment|pretensioner|belt|restraint|"
        r"occupant|warning|severity|power|"
        r"high[- ]?voltage|algorithm|fault|status"
        r")\b",
        norm(label),
        re.I,
    ):
        score += 1
        evidence.append("group3_terms")

    if re.search(
        r"\b(?:"
        r"system status|deployment|non[- ]deployment|"
        r"restraint|occupant|event status"
        r")\b",
        norm(section),
        re.I,
    ):
        score += 1
        evidence.append("group3_section_context")

    if matches_any(label, PDF_GROUP2_PATTERNS):
        exclusions.append("group2_record_structure")

    if matches_any(label, PDF_GROUP5_PATTERNS):
        exclusions.append("group5_crash_measurement")

    if matches_any(label, PDF_GROUP6_PATTERNS):
        exclusions.append("group6_technical_or_investigation")

    if matches_any(label, PDF_GROUP1_PATTERNS):
        exclusions.append("group1_report_metadata")

    if exclusions:
        decision = "excluded_overlap"
    elif score >= 6:
        decision = "candidate"
    elif score >= 3:
        decision = "review"
    else:
        decision = "not_group3"

    return {
        "family":
            family or "other_event_condition",
        "score":
            score,
        "decision":
            decision,
        "evidence":
            evidence,
        "exclusions":
            exclusions,
    }



EXPLANATORY_LABELS = {
    "-Driver's and Passenger's Belt Switch Circuit Status indicates the status of the seat belt switch circuit, except",
    "- Frontal Airbag Disable Indicator Status",
    "- Airbag Warning Lamp, Status",
    "- Safety Belt Status",
    "- Seat Track Position Switch",
    "- Occupant Size Classification, Front Passenger",
    "- Time to Deployment",
}


def pdf_audit_candidate(row):
    label = norm(row.get("field_label_raw", ""))
    value = norm(row.get("field_value_raw", ""))
    family = norm(row.get("candidate_family", ""))

    if label in EXPLANATORY_LABELS:
        return (
            "exclude",
            family or "documentation",
            "documentation",
            "explanatory_or_definition_line_misparsed_as_field",
        )

    if label.casefold() == (
        "power supply status at the time of max. delta-v"
    ).casefold():
        return (
            "exclude",
            "group5_measurement_context",
            "group5",
            "power_supply_status_is_context_for_maximum_delta_v",
        )

    if (
        label.casefold()
        == "passenger classification status at event enable classificati".casefold()
        and value.casefold() == "on"
    ):
        return (
            "exclude",
            "occupant_status",
            "parse_artifact",
            "terminal_on_split_from_word_classification",
        )

    return (
        "accept",
        family or "other_event_condition",
        "group3",
        "valid_group3_pdf_candidate",
    )

def pdf_audit_review(row):
    label = norm(row.get("field_label_raw", ""))

    if label == "Rollover Sensor Status Data":
        return (
            "accept",
            "sensor_status",
            "group3",
            "rollover_sensor_status_is_event_status_information",
        )

    if label.startswith(
        "Time (sec) Status Status (Mpa) (m/s^2) (deg/s) (degrees) Shift Positi"
    ):
        return (
            "exclude",
            "group4_timeseries_header",
            "group4",
            "time_series_table_header_not_scalar_group3_field",
        )

    if label == "Longitudinal velocity change during algorithm run time (MPH)":
        return (
            "exclude",
            "group5_scalar_measurement",
            "group5",
            "scalar_velocity_change_measurement",
        )

    if label == "Algorithm run time (msec)":
        return (
            "exclude",
            "group5_scalar_measurement",
            "group5",
            "scalar_event_runtime_measurement",
        )

    if label.startswith(
        'The status "Data not Available" is reported if the ACM was unable to store the data element'
    ):
        return (
            "exclude",
            "documentation",
            "documentation",
            "explanatory_prose_not_structured_measurement",
        )

    return (
        "review",
        "unresolved_review",
        "review",
        "no_safe_resolution_rule",
    )



MISSING_VALUES = {
    "", "n/a", "na", "sna", "not available", "not applicable",
    "unknown", "invalid", "data not available", "no data",
}

NUMERIC_RE = re.compile(
    r"""^\s*(?P<num>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*
    (?P<unit>%|mph|km/h|kph|m/s|m/s\^2|m/s2|g|ms|msec|milliseconds?|
    sec|seconds?|s|V|volts?|cycles?|min|minutes?|deg|degrees?)?\s*$""",
    re.I | re.X,
)

def is_missing_like(value: Any) -> bool:
    return norm(value).casefold() in MISSING_VALUES

def parse_numeric_scalar(value: Any):
    text = norm(value)
    if not text or is_missing_like(text):
        return None, "", "missing_or_unavailable"
    match = NUMERIC_RE.fullmatch(text.replace(",", ""))
    if not match:
        return None, "", "textual_or_non_scalar"
    try:
        number = float(match.group("num"))
    except Exception:
        return None, "", "numeric_parse_failed"
    return number, norm(match.group("unit") or ""), "numeric_scalar"

def raw_unit_from_label(label: Any) -> str:
    text = norm(label)
    for pattern in [r"\(([^()]*)\)\s*$", r",\s*([^,]+)\s*$"]:
        match = re.search(pattern, text)
        if match:
            candidate = norm(match.group(1))
            if re.fullmatch(
                r"(?:ms|msec|milliseconds?|sec|seconds?|s|V|volts?|cycles?|min|minutes?|%|mph|km/h|kph|deg|degrees?)",
                candidate, re.I,
            ):
                return candidate
    return ""

def _condition_rows(observation: dict[str, Any], family: str, source_format: str):
    raw_value = norm(observation.get("field_value_raw", ""))
    raw_label = norm(observation.get("field_label_raw", ""))
    numeric_value, value_unit, parse_status = parse_numeric_scalar(raw_value)
    raw_unit = value_unit or raw_unit_from_label(raw_label)

    if source_format == "csv":
        cid = "g3csv_" + identifier(
            observation.get("report_id", ""), observation.get("case_id", ""),
            observation.get("vehicle_number", ""), observation.get("export_basename", ""),
            observation.get("source_path", ""), observation.get("source_record_index", ""),
            raw_label, raw_value, family,
        )
    else:
        cid = "g3pdf_" + identifier(
            observation.get("report_id", ""), observation.get("case_id", ""),
            observation.get("vehicle_number", ""), observation.get("export_basename", ""),
            observation.get("source_path", ""), observation.get("pdf_page", ""),
            observation.get("pdf_line_number", ""), raw_label, raw_value, family,
        )

    registry = {
        "group3_condition_id": cid,
        "source_candidate_id": observation.get("group3_candidate_id", ""),
        "report_id": observation.get("report_id", ""),
        "case_id": observation.get("case_id", ""),
        "vehicle_number": observation.get("vehicle_number", ""),
        "export_basename": observation.get("export_basename", ""),
        "source_format": source_format,
        "source_path": observation.get("source_path", ""),
        "source_record_index": observation.get("source_record_index", "") if source_format == "csv" else "",
        "pdf_page": observation.get("pdf_page", "") if source_format == "pdf" else "",
        "pdf_line_number": observation.get("pdf_line_number", "") if source_format == "pdf" else "",
        "source_section_heading": observation.get("source_section_heading", ""),
        "event_hint": observation.get("event_hint", ""),
        "source_line_raw": observation.get("source_line_raw", "") if source_format == "pdf" else "",
        "family": family,
        "field_label_raw": raw_label,
        "field_value_raw": raw_value,
        "raw_unit": raw_unit,
        "event_link_status": observation.get("event_link_status", "") or ("source_hint_only" if observation.get("event_hint") else "not_linked"),
        "semantic_normalization_status": "not_normalized",
        "unit_conversion_status": "not_converted",
        "rule_version": RULE_VERSION,
    }
    value = {
        "group3_condition_id": cid,
        "field_value_raw": raw_value,
        "numeric_value": "" if numeric_value is None else repr(numeric_value),
        "raw_unit": raw_unit,
        "value_parse_status": parse_status,
        "missing_or_unavailable": "true" if is_missing_like(raw_value) else "false",
        "rule_version": RULE_VERSION,
    }
    review = None
    if parse_status == "textual_or_non_scalar":
        review = {
            **registry,
            **value,
            "review_reason": "textual_or_non_scalar_explicit_evidence",
        }
    return registry, value, review




def select_group3_source(*, csv_path=None, pdf_path=None):
    if csv_path:
        p = Path(csv_path)
        if p.is_file():
            return "csv", p
    if pdf_path:
        p = Path(pdf_path)
        if p.is_file():
            return "pdf", p
    raise FileNotFoundError("No usable CSV or PDF source is available for this report.")

def _base_identity(identity):
    return {key: identity.get(key, "") for key in BASE}

def extract_group3_csv(path: str | Path, identity: dict[str, Any]) -> Group3ExtractionResult:
    path = Path(path)
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = [(i, [clean_cell(c) for c in row]) for i, row in enumerate(csv.reader(f))]

    conditions=[]; values=[]; reviews=[]; excluded=[]; unresolved=[]; issues=[]
    current_section = ""
    handoff_support = _validated_handoff_counter()

    for row_index, row in rows:
        if is_heading_row(row):
            current_section = populated(row)[0]
            continue
        parsed = parse_scalar_observation(row)
        if parsed is None:
            continue
        label=parsed["label"]; value=parsed["value"]
        result=score_field(label, value, current_section, handoff_support)
        if result["decision"] == "not_group3":
            continue
        event_hint=extract_event_hint(current_section, label)
        obs={
            **_base_identity(identity),
            "group3_candidate_id":"g3csv_"+identifier(identity.get("report_id",""),row_index,label,value),
            "source_format":"csv", "source_path":str(path),
            "source_record_index":row_index, "source_section_heading":current_section,
            "event_hint":event_hint, "field_label_raw":label, "field_value_raw":value,
            "event_link_status":"source_hint_only" if event_hint else "not_linked",
            "candidate_family":result["family"],
        }

        if result["decision"] == "excluded_overlap":
            excluded.append(obs); continue

        if result["decision"] == "candidate":
            decision,family,_,reason = refine_candidate_family(label,result["family"])
        else:
            decision,family,_,reason = classify_review(label)
            if decision == "review":
                decision2,family2,reason2 = resolve_row({"field_label_raw":label})
                if decision2 == "accept":
                    decision,family,reason = decision2,family2,reason2

        if decision == "exclude":
            excluded.append({**obs,"audit_reason":reason}); continue
        if decision != "accept":
            unresolved.append({**obs,"review_reason":reason}); continue

        reg,val,rev=_condition_rows(obs,family,"csv")
        conditions.append(reg); values.append(val)
        if rev is not None: reviews.append(rev)

    return Group3ExtractionResult("csv",str(path),conditions,values,reviews,excluded,unresolved,issues)

def extract_group3_pdf(path: str | Path, identity: dict[str, Any]) -> Group3ExtractionResult:
    path=Path(path)
    conditions=[]; values=[]; reviews=[]; excluded=[]; unresolved=[]; issues=[]
    with pdfplumber.open(path) as pdf:
        current_section=""
        for page_index,page in enumerate(pdf.pages,start=1):
            text=page.extract_text() or ""
            lines=[norm(line) for line in text.splitlines() if norm(line)]
            for line_index,line in enumerate(lines,start=1):
                if pdf_looks_heading(line):
                    current_section=line; continue
                parsed=pdf_split_line(line)
                if parsed is None: continue
                label,value,split_method=parsed
                result=pdf_score_field(label,value,current_section)
                if result["decision"] == "not_group3": continue
                event_hint=pdf_extract_event_hint(current_section,label,line)
                obs={
                    **_base_identity(identity),
                    "group3_candidate_id":"g3pdf_"+identifier(identity.get("report_id",""),page_index,line_index,label,value),
                    "source_format":"pdf", "source_path":str(path),
                    "pdf_page":page_index, "pdf_line_number":line_index,
                    "source_section_heading":current_section, "event_hint":event_hint,
                    "source_line_raw":line, "field_label_raw":label, "field_value_raw":value,
                    "event_link_status":"source_hint_only" if event_hint else "not_linked",
                    "candidate_family":result["family"],
                }
                if result["decision"] == "excluded_overlap":
                    excluded.append(obs); continue
                if result["decision"] == "candidate":
                    decision,family,route,reason=pdf_audit_candidate(obs)
                else:
                    decision,family,route,reason=pdf_audit_review(obs)
                if decision == "exclude":
                    excluded.append({**obs,"audit_reason":reason}); continue
                if decision != "accept":
                    unresolved.append({**obs,"review_reason":reason}); continue
                reg,val,rev=_condition_rows(obs,family,"pdf")
                conditions.append(reg); values.append(val)
                if rev is not None: reviews.append(rev)
    return Group3ExtractionResult("pdf",str(path),conditions,values,reviews,excluded,unresolved,issues)

def extract_group3_report(*, identity: dict[str, Any], csv_path=None, pdf_path=None) -> Group3ExtractionResult:
    source_format, source_path = select_group3_source(csv_path=csv_path,pdf_path=pdf_path)
    if source_format == "csv":
        return extract_group3_csv(source_path,identity)
    return extract_group3_pdf(source_path,identity)
