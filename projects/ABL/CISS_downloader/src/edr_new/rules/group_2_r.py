from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber


GROUP_NAME = "group2"
RULE_VERSION = "2.3"


# ============================================================
# Models
# ============================================================

@dataclass
class Group2ExtractionResult:
    source_format: str
    source_path: str
    record_candidates: list[dict[str, Any]]
    record_status: list[dict[str, Any]]
    retrieval_status: list[dict[str, Any]]
    context_status: list[dict[str, Any]]
    summary_rows: list[dict[str, Any]]
    summary_cells: list[dict[str, Any]]
    retrieval_event_descriptors: list[dict[str, Any]]
    pdf_fields: list[dict[str, Any]]
    pdf_unresolved: list[dict[str, Any]]
    group4_handoff_sections: list[dict[str, Any]]
    group4_handoff_rows: list[dict[str, Any]]
    issues: list[str]

    @property
    def requires_review(self) -> bool:
        return bool(self.issues)

    def audit_record(self, identity: dict[str, Any]) -> dict[str, Any]:
        return {
            **identity,
            "source_format": self.source_format,
            "source_path": self.source_path,
            "record_candidates": len(self.record_candidates),
            "record_status_rows": len(self.record_status),
            "retrieval_status_rows": len(self.retrieval_status),
            "context_status_rows": len(self.context_status),
            "summary_rows": len(self.summary_rows),
            "summary_cells": len(self.summary_cells),
            "retrieval_event_descriptors": len(self.retrieval_event_descriptors),
            "pdf_fields": len(self.pdf_fields),
            "pdf_unresolved": len(self.pdf_unresolved),
            "group4_handoff_sections": len(self.group4_handoff_sections),
            "group4_handoff_rows": len(self.group4_handoff_rows),
            "status": "extracted_needs_review" if self.issues else "extracted",
            "issue": "|".join(sorted(set(self.issues))),
            "rule_version": RULE_VERSION,
        }


# ============================================================
# Shared helpers
# ============================================================

def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value)).strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identifier(*parts: Any) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:24]


def _value_status(value: Any) -> str:
    text = _lower(value)
    if not text:
        return "blank"
    if text in {"n/a", "na", "sna", "not available", "not applicable", "unknown"}:
        return "not_available"
    return "present"


def _read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return [["" if cell is None else str(cell) for cell in row] for row in csv.reader(handle)]


def select_group2_source(
    *,
    csv_path: str | Path | None,
    pdf_path: str | Path | None,
) -> tuple[str, Path]:
    """CSV is selected for the whole report whenever available."""
    if csv_path:
        p = Path(csv_path)
        if p.is_file():
            return "csv", p

    if pdf_path:
        p = Path(pdf_path)
        if p.is_file():
            return "pdf", p

    raise FileNotFoundError("No usable CSV or PDF source is available for this report.")


# ============================================================
# Validated heading recognition
# ============================================================

TARGET_RE = re.compile(
    r"^(?:"
    r"system status"
    r"|status (?:at|of)"
    r"|event (?:record )?summary"
    r"|front/?rear event record summary"
    r"|event data"
    r"|crash event data"
    r"|record status"
    r"|event record(?: information| status)?\b"
    r"|impact event record\b"
    r"|pcm module information"
    r"|pcm edr data"
    r")",
    re.I,
)

EVENT_RE = re.compile(
    r"(?:"
    r"(?:most recent|\d+(?:st|nd|rd|th) prior|prior|first|second|third|\d+)"
    r"\s+(?:frontal\s*/\s*rear\s+)?(?:event|record)"
    r"|(?:impact )?event record\s*\d+"
    r"|record\s*\d+"
    r"|event\s*\d+"
    r"|rollover event record"
    r"|TRG INVALID\s*#\d+"
    r")",
    re.I,
)

HEX_RE = re.compile(
    r"^(?:pidsstart|pidsend|hexadecimal data|raw (?:hex|byte))\b",
    re.I,
)


def is_group2_target_heading(heading: str) -> bool:
    text = _norm(heading)
    if not text or not TARGET_RE.search(text):
        return False

    if re.search(
        r"\b(?:section of the report|reflects the|experienced from|refer to|indicates that)\b",
        text,
        re.I,
    ):
        return False

    if re.match(r"^Event Record Type\b", text, re.I):
        return False

    if len(text) > 180:
        return False

    if re.match(r"^(?:Impact )?Event Record\b", text, re.I):
        return bool(
            re.fullmatch(
                r"(?:Impact )?Event Record"
                r"(?:\s+#?\d+|\s+(?:Information|Status)|\s+Summary(?:\s+At\s+Retrieval)?)"
                r"(?:\s*\([^)]*\))?",
                text,
                re.I,
            )
        )

    return True


def classify_group2_heading(heading: str) -> tuple[str, str, str]:
    text = _norm(heading)

    if re.fullmatch(r"PCM MODULE INFORMATION", text, re.I):
        return "module_level", "", "not_event_specific"

    if re.fullmatch(r"PCM EDR DATA", text, re.I):
        return "pcm_buffer_scope_requires_review", "", "buffer_not_assumed_event"

    if re.search(r"retrieval|download|current", text, re.I):
        return "retrieval_level", "", "not_event_specific"

    if re.search(r"event.*summary|summary.*event", text, re.I):
        return "record_summary_scope_requires_review", "", "summary_not_one_event"

    match = re.search(r"\((.*)\)", text)
    label = match.group(1) if match and EVENT_RE.search(match.group(1)) else ""

    if not label:
        m = EVENT_RE.search(text)
        if m:
            label = m.group(0)

    if label:
        return "reported_record_candidate", label, "provisional_source_label"

    return "scope_requires_review", "", "unspecified"


# ============================================================
# Validated field routing
# ============================================================

GROUP2_FIELD_RE = re.compile(
    r"(?:"
    r"event record type"
    r"|life\s*time counter"
    r"|record.*status"
    r"|recording status"
    r"|complete.*record"
    r"|record.*complete"
    r"|locked"
    r"|freeze signal"
    r"|data (?:sent|recorded|available)"
    r"|concurrent event"
    r"|event (?:counter|number|type)"
    r"|crash type"
    r"|trg count"
    r"|number of events"
    r"|ignition cycle"
    r"|timer"
    r"|time from event"
    r"|linked.*page"
    r"|event recorded last"
    r")",
    re.I,
)

GROUP2_CONTEXT_LABELS = {
    "dynamic deployment event counter": "report_event_context",
    "dynamic event counter": "report_event_context",
    "dynamic onstar notification event counter": "report_event_context",
    "recording status, rollover crash info.": "event_context_unlinked",
}

GROUP3_DEFERRED_LABELS = {
    "event severity status, driver",
    "event severity status, passenger",
}

GROUP6_DEFERRED_LABELS = {
    "ignition cycles at investigation",
}

# Exact reviewed decisions from the frozen Group 2 working-table stage.
UNRESOLVED_STATUS_ROUTING = {
    "dynamic deployment event counter": (
        "group2_context",
        "report_event_context",
    ),
    "dynamic event counter": (
        "group2_context",
        "report_event_context",
    ),
    "dynamic onstar notification event counter": (
        "group2_context",
        "report_event_context",
    ),
    "recording status, rollover crash info.": (
        "group2_context",
        "event_context_unlinked",
    ),
    "event severity status, driver": (
        "group3",
        "",
    ),
    "event severity status, passenger": (
        "group3",
        "",
    ),
    "ignition cycles at investigation": (
        "group6",
        "",
    ),
}

RETRIEVAL_EVENT_DESCRIPTORS = {
    "unlocked event": {
        "descriptor_subtype": "standard_retrieved_event",
        "record_storage_status": "not_assumed",
    },
    "locked side event": {
        "descriptor_subtype": "standard_retrieved_event",
        "record_storage_status": "not_assumed",
    },
    "locked rollover event": {
        "descriptor_subtype": "standard_retrieved_event",
        "record_storage_status": "not_assumed",
    },
    "fuel cutoff level 1": {
        "descriptor_subtype": "fuel_cutoff_event_descriptor",
        "record_storage_status": "not_assumed",
    },
}


def route_group2_field(label: str) -> tuple[str, str]:
    """
    Exact frozen Group 2 field-audit routing.

    Returns:
        proposed_group, routing_reason

    This deliberately preserves the validated historical routing used to
    create group2_final_v1. Semantic cleanup belongs to later groups/stages.
    """
    t = _lower(label)

    if re.search(
        r"warning lamp|indicator|dtc|diagnostic|part number|serial number|supplier|"
        r"configuration|vin|voltage|software|hardware|system type|"
        r"component identifier|traceability",
        t,
    ):
        return (
            "group6_diagnostics_configuration_candidate",
            "indicator_diagnostic_or_module_identifier",
        )

    if re.search(
        r"event record type|algorithm active|event severity status|life\s*time counter|"
        r"operation.*time|record.*status|recording status|complete.*record|"
        r"record.*complete|locked|freeze signal|data (?:sent|recorded|available)|"
        r"concurrent event|event (?:counter|number|type)|crash type|trg count|"
        r"number of events|ignition cycle|timer|time from event|time from pre-crash|"
        r"linked.*page|event recorded last",
        t,
    ):
        return (
            "group2_status_context",
            "record_status_counter_or_reference_pattern",
        )

    if re.search(
        r"air.?bag|pretension|belt|restraint|occupan|seat|deployment loop|squib|"
        r"loop commanded|roof rail|head curtain",
        t,
    ):
        return (
            "group3_restraint_candidate",
            "restraint_or_occupant_status_pattern",
        )

    if re.search(
        r"delta.?v|velocity change|acceleration|roll angle|roll rate|"
        r"angular velocity|pressure",
        t,
    ):
        return (
            "group5_crash_measurement_candidate",
            "measurement_word_requires_definition_review",
        )

    if re.search(
        r"speed|rpm|throttle|accelerator|brak|steer|gear|cruise|engine torque",
        t,
    ):
        return (
            "group4_vehicle_measurement_candidate",
            "vehicle_parameter_requires_time_scope_review",
        )

    return (
        "unclassified_requires_review",
        "no_rule_matched",
    )


# ============================================================
# Record label / trigger handling
# ============================================================

def split_record_label_and_trigger(record_label_raw: str) -> tuple[str, str]:
    text = _upper(record_label_raw)

    match = re.match(
        r"^(.*?)"
        r"(?:\s*[,;\-]?\s*TRG(?:IGGER)?\s*#?\s*([A-Z0-9]+))$",
        text,
    )

    if not match:
        return text, ""

    return match.group(1).strip(" ,;-"), match.group(2).strip()


def link_summary_to_record_candidate(
    report_id: str,
    reported_record_label: str,
    reported_trigger_reference: str,
    record_candidates_by_report: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    summary_label = _upper(reported_record_label)
    summary_trigger = _upper(reported_trigger_reference)
    candidates = record_candidates_by_report.get(report_id, [])

    trigger_matches = []

    for candidate in candidates:
        candidate_label, candidate_trigger = split_record_label_and_trigger(
            candidate.get("record_label_raw", "")
        )

        if (
            candidate_label == summary_label
            and candidate_trigger
            and candidate_trigger == summary_trigger
        ):
            trigger_matches.append(candidate)

    if len(trigger_matches) == 1:
        candidate = trigger_matches[0]
        return {
            "linked_record_candidate_id": candidate.get("record_candidate_id", ""),
            "linked_record_label_raw": candidate.get("record_label_raw", ""),
            "link_method": "same_report_exact_label_trigger",
            "link_status": "linked_exact_label_trigger",
            "link_candidate_count": 1,
            "requires_review": False,
        }

    label_matches = []

    for candidate in candidates:
        candidate_label, _ = split_record_label_and_trigger(
            candidate.get("record_label_raw", "")
        )
        if candidate_label == summary_label:
            label_matches.append(candidate)

    if len(label_matches) == 1:
        candidate = label_matches[0]
        return {
            "linked_record_candidate_id": candidate.get("record_candidate_id", ""),
            "linked_record_label_raw": candidate.get("record_label_raw", ""),
            "link_method": "same_report_unique_exact_label",
            "link_status": "linked_unique_label",
            "link_candidate_count": 1,
            "requires_review": False,
        }

    if not candidates:
        return {
            "linked_record_candidate_id": "",
            "linked_record_label_raw": "",
            "link_method": "report_has_no_record_candidates",
            "link_status": "no_record_candidate_available",
            "link_candidate_count": 0,
            "requires_review": True,
        }

    return {
        "linked_record_candidate_id": "",
        "linked_record_label_raw": "",
        "link_method": "no_unique_conservative_match",
        "link_status": "ambiguous_or_unresolved",
        "link_candidate_count": max(len(trigger_matches), len(label_matches)),
        "requires_review": True,
    }


# ============================================================
# CSV extraction
# ============================================================

def _csv_headings(rows: list[list[str]], intro_end: int) -> list[tuple[int, str]]:
    headings: list[tuple[int, str]] = []

    for i, row in enumerate(rows):
        if i <= intro_end:
            continue

        filled = [_norm(cell) for cell in row if _norm(cell)]

        if len(filled) != 1:
            continue

        heading = filled[0]

        if (
            is_group2_target_heading(heading)
            or HEX_RE.search(heading)
            or (heading.isupper() and len(heading) > 5)
        ):
            headings.append((i, heading))

    return headings


def _emit_csv_section(
    *,
    identity: dict[str, Any],
    source_path: Path,
    source_sha256: str,
    heading: str,
    section_rows: list[list[str]],
    source_record: int,
    source_end_record: int,
    record_candidates: dict[str, dict[str, Any]],
    record_status: list[dict[str, Any]],
    retrieval_status: list[dict[str, Any]],
    context_status: list[dict[str, Any]],
    summary_raw_rows: list[dict[str, Any]],
    retrieval_event_descriptors: list[dict[str, Any]],
    issues: list[str],
) -> None:
    scope, event_label, _ = classify_group2_heading(heading)

    section_id = "g2s_" + _identifier(
        identity.get("report_id", ""),
        "csv",
        source_record,
        heading,
    )

    record_candidate_id = ""

    if scope == "reported_record_candidate":
        record_candidate_id = "g2r_" + _identifier(
            identity.get("report_id", ""),
            _upper(event_label),
        )

        candidate = record_candidates.setdefault(
            record_candidate_id,
            {
                **identity,
                "record_candidate_id": record_candidate_id,
                "record_label_raw": event_label,
                "identity_status": "source_label_candidate_not_validated_event",
                "section_count": 0,
                "rule_version": RULE_VERSION,
            },
        )
        candidate["section_count"] += 1

    useful = [
        (i, row)
        for i, row in enumerate(section_rows)
        if any(_norm(cell) for cell in row)
    ]

    content = "\n".join(",".join(row) for _, row in useful)

    if re.search(r"contains no recorded data", content, re.I):
        return

    is_summary = "summary" in heading.lower()
    tabular = (
        is_summary
        or scope == "pcm_buffer_scope_requires_review"
        or any(sum(bool(_norm(c)) for c in row) > 2 for _, row in useful)
    )

    if tabular:
        if scope == "pcm_buffer_scope_requires_review":
            # Do not force PCM buffer material into Group 2.
            issues.append("pcm_buffer_requires_group4_structural_handling")
            return

        header = useful[0][1] if useful else []

        for i, row in useful:
            summary_raw_rows.append(
                {
                    **identity,
                    "section_id": section_id,
                    "record_candidate_id": record_candidate_id,
                    "scope_candidate": scope,
                    "source_format": "csv",
                    "source_path": str(source_path),
                    "source_sha256": source_sha256,
                    "source_heading": heading,
                    "source_record": source_record + i + 1,
                    "row_role": (
                        "header_candidate"
                        if useful and i == useful[0][0]
                        else "data_candidate"
                    ),
                    "source_header_json": json.dumps(header, ensure_ascii=False),
                    "source_row_json": json.dumps(row, ensure_ascii=False),
                }
            )
        return

    for i, row in useful:
        if len(row) < 2:
            values = [_norm(v) for v in row if _norm(v)]

            if scope == "retrieval_level" and len(values) == 1:
                descriptor = RETRIEVAL_EVENT_DESCRIPTORS.get(values[0].lower())

                if descriptor:
                    retrieval_event_descriptors.append(
                        {
                            **identity,
                            "section_id": section_id,
                            "source_format": "csv",
                            "source_path": str(source_path),
                            "source_sha256": source_sha256,
                            "source_heading": heading,
                            "source_record": source_record + i + 1,
                            "descriptor_raw": values[0],
                            "descriptor_normalized": values[0].lower(),
                            "descriptor_type": "retrieved_event_descriptor",
                            **descriptor,
                            "requires_review": False,
                            "rule_version": RULE_VERSION,
                        }
                    )
            continue

        label_raw = row[0]
        value_raw = row[1]

        original_group, reason = route_group2_field(label_raw)

        base = {
            **identity,
            "section_id": section_id,
            "record_candidate_id": record_candidate_id,
            "scope_candidate": scope,
            "source_format": "csv",
            "source_path": str(source_path),
            "source_sha256": source_sha256,
            "source_heading": heading,
            "source_record": source_record + i + 1,
            "field_label_raw": label_raw,
            "value_raw": value_raw,
            "value_status": _value_status(value_raw),
            "proposed_group": original_group,
            "routing_reason": reason,
            "resolved_scope": "",
            "rule_version": RULE_VERSION,
        }

        # Preserve the frozen Group 2 working-table behavior exactly.
        if original_group != "group2_status_context":
            continue

        if scope == "reported_record_candidate":
            record_status.append(base)
            continue

        if scope == "retrieval_level":
            retrieval_status.append(base)
            continue

        decision = UNRESOLVED_STATUS_ROUTING.get(_lower(label_raw))

        if decision is None:
            # Historically this remained unresolved and was not promoted into
            # Group 2 context.
            continue

        target, resolved_scope = decision
        base["resolved_scope"] = resolved_scope

        if target == "group2_context":
            context_status.append(base)
        # group3/group6 reviewed deferrals remain outside Group 2 outputs.


def _build_summary_outputs(
    raw_rows: list[dict[str, Any]],
    record_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates_by_report: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for record in record_candidates:
        candidates_by_report[record.get("report_id", "")].append(record)

    summary_rows: list[dict[str, Any]] = []
    summary_cells: list[dict[str, Any]] = []

    for row in raw_rows:
        if row.get("row_role") != "data_candidate":
            continue

        header = json.loads(row.get("source_header_json") or "[]")
        values = json.loads(row.get("source_row_json") or "[]")

        summary_id = "g2summary_" + _identifier(
            row.get("section_id", ""),
            row.get("source_record", ""),
        )

        label = ""
        trigger = ""

        for index, heading in enumerate(header):
            if index >= len(values):
                continue

            h = _lower(heading)

            if h in {
                "events recorded",
                "event recorded",
                "event record",
                "event",
            }:
                label = values[index]

            if h in {"trg count", "trigger count"}:
                trigger = values[index]

        if not label and not trigger and len(values) >= 2:
            v0 = _norm(values[0])
            v1 = _norm(values[1])

            if "summary" in _lower(row.get("source_heading", "")) and "event" in v0.lower() and v1.isdigit():
                label = v0
                trigger = v1

        link = link_summary_to_record_candidate(
            report_id=row.get("report_id", ""),
            reported_record_label=label,
            reported_trigger_reference=trigger,
            record_candidates_by_report=candidates_by_report,
        )

        summary_rows.append(
            {
                "report_id": row.get("report_id", ""),
                "case_id": row.get("case_id", ""),
                "vehicle_number": row.get("vehicle_number", ""),
                "export_basename": row.get("export_basename", ""),
                "summary_row_id": summary_id,
                "section_id": row.get("section_id", ""),
                "source_record": row.get("source_record", ""),
                "reported_record_label": label,
                "reported_trigger_reference": trigger,
                "source_path": row.get("source_path", ""),
                "source_sha256": row.get("source_sha256", ""),
                "source_heading": row.get("source_heading", ""),
                "row_values_json": row.get("source_row_json", "[]"),
                **link,
                "rule_version": RULE_VERSION,
            }
        )

        for index, value in enumerate(values):
            heading = header[index] if index < len(header) else ""
            summary_cells.append(
                {
                    "report_id": row.get("report_id", ""),
                    "case_id": row.get("case_id", ""),
                    "vehicle_number": row.get("vehicle_number", ""),
                    "export_basename": row.get("export_basename", ""),
                    "summary_row_id": summary_id,
                    "cell_index": index,
                    "heading_raw": heading,
                    "value_raw": value,
                    "value_status": _value_status(value),
                    "rule_version": RULE_VERSION,
                }
            )

    return summary_rows, summary_cells


def extract_group2_csv(
    path: str | Path,
    identity: dict[str, Any],
) -> Group2ExtractionResult:
    path = Path(path)
    rows = _read_csv_rows(path)
    sha = _digest(path)

    record_candidates: dict[str, dict[str, Any]] = {}
    record_status: list[dict[str, Any]] = []
    retrieval_status: list[dict[str, Any]] = []
    context_status: list[dict[str, Any]] = []
    summary_raw_rows: list[dict[str, Any]] = []
    descriptors: list[dict[str, Any]] = []
    issues: list[str] = []

    intro_end = next(
        (
            i
            for i, row in enumerate(rows)
            if row and _upper(row[0]) == "DATA LIMITATIONS"
        ),
        None,
    )

    if intro_end is None:
        raise ValueError("Introduction boundary not found; inspect CSV before extraction.")

    headings = _csv_headings(rows, intro_end)

    for j, (start, heading) in enumerate(headings):
        if not is_group2_target_heading(heading):
            continue

        end = headings[j + 1][0] if j + 1 < len(headings) else len(rows)

        _emit_csv_section(
            identity=identity,
            source_path=path,
            source_sha256=sha,
            heading=heading,
            section_rows=rows[start + 1 : end],
            source_record=start + 1,
            source_end_record=end,
            record_candidates=record_candidates,
            record_status=record_status,
            retrieval_status=retrieval_status,
            context_status=context_status,
            summary_raw_rows=summary_raw_rows,
            retrieval_event_descriptors=descriptors,
            issues=issues,
        )

    records = list(record_candidates.values())
    summary_rows, summary_cells = _build_summary_outputs(summary_raw_rows, records)

    return Group2ExtractionResult(
        source_format="csv",
        source_path=str(path),
        record_candidates=records,
        record_status=record_status,
        retrieval_status=retrieval_status,
        context_status=context_status,
        summary_rows=summary_rows,
        summary_cells=summary_cells,
        retrieval_event_descriptors=descriptors,
        pdf_fields=[],
        pdf_unresolved=[],
        group4_handoff_sections=[],
        group4_handoff_rows=[],
        issues=issues,
    )


# ============================================================
# PDF-only extraction
# ============================================================

# ============================================================
# Exact validated PDF structural helpers
# Migrated from build_edr_group2_pdf_structured.py
# ============================================================

def normalize_space(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )


def normalize_key(value):
    value = normalize_space(value)
    value = value.casefold()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return normalize_space(value)


def identifier(*parts):
    text = "|".join(
        str(part)
        for part in parts
    )

    return hashlib.sha256(
        text.encode()
    ).hexdigest()[:24]


def value_state(value):
    text = normalize_space(
        value
    ).casefold()

    if not text:
        return "blank"

    if text in {
        "n/a",
        "na",
        "sna",
        "not available",
        "not applicable",
        "unknown",
    }:
        return "not_available"

    return "present"


def safe_json(
    value,
    default=None,
):
    if default is None:
        default = []

    try:
        return json.loads(value)

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        return default


def resolve_source_path(
    value,
    source_root: Path,
):
    raw = normalize_space(value)

    if not raw:
        return None

    path = Path(raw)

    if path.exists():
        return path

    candidate = (
        source_root
        / path
    )

    if candidate.exists():
        return candidate

    return None


# ============================================================
# Bounding boxes
# ============================================================

def parse_bbox(
    bbox_json,
    page,
):
    bbox = safe_json(
        bbox_json,
        default=[],
    )

    if (
        isinstance(bbox, list)
        and len(bbox) == 4
    ):
        try:
            x0 = float(bbox[0])
            top = float(bbox[1])
            x1 = float(bbox[2])
            bottom = float(bbox[3])

            x0 = max(
                0.0,
                x0,
            )

            top = max(
                0.0,
                top,
            )

            x1 = min(
                float(page.width),
                x1,
            )

            bottom = min(
                float(page.height),
                bottom,
            )

            if (
                x1 > x0
                and bottom > top
            ):
                return (
                    x0,
                    top,
                    x1,
                    bottom,
                )

        except (
            TypeError,
            ValueError,
        ):
            pass

    return (
        0.0,
        0.0,
        float(page.width),
        float(page.height),
    )


# ============================================================
# PDF table extraction
# ============================================================

def clean_table(table):
    cleaned = []

    for row in table or []:

        if row is None:
            continue

        values = [
            normalize_space(cell)
            for cell in row
        ]

        if any(values):
            cleaned.append(values)

    return cleaned


def table_is_useful(table):

    if len(table) < 1:
        return False

    max_columns = max(
        len(row)
        for row in table
    )

    if max_columns < 2:
        return False

    useful_rows = sum(
        1
        for row in table
        if sum(
            bool(
                normalize_space(value)
            )
            for value in row
        ) >= 2
    )

    return (
        useful_rows >= 1
    )


def extract_candidate_tables(
    cropped_page,
):
    strategies = [
        (
            "lines",
            {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
                "join_tolerance": 3,
                "intersection_tolerance": 3,
            },
        ),
        (
            "text",
            {
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "min_words_vertical": 2,
                "min_words_horizontal": 1,
                "text_x_tolerance": 2,
                "text_y_tolerance": 3,
            },
        ),
    ]

    candidates = []

    for method, settings in strategies:

        try:
            extracted = (
                cropped_page.extract_tables(
                    table_settings=settings
                )
                or []
            )

        except Exception:
            continue

        for table_index, table in enumerate(extracted):

            cleaned = clean_table(table)

            if table_is_useful(cleaned):
                candidates.append({
                    "method": method,
                    "table_index": table_index,
                    "rows": cleaned,
                })

    return candidates


def choose_best_table(candidates):

    if not candidates:
        return None

    def score(candidate):

        rows = candidate["rows"]

        multi_cell_rows = sum(
            1
            for row in rows
            if sum(
                bool(
                    normalize_space(cell)
                )
                for cell in row
            ) >= 2
        )

        populated = sum(
            sum(
                bool(
                    normalize_space(cell)
                )
                for cell in row
            )
            for row in rows
        )

        return (
            multi_cell_rows,
            populated,
            len(rows),
        )

    return max(
        candidates,
        key=score,
    )


# ============================================================
# Fragment reconstruction
# ============================================================

def join_label_fragments(parts):

    parts = [
        normalize_space(part)
        for part in parts
        if normalize_space(part)
    ]

    if not parts:
        return ""

    result = parts[0]

    for part in parts[1:]:

        if not part:
            continue

        if (
            part[0].islower()
            or result.endswith("-")
        ):
            result += part

        else:
            result += (
                " "
                + part
            )

    return normalize_space(result)


# ============================================================
# Units
# ============================================================

KNOWN_UNITS = {
    "mph",
    "km/h",
    "kmh",
    "kph",
    "rpm",
    "%",
    "percent",
    "g",
    "ms",
    "msec",
    "milliseconds",
    "s",
    "sec",
    "seconds",
    "degrees",
    "degree",
    "deg",
    "rad/s",
    "deg/s",
    "psi",
    "kpa",
    "volts",
    "volt",
    "v",
}


def looks_like_unit(value):
    return (
        normalize_space(
            value
        ).casefold()
        in KNOWN_UNITS
    )


# ============================================================
# Time-series detection
# ============================================================

TIME_HEADER_PATTERNS = [
    r"\bseconds?\s+before\b",
    r"\bseconds?\s+after\b",
    r"\btime\b",
    r"\brelative\s+time\b",
    r"\bvehicle\s+speed\b",
    r"\bengine\s+speed\b",
    r"\bengine\s+rpm\b",
    r"\bthrottle\b",
    r"\baccelerator\b",
    r"\bbrake\s+switch\b",
    r"\blongitudinal\b",
    r"\blateral\b",
    r"\bdelta[- ]?v\b",
    r"\bacceleration\b",
    r"\bangular\s+velocity\b",
    r"\broll\s+rate\b",
]


def row_text(row):
    return normalize_space(
        " ".join(
            normalize_space(cell)
            for cell in row
            if normalize_space(cell)
        )
    )


def looks_like_timeseries_header_text(text):

    text = normalize_space(
        text
    ).casefold()

    if not text:
        return False

    matches = sum(
        1
        for pattern
        in TIME_HEADER_PATTERNS
        if re.search(
            pattern,
            text,
            re.I,
        )
    )

    return (
        matches >= 2
    )


def looks_numeric_token(value):

    text = normalize_space(value)

    if not text:
        return False

    if text.casefold() in {
        "n/a",
        "na",
    }:
        return True

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def looks_like_timeseries_data_row(row):

    populated = [
        normalize_space(cell)
        for cell in row
        if normalize_space(cell)
    ]

    if len(populated) < 2:
        return False

    if not looks_numeric_token(
        populated[0]
    ):
        return False

    return any(
        normalize_space(value)
        for value in populated[1:]
    )


def find_timeseries_header_window(
    rows,
    start,
    max_header_rows=6,
    data_lookahead=10,
):
    """
    Test whether a temporal block starts at `start`.

    Returns:
        {
            "header_start": int,
            "header_end": int,
            "first_data_index": int
        }

    or None.
    """

    for header_len in range(
        1,
        max_header_rows + 1,
    ):

        header_end = (
            start
            + header_len
        )

        if header_end > len(rows):
            break

        header_rows = rows[
            start:header_end
        ]

        combined_header = (
            " ".join(
                row_text(row)
                for row in header_rows
            )
        )

        if not looks_like_timeseries_header_text(
            combined_header
        ):
            continue

        future_end = min(
            len(rows),
            header_end
            + data_lookahead,
        )

        future_rows = rows[
            header_end:future_end
        ]

        numeric_positions = [
            index
            for index, candidate
            in enumerate(future_rows)
            if looks_like_timeseries_data_row(
                candidate
            )
        ]

        if len(
            numeric_positions
        ) < 2:
            continue

        if numeric_positions[0] > 3:
            continue

        first_data_index = (
            header_end
            + numeric_positions[0]
        )

        return {
            "header_start":
                start,

            "header_end":
                header_end,

            "first_data_index":
                first_data_index,
        }

    return None


def extend_timeseries_block(
    rows,
    first_data_index,
):
    """
    Extend a detected time-series block through repeated sample rows.

    Allow occasional header/unit/continuation rows inside the table,
    but stop once the sequence clearly returns to ordinary text.

    Returns exclusive end index.
    """

    index = first_data_index

    last_data_index = (
        first_data_index - 1
    )

    nondata_run = 0
    max_nondata_run = 3

    while index < len(rows):

        row = rows[index]

        if looks_like_timeseries_data_row(
            row
        ):
            last_data_index = index
            nondata_run = 0
            index += 1
            continue

        # Empty/fragmented/unit-like rows can appear inside
        # a temporal table.
        text = row_text(row)

        if not text:
            nondata_run += 1

        else:
            # If another strong temporal header starts here,
            # stop so it can become a separate block.
            if (
                index > first_data_index
                and find_timeseries_header_window(
                    rows,
                    index,
                )
                is not None
            ):
                break

            nondata_run += 1

        if nondata_run > max_nondata_run:
            break

        index += 1

    if last_data_index < first_data_index:
        return first_data_index

    return (
        last_data_index + 1
    )


def detect_timeseries_blocks(rows):
    """
    Detect ALL non-overlapping temporal blocks in a PDF table.

    A block contains:
    - one or more temporal header rows
    - optional unit/continuation rows
    - repeated numeric-leading samples

    Returns a list of dicts:
        {
            "start": int,
            "header_end": int,
            "first_data_index": int,
            "end": int
        }

    `end` is exclusive.
    """

    blocks = []

    index = 0

    while index < len(rows):

        detected = (
            find_timeseries_header_window(
                rows,
                index,
            )
        )

        if detected is None:
            index += 1
            continue

        block_end = extend_timeseries_block(
            rows,
            detected[
                "first_data_index"
            ],
        )

        # Must contain at least two actual sample rows.
        sample_count = sum(
            1
            for row in rows[
                detected[
                    "first_data_index"
                ]:
                block_end
            ]
            if looks_like_timeseries_data_row(
                row
            )
        )

        if sample_count < 2:
            index += 1
            continue

        blocks.append({
            "start":
                detected[
                    "header_start"
                ],

            "header_end":
                detected[
                    "header_end"
                ],

            "first_data_index":
                detected[
                    "first_data_index"
                ],

            "end":
                block_end,
        })

        index = max(
            block_end,
            index + 1,
        )

    return blocks


def classify_timeseries_row(
    row,
    row_index,
    block,
):
    if (
        block["start"]
        <= row_index
        < block["first_data_index"]
    ):
        if (
            row_index
            == block["start"]
        ):
            return "header_candidate"

        return (
            "header_or_unit_continuation"
        )

    if looks_like_timeseries_data_row(
        row
    ):
        return "data_candidate"

    return (
        "header_or_unit_continuation"
    )


# ============================================================
# Field reconstruction
# ============================================================

def reconstruct_field_row(
    row,
    section_heading,
):

    populated = [
        normalize_space(cell)
        for cell in row
        if normalize_space(cell)
    ]

    if len(populated) < 2:
        return None

    entire_row = join_label_fragments(
        populated
    )

    if (
        normalize_key(
            entire_row
        )
        == normalize_key(
            section_heading
        )
    ):
        return None

    value = populated[-1]

    before_value = populated[:-1]

    unit = ""

    if (
        len(before_value) >= 2
        and looks_like_unit(
            before_value[-1]
        )
    ):
        unit = before_value[-1]
        label_parts = before_value[:-1]

    else:
        label_parts = before_value

    label = join_label_fragments(
        label_parts
    )

    if (
        not label
        or not value
    ):
        return None

    if (
        normalize_key(
            label
        )
        == normalize_key(
            section_heading
        )
    ):
        return None

    if not re.search(
        r"[A-Za-z]",
        label,
    ):
        return None

    return {
        "field_label_raw":
            label,

        "value_raw":
            value,

        "unit_raw":
            unit,

        "extraction_method":
            "table_row_reconstruction",
    }


# ============================================================
# Visual-line fallback
# ============================================================

def extract_words_from_crop(
    cropped_page,
):
    try:
        return (
            cropped_page.extract_words(
                x_tolerance=2,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=True,
            )
            or []
        )

    except Exception:
        return []


def group_words_into_lines(
    words,
    y_tolerance=3.0,
):

    if not words:
        return []

    ordered = sorted(
        words,
        key=lambda word: (
            float(
                word.get(
                    "top",
                    0,
                )
            ),
            float(
                word.get(
                    "x0",
                    0,
                )
            ),
        ),
    )

    lines = []

    for word in ordered:

        top = float(
            word.get(
                "top",
                0,
            )
        )

        best = None
        best_distance = None

        for line in lines:

            distance = abs(
                line["top"]
                - top
            )

            if (
                distance <= y_tolerance
                and (
                    best_distance is None
                    or distance
                    < best_distance
                )
            ):
                best = line
                best_distance = distance

        if best is None:

            lines.append({
                "top":
                    top,

                "words":
                    [word],
            })

        else:
            best["words"].append(word)

    for line in lines:

        line["words"].sort(
            key=lambda word:
                float(
                    word.get(
                        "x0",
                        0,
                    )
                )
        )

        line["text"] = normalize_space(
            " ".join(
                word.get(
                    "text",
                    ""
                )
                for word
                in line["words"]
            )
        )

    return sorted(
        lines,
        key=lambda line:
            line["top"],
    )


def split_colon_field(text):

    text = normalize_space(text)

    if ":" not in text:
        return None

    left, right = text.split(
        ":",
        1,
    )

    left = normalize_space(left)
    right = normalize_space(right)

    if (
        not left
        or not right
    ):
        return None

    return {
        "field_label_raw":
            left,

        "value_raw":
            right,

        "unit_raw":
            "",

        "extraction_method":
            "colon_split",
    }


def split_line_by_visual_gap(words):

    if len(words) < 2:
        return None

    ordered = sorted(
        words,
        key=lambda word:
            float(
                word.get(
                    "x0",
                    0,
                )
            ),
    )

    gaps = []

    for index in range(
        len(ordered) - 1
    ):

        left = ordered[index]

        right = ordered[
            index + 1
        ]

        gap = (
            float(
                right.get(
                    "x0",
                    0,
                )
            )
            - float(
                left.get(
                    "x1",
                    0,
                )
            )
        )

        gaps.append(
            (
                gap,
                index,
            )
        )

    if not gaps:
        return None

    largest_gap, split_index = max(
        gaps,
        key=lambda item:
            item[0],
    )

    positive_gaps = sorted(
        gap
        for gap, _
        in gaps
        if gap > 0
    )

    if positive_gaps:

        typical_gap = (
            positive_gaps[
                len(
                    positive_gaps
                )
                // 2
            ]
        )

    else:
        typical_gap = 0

    threshold = max(
        24.0,
        typical_gap * 3.0,
    )

    if largest_gap < threshold:
        return None

    left_words = ordered[
        :split_index + 1
    ]

    right_words = ordered[
        split_index + 1:
    ]

    label = normalize_space(
        " ".join(
            word.get(
                "text",
                ""
            )
            for word
            in left_words
        )
    )

    value = normalize_space(
        " ".join(
            word.get(
                "text",
                ""
            )
            for word
            in right_words
        )
    )

    if (
        not label
        or not value
    ):
        return None

    return {
        "field_label_raw":
            label,

        "value_raw":
            value,

        "unit_raw":
            "",

        "extraction_method":
            "visual_gap_split",
    }


def parse_visual_line(line):

    text = normalize_space(
        line.get(
            "text",
            ""
        )
    )

    colon = split_colon_field(text)

    if colon:
        return colon

    return split_line_by_visual_gap(
        line.get(
            "words",
            [],
        )
    )


# ============================================================
# Summary sections
# ============================================================

def is_true_table_section(heading):

    return (
        "summary"
        in normalize_space(
            heading
        ).casefold()
    )


# ============================================================
# Row masks
# ============================================================

def build_timeseries_row_map(
    rows,
    blocks,
):
    """
    Map each row index to its temporal block index.
    """

    row_to_block = {}

    for block_index, block in enumerate(
        blocks
    ):

        for row_index in range(
            block["start"],
            block["end"],
        ):
            row_to_block[
                row_index
            ] = block_index

    return row_to_block


# ============================================================
# Main
# ============================================================


def extract_group2_pdf(
    path: str | Path,
    identity: dict[str, Any],
) -> Group2ExtractionResult:
    """
    Validated PDF-only Group 2 fallback.

    This is a single-report adaptation of the frozen
    build_edr_group2_pdf_structured.py behavior.

    PDF summary evidence remains separate and is NOT merged into
    retrieval_summary_rows. Embedded temporal structures are handed
    off to Group 4.
    """
    path = Path(path)
    sha = _digest(path)

    record_candidates: dict[str, dict[str, Any]] = {}

    pdf_fields: list[dict[str, Any]] = []
    pdf_unresolved: list[dict[str, Any]] = []
    g4_sections: list[dict[str, Any]] = []
    g4_rows: list[dict[str, Any]] = []

    issues: list[str] = []

    # --------------------------------------------------------
    # Recreate the validated first-stage PDF section evidence.
    # --------------------------------------------------------
    sections: list[dict[str, Any]] = []

    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            lines = page.extract_text_lines(
                layout=False,
                strip=True,
            )

            for line_index, line in enumerate(lines):
                heading = _norm(
                    line.get("text", "")
                )

                if not is_group2_target_heading(
                    heading
                ):
                    continue

                bottom = page.height - 20

                for next_line in lines[
                    line_index + 1:
                ]:
                    candidate = _norm(
                        next_line.get(
                            "text",
                            "",
                        )
                    )

                    if (
                        is_group2_target_heading(candidate)
                        or HEX_RE.search(candidate)
                        or re.match(
                            r"^(?:"
                            r"Pre[- ]crash"
                            r"|Deployment (?:Data|Command)"
                            r"|(?:Longitudinal|Lateral|Rollover).*Data"
                            r"|.*Crash Pulse"
                            r"|Disclaimer"
                            r")",
                            candidate,
                            re.I,
                        )
                    ):
                        bottom = next_line["top"]
                        break

                    if re.search(
                        r"Page\s+\d+\s+of\s+\d+",
                        candidate,
                        re.I,
                    ):
                        bottom = next_line["top"]
                        break

                scope, event_label, _ = (
                    classify_group2_heading(
                        heading
                    )
                )

                section_id = (
                    "g2s_"
                    + _identifier(
                        identity.get(
                            "report_id",
                            "",
                        ),
                        "pdf",
                        "",
                        page_number,
                        heading,
                    )
                )

                record_candidate_id = ""

                if (
                    scope
                    == "reported_record_candidate"
                ):
                    record_candidate_id = (
                        "g2r_"
                        + _identifier(
                            identity.get(
                                "report_id",
                                "",
                            ),
                            _upper(event_label),
                        )
                    )

                    candidate = (
                        record_candidates.setdefault(
                            record_candidate_id,
                            {
                                **identity,
                                "record_candidate_id":
                                    record_candidate_id,
                                "record_label_raw":
                                    event_label,
                                "identity_status":
                                    (
                                        "source_label_candidate_"
                                        "not_validated_event"
                                    ),
                                "section_count":
                                    0,
                                "rule_version":
                                    RULE_VERSION,
                            },
                        )
                    )

                    candidate[
                        "section_count"
                    ] += 1

                crop_box = [
                    0,
                    line["top"],
                    page.width,
                    bottom,
                ]

                crop = page.crop(
                    tuple(crop_box)
                )

                crop_text = (
                    crop.extract_text(
                        x_tolerance=2,
                        y_tolerance=2,
                    )
                    or ""
                )

                availability = (
                    "no_recorded_data"
                    if re.search(
                        r"contains no recorded data",
                        crop_text,
                        re.I,
                    )
                    else (
                        "content_present"
                        if crop_text.strip()
                        else "empty"
                    )
                )

                sections.append({
                    **identity,
                    "section_id":
                        section_id,
                    "record_candidate_id":
                        record_candidate_id,
                    "source_format":
                        "pdf",
                    "source_path":
                        str(path),
                    "source_sha256":
                        sha,
                    "source_record":
                        "",
                    "source_end_record":
                        "",
                    "source_page":
                        page_number,
                    "source_bbox_json":
                        json.dumps(
                            crop_box
                        ),
                    "source_heading":
                        heading,
                    "scope_candidate":
                        scope,
                    "event_label_candidate":
                        event_label,
                    "availability":
                        availability,
                })

    pdf_sections = [
        section
        for section in sections
        if (
            section.get(
                "availability",
                "",
            )
            == "content_present"
        )
    ]

    # --------------------------------------------------------
    # Exact structured PDF extraction behavior.
    # --------------------------------------------------------
    with pdfplumber.open(path) as pdf:

        for section in pdf_sections:

            page_number = int(
                section[
                    "source_page"
                ]
            )

            page = pdf.pages[
                page_number - 1
            ]

            bbox = parse_bbox(
                section.get(
                    "source_bbox_json",
                    "",
                ),
                page,
            )

            try:
                crop = page.crop(
                    bbox
                )
            except Exception:
                crop = page

            heading = section.get(
                "source_heading",
                "",
            )

            section_id = section[
                "section_id"
            ]

            candidates = (
                extract_candidate_tables(
                    crop
                )
            )

            best_table = (
                choose_best_table(
                    candidates
                )
            )

            true_summary = (
                is_true_table_section(
                    heading
                )
            )

            # ====================================================
            # Summary evidence stays separate from validated
            # retrieval summary output.
            # ====================================================
            if true_summary:
                continue

            rows = (
                best_table["rows"]
                if best_table
                else []
            )

            blocks = (
                detect_timeseries_blocks(
                    rows
                )
                if rows
                else []
            )

            row_to_block = (
                build_timeseries_row_map(
                    rows,
                    blocks,
                )
            )

            # ----------------------------------------------------
            # Group 4 handoff: exact temporal block logic.
            # ----------------------------------------------------
            for block_index, block in enumerate(
                blocks
            ):

                ts_id = (
                    "g4pdf_ts_"
                    + identifier(
                        section_id,
                        page_number,
                        block_index,
                        block["start"],
                        block["end"],
                    )
                )

                block_rows = rows[
                    block["start"]:
                    block["end"]
                ]

                sample_count = sum(
                    1
                    for row
                    in block_rows
                    if looks_like_timeseries_data_row(
                        row
                    )
                )

                g4_sections.append({
                    **identity,
                    "timeseries_candidate_id":
                        ts_id,
                    "section_id":
                        section_id,
                    "record_candidate_id":
                        section.get(
                            "record_candidate_id",
                            "",
                        ),
                    "scope_candidate":
                        section.get(
                            "scope_candidate",
                            "",
                        ),
                    "source_page":
                        page_number,
                    "source_heading":
                        heading,
                    "block_index":
                        block_index,
                    "start_pdf_row_index":
                        block["start"],
                    "first_data_pdf_row_index":
                        block[
                            "first_data_index"
                        ],
                    "end_pdf_row_index_exclusive":
                        block["end"],
                    "row_count":
                        len(block_rows),
                    "data_candidate_count":
                        sample_count,
                    "extraction_method":
                        (
                            "embedded_pdf_"
                            "table_sequence"
                        ),
                    "target_extraction_group":
                        "group4_timeseries",
                    "requires_review":
                        True,
                    "rule_version":
                        RULE_VERSION,
                })

                for row_index in range(
                    block["start"],
                    block["end"],
                ):
                    row = rows[
                        row_index
                    ]

                    g4_rows.append({
                        **identity,
                        "timeseries_candidate_id":
                            ts_id,
                        "section_id":
                            section_id,
                        "record_candidate_id":
                            section.get(
                                "record_candidate_id",
                                "",
                            ),
                        "scope_candidate":
                            section.get(
                                "scope_candidate",
                                "",
                            ),
                        "source_page":
                            page_number,
                        "source_heading":
                            heading,
                        "block_index":
                            block_index,
                        "pdf_row_index":
                            row_index,
                        "row_role":
                            classify_timeseries_row(
                                row,
                                row_index,
                                block,
                            ),
                        "source_row_json":
                            json.dumps(
                                row,
                                ensure_ascii=False,
                            ),
                        "target_extraction_group":
                            "group4_timeseries",
                        "requires_review":
                            True,
                        "rule_version":
                            RULE_VERSION,
                    })

            # ----------------------------------------------------
            # Non-time-series rows: exact conservative handling.
            # ----------------------------------------------------
            if rows:

                for row_index, row in enumerate(
                    rows
                ):

                    if (
                        row_index
                        in row_to_block
                    ):
                        continue

                    reconstructed = (
                        reconstruct_field_row(
                            row,
                            heading,
                        )
                    )

                    if (
                        reconstructed
                        is None
                    ):
                        populated = [
                            normalize_space(
                                cell
                            )
                            for cell
                            in row
                            if normalize_space(
                                cell
                            )
                        ]

                        if populated:
                            raw_text = (
                                " | ".join(
                                    populated
                                )
                            )

                            pdf_unresolved.append({
                                **identity,
                                "pdf_unresolved_id":
                                    (
                                        "g2pdf_unresolved_"
                                        + identifier(
                                            section_id,
                                            page_number,
                                            row_index,
                                            raw_text,
                                        )
                                    ),
                                "section_id":
                                    section_id,
                                "record_candidate_id":
                                    section.get(
                                        "record_candidate_id",
                                        "",
                                    ),
                                "scope_candidate":
                                    section.get(
                                        "scope_candidate",
                                        "",
                                    ),
                                "source_page":
                                    page_number,
                                "source_heading":
                                    heading,
                                "source_index":
                                    row_index,
                                "text_raw":
                                    raw_text,
                                "reason":
                                    (
                                        "field_row_not_"
                                        "conservatively_"
                                        "reconstructed"
                                    ),
                                "requires_review":
                                    True,
                                "rule_version":
                                    RULE_VERSION,
                            })

                        continue

                    pdf_fields.append({
                        **identity,
                        "pdf_field_id":
                            (
                                "g2pdf_field_"
                                + identifier(
                                    section_id,
                                    page_number,
                                    row_index,
                                    reconstructed[
                                        "field_label_raw"
                                    ],
                                    reconstructed[
                                        "value_raw"
                                    ],
                                )
                            ),
                        "section_id":
                            section_id,
                        "record_candidate_id":
                            section.get(
                                "record_candidate_id",
                                "",
                            ),
                        "scope_candidate":
                            section.get(
                                "scope_candidate",
                                "",
                            ),
                        "source_page":
                            page_number,
                        "source_heading":
                            heading,
                        "source_index":
                            row_index,
                        "field_label_raw":
                            reconstructed[
                                "field_label_raw"
                            ],
                        "value_raw":
                            reconstructed[
                                "value_raw"
                            ],
                        "value_status":
                            value_state(
                                reconstructed[
                                    "value_raw"
                                ]
                            ),
                        "unit_raw":
                            reconstructed[
                                "unit_raw"
                            ],
                        "extraction_method":
                            reconstructed[
                                "extraction_method"
                            ],
                        "semantic_status":
                            "unmapped_source_field",
                        "requires_review":
                            True,
                        "rule_version":
                            RULE_VERSION,
                    })

            # ----------------------------------------------------
            # Exact no-table visual-line fallback.
            # ----------------------------------------------------
            if best_table is None:

                words = (
                    extract_words_from_crop(
                        crop
                    )
                )

                visual_lines = (
                    group_words_into_lines(
                        words
                    )
                )

                for line_index, line in enumerate(
                    visual_lines
                ):

                    raw_text = normalize_space(
                        line.get(
                            "text",
                            "",
                        )
                    )

                    if not raw_text:
                        continue

                    if (
                        normalize_key(
                            raw_text
                        )
                        == normalize_key(
                            heading
                        )
                    ):
                        continue

                    reconstructed = (
                        parse_visual_line(
                            line
                        )
                    )

                    if (
                        reconstructed
                        is None
                    ):
                        pdf_unresolved.append({
                            **identity,
                            "pdf_unresolved_id":
                                (
                                    "g2pdf_unresolved_"
                                    + identifier(
                                        section_id,
                                        page_number,
                                        line_index,
                                        raw_text,
                                    )
                                ),
                            "section_id":
                                section_id,
                            "record_candidate_id":
                                section.get(
                                    "record_candidate_id",
                                    "",
                                ),
                            "scope_candidate":
                                section.get(
                                    "scope_candidate",
                                    "",
                                ),
                            "source_page":
                                page_number,
                            "source_heading":
                                heading,
                            "source_index":
                                line_index,
                            "text_raw":
                                raw_text,
                            "reason":
                                (
                                    "no_conservative_"
                                    "field_value_split"
                                ),
                            "requires_review":
                                True,
                            "rule_version":
                                RULE_VERSION,
                        })

                        continue

                    pdf_fields.append({
                        **identity,
                        "pdf_field_id":
                            (
                                "g2pdf_field_"
                                + identifier(
                                    section_id,
                                    page_number,
                                    line_index,
                                    reconstructed[
                                        "field_label_raw"
                                    ],
                                    reconstructed[
                                        "value_raw"
                                    ],
                                )
                            ),
                        "section_id":
                            section_id,
                        "record_candidate_id":
                            section.get(
                                "record_candidate_id",
                                "",
                            ),
                        "scope_candidate":
                            section.get(
                                "scope_candidate",
                                "",
                            ),
                        "source_page":
                            page_number,
                        "source_heading":
                            heading,
                        "source_index":
                            line_index,
                        "field_label_raw":
                            reconstructed[
                                "field_label_raw"
                            ],
                        "value_raw":
                            reconstructed[
                                "value_raw"
                            ],
                        "value_status":
                            value_state(
                                reconstructed[
                                    "value_raw"
                                ]
                            ),
                        "unit_raw":
                            reconstructed[
                                "unit_raw"
                            ],
                        "extraction_method":
                            reconstructed[
                                "extraction_method"
                            ],
                        "semantic_status":
                            "unmapped_source_field",
                        "requires_review":
                            True,
                        "rule_version":
                            RULE_VERSION,
                    })

    return Group2ExtractionResult(
        source_format="pdf",
        source_path=str(path),
        record_candidates=list(
            record_candidates.values()
        ),
        record_status=[],
        retrieval_status=[],
        context_status=[],
        summary_rows=[],
        summary_cells=[],
        retrieval_event_descriptors=[],
        pdf_fields=pdf_fields,
        pdf_unresolved=pdf_unresolved,
        group4_handoff_sections=g4_sections,
        group4_handoff_rows=g4_rows,
        issues=issues,
    )


# ============================================================
# Unified production entry point
# ============================================================

def extract_group2_report(
    *,
    identity: dict[str, Any],
    csv_path: str | Path | None = None,
    pdf_path: str | Path | None = None,
) -> Group2ExtractionResult:
    """
    Production Group 2 entry point.

    Source policy:
        CSV available -> CSV only
        otherwise      -> PDF only
    """
    source_format, source_path = select_group2_source(
        csv_path=csv_path,
        pdf_path=pdf_path,
    )

    if source_format == "csv":
        return extract_group2_csv(source_path, identity)

    return extract_group2_pdf(source_path, identity)
