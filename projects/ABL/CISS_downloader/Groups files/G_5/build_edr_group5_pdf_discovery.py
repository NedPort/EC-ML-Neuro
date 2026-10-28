"""
Discover Group 5 measurements in PDF-only EDR reports.

Inputs
------
data/processed/edr/group1_v4/report_index.csv

Optional Group 5 CSV vocabulary support
---------------------------------------
data/processed/edr/group5_csv_final_v1/measurement_registry.csv

Authoritative source
--------------------
Original PDF reports referenced by report_index.csv.

Output
------
data/processed/edr/group5_pdf_discovery_v1/

    group5_pdf_candidate_fields.csv
    group5_pdf_review_fields.csv
    group5_pdf_excluded_overlap_fields.csv
    group5_pdf_report_coverage.csv
    group5_pdf_label_summary.csv
    group5_pdf_family_summary.csv
    group5_pdf_section_summary.csv
    pdf_source_errors.csv
    metadata.json

Scope
-----
Process ONLY PDF-only reports.

This is discovery only:
- preserve original PDF page, line, label, value, unit, section and provenance
- no semantic value normalization
- no unit conversion
- no fuzzy event identity inference
- no OCR
- no final structured extraction

The original PDF is authoritative. The frozen Group 5 CSV package is used only
as optional vocabulary support for label recognition.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

try:
    import pdfplumber
except ImportError as exc:
    raise SystemExit(
        "pdfplumber is required. Install it with:\n"
        "  uv add pdfplumber\n"
        "or\n"
        "  uv pip install pdfplumber"
    ) from exc


csv.field_size_limit(100_000_000)

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


def write_csv(path: Path, rows: list[dict], columns: list[str]):
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

def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value if value is not None else "").strip(),
    )


def norm_key(value):
    return clean(
        re.sub(
            r"[^a-z0-9]+",
            " ",
            clean(value).casefold(),
        )
    )


def identifier(*parts):
    text = "|".join(
        clean(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:24]


def is_numeric_like(value):
    text = clean(value).replace(",", "")

    if not text:
        return False

    text = re.sub(
        r"\s*(?:"
        r"mph|km/h|kph|m/s|m/s\^?2|m/s²|"
        r"ft/s\^?2|ft/s²|g|"
        r"ms|msec|milliseconds?|"
        r"sec|seconds?|"
        r"deg|degrees?|deg/s|rad/s|"
        r"%|percent"
        r")\s*$",
        "",
        text,
        flags=re.I,
    )

    return bool(
        re.fullmatch(
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def is_value_like(value):
    text = clean(value)

    if not text:
        return False

    if is_numeric_like(text):
        return True

    if text.casefold() in {
        "n/a",
        "na",
        "sna",
        "not available",
        "unknown",
        "invalid",
        "not recorded",
        "yes",
        "no",
        "left",
        "right",
        "front",
        "rear",
        "frontal",
        "side",
        "rollover",
    }:
        return True

    return False


# ============================================================
# Path resolution
# ============================================================

def pdf_only_report(row):
    csv_path = clean(row.get("csv_path", ""))
    csv_status = clean(row.get("csv_status", "")).casefold()

    pdf_path = clean(row.get("pdf_path", ""))
    pdf_status = clean(row.get("pdf_status", "")).casefold()

    has_pdf = bool(pdf_path) and pdf_status not in {
        "missing",
        "not_available",
        "none",
    }

    has_csv = bool(csv_path) and csv_status not in {
        "missing",
        "not_available",
        "none",
    }

    return has_pdf and not has_csv


def resolve_pdf_path(row: dict, source_root: Path):
    raw = clean(row.get("pdf_path", ""))

    if raw:
        direct = Path(raw)

        if direct.exists():
            return direct

        basename = PureWindowsPath(raw).name
        case_id = clean(row.get("case_id", ""))

        if case_id and basename:
            case_root = source_root / case_id

            if case_root.exists():
                matches = list(
                    case_root.rglob(basename)
                )

                if matches:
                    return matches[0]

    basename = clean(
        row.get(
            "export_basename",
            "",
        )
    )
    case_id = clean(row.get("case_id", ""))

    if basename and case_id:
        case_root = source_root / case_id

        if case_root.exists():
            matches = list(
                case_root.rglob(
                    basename + ".PDF"
                )
            )

            if not matches:
                matches = list(
                    case_root.rglob(
                        basename + ".pdf"
                    )
                )

            if matches:
                return matches[0]

    return None


# ============================================================
# PDF text extraction
# ============================================================

def extract_pages(pdf_path: Path):
    pages = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(
            pdf.pages,
            1,
        ):
            text = page.extract_text(
                x_tolerance=2,
                y_tolerance=2,
                layout=False,
            ) or ""

            lines = [
                clean(line)
                for line in text.splitlines()
                if clean(line)
            ]

            pages.append(
                (
                    page_number,
                    lines,
                )
            )

    return pages


# ============================================================
# Section / event context
# ============================================================

SECTION_PATTERNS = [
    r"^System Status At\b",
    r"^Event Data\b",
    r"^Crash Data\b",
    r"^Deployment Data\b",
    r"^Non[- ]Deployment Data\b",
    r"^Rollover Data\b",
    r"^Side Impact Data\b",
    r"^Longitudinal Delta[- ]?V\b",
    r"^Lateral Delta[- ]?V\b",
    r"^Multiple Event Data\b",
    r"^Pre[- ]?Crash Data\b",
]

EVENT_PATTERNS = [
    r"\bDeployment Event\s*#?\s*\d*\b",
    r"\bNon[- ]Deployment Event\b",
    r"\bMost Recent Event\b",
    r"\b\d+(?:st|nd|rd|th) Prior Event\b",
    r"\bEvent Record\s*#?\s*\d+\b",
]


def detect_section(line):
    text = clean(line)

    for pattern in SECTION_PATTERNS:
        if re.search(
            pattern,
            text,
            re.I,
        ):
            return text

    return ""


def extract_event_hint(*texts):
    combined = " | ".join(
        clean(text)
        for text in texts
        if clean(text)
    )

    hints = []

    for pattern in EVENT_PATTERNS:
        for match in re.findall(
            pattern,
            combined,
            flags=re.I,
        ):
            value = clean(match)

            if value.casefold() not in {
                item.casefold()
                for item in hints
            }:
                hints.append(value)

    return " | ".join(hints)


# ============================================================
# Group 5 family rules
# ============================================================

FAMILY_RULES = [
    (
        "range_clipping_timing",
        [
            r"\bclipping time\b",
            r"\baccelerometer range exceeded\b",
            r"\bsensor design range exceeded\b",
            r"\breached maximum sensor range\b",
        ],
    ),
    (
        "acceleration_peak_timing",
        [
            r"\btime\b.*\bmaximum acceleration\b",
        ],
    ),
    (
        "acceleration_peak",
        [
            r"\bmaximum acceleration\b",
            r"\bpeak acceleration\b",
        ],
    ),
    (
        "delta_v_timing",
        [
            r"\balgorithm enable\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime\b.*\bmaximum\b.*\bdelta[- ]?v\b",
            r"\btime to\b.*\bmaximum\b.*\bvelocity change\b",
            r"\btime from\b.*\bmaximum\b.*\bvelocity change\b",
        ],
    ),
    (
        "delta_v_time_zero_offset",
        [
            r"\bdelta[- ]?v\b.*\btime zero offset\b",
        ],
    ),
    (
        "delta_v_duration",
        [
            r"\blength of delta[- ]?v\b",
            r"\bduration\b.*\bdelta[- ]?v\b",
            r"\bcrash pulse\b.*\bduration\b",
        ],
    ),
    (
        "delta_v_integration_time",
        [
            r"\bintegration time\b.*\bdelta[- ]?v\b",
        ],
    ),
    (
        "delta_v_component_at_maximum",
        [
            r"\b(?:longitudinal|lateral)\b.*"
            r"\bvelocity change\b.*"
            r"\bat time of maximum\b",
        ],
    ),
    (
        "delta_v_summary",
        [
            r"\bmaximum\b.*\bvelocity change\b",
            r"\bmaximum\b.*\bdelta[- ]?v\b",
            r"\bmax(?:imum)?\b.*\bvelocity change\b",
            r"\bmax(?:imum)?\b.*\bdelta[- ]?v\b",
            r"\bresultant\b.*\bdelta[- ]?v\b",
            r"\bfinal\b.*\bdelta[- ]?v\b",
            r"\bfinal\b.*\bvelocity change\b",
        ],
    ),
    (
        "roll_peak",
        [
            r"\broll ?angle peak\b",
            r"\bmaximum\b.*\broll angle\b",
            r"\bpeak\b.*\broll angle\b",
        ],
    ),
    (
        "roll_at_trigger",
        [
            r"\broll angle at the time of trg\b",
        ],
    ),
    (
        "roll_time_zero_offset",
        [
            r"\broll angle time zero offset\b",
        ],
    ),
    (
        "trigger_relative_timing",
        [
            r"\btime from time zero to trg\b",
        ],
    ),
    (
        "precrash_time_alignment",
        [
            r"\btime from last speed data sample\b.*\btime zero\b",
        ],
    ),
    (
        "sensor_loss_timing",
        [
            r"\btime yaw rate lost\b",
        ],
    ),
    (
        "direction_summary",
        [
            r"\brecorded side\b",
            r"\bpdof\b",
            r"\bprincipal direction of force\b",
            r"\bcrash direction\b",
            r"\brecorded direction\b",
        ],
    ),
]


def classify_family(label):
    text = clean(label)

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

GROUP3_PATTERNS = [
    r"\bair ?bag\b",
    r"\bpretensioner\b",
    r"\bdeployment command\b",
    r"\bdeployment criteria\b",
    r"\b1st stage\b",
    r"\b2nd stage\b",
    r"\bbelt switch\b",
    r"\bseat belt\b",
    r"\boccupant\b",
    r"\bpassenger classification\b",
    r"\bsuppression\b",
    r"\bwarning lamp\b",
    r"\bsir\b",
    r"\bdtc\b",
    r"\bdiagnostic trouble\b",
    r"\bseat position\b",
    r"\brestraint\b",
    r"\bhigh voltage disable\b",
    r"\bpower loss detected during event\b",
]

GROUP2_PATTERNS = [
    r"\bevent recording complete\b",
    r"\bcrash record locked\b",
    r"\brecording complete\b",
    r"\bmultiple events?\b",
    r"\bevent counter\b",
    r"\bassociated events?\b",
    r"\bevents? not recorded\b",
    r"\btime between\b.*\bevents?\b",
]

GROUP6_PATTERNS = [
    r"\bignition cycles?\b",
    r"\bpart number\b",
    r"\bserial number\b",
    r"\bsoftware version\b",
    r"\bsupplier id\b",
    r"\bproduction date\b",
    r"\bconfiguration\b",
    r"\bvehicle mileage\b",
    r"\bodometer\b",
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


def matches_any(text, patterns):
    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in patterns
    )


# ============================================================
# CSV vocabulary support
# ============================================================

def load_csv_label_vocabulary(path: Path):
    labels = Counter()

    if not path.exists():
        return labels

    for row in read_csv_dict(path):
        key = norm_key(
            row.get(
                "field_label_raw",
                "",
            )
        )

        if key:
            labels[key] += 1

    return labels


# ============================================================
# Label/value parsing from PDF lines
# ============================================================

VALUE_SUFFIX = re.compile(
    r"^(?P<label>.+?)\s{2,}(?P<value>\S(?:.*\S)?)$"
)

VALUE_END_PATTERNS = [
    re.compile(
        r"^(?P<label>.+?)\s+"
        r"(?P<value>"
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:\s*(?:MPH|km/h|kph|m/s|g|"
        r"msec|ms|sec|seconds?|deg|degrees?|%))?"
        r")$",
        re.I,
    ),
    re.compile(
        r"^(?P<label>.+?)\s+"
        r"(?P<value>N/A|NA|SNA|Yes|No|Left|Right|Front|Rear)$",
        re.I,
    ),
]


def parse_label_value(line):
    """
    Conservative line parser.

    pdfplumber usually preserves several spaces between label/value columns.
    We try:
      1. two-or-more spaces
      2. a numeric/status suffix
    """

    raw = line.rstrip()

    match = VALUE_SUFFIX.match(raw)

    if match:
        label = clean(
            match.group("label")
        )
        value = clean(
            match.group("value")
        )

        if label and value:
            return label, value

    for pattern in VALUE_END_PATTERNS:
        match = pattern.match(
            clean(raw)
        )

        if match:
            label = clean(
                match.group("label")
            )
            value = clean(
                match.group("value")
            )

            if label and value:
                return label, value

    return None


# ============================================================
# Candidate scoring
# ============================================================

def score_observation(
    label,
    value,
    section,
    csv_vocab,
):
    family = classify_family(label)

    score = 0
    evidence = []
    exclusions = []

    if family:
        score += 6
        evidence.append(
            f"family:{family}"
        )

    if is_value_like(value):
        score += 1
        evidence.append(
            "scalar_value_like"
        )

    key = norm_key(label)

    if key in csv_vocab:
        score += 3
        evidence.append(
            "matches_frozen_csv_group5_label"
        )

    if re.search(
        r"\b(?:"
        r"maximum|max|peak|final|"
        r"delta[- ]?v|velocity change|"
        r"acceleration|roll angle|"
        r"recorded side|pdof|"
        r"clipping"
        r")\b",
        label,
        re.I,
    ):
        score += 1
        evidence.append(
            "crash_measurement_terms"
        )

    if matches_any(
        label,
        GROUP3_PATTERNS,
    ):
        exclusions.append(
            "group3_deployment_or_status"
        )

    if matches_any(
        label,
        GROUP2_PATTERNS,
    ):
        exclusions.append(
            "group2_record_structure"
        )

    if matches_any(
        label,
        GROUP6_PATTERNS,
    ):
        exclusions.append(
            "group6_technical"
        )

    if matches_any(
        label,
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
        decision = "not_group5"

    return {
        "family":
            family
            or "other_crash_measurement",

        "score":
            score,

        "decision":
            decision,

        "evidence":
            evidence,

        "exclusions":
            exclusions,

        "csv_label_support_count":
            csv_vocab.get(key, 0),
    }


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--report-index",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group1_v4/report_index.csv"
        ),
    )

    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("data/temp"),
    )

    parser.add_argument(
        "--csv-vocabulary",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_csv_final_v1/"
            "measurement_registry.csv"
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(
            "data/processed/edr/"
            "group5_pdf_discovery_v1"
        ),
    )

    args = parser.parse_args()

    if not args.report_index.exists():
        raise FileNotFoundError(
            args.report_index
        )

    report_index = read_csv_dict(
        args.report_index
    )

    csv_vocab = load_csv_label_vocabulary(
        args.csv_vocabulary
    )

    selected = [
        row
        for row in report_index
        if pdf_only_report(row)
    ]

    candidates = []
    reviews = []
    excluded = []
    coverage = []
    errors = []

    family_counter = Counter()
    label_counter = Counter()
    section_counter = Counter()
    decision_counter = Counter()

    reports_with_candidates = set()
    reports_with_reviews = set()

    for report_number, row in enumerate(
        selected,
        1,
    ):
        pdf_path = resolve_pdf_path(
            row,
            args.source_root,
        )

        if (
            pdf_path is None
            or not pdf_path.exists()
        ):
            errors.append({
                **{
                    key:
                        row.get(key, "")
                    for key in BASE
                },
                "error_type":
                    "pdf_source_not_found",
                "pdf_path":
                    row.get(
                        "pdf_path",
                        "",
                    ),
                "error":
                    "Could not resolve original PDF source.",
            })

            coverage.append({
                **{
                    key:
                        row.get(key, "")
                    for key in BASE
                },
                "pdf_path":
                    row.get(
                        "pdf_path",
                        "",
                    ),
                "processing_status":
                    "source_not_found",
                "candidate_count":
                    0,
                "review_count":
                    0,
                "excluded_overlap_count":
                    0,
            })

            continue

        try:
            pages = extract_pages(
                pdf_path
            )

        except Exception as exc:
            errors.append({
                **{
                    key:
                        row.get(key, "")
                    for key in BASE
                },
                "error_type":
                    type(exc).__name__,
                "pdf_path":
                    str(pdf_path),
                "error":
                    str(exc),
            })

            coverage.append({
                **{
                    key:
                        row.get(key, "")
                    for key in BASE
                },
                "pdf_path":
                    str(pdf_path),
                "processing_status":
                    "source_error",
                "candidate_count":
                    0,
                "review_count":
                    0,
                "excluded_overlap_count":
                    0,
            })

            continue

        report_candidates = 0
        report_reviews = 0
        report_excluded = 0

        current_section = ""

        for page_number, lines in pages:
            page_section = current_section

            for line_index, line in enumerate(
                lines,
                1,
            ):
                detected = detect_section(
                    line
                )

                if detected:
                    current_section = detected
                    page_section = detected

                parsed = parse_label_value(
                    line
                )

                if not parsed:
                    continue

                label, value = parsed

                result = score_observation(
                    label=label,
                    value=value,
                    section=current_section,
                    csv_vocab=csv_vocab,
                )

                if result[
                    "decision"
                ] == "not_group5":
                    continue

                event_hint = extract_event_hint(
                    current_section,
                    label,
                )

                candidate_id = (
                    "g5pdf_"
                    + identifier(
                        row.get(
                            "report_id",
                            "",
                        ),
                        page_number,
                        line_index,
                        label,
                        value,
                    )
                )

                record = {
                    **{
                        key:
                            row.get(key, "")
                        for key in BASE
                    },

                    "group5_pdf_candidate_id":
                        candidate_id,

                    "source_format":
                        "pdf",

                    "source_path":
                        str(pdf_path),

                    "source_page_number":
                        page_number,

                    "source_line_number_on_page":
                        line_index,

                    "source_section_heading":
                        current_section,

                    "event_hint":
                        event_hint,

                    "field_label_raw":
                        label,

                    "field_value_raw":
                        value,

                    "source_line_raw":
                        line,

                    "candidate_family":
                        result[
                            "family"
                        ],

                    "candidate_score":
                        result[
                            "score"
                        ],

                    "discovery_decision":
                        result[
                            "decision"
                        ],

                    "evidence_json":
                        json.dumps(
                            result[
                                "evidence"
                            ],
                            ensure_ascii=False,
                        ),

                    "overlap_exclusions_json":
                        json.dumps(
                            result[
                                "exclusions"
                            ],
                            ensure_ascii=False,
                        ),

                    "csv_label_support_count":
                        result[
                            "csv_label_support_count"
                        ],

                    "semantic_normalization_status":
                        "not_normalized",

                    "unit_conversion_status":
                        "not_converted",

                    "event_link_status":
                        (
                            "source_hint_only"
                            if event_hint
                            else "not_linked"
                        ),
                }

                decision_counter[
                    result[
                        "decision"
                    ]
                ] += 1

                if result[
                    "decision"
                ] == "candidate":
                    candidates.append(
                        record
                    )

                    report_candidates += 1

                    reports_with_candidates.add(
                        row.get(
                            "report_id",
                            "",
                        )
                    )

                    family_counter[
                        result[
                            "family"
                        ]
                    ] += 1

                    label_counter[
                        norm_key(label)
                    ] += 1

                    section_counter[
                        clean(
                            current_section
                        )
                        or "<no_section_heading>"
                    ] += 1

                elif result[
                    "decision"
                ] == "review":
                    reviews.append(
                        record
                    )

                    report_reviews += 1

                    reports_with_reviews.add(
                        row.get(
                            "report_id",
                            "",
                        )
                    )

                elif result[
                    "decision"
                ] == "excluded_overlap":
                    excluded.append(
                        record
                    )
                    report_excluded += 1

        if report_candidates:
            status = (
                "group5_candidates_found"
            )

        elif report_reviews:
            status = "review_only"

        else:
            status = (
                "no_group5_candidates"
            )

        coverage.append({
            **{
                key:
                    row.get(key, "")
                for key in BASE
            },

            "pdf_path":
                str(pdf_path),

            "processing_status":
                status,

            "candidate_count":
                report_candidates,

            "review_count":
                report_reviews,

            "excluded_overlap_count":
                report_excluded,
        })

        if (
            report_number % 25 == 0
            or report_number
            == len(selected)
        ):
            print(
                "Discovered Group 5 PDF "
                f"{report_number}/"
                f"{len(selected)} reports...",
                flush=True,
            )

    # ========================================================
    # Summaries
    # ========================================================

    raw_label_examples = defaultdict(
        Counter
    )

    for row in candidates:
        key = norm_key(
            row[
                "field_label_raw"
            ]
        )

        raw_label_examples[
            key
        ][
            row[
                "field_label_raw"
            ]
        ] += 1

    label_summary = []

    for key, count in (
        label_counter.most_common()
    ):
        label_summary.append({
            "normalized_label":
                key,

            "candidate_count":
                count,

            "raw_label_examples_json":
                json.dumps(
                    [
                        label
                        for label, _
                        in raw_label_examples[
                            key
                        ].most_common(5)
                    ],
                    ensure_ascii=False,
                ),
        })

    family_summary = [
        {
            "candidate_family":
                family,
            "candidate_count":
                count,
        }
        for family, count
        in family_counter.most_common()
    ]

    section_summary = [
        {
            "source_section_heading":
                section,
            "candidate_count":
                count,
        }
        for section, count
        in section_counter.most_common()
    ]

    # ========================================================
    # Write
    # ========================================================

    out = args.output_directory

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    columns = [
        *BASE,
        "group5_pdf_candidate_id",
        "source_format",
        "source_path",
        "source_page_number",
        "source_line_number_on_page",
        "source_section_heading",
        "event_hint",
        "field_label_raw",
        "field_value_raw",
        "source_line_raw",
        "candidate_family",
        "candidate_score",
        "discovery_decision",
        "evidence_json",
        "overlap_exclusions_json",
        "csv_label_support_count",
        "semantic_normalization_status",
        "unit_conversion_status",
        "event_link_status",
    ]

    write_csv(
        out
        / "group5_pdf_candidate_fields.csv",
        candidates,
        columns,
    )

    write_csv(
        out
        / "group5_pdf_review_fields.csv",
        reviews,
        columns,
    )

    write_csv(
        out
        / "group5_pdf_excluded_overlap_fields.csv",
        excluded,
        columns,
    )

    write_csv(
        out
        / "group5_pdf_report_coverage.csv",
        coverage,
        [
            *BASE,
            "pdf_path",
            "processing_status",
            "candidate_count",
            "review_count",
            "excluded_overlap_count",
        ],
    )

    write_csv(
        out
        / "group5_pdf_label_summary.csv",
        label_summary,
        [
            "normalized_label",
            "candidate_count",
            "raw_label_examples_json",
        ],
    )

    write_csv(
        out
        / "group5_pdf_family_summary.csv",
        family_summary,
        [
            "candidate_family",
            "candidate_count",
        ],
    )

    write_csv(
        out
        / "group5_pdf_section_summary.csv",
        section_summary,
        [
            "source_section_heading",
            "candidate_count",
        ],
    )

    write_csv(
        out
        / "pdf_source_errors.csv",
        errors,
        [
            *BASE,
            "error_type",
            "pdf_path",
            "error",
        ],
    )

    coverage_counts = Counter(
        row[
            "processing_status"
        ]
        for row in coverage
    )

    metadata = {
        "created_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "group":
            "Group 5 - Non-time-series crash and event measurements",

        "stage":
            "PDF-only discovery",

        "reports_in_index":
            len(report_index),

        "pdf_only_reports_selected":
            len(selected),

        "pdf_only_reports_processed":
            len(coverage)
            - sum(
                1
                for row in coverage
                if row[
                    "processing_status"
                ] in {
                    "source_not_found",
                    "source_error",
                }
            ),

        "reports_with_group5_candidates":
            len(
                reports_with_candidates
            ),

        "reports_with_review_fields":
            len(
                reports_with_reviews
            ),

        "candidate_field_count":
            len(candidates),

        "review_field_count":
            len(reviews),

        "excluded_overlap_field_count":
            len(excluded),

        "candidate_family_counts":
            dict(
                family_counter
            ),

        "decision_counts":
            dict(
                decision_counter
            ),

        "coverage_status_counts":
            dict(
                coverage_counts
            ),

        "unique_candidate_labels":
            len(
                label_counter
            ),

        "csv_vocabulary_available":
            args.csv_vocabulary.exists(),

        "csv_vocabulary_label_count":
            len(
                csv_vocab
            ),

        "pdf_source_errors":
            len(errors),

        "scope":
            (
                "PDF-only discovery for Group 5 scalar/non-time-series "
                "crash and event measurements. Only reports without CSV "
                "sources are processed. Original PDFs are authoritative. "
                "The frozen Group 5 CSV package is used only as optional "
                "label-vocabulary support. Page, line, section, event hint, "
                "raw label, raw value, and original source line are "
                "preserved. No OCR, semantic normalization, unit conversion, "
                "fuzzy event linking, final extraction, or CSV/PDF "
                "integration is performed."
            ),
    }

    tmp = (
        out
        / "metadata.json.part"
    )

    tmp.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    tmp.replace(
        out
        / "metadata.json"
    )

    print()
    print(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        f"Outputs: {out}"
    )

    print()
    print(
        "GROUP 5 PDF DISCOVERY COMPLETE."
    )


if __name__ == "__main__":
    main()
