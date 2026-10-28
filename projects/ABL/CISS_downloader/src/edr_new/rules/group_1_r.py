from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.edr.parsers.observation_parser import Observation, normalize_text


# ============================================================
# Group definition
# ============================================================

GROUP_NAME = "group1"
RULE_VERSION = "2.1"


# ============================================================
# Validated Group 1 field vocabulary
# ============================================================

GROUP1_FIELD_NAMES = {
    "vin_entered",
    "user_entered",
    "case_number_entered",
    "imaging_date",
    "crash_date",
    "source_filename",
    "saved_on",
    "imaging_cdr_version",
    "reporting_cdr_version",
    "imaging_license_company",
    "reporting_license_company",
    "edr_device_type",
    "events_recovered_text",
    "acm_adapter_detected",
    "restraint_deployment_signal_text",
}

# Original validated labels + conservative aliases already used in src/edr.
GROUP1_LABEL_TO_FIELD = {
    "user entered vin": "vin_entered",
    "user entered vin/frame number": "vin_entered",
    "vin entered": "vin_entered",
    "vin/frame number": "vin_entered",
    "vin / frame number": "vin_entered",
    "vin entered / frame number": "vin_entered",
    "user": "user_entered",
    "user entered": "user_entered",
    "case number": "case_number_entered",
    "case number entered": "case_number_entered",
    "edr data imaging date": "imaging_date",
    "imaging date": "imaging_date",
    "crash date": "crash_date",
    "filename": "source_filename",
    "file name": "source_filename",
    "source filename": "source_filename",
    "saved on": "saved_on",
    "imaged with cdr version": "imaging_cdr_version",
    "imaging cdr version": "imaging_cdr_version",
    "reported with cdr version": "reporting_cdr_version",
    "reporting cdr version": "reporting_cdr_version",
    "imaged with software licensed to (company name)": "imaging_license_company",
    "imaging license company": "imaging_license_company",
    "reported with software licensed to (company name)": "reporting_license_company",
    "reporting license company": "reporting_license_company",
    "edr device type": "edr_device_type",
    "event(s) recovered": "events_recovered_text",
    "events recovered": "events_recovered_text",
    "recovered events": "events_recovered_text",
    "acm adapter detected during download": "acm_adapter_detected",
    "acm adapter detected": "acm_adapter_detected",
    "restraint deployment signal received": "restraint_deployment_signal_text",
    "restraint deployment signal": "restraint_deployment_signal_text",
}

CORE_FIELDS = {
    "vin_entered",
    "source_filename",
    "imaging_cdr_version",
    "reporting_cdr_version",
    "edr_device_type",
}

GROUP1_METADATA_SECTION_PATTERNS = (
    "cdr file information",
    "file information",
    "report information",
)

# Production extraction remains conservative and follows the original workflow.
GROUP1_DOCUMENTATION_SECTION_PATTERNS = (
    "comments",
    "data limitations",
)

BODY_BOUNDARY = re.compile(
    r"^(?:System Status|System Configuration|PCM Module Information|PCM EDR Data|"
    r"Event Record Summary|Front/Rear Event Record Summary|Event Data\s*\(|"
    r"Status of the Data|Deployment (?:Data|Command)|Pre[-_ ]Crash Data|"
    r"Longitudinal(?:/Lateral)? Crash Pulse|Lateral Crash Pulse|"
    r"Rollover Crash Pulse|Hexadecimal Data\s*$)",
    re.I,
)

DOC_HEAD = re.compile(
    r"^(?:Comments|Data Limitations|Data Source|PCM Data Source|"
    r"Data Element Sign Convention|Recorded Crash Events|Data|Hexadecimal Data):?$",
    re.I,
)

EVENT_CONTINUATION = re.compile(
    r"(?:Event Record \d+|Record \d+|Event \d+|(?:First|Second|Third) Record|"
    r"Most Recent Event|\d+(?:st|nd|rd|th) Prior Event|"
    r"(?:locked|unlocked) (?:frontal|side|rollover) event|unlocked events?|"
    r"Fuel cutoff level \d+)(?:\s*\([^\n]*\))?\s*,?",
    re.I,
)


# ============================================================
# Result models
# ============================================================

@dataclass
class Group1RuleResult:
    matched: bool
    destination: str
    field_family: str
    canonical_field: str
    confidence: str
    reason: str
    requires_review: bool = False
    review_reason: str = ""
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "destination": self.destination,
            "field_family": self.field_family,
            "canonical_field": self.canonical_field,
            "confidence": self.confidence,
            "reason": self.reason,
            "requires_review": self.requires_review,
            "review_reason": self.review_reason,
            "rule_version": self.rule_version,
        }


@dataclass
class Group1ExtractionResult:
    source_format: str
    source_path: str
    fields: list[dict[str, Any]]
    documentation: list[dict[str, Any]]
    issues: list[str]
    intro_pages: int | str = ""
    body_boundary: str = ""

    @property
    def requires_review(self) -> bool:
        return bool(self.issues)

    def audit_record(self, identity: dict[str, Any]) -> dict[str, Any]:
        return {
            **identity,
            "source_format": self.source_format,
            "source_path": self.source_path,
            "status": "extracted_needs_review" if self.issues else "extracted",
            "metadata_field_count": len(self.fields),
            "documentation_block_count": len(self.documentation),
            "intro_pages": self.intro_pages,
            "body_boundary": self.body_boundary,
            "issue": "|".join(sorted(set(self.issues))),
            "rule_version": RULE_VERSION,
        }


# ============================================================
# Helpers
# ============================================================

def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value)).strip()


def _key(value: Any) -> str:
    return _norm(value).casefold()


def normalize_group1_label(value: str) -> str:
    return normalize_text(value).strip(" :")


def canonical_group1_field(label: str) -> str:
    return GROUP1_LABEL_TO_FIELD.get(normalize_group1_label(label), "")


def _value_status(value: Any) -> str:
    text = _norm(value)
    if not text:
        return "blank"
    if text.casefold() in {"n/a", "na", "not available"}:
        return "not_available"
    return "present"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_group1_metadata_section(section: str) -> bool:
    section_norm = normalize_text(section)
    return any(pattern in section_norm for pattern in GROUP1_METADATA_SECTION_PATTERNS)


def is_group1_documentation_section(section: str) -> bool:
    section_norm = normalize_text(section)
    return any(section_norm == pattern for pattern in GROUP1_DOCUMENTATION_SECTION_PATTERNS)


def documentation_category(text: str) -> str:
    normalized = normalize_text(text)
    if normalized == "comments":
        return "comments"
    if normalized == "data limitations":
        return "data_limitations"
    return ""


def recovered_event_semantic_status() -> str:
    return "report_level_source_text_not_validated_event_identity"


def classify_pdf_text_quality(text_raw: str) -> str:
    if "(cid:" in str(text_raw or ""):
        return "font_encoding_artifact_requires_review"
    return "extracted_text_candidate"


def _evidence(
    identity: dict[str, Any],
    *,
    source_format: str,
    source_path: Path,
    source_sha256: str,
    label: str,
    value: Any,
    source_page: int | str = "",
    source_record: int | str = "",
    source_record_end: int | str = "",
    source_cells_json: str = "",
    source_bbox_json: str = "",
    source_label_status: str = "present",
    extraction_method: str = "",
) -> dict[str, Any]:
    canonical = canonical_group1_field(label)
    return {
        **identity,
        "source_format": source_format,
        "source_path": str(source_path),
        "source_sha256": source_sha256,
        "source_page": source_page,
        "source_record": source_record,
        "source_record_end": source_record_end,
        "source_cells_json": source_cells_json,
        "source_bbox_json": source_bbox_json,
        "field_name": canonical or f"unmapped:{_norm(label)}",
        "field_label_raw": label,
        "source_label_status": source_label_status,
        "value_raw": value,
        "value_text": _norm(value),
        "value_status": _value_status(value),
        "extraction_method": extraction_method,
        "rule_version": RULE_VERSION,
    }


def _read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return [["" if value is None else str(value) for value in row] for row in csv.reader(handle)]


# ============================================================
# Report-level source selection
# ============================================================

def select_group1_source(
    *,
    csv_path: str | Path | None,
    pdf_path: str | Path | None,
) -> tuple[str, Path]:
    """Choose one source for the whole report: CSV first, PDF only if CSV is absent."""

    if csv_path:
        csv_candidate = Path(csv_path)
        if csv_candidate.is_file():
            return "csv", csv_candidate

    if pdf_path:
        pdf_candidate = Path(pdf_path)
        if pdf_candidate.is_file():
            return "pdf", pdf_candidate

    raise FileNotFoundError("No usable CSV or PDF source is available for this report.")


# ============================================================
# Validated CSV extraction
# ============================================================

def extract_group1_csv(
    path: str | Path,
    identity: dict[str, Any],
) -> Group1ExtractionResult:
    path = Path(path)
    rows = _read_csv_rows(path)
    sha = _digest(path)
    fields: list[dict[str, Any]] = []
    docs: list[dict[str, Any]] = []
    issues: list[str] = []

    start = next(
        (i for i, row in enumerate(rows) if row and _key(row[0]) == "cdr file information"),
        None,
    )
    if start is None:
        raise ValueError("CDR FILE INFORMATION heading not found")

    end = start + 1
    while end < len(rows):
        row = rows[end]
        filled = [value for value in row if value.strip()]

        if len(filled) == 1 and (
            DOC_HEAD.fullmatch(filled[0].strip())
            or (filled[0].isupper() and len(row) < 3)
        ):
            break

        if row and row[0].strip():
            label = row[0]
            continuation = EVENT_CONTINUATION.fullmatch(_norm(label))
            previous = fields[-1] if fields else None
            adjacent = bool(previous and int(previous.get("source_record_end") or 0) == end)

            if (
                len(filled) == 1
                and continuation
                and adjacent
                and previous.get("field_name") == "events_recovered_text"
            ):
                previous["value_raw"] = f"{previous['value_raw']}\n{label}"
                previous["value_text"] = _norm(previous["value_raw"])
                previous["source_record_end"] = end + 1
                cells = json.loads(previous.get("source_cells_json") or "[]")
                cells.extend(
                    {"record": end + 1, "column": ci + 1, "value_raw": value}
                    for ci, value in enumerate(row)
                )
                previous["source_cells_json"] = json.dumps(cells, ensure_ascii=False)
                if previous.get("source_label_status") == "present":
                    previous["extraction_method"] = (
                        "csv_intro_field_with_verified_event_continuation"
                    )

            elif (
                len(filled) == 1
                and adjacent
                and previous
                and previous.get("field_name") == "acm_adapter_detected"
                and re.fullmatch(r"(?:First|Second|Third) Record|None", _norm(label), re.I)
            ):
                cells = [
                    {"record": end + 1, "column": ci + 1, "value_raw": value}
                    for ci, value in enumerate(row)
                ]
                item = _evidence(
                    identity,
                    source_format="csv",
                    source_path=path,
                    source_sha256=sha,
                    label="Event(s) recovered",
                    value=label,
                    source_record=end + 1,
                    source_record_end=end + 1,
                    source_cells_json=json.dumps(cells, ensure_ascii=False),
                    source_label_status="absent_contextual_candidate",
                    extraction_method="csv_unlabeled_event_description_candidate_after_adapter",
                )
                item["field_label_raw"] = ""
                fields.append(item)
                issues.append("unlabeled_event_description_candidate_requires_review")

            elif len(row) > 1:
                if len(row) > 2 and any(value.strip() for value in row[2:]):
                    value: Any = json.dumps(row[1:], ensure_ascii=False)
                    issues.append("multivalue_intro_field_preserved_as_json")
                else:
                    value = row[1]

                cells = [
                    {"record": end + 1, "column": ci + 1, "value_raw": value_cell}
                    for ci, value_cell in enumerate(row)
                    if ci > 0
                ]
                fields.append(
                    _evidence(
                        identity,
                        source_format="csv",
                        source_path=path,
                        source_sha256=sha,
                        label=label,
                        value=value,
                        source_record=end + 1,
                        source_record_end=end + 1,
                        source_cells_json=json.dumps(cells, ensure_ascii=False),
                        extraction_method="csv_intro_field",
                    )
                )

            elif _key(label).startswith("system:"):
                fields.append(
                    _evidence(
                        identity,
                        source_format="csv",
                        source_path=path,
                        source_sha256=sha,
                        label="System",
                        value=label.split(":", 1)[1],
                        source_record=end + 1,
                        extraction_method="csv_system_label",
                    )
                )

            elif label.strip():
                issues.append("unrecognized_single_cell_intro_content")
                docs.append(
                    {
                        **identity,
                        "source_format": "csv",
                        "source_path": str(path),
                        "source_sha256": sha,
                        "source_page": "",
                        "source_record": end + 1,
                        "documentation_category": "unresolved_introductory_content",
                        "text_raw": label,
                        "extraction_status": "unresolved_source_text_preserved",
                        "rule_version": RULE_VERSION,
                    }
                )
        end += 1

    # System labels may appear before CDR FILE INFORMATION.
    for row_index, row in enumerate(rows[:start]):
        if row and _key(row[0]).startswith("system:"):
            fields.append(
                _evidence(
                    identity,
                    source_format="csv",
                    source_path=path,
                    source_sha256=sha,
                    label="System",
                    value=row[0].split(":", 1)[1],
                    source_record=row_index + 1,
                    extraction_method="csv_system_label",
                )
            )

    # Preserve only validated introductory Comments / Data Limitations blocks.
    j = end
    category = ""
    buffer: list[str] = []
    first_record = j + 1

    def flush() -> None:
        nonlocal buffer
        if buffer:
            docs.append(
                {
                    **identity,
                    "source_format": "csv",
                    "source_path": str(path),
                    "source_sha256": sha,
                    "source_page": "",
                    "source_record": first_record,
                    "documentation_category": category,
                    "text_raw": "\n".join(buffer),
                    "extraction_status": "source_text_preserved",
                    "rule_version": RULE_VERSION,
                }
            )
            buffer = []

    while j < len(rows):
        row = rows[j]
        filled = [value for value in row if value.strip()]
        text = ",".join(row)

        if filled and _key(filled[0]) in {"pidsstart", "hexadecimal data"}:
            break

        if len(filled) == 1:
            token = filled[0].strip()
            if _key(token) in {"comments", "data limitations"}:
                flush()
                category = "comments" if _key(token) == "comments" else "data_limitations"
                first_record = j + 1
            elif category and token.isupper() and not DOC_HEAD.fullmatch(token):
                break
            elif not category and token:
                break

        if category:
            buffer.append(text)
        j += 1

    flush()

    return Group1ExtractionResult(
        source_format="csv",
        source_path=str(path),
        fields=fields,
        documentation=docs,
        issues=issues,
        body_boundary="csv_intro_heading_boundary",
    )


# ============================================================
# Validated PDF fallback extraction
# ============================================================

def extract_group1_pdf(
    path: str | Path,
    identity: dict[str, Any],
    *,
    max_intro_pages: int = 15,
) -> Group1ExtractionResult:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required for Group 1 PDF fallback extraction") from exc

    path = Path(path)
    sha = _digest(path)
    fields: list[dict[str, Any]] = []
    docs: list[dict[str, Any]] = []
    issues: list[str] = []
    boundary = ""
    pages_seen = 0
    info_seen = False

    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages[:max_intro_pages]):
            pages_seen = page_index + 1
            lines = page.extract_text_lines(layout=False, strip=True)

            footer_tops = [
                line["top"]
                for line in lines
                if re.search(r"Page\s+\d+\s+of\s+\d+", line["text"], re.I)
            ]
            cutoff = min(footer_tops) if footer_tops else page.height - 20
            lines = [
                line
                for line in lines
                if line["top"] < cutoff
                and _norm(line["text"]) not in {"BOSCH", "CRASH DATA RETRIEVAL"}
            ]

            header_index = next(
                (i for i, line in enumerate(lines) if _key(line["text"]) == "cdr file information"),
                None,
            )
            metadata_end = None

            if header_index is not None:
                info_seen = True
                metadata_end = next(
                    (
                        i
                        for i in range(header_index + 1, len(lines))
                        if _key(lines[i]["text"]) in {"comments", "data limitations"}
                    ),
                    len(lines),
                )

                anchors: list[float] = []
                anchor_labels = (
                    "User Entered VIN/Frame Number",
                    "User Entered VIN",
                    "Filename",
                    "EDR Device Type",
                )
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
                for line in lines[header_index + 1 : metadata_end]:
                    for label in anchor_labels:
                        if _key(line["text"]).startswith(_key(label) + " "):
                            row_words = [word for word in words if abs(word["top"] - line["top"]) < 2]
                            label_word_count = len(label.split())
                            if len(row_words) > label_word_count:
                                anchors.append(row_words[label_word_count]["x0"])

                split_x = sorted(anchors)[len(anchors) // 2] - 1 if anchors else None
                if split_x is None:
                    issues.append("metadata_value_column_not_identified")
                else:
                    starts: list[tuple[dict[str, Any], str]] = []
                    labels = sorted(GROUP1_LABEL_TO_FIELD, key=len, reverse=True)
                    for line in lines[header_index + 1 : metadata_end]:
                        if line["x0"] >= split_x:
                            continue
                        normalized_line = normalize_group1_label(line["text"])

                        label = next(
                            (
                                candidate
                                for candidate in labels
                                if (
                                    normalized_line.startswith(candidate)
                                    or (
                                        candidate.endswith(" name)")
                                        and normalized_line.startswith(
                                            candidate.rsplit(" name)", 1)[0]
                                        )
                                    )
                                )
                            ),
                            None,
                        )

                        if label:
                            starts.append((line, label))

                    for n, (line, label) in enumerate(starts):
                        bottom = (
                            starts[n + 1][0]["top"] - 0.1
                            if n + 1 < len(starts)
                            else (
                                lines[metadata_end]["top"] - 0.1
                                if metadata_end < len(lines)
                                else cutoff
                            )
                        )
                        top = line["top"] - 1

                        horizontal_rules = sorted(
                            set(
                                rule["top"]
                                for rule in page.lines
                                if abs(rule["top"] - rule["bottom"]) < 0.1
                                and rule["x0"] <= split_x <= rule["x1"]
                                and rule["x1"] - rule["x0"] > 80
                            )
                        )
                        above = [y for y in horizontal_rules if y <= line["top"]]
                        below = [y for y in horizontal_rules if y > line["top"]]
                        if above and below:
                            in_band = sum(
                                max(above) <= other_line["top"] < min(below)
                                for other_line, _ in starts
                            )
                            if in_band == 1:
                                top = max(above) + 1.3
                                bottom = min(below) + 1.3

                        box = (split_x, top, page.width, bottom)
                        value = page.crop(box).extract_text(x_tolerance=2, y_tolerance=2) or ""
                        fields.append(
                            _evidence(
                                identity,
                                source_format="pdf",
                                source_path=path,
                                source_sha256=sha,
                                label=label,
                                value=value,
                                source_page=page_index + 1,
                                source_bbox_json=json.dumps(box),
                                extraction_method="pdf_text_geometry_candidate",
                            )
                        )

                    if not starts:
                        issues.append("metadata_fields_not_recognized")

            # Preserve page-local introductory documentation until the body starts.
            category = "notice"
            buffer: list[str] = []

            def flush_pdf() -> None:
                nonlocal buffer
                if buffer:
                    text_raw = "\n".join(buffer)
                    docs.append(
                        {
                            **identity,
                            "source_format": "pdf",
                            "source_path": str(path),
                            "source_sha256": sha,
                            "source_page": page_index + 1,
                            "source_record": "",
                            "documentation_category": category,
                            "text_raw": text_raw,
                            "extraction_status": classify_pdf_text_quality(text_raw),
                            "rule_version": RULE_VERSION,
                        }
                    )
                    buffer = []

            for line_index, line in enumerate(lines):
                text = line["text"]
                if (
                    header_index is not None
                    and header_index <= line_index < (metadata_end if metadata_end is not None else len(lines))
                ):
                    continue

                if BODY_BOUNDARY.match(text) and not (
                    category == "data_limitations"
                    and text.strip().endswith(":")
                    and _key(text).startswith("hexadecimal data")
                ):
                    flush_pdf()
                    boundary = text
                    break

                if _key(text) in {"comments", "data limitations"}:
                    flush_pdf()
                    category = "comments" if _key(text) == "comments" else "data_limitations"

                buffer.append(text)

            flush_pdf()
            if boundary:
                break

        if not boundary:
            issues.append(
                "intro_boundary_not_confirmed"
                if len(pdf.pages) <= max_intro_pages
                else "intro_page_limit_reached"
            )

    if not info_seen:
        issues.append("cdr_file_information_heading_not_found")
    if not fields:
        issues.append("no_metadata_fields_extracted")
    if not docs:
        issues.append("no_introductory_text_extracted_possible_image_only_pdf")

    present = {field["field_name"] for field in fields}
    missing_core = sorted(CORE_FIELDS - present)
    if missing_core:
        issues.append("core_metadata_fields_not_extracted:" + ",".join(missing_core))
    if any("(cid:" in doc.get("text_raw", "") for doc in docs):
        issues.append("pdf_text_contains_font_encoding_artifacts")

    return Group1ExtractionResult(
        source_format="pdf",
        source_path=str(path),
        fields=fields,
        documentation=docs,
        issues=issues,
        intro_pages=pages_seen,
        body_boundary=boundary,
    )


# ============================================================
# Unified Group 1 report extractor
# ============================================================

def extract_group1_report(
    *,
    identity: dict[str, Any],
    csv_path: str | Path | None = None,
    pdf_path: str | Path | None = None,
    max_intro_pages: int = 15,
) -> Group1ExtractionResult:
    """Production Group 1 entry point: choose source once, then extract once."""

    source_format, source_path = select_group1_source(csv_path=csv_path, pdf_path=pdf_path)
    if source_format == "csv":
        return extract_group1_csv(source_path, identity)
    return extract_group1_pdf(source_path, identity, max_intro_pages=max_intro_pages)


# ============================================================
# Observation-level classifier (kept for router compatibility)
# ============================================================

def classify_group1(observation: Observation) -> Group1RuleResult:
    label = normalize_group1_label(observation.label)
    section = normalize_text(observation.section_context)

    if observation.is_empty:
        return Group1RuleResult(False, "", "", "", "", "Empty row.")

    if observation.is_repeated:
        return Group1RuleResult(
            False,
            "",
            "",
            "",
            "",
            "Repeated measurement structure is outside Group 1 scope.",
        )

    if observation.is_table_header:
        return Group1RuleResult(False, "", "", "", "", "Measurement table header is outside Group 1.")

    canonical = canonical_group1_field(label)
    if canonical:
        return Group1RuleResult(
            True,
            GROUP_NAME,
            "report_metadata",
            canonical,
            "high",
            "Source label maps explicitly to a validated Group 1 metadata field.",
        )

    if observation.is_scalar and is_group1_metadata_section(section):
        return Group1RuleResult(
            True,
            GROUP_NAME,
            "report_metadata_unmapped",
            "",
            "medium",
            "Scalar observation occurs inside Group 1 metadata but has no validated mapping.",
            requires_review=True,
            review_reason="Unknown Group 1 metadata label requires review.",
        )

    if observation.is_section_heading and is_group1_metadata_section(observation.label):
        return Group1RuleResult(
            True,
            GROUP_NAME,
            "report_metadata_section",
            "",
            "high",
            "Section heading identifies Group 1 report metadata.",
        )

    if observation.is_section_heading and is_group1_documentation_section(observation.label):
        return Group1RuleResult(
            True,
            GROUP_NAME,
            documentation_category(observation.label) or "report_documentation",
            "",
            "high",
            "Section heading identifies validated Group 1 introductory documentation.",
        )

    if section and is_group1_documentation_section(section):
        return Group1RuleResult(
            True,
            GROUP_NAME,
            documentation_category(section) or "report_documentation",
            "",
            "medium",
            "Observation occurs inside validated Group 1 introductory documentation.",
        )

    return Group1RuleResult(False, "", "", "", "", "No Group 1 rule matched.")


# ============================================================
# Review / provenance helpers
# ============================================================

def classify_group1_contextual_candidate(
    source_label_status: str,
    canonical_field: str = "",
) -> tuple[bool, str]:
    status = normalize_text(source_label_status)
    if status == "absent_contextual_candidate":
        return True, "Source evidence is an unlabeled/contextual candidate and requires review."
    return False, ""


def build_group1_selected_record(
    *,
    identity: dict[str, Any],
    field_name: str,
    observations: Iterable[dict[str, Any]],
    selected_source: str,
    source_issue: str = "",
) -> dict[str, Any]:
    """
    Build one selected Group 1 record after report-level source selection.

    IMPORTANT: observations should come from ONE selected report source only.
    This function performs no CSV->PDF field-level fallback.
    """

    rows = list(observations)
    distinct = {(row.get("value_text", ""), row.get("value_status", "")) for row in rows}

    chosen: dict[str, Any] | None = None
    selection_status = "not_extracted"
    review_reasons: list[str] = []

    if len(distinct) > 1:
        selection_status = "multiple_source_values_requires_review"
        review_reasons.append("Selected report source contains multiple distinct values.")
    elif rows:
        chosen = rows[0]
        selection_status = "selected"
        if chosen.get("source_label_status") == "absent_contextual_candidate":
            selection_status = "candidate_requires_review"
            review_reasons.append("Unlabeled/contextual source candidate.")
        if str(chosen.get("value_raw", "")).lstrip().startswith("["):
            selection_status = "multivalue_requires_review"
            review_reasons.append("Selected source contains a multivalue introductory field.")

    if source_issue:
        review_reasons.append(f"Source audit issue: {source_issue}")

    value_text = str(chosen.get("value_text", "")) if chosen else ""
    value_raw = chosen.get("value_raw", "") if chosen else ""
    value_status = (
        str(chosen.get("value_status", ""))
        if chosen
        else ("ambiguous" if rows else "absent")
    )

    return {
        **identity,
        "field_name": field_name,
        "value_text": value_text,
        "value_raw": value_raw,
        "value_status": value_status,
        "selected_source": selected_source,
        "selection_status": selection_status,
        "requires_review": bool(review_reasons or "requires_review" in selection_status),
        "review_reasons": review_reasons,
        "selected_source_issue": source_issue,
        "selected_evidence": chosen,
        "all_source_evidence": rows,
        "semantic_status": (
            recovered_event_semantic_status()
            if field_name == "events_recovered_text"
            else "source_metadata"
        ),
        "rule_version": RULE_VERSION,
    }
