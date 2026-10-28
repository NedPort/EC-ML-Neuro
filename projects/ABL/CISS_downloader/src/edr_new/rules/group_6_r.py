from __future__ import annotations

"""
Reusable Group 6 technical/module/configuration/readout extractor.

Migrated from the validated historical Group 6 pipeline.

Source policy:
    CSV exists -> CSV only
    CSV absent -> PDF

Important PDF behavior:
    The validated PDF path uses exact anchored reconstruction rules from
    the Group 6 PDF audit/review-resolution pipeline. The original generic
    PDF discovery is intentionally not used as the extraction engine.

No OCR.
No semantic normalization.
No unit conversion.
No fuzzy inference.
No source mutation.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GROUP_NAME = "group6"
RULE_VERSION = "2.0"


@dataclass
class Group6ExtractionResult:
    source_format: str
    source_path: str
    technical_registry: list[dict] = field(default_factory=list)
    technical_values: list[dict] = field(default_factory=list)
    review_evidence: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def _make_ns(name: str, source: str):
    ns = {"__name__": f"_embedded_{name}"}
    exec(
        compile(
            source,
            f"<embedded:{name}>",
            "exec",
        ),
        ns,
    )
    return ns

_CSV_DISCOVERY_SOURCE = '"""\nDiscover Group 6 CSV candidates: other structured technical,\nmodule/configuration, investigation, and readout information.\n\nInputs\n------\ndata/processed/edr/group1_v4/report_index.csv\n\nAuthoritative source\n--------------------\nOriginal CSV exports referenced by report_index.csv.\n\nOutput\n------\ndata/processed/edr/group6_csv_discovery_v1/\n\n    group6_candidate_fields.csv\n    group6_review_fields.csv\n    group6_excluded_overlap_fields.csv\n    group6_report_coverage.csv\n    group6_label_summary.csv\n    group6_family_summary.csv\n    group6_section_summary.csv\n    errors.csv\n    metadata.json\n\nPurpose\n-------\nDiscover structured information that does not belong to Groups 1--5,\nincluding technical/module/configuration/investigation/readout metadata.\n\nTypical Group 6 content\n-----------------------\n- ignition cycles at investigation/readout\n- power-on cycles at reading\n- module supplier/part/serial identifiers\n- software/calibration/version identifiers\n- production/manufacture date\n- module configuration / configured-for fields\n- odometer / vehicle mileage / operating time\n- readout/download/investigation context\n- module/equipment technical status\n- other structured technical fields\n\nImportant boundaries\n--------------------\nGroup 1:\n    report introduction/documentation metadata.\n\nGroup 2:\n    recorded-event structure, counters, lock/retrieval/recording status.\n\nGroup 3:\n    event conditions, deployment, restraint, occupant, warning/status.\n\nGroup 4:\n    repeated time-series measurements.\n\nGroup 5:\n    scalar crash/event measurements.\n\nThis is DISCOVERY only:\n- no semantic normalization\n- no unit conversion\n- no fuzzy inference\n- no source modification\n"""\n\nfrom __future__ import annotations\n\nimport argparse\nimport csv\nimport hashlib\nimport json\nimport re\nfrom collections import Counter, defaultdict\nfrom datetime import datetime, timezone\nfrom pathlib import Path, PureWindowsPath\n\ncsv.field_size_limit(100_000_000)\n\nBASE = [\n    "report_id",\n    "case_id",\n    "vehicle_number",\n    "export_basename",\n]\n\n\ndef read_csv_dict(path: Path):\n    with path.open(\n        encoding="utf-8-sig",\n        errors="replace",\n        newline="",\n    ) as f:\n        return list(csv.DictReader(f))\n\n\ndef read_raw_csv(path: Path):\n    rows = []\n    with path.open(\n        encoding="utf-8-sig",\n        errors="replace",\n        newline="",\n    ) as f:\n        for index, row in enumerate(csv.reader(f)):\n            rows.append((index, [clean_cell(x) for x in row]))\n    return rows\n\n\ndef write_csv(path: Path, rows: list[dict], columns: list[str]):\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_suffix(path.suffix + ".part")\n    with tmp.open("w", encoding="utf-8-sig", newline="") as f:\n        writer = csv.DictWriter(\n            f,\n            fieldnames=columns,\n            extrasaction="ignore",\n        )\n        writer.writeheader()\n        writer.writerows(rows)\n    tmp.replace(path)\n\n\ndef clean_cell(value):\n    text = str(value if value is not None else "")\n    text = text.replace("\\r", " ").replace("\\n", " ")\n    return re.sub(r"\\s+", " ", text).strip()\n\n\ndef norm(value):\n    return clean_cell(value)\n\n\ndef norm_key(value):\n    return norm(\n        re.sub(\n            r"[^a-z0-9]+",\n            " ",\n            norm(value).casefold(),\n        )\n    )\n\n\ndef stable_id(*parts):\n    text = "|".join(norm(x) for x in parts)\n    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]\n\n\ndef populated(row):\n    return [x for x in row if norm(x)]\n\n\ndef looks_numeric(value):\n    text = norm(value).replace(",", "")\n    return bool(\n        re.fullmatch(\n            r"[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)"\n            r"(?:[eE][-+]?\\d+)?"\n            r"(?:\\s*(?:"\n            r"miles?|mi|km|hours?|hrs?|minutes?|min|"\n            r"cycles?|V|volts?|%|mph|km/h|kph"\n            r"))?",\n            text,\n            flags=re.I,\n        )\n    )\n\n\ndef resolve_csv_path(index_row: dict, source_root: Path):\n    raw = norm(index_row.get("csv_path", ""))\n\n    if raw:\n        direct = Path(raw)\n        if direct.exists():\n            return direct\n\n        basename = PureWindowsPath(raw).name\n        case_id = norm(index_row.get("case_id", ""))\n\n        if case_id and basename:\n            case_root = source_root / case_id\n            if case_root.exists():\n                matches = list(case_root.rglob(basename))\n                if len(matches) == 1:\n                    return matches[0]\n                if matches:\n                    preferred = [\n                        p for p in matches\n                        if "cdr_exports" in str(p).casefold()\n                    ]\n                    return preferred[0] if preferred else matches[0]\n\n    basename = norm(index_row.get("export_basename", ""))\n    case_id = norm(index_row.get("case_id", ""))\n\n    if basename and case_id:\n        case_root = source_root / case_id\n        if case_root.exists():\n            matches = list(case_root.rglob(basename + ".CSV"))\n            if not matches:\n                matches = list(case_root.rglob(basename + ".csv"))\n            if matches:\n                return matches[0]\n\n    return None\n\n\ndef is_heading_row(row):\n    values = populated(row)\n\n    if len(values) != 1:\n        return False\n\n    text = values[0]\n\n    if not text or looks_numeric(text) or len(text) > 220:\n        return False\n\n    alpha = [c for c in text if c.isalpha()]\n    upper_ratio = (\n        sum(c.isupper() for c in alpha) / len(alpha)\n        if alpha else 0.0\n    )\n\n    technical_terms = bool(\n        re.search(\n            r"\\b(?:"\n            r"module|acm|sdm|ecm|pcm|technical|"\n            r"vehicle information|system information|"\n            r"investigation|readout|configuration|"\n            r"identification|identifiers|version|"\n            r"diagnostic|manufacturer|production"\n            r")\\b",\n            text,\n            re.I,\n        )\n    )\n\n    return upper_ratio >= 0.70 or technical_terms\n\n\ndef parse_scalar_observation(row):\n    nonblank = [\n        (i, norm(v))\n        for i, v in enumerate(row)\n        if norm(v)\n    ]\n\n    if len(nonblank) < 2 or len(nonblank) > 5:\n        return None\n\n    label_index, label = nonblank[0]\n    value_index, value = nonblank[-1]\n\n    if label_index == value_index or looks_numeric(label):\n        return None\n\n    return {\n        "label_index": label_index,\n        "label": label,\n        "value_index": value_index,\n        "value": value,\n        "populated_cell_count": len(nonblank),\n    }\n\n\nFAMILY_RULES = [\n    (\n        "ignition_cycle_readout",\n        [\n            r"\\bignition cycles?\\b.*\\b(?:investigation|readout|reading|download)\\b",\n            r"\\bpower[- ]on cycles?\\b.*\\b(?:reading|readout|download)\\b",\n            r"\\bcycles? at investigation\\b",\n            r"\\bcycles? at reading\\b",\n        ],\n    ),\n    (\n        "module_identifier",\n        [\n            r"\\b(?:module|acm|sdm|pcm|ecm)\\b.*\\b(?:id|identifier)\\b",\n            r"\\bsupplier id\\b",\n            r"\\bmanufacturer id\\b",\n        ],\n    ),\n    (\n        "part_serial_identifier",\n        [\n            r"\\bpart number\\b",\n            r"\\bserial number\\b",\n            r"\\bhardware number\\b",\n        ],\n    ),\n    (\n        "software_calibration_version",\n        [\n            r"\\bsoftware\\b.*\\b(?:version|number|id)\\b",\n            r"\\bcalibration\\b.*\\b(?:version|number|id)\\b",\n            r"\\bfirmware\\b.*\\b(?:version|number|id)\\b",\n            r"\\bbootloader\\b",\n        ],\n    ),\n    (\n        "production_manufacture_date",\n        [\n            r"\\bproduction date\\b",\n            r"\\bmanufacture date\\b",\n            r"\\bmanufacturing date\\b",\n            r"\\bdate of manufacture\\b",\n        ],\n    ),\n    (\n        "configuration",\n        [\n            r"\\bconfigured for\\b",\n            r"\\bconfiguration\\b",\n            r"\\bmodule configuration\\b",\n            r"\\bequipment configuration\\b",\n            r"\\bvehicle configuration\\b",\n        ],\n    ),\n    (\n        "odometer_mileage",\n        [\n            r"\\bodometer\\b",\n            r"\\bvehicle mileage\\b",\n            r"\\bmileage at\\b",\n        ],\n    ),\n    (\n        "operating_time",\n        [\n            r"\\boperating time\\b",\n            r"\\blifetime operating timer\\b",\n            r"\\bengine operating time\\b",\n            r"\\bmodule operating time\\b",\n        ],\n    ),\n    (\n        "readout_investigation_context",\n        [\n            r"\\bdownload date\\b",\n            r"\\bdownload time\\b",\n            r"\\breadout date\\b",\n            r"\\breadout time\\b",\n            r"\\binvestigation date\\b",\n            r"\\binvestigator\\b",\n            r"\\bdownload tool\\b",\n            r"\\breadout tool\\b",\n        ],\n    ),\n    (\n        "technical_status",\n        [\n            r"\\bmodule status\\b",\n            r"\\bdiagnostic status\\b",\n            r"\\bcommunication status\\b",\n            r"\\bdata retrieval status\\b",\n        ],\n    ),\n    (\n        "other_structured_technical",\n        [\n            r"\\btechnical\\b",\n            r"\\bmanufacturer\\b",\n            r"\\bmodule\\b",\n            r"\\bacm\\b",\n            r"\\bsdm\\b",\n            r"\\bpcm\\b",\n            r"\\becm\\b",\n        ],\n    ),\n]\n\n\nGROUP1_PATTERNS = [\n    r"\\bfilename\\b",\n    r"\\bsaved on\\b",\n    r"\\bimaged with\\b",\n    r"\\breported with\\b",\n    r"\\bcrash date\\b",\n    r"\\bedr data imaging date\\b",\n    r"\\buser entered vin\\b",\n    r"\\bcase number entered\\b",\n]\n\nGROUP2_PATTERNS = [\n    r"\\bevent recording complete\\b",\n    r"\\brecording status\\b",\n    r"\\bcrash record locked\\b",\n    r"\\brecord complete\\b",\n    r"\\bevent counter\\b",\n    r"\\bdeployment command counter\\b",\n    r"\\bretrieval status\\b",\n    r"\\bmultiple events?\\b",\n    r"\\bmost recent event\\b",\n    r"\\b\\d+(?:st|nd|rd|th)\\s+prior event\\b",\n]\n\nGROUP3_PATTERNS = [\n    r"\\bair ?bag\\b.*\\b(?:deployment|deployed|status)\\b",\n    r"\\bpretensioner\\b",\n    r"\\bseat belt\\b",\n    r"\\bsafety belt\\b",\n    r"\\boccupant\\b",\n    r"\\bpassenger classification\\b",\n    r"\\bwarning lamp\\b",\n    r"\\bevent severity\\b",\n    r"\\bhigh[- ]?voltage disable\\b",\n    r"\\balgorithm\\b.*\\b(?:wake|reset|deployment)\\b",\n]\n\nGROUP5_PATTERNS = [\n    r"\\bmaximum\\b.*\\bdelta[- ]?v\\b",\n    r"\\bmax(?:imum)?\\b.*\\bvelocity change\\b",\n    r"\\btime\\b.*\\bmaximum\\b.*\\bvelocity change\\b",\n    r"\\bmaximum acceleration\\b",\n    r"\\btime\\b.*\\bmaximum acceleration\\b",\n    r"\\broll angle peak\\b",\n    r"\\blength of delta[- ]?v\\b",\n    r"\\bclipping time\\b",\n    r"\\bpdof\\b",\n]\n\nGROUP4_PATTERNS = [\n    r"^\\s*time\\s*(?:\\([^)]*\\))?\\s*$",\n    r"^\\s*times\\s*(?:\\([^)]*\\))?\\s*$",\n    r"^\\s*sample\\s+count\\b",\n    r"^\\s*buffer address\\b",\n]\n\n\ndef classify_family(label):\n    text = norm(label)\n\n    for family, patterns in FAMILY_RULES:\n        if any(re.search(p, text, re.I) for p in patterns):\n            return family\n\n    return ""\n\n\ndef matches_any(text, patterns):\n    return any(\n        re.search(pattern, norm(text), re.I)\n        for pattern in patterns\n    )\n\n\ndef score_field(label, value, section):\n    family = classify_family(label)\n    score = 0\n    evidence = []\n    exclusions = []\n\n    if family:\n        score += 6\n        evidence.append(f"family:{family}")\n\n    if re.search(\n        r"\\b(?:"\n        r"module|part number|serial number|supplier|"\n        r"software|firmware|calibration|production date|"\n        r"configuration|odometer|mileage|operating time|"\n        r"investigation|readout|download|ignition cycles?|"\n        r"power[- ]on cycles?"\n        r")\\b",\n        norm(label),\n        re.I,\n    ):\n        score += 1\n        evidence.append("group6_terms")\n\n    if re.search(\n        r"\\b(?:"\n        r"module|technical|vehicle information|"\n        r"system information|investigation|readout|"\n        r"configuration|identification"\n        r")\\b",\n        norm(section),\n        re.I,\n    ):\n        score += 1\n        evidence.append("group6_section_context")\n\n    if looks_numeric(value):\n        score += 1\n        evidence.append("scalar_value")\n\n    if matches_any(label, GROUP1_PATTERNS):\n        exclusions.append("group1_report_metadata")\n\n    if matches_any(label, GROUP2_PATTERNS):\n        exclusions.append("group2_record_structure")\n\n    if matches_any(label, GROUP3_PATTERNS):\n        exclusions.append("group3_event_condition")\n\n    if matches_any(label, GROUP5_PATTERNS):\n        exclusions.append("group5_crash_measurement")\n\n    if matches_any(label, GROUP4_PATTERNS):\n        exclusions.append("group4_timeseries_axis")\n\n    if exclusions:\n        decision = "excluded_overlap"\n    elif score >= 6:\n        decision = "candidate"\n    elif score >= 3:\n        decision = "review"\n    else:\n        decision = "not_group6"\n\n    return {\n        "family":\n            family or "other_structured_technical",\n        "score":\n            score,\n        "decision":\n            decision,\n        "evidence":\n            evidence,\n        "exclusions":\n            exclusions,\n    }\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=__doc__)\n\n    parser.add_argument(\n        "--report-index",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group1_v4/report_index.csv"\n        ),\n    )\n\n    parser.add_argument(\n        "--source-root",\n        type=Path,\n        default=Path("data/temp"),\n    )\n\n    parser.add_argument(\n        "--output-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_csv_discovery_v1"\n        ),\n    )\n\n    args = parser.parse_args()\n\n    if not args.report_index.exists():\n        raise FileNotFoundError(args.report_index)\n\n    report_index = read_csv_dict(args.report_index)\n    out = args.output_directory\n    out.mkdir(parents=True, exist_ok=True)\n\n    candidates = []\n    reviews = []\n    excluded = []\n    coverage = []\n    errors = []\n\n    family_counts = Counter()\n    label_counts = Counter()\n    section_counts = Counter()\n\n    selected = 0\n    processed = 0\n\n    reports_with_candidates = set()\n    reports_with_reviews = set()\n\n    for index_row in report_index:\n        csv_path_text = norm(index_row.get("csv_path", ""))\n\n        if not csv_path_text:\n            continue\n\n        selected += 1\n\n        csv_path = resolve_csv_path(index_row, args.source_root)\n\n        if csv_path is None or not csv_path.exists():\n            errors.append({\n                **{\n                    k: index_row.get(k, "")\n                    for k in BASE\n                },\n                "error_type": "csv_source_not_found",\n                "csv_path": csv_path_text,\n                "error": "Could not resolve CSV source path.",\n            })\n            continue\n\n        try:\n            rows = read_raw_csv(csv_path)\n        except Exception as exc:\n            errors.append({\n                **{\n                    k: index_row.get(k, "")\n                    for k in BASE\n                },\n                "error_type": type(exc).__name__,\n                "csv_path": str(csv_path),\n                "error": str(exc),\n            })\n            continue\n\n        processed += 1\n\n        current_section = ""\n        c_count = 0\n        r_count = 0\n        e_count = 0\n\n        for row_index, row in rows:\n            if is_heading_row(row):\n                current_section = populated(row)[0]\n                continue\n\n            parsed = parse_scalar_observation(row)\n\n            if parsed is None:\n                continue\n\n            label = parsed["label"]\n            value = parsed["value"]\n\n            result = score_field(\n                label,\n                value,\n                current_section,\n            )\n\n            if result["decision"] == "not_group6":\n                continue\n\n            candidate_id = (\n                "g6csv_"\n                + stable_id(\n                    index_row.get("report_id", ""),\n                    row_index,\n                    label,\n                    value,\n                )\n            )\n\n            observation = {\n                **{\n                    k: index_row.get(k, "")\n                    for k in BASE\n                },\n                "group6_candidate_id": candidate_id,\n                "source_format": "csv",\n                "source_path": str(csv_path),\n                "source_record_index": row_index,\n                "source_section_heading": current_section,\n                "field_label_raw": label,\n                "field_value_raw": value,\n                "value_column_index": parsed["value_index"],\n                "populated_cell_count": parsed["populated_cell_count"],\n                "source_row_json": json.dumps(\n                    row,\n                    ensure_ascii=False,\n                ),\n                "candidate_family": result["family"],\n                "candidate_score": result["score"],\n                "discovery_decision": result["decision"],\n                "evidence_json": json.dumps(\n                    result["evidence"],\n                    ensure_ascii=False,\n                ),\n                "overlap_exclusions_json": json.dumps(\n                    result["exclusions"],\n                    ensure_ascii=False,\n                ),\n                "semantic_normalization_status": "not_normalized",\n                "unit_conversion_status": "not_converted",\n            }\n\n            if result["decision"] == "candidate":\n                candidates.append(observation)\n                c_count += 1\n                reports_with_candidates.add(\n                    index_row.get("report_id", "")\n                )\n                family_counts[result["family"]] += 1\n                label_counts[norm_key(label)] += 1\n                section_counts[\n                    norm(current_section)\n                    or "<no_section_heading>"\n                ] += 1\n\n            elif result["decision"] == "review":\n                reviews.append(observation)\n                r_count += 1\n                reports_with_reviews.add(\n                    index_row.get("report_id", "")\n                )\n\n            elif result["decision"] == "excluded_overlap":\n                excluded.append(observation)\n                e_count += 1\n\n        coverage.append({\n            **{\n                k: index_row.get(k, "")\n                for k in BASE\n            },\n            "csv_path": str(csv_path),\n            "processing_status":\n                "group6_candidates_found"\n                if c_count\n                else (\n                    "review_only"\n                    if r_count\n                    else "no_group6_candidates"\n                ),\n            "candidate_count": c_count,\n            "review_count": r_count,\n            "excluded_overlap_count": e_count,\n        })\n\n        if processed % 100 == 0 or processed == selected:\n            print(\n                f"Discovered Group 6 CSV {processed}/{selected} reports...",\n                flush=True,\n            )\n\n    raw_label_examples = defaultdict(Counter)\n\n    for row in candidates:\n        raw_label_examples[\n            norm_key(row["field_label_raw"])\n        ][\n            row["field_label_raw"]\n        ] += 1\n\n    label_summary = []\n\n    for key, count in label_counts.most_common():\n        label_summary.append({\n            "normalized_label": key,\n            "candidate_count": count,\n            "raw_label_examples_json": json.dumps(\n                [\n                    label\n                    for label, _\n                    in raw_label_examples[key].most_common(5)\n                ],\n                ensure_ascii=False,\n            ),\n        })\n\n    family_summary = [\n        {\n            "candidate_family": family,\n            "candidate_count": count,\n        }\n        for family, count\n        in family_counts.most_common()\n    ]\n\n    section_summary = [\n        {\n            "source_section_heading": section,\n            "candidate_count": count,\n        }\n        for section, count\n        in section_counts.most_common()\n    ]\n\n    candidate_columns = [\n        *BASE,\n        "group6_candidate_id",\n        "source_format",\n        "source_path",\n        "source_record_index",\n        "source_section_heading",\n        "field_label_raw",\n        "field_value_raw",\n        "value_column_index",\n        "populated_cell_count",\n        "source_row_json",\n        "candidate_family",\n        "candidate_score",\n        "discovery_decision",\n        "evidence_json",\n        "overlap_exclusions_json",\n        "semantic_normalization_status",\n        "unit_conversion_status",\n    ]\n\n    write_csv(\n        out / "group6_candidate_fields.csv",\n        candidates,\n        candidate_columns,\n    )\n\n    write_csv(\n        out / "group6_review_fields.csv",\n        reviews,\n        candidate_columns,\n    )\n\n    write_csv(\n        out / "group6_excluded_overlap_fields.csv",\n        excluded,\n        candidate_columns,\n    )\n\n    write_csv(\n        out / "group6_report_coverage.csv",\n        coverage,\n        [\n            *BASE,\n            "csv_path",\n            "processing_status",\n            "candidate_count",\n            "review_count",\n            "excluded_overlap_count",\n        ],\n    )\n\n    write_csv(\n        out / "group6_label_summary.csv",\n        label_summary,\n        [\n            "normalized_label",\n            "candidate_count",\n            "raw_label_examples_json",\n        ],\n    )\n\n    write_csv(\n        out / "group6_family_summary.csv",\n        family_summary,\n        [\n            "candidate_family",\n            "candidate_count",\n        ],\n    )\n\n    write_csv(\n        out / "group6_section_summary.csv",\n        section_summary,\n        [\n            "source_section_heading",\n            "candidate_count",\n        ],\n    )\n\n    write_csv(\n        out / "errors.csv",\n        errors,\n        [\n            *BASE,\n            "error_type",\n            "csv_path",\n            "error",\n        ],\n    )\n\n    coverage_counts = Counter(\n        row["processing_status"]\n        for row in coverage\n    )\n\n    metadata = {\n        "created_at":\n            datetime.now(timezone.utc).isoformat(),\n\n        "group":\n            "Group 6 - Other structured technical and investigation information",\n\n        "stage":\n            "CSV discovery",\n\n        "reports_in_index":\n            len(report_index),\n\n        "csv_reports_selected":\n            selected,\n\n        "csv_reports_processed":\n            processed,\n\n        "reports_with_group6_candidates":\n            len(reports_with_candidates),\n\n        "reports_with_review_fields":\n            len(reports_with_reviews),\n\n        "candidate_field_count":\n            len(candidates),\n\n        "review_field_count":\n            len(reviews),\n\n        "excluded_overlap_field_count":\n            len(excluded),\n\n        "candidate_family_counts":\n            dict(family_counts),\n\n        "unique_candidate_labels":\n            len(label_counts),\n\n        "coverage_status_counts":\n            dict(coverage_counts),\n\n        "source_errors":\n            len(errors),\n\n        "scope":\n            (\n                "CSV-first discovery for Group 6 other structured technical, "\n                "module/configuration, investigation, and readout information. "\n                "Original CSV exports remain authoritative. Group 1 report "\n                "metadata, Group 2 record structure, Group 3 event conditions, "\n                "Group 4 time-series, and Group 5 scalar crash/event measurements "\n                "are explicitly excluded. No semantic normalization, unit "\n                "conversion, fuzzy inference, PDF processing, or source mutation "\n                "is performed."\n            ),\n    }\n\n    tmp = out / "metadata.json.part"\n    tmp.write_text(\n        json.dumps(\n            metadata,\n            indent=2,\n            ensure_ascii=False,\n        ),\n        encoding="utf-8",\n    )\n    tmp.replace(out / "metadata.json")\n\n    print()\n    print(json.dumps(metadata, indent=2, ensure_ascii=False))\n    print()\n    print(f"Outputs: {out}")\n    print()\n    print("GROUP 6 CSV DISCOVERY COMPLETE.")\n\n\n'

_CSV_AUDIT_SOURCE = '"""\nAudit Group 6 CSV discovery results.\n\nInputs\n------\ndata/processed/edr/group6_csv_discovery_v1/\n    group6_candidate_fields.csv\n\nOutput\n------\ndata/processed/edr/group6_csv_audit_v1/\n\n    accepted_group6_fields.csv\n    excluded_non_group6_fields.csv\n    remaining_review_fields.csv\n    audit_all_fields.csv\n    family_summary.csv\n    routing_summary.csv\n    validation_checks.csv\n    metadata.json\n\nAudit decisions\n---------------\nThe Group 6 candidate labels were inspected explicitly.\n\nRefinements inside Group 6:\n- software/calibration/version identifiers are separated from generic\n  part/serial identifiers\n- module supplier information gets its own family\n- VIN values read from PCM/ACM are retained as technical vehicle identifiers\n- module voltage at retrieval is kept as readout voltage\n- adapter detection during download is kept as readout-tool status\n- SDM primary key definitions are kept as module-key definitions\n- PCM calibration filenames are kept under software/calibration/version\n\nCross-group exclusions:\n- OnStar SDM Recorded Vehicle Velocity Change Data Sent -> Group 3\n- ACM/Supply/System Voltage at Event -> Group 3 power/event condition\n\nNo semantic normalization, unit conversion, fuzzy inference, or source\nmodification is performed.\n"""\n\nfrom __future__ import annotations\n\nimport argparse\nimport csv\nimport json\nimport re\nfrom collections import Counter\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\ncsv.field_size_limit(100_000_000)\n\n\ndef read_csv(path: Path):\n    with path.open(\n        encoding="utf-8-sig",\n        errors="replace",\n        newline="",\n    ) as f:\n        return list(csv.DictReader(f))\n\n\ndef write_csv(path: Path, rows: list[dict], columns: list[str]):\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_suffix(path.suffix + ".part")\n\n    with tmp.open("w", encoding="utf-8-sig", newline="") as f:\n        writer = csv.DictWriter(\n            f,\n            fieldnames=columns,\n            extrasaction="ignore",\n        )\n        writer.writeheader()\n        writer.writerows(rows)\n\n    tmp.replace(path)\n\n\ndef norm(value):\n    return re.sub(\n        r"\\s+",\n        " ",\n        str(value if value is not None else "").strip(),\n    )\n\n\ndef union_columns(rows):\n    seen = set()\n    cols = []\n\n    preferred = [\n        "report_id",\n        "case_id",\n        "vehicle_number",\n        "export_basename",\n        "group6_candidate_id",\n        "source_format",\n        "source_path",\n        "source_record_index",\n        "source_section_heading",\n        "field_label_raw",\n        "field_value_raw",\n        "candidate_family",\n        "audited_family",\n        "audit_decision",\n        "audit_route",\n        "audit_reason",\n    ]\n\n    for col in preferred:\n        if col not in seen:\n            seen.add(col)\n            cols.append(col)\n\n    for row in rows:\n        for key in row:\n            if key not in seen:\n                seen.add(key)\n                cols.append(key)\n\n    return cols\n\n\ndef audit_candidate(row):\n    label = norm(row.get("field_label_raw", ""))\n    family = norm(row.get("candidate_family", ""))\n\n    # --------------------------------------------------------\n    # Group 3 overlap: event-related status/condition\n    # --------------------------------------------------------\n\n    if label.casefold() == (\n        "OnStar SDM Recorded Vehicle Velocity Change Data Sent"\n    ).casefold():\n        return (\n            "exclude",\n            "group3_event_condition",\n            "group3",\n            "event_data_transmission_status",\n        )\n\n    if re.fullmatch(\n        r"(?:"\n        r"Supply Voltage at Event, ACM \\(V\\)|"\n        r"ACM System Voltage at Event \\(V\\)|"\n        r"ACM Supply Voltage at Event \\(V\\)"\n        r")",\n        label,\n        flags=re.I,\n    ):\n        return (\n            "exclude",\n            "group3_power_event_condition",\n            "group3",\n            "module_voltage_at_event_is_event_condition",\n        )\n\n    # --------------------------------------------------------\n    # Group 6 family refinements\n    # --------------------------------------------------------\n\n    if re.search(\n        r"\\b(?:"\n        r"software|calibration|firmware|application version|"\n        r"hardware version|software strategy"\n        r")\\b",\n        label,\n        re.I,\n    ):\n        return (\n            "accept",\n            "software_calibration_version",\n            "group6",\n            "software_calibration_or_version_identifier",\n        )\n\n    if re.search(\n        r"\\b(?:Current VIN|Vehicle Identification Number)\\b",\n        label,\n        re.I,\n    ):\n        return (\n            "accept",\n            "vehicle_identifier_technical",\n            "group6",\n            "technical_vehicle_identifier_from_module",\n        )\n\n    if re.search(\n        r"\\b(?:ACM Supplier|Airbag Control Module Supplier)\\b",\n        label,\n        re.I,\n    ):\n        return (\n            "accept",\n            "module_supplier",\n            "group6",\n            "module_supplier_information",\n        )\n\n    if re.search(\n        r"\\bACM Supply Voltage at Time of Retrieval\\b",\n        label,\n        re.I,\n    ):\n        return (\n            "accept",\n            "readout_voltage",\n            "group6",\n            "retrieval_time_module_voltage",\n        )\n\n    if re.search(\n        r"\\bACM Adapter Detected During Download\\b",\n        label,\n        re.I,\n    ):\n        return (\n            "accept",\n            "readout_tool_status",\n            "group6",\n            "download_adapter_detection_status",\n        )\n\n    if re.search(\n        r"\\bSDM Primary Key Definition\\b",\n        label,\n        re.I,\n    ):\n        return (\n            "accept",\n            "module_key_definition",\n            "group6",\n            "module_primary_key_definition",\n        )\n\n    if re.search(\n        r"\\bPCM File Name \\(calibration level\\)\\b",\n        label,\n        re.I,\n    ):\n        return (\n            "accept",\n            "software_calibration_version",\n            "group6",\n            "pcm_calibration_filename",\n        )\n\n    return (\n        "accept",\n        family or "other_structured_technical",\n        "group6",\n        "valid_group6_candidate",\n    )\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=__doc__)\n\n    parser.add_argument(\n        "--discovery-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_csv_discovery_v1"\n        ),\n    )\n\n    parser.add_argument(\n        "--output-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_csv_audit_v1"\n        ),\n    )\n\n    args = parser.parse_args()\n\n    src = args.discovery_directory\n    out = args.output_directory\n\n    candidate_path = src / "group6_candidate_fields.csv"\n\n    if not candidate_path.exists():\n        raise FileNotFoundError(candidate_path)\n\n    candidates = read_csv(candidate_path)\n\n    audited = []\n\n    for row in candidates:\n        decision, family, route, reason = audit_candidate(row)\n\n        audited.append({\n            **row,\n            "audited_family": family,\n            "audit_decision": decision,\n            "audit_route": route,\n            "audit_reason": reason,\n        })\n\n    accepted = [\n        row\n        for row in audited\n        if row["audit_decision"] == "accept"\n    ]\n\n    excluded = [\n        row\n        for row in audited\n        if row["audit_decision"] == "exclude"\n    ]\n\n    remaining_review = [\n        row\n        for row in audited\n        if row["audit_decision"] == "review"\n    ]\n\n    # ========================================================\n    # Validation\n    # ========================================================\n\n    checks = []\n\n    def check(\n        name,\n        condition,\n        observed,\n        expected,\n        severity="hard",\n        note="",\n    ):\n        checks.append({\n            "check": name,\n            "status": "PASS" if condition else "FAIL",\n            "severity": severity,\n            "observed": str(observed),\n            "expected": str(expected),\n            "note": note,\n        })\n\n    check(\n        "input_candidate_count",\n        len(candidates) == 13575,\n        len(candidates),\n        13575,\n    )\n\n    check(\n        "all_candidates_accounted_for",\n        (\n            len(accepted)\n            + len(excluded)\n            + len(remaining_review)\n        ) == len(candidates),\n        len(accepted) + len(excluded) + len(remaining_review),\n        len(candidates),\n    )\n\n    check(\n        "expected_accepted_count",\n        len(accepted) == 13202,\n        len(accepted),\n        13202,\n    )\n\n    check(\n        "expected_excluded_count",\n        len(excluded) == 373,\n        len(excluded),\n        373,\n    )\n\n    check(\n        "remaining_review_zero",\n        len(remaining_review) == 0,\n        len(remaining_review),\n        0,\n    )\n\n    ids = [\n        norm(row.get("group6_candidate_id", ""))\n        for row in audited\n        if norm(row.get("group6_candidate_id", ""))\n    ]\n\n    duplicate_ids = len(ids) - len(set(ids))\n\n    check(\n        "duplicate_candidate_ids",\n        duplicate_ids == 0,\n        duplicate_ids,\n        0,\n    )\n\n    blank_labels = sum(\n        1\n        for row in accepted\n        if not norm(row.get("field_label_raw", ""))\n    )\n\n    check(\n        "blank_accepted_labels",\n        blank_labels == 0,\n        blank_labels,\n        0,\n    )\n\n    # ========================================================\n    # Summaries\n    # ========================================================\n\n    family_counts = Counter(\n        row["audited_family"]\n        for row in accepted\n    )\n\n    route_counts = Counter(\n        row["audit_route"]\n        for row in excluded\n    )\n\n    reports = {\n        row.get("report_id", "")\n        for row in accepted\n        if row.get("report_id", "")\n    }\n\n    cases = {\n        row.get("case_id", "")\n        for row in accepted\n        if row.get("case_id", "")\n    }\n\n    family_summary = [\n        {\n            "audited_family": family,\n            "field_count": count,\n        }\n        for family, count\n        in family_counts.most_common()\n    ]\n\n    routing_summary = [\n        {\n            "audit_route": route,\n            "field_count": count,\n        }\n        for route, count\n        in route_counts.most_common()\n    ]\n\n    # ========================================================\n    # Write\n    # ========================================================\n\n    out.mkdir(parents=True, exist_ok=True)\n    cols = union_columns(audited)\n\n    write_csv(\n        out / "accepted_group6_fields.csv",\n        accepted,\n        cols,\n    )\n\n    write_csv(\n        out / "excluded_non_group6_fields.csv",\n        excluded,\n        cols,\n    )\n\n    write_csv(\n        out / "remaining_review_fields.csv",\n        remaining_review,\n        cols,\n    )\n\n    write_csv(\n        out / "audit_all_fields.csv",\n        audited,\n        cols,\n    )\n\n    write_csv(\n        out / "family_summary.csv",\n        family_summary,\n        [\n            "audited_family",\n            "field_count",\n        ],\n    )\n\n    write_csv(\n        out / "routing_summary.csv",\n        routing_summary,\n        [\n            "audit_route",\n            "field_count",\n        ],\n    )\n\n    write_csv(\n        out / "validation_checks.csv",\n        checks,\n        [\n            "check",\n            "status",\n            "severity",\n            "observed",\n            "expected",\n            "note",\n        ],\n    )\n\n    hard_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "hard"\n        )\n    )\n\n    warning_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "warning"\n        )\n    )\n\n    metadata = {\n        "created_at":\n            datetime.now(timezone.utc).isoformat(),\n\n        "group":\n            "Group 6 - Other structured technical and investigation information",\n\n        "stage":\n            "CSV candidate audit",\n\n        "input_candidates":\n            len(candidates),\n\n        "accepted_group6_fields":\n            len(accepted),\n\n        "excluded_non_group6_fields":\n            len(excluded),\n\n        "remaining_review_fields":\n            len(remaining_review),\n\n        "reports_with_accepted_group6_fields":\n            len(reports),\n\n        "cases_with_accepted_group6_fields":\n            len(cases),\n\n        "accepted_family_counts":\n            dict(family_counts),\n\n        "excluded_route_counts":\n            dict(route_counts),\n\n        "validation_checks":\n            len(checks),\n\n        "hard_validation_failures":\n            hard_failures,\n\n        "warning_validation_failures":\n            warning_failures,\n\n        "scope":\n            (\n                "Audit of Group 6 CSV discovery. Software/calibration/version "\n                "identifiers, technical vehicle identifiers, module suppliers, "\n                "retrieval-time voltage, adapter/download status, and module "\n                "key definitions are refined into explicit Group 6 families. "\n                "OnStar event-data transmission status and ACM/system voltage "\n                "at the event are routed to Group 3 because they represent "\n                "event-state information rather than technical/readout metadata. "\n                "No semantic normalization, unit conversion, fuzzy inference, "\n                "PDF processing, or source mutation is performed."\n            ),\n    }\n\n    tmp = out / "metadata.json.part"\n    tmp.write_text(\n        json.dumps(\n            metadata,\n            indent=2,\n            ensure_ascii=False,\n        ),\n        encoding="utf-8",\n    )\n    tmp.replace(out / "metadata.json")\n\n    print()\n    print(json.dumps(metadata, indent=2, ensure_ascii=False))\n    print()\n    print(f"Outputs: {out}")\n\n    if hard_failures:\n        print()\n        print("GROUP 6 CSV AUDIT HAS HARD VALIDATION FAILURES.")\n        raise SystemExit(1)\n\n    print()\n    print("GROUP 6 CSV AUDIT COMPLETE.")\n\n\n'

_CSV_EXTRACT_SOURCE = '"""\nBuild structured Group 6 CSV package from audited fields.\n\nInput\n-----\ndata/processed/edr/group6_csv_audit_v1/\n    accepted_group6_fields.csv\n    remaining_review_fields.csv\n\nOutput\n------\ndata/processed/edr/group6_csv_structured_v1/\n    technical_registry.csv\n    technical_values.csv\n    extraction_failures.csv\n    family_summary.csv\n    validation_checks.csv\n    metadata.json\n\nRules\n-----\n- One accepted source observation becomes one structured Group 6 record.\n- Preserve raw label, raw value, section, source row, source path, family,\n  and source-format provenance.\n- Parse a numeric value only when the raw value is safely representable as\n  one scalar number, optionally followed by a simple unit.\n- Preserve identifiers, versions, filenames, serials, VINs, configuration\n  strings, and textual states exactly as raw values.\n- No semantic normalization.\n- No unit conversion.\n- No fuzzy inference.\n- No source mutation.\n"""\n\nfrom __future__ import annotations\n\nimport argparse\nimport csv\nimport hashlib\nimport json\nimport re\nfrom collections import Counter\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\ncsv.field_size_limit(100_000_000)\n\n\ndef read_csv(path: Path):\n    with path.open(\n        encoding="utf-8-sig",\n        errors="replace",\n        newline="",\n    ) as f:\n        return list(csv.DictReader(f))\n\n\ndef write_csv(path: Path, rows: list[dict], columns: list[str]):\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_suffix(path.suffix + ".part")\n\n    with tmp.open(\n        "w",\n        encoding="utf-8-sig",\n        newline="",\n    ) as f:\n        writer = csv.DictWriter(\n            f,\n            fieldnames=columns,\n            extrasaction="ignore",\n        )\n        writer.writeheader()\n        writer.writerows(rows)\n\n    tmp.replace(path)\n\n\ndef norm(value):\n    return re.sub(\n        r"\\s+",\n        " ",\n        str(value if value is not None else "").strip(),\n    )\n\n\ndef stable_id(*parts):\n    text = "|".join(norm(part) for part in parts)\n    return hashlib.sha256(\n        text.encode("utf-8")\n    ).hexdigest()[:24]\n\n\nMISSING_VALUES = {\n    "",\n    "n/a",\n    "na",\n    "sna",\n    "not available",\n    "not applicable",\n    "unknown",\n    "invalid",\n    "data not available",\n    "no data",\n}\n\n\ndef is_missing_like(value):\n    return norm(value).casefold() in MISSING_VALUES\n\n\nNUMERIC_RE = re.compile(\n    r"""\n    ^\\s*\n    (?P<num>\n        [-+]?\n        (?:\n            \\d+(?:\\.\\d*)?\n            |\n            \\.\\d+\n        )\n        (?:[eE][-+]?\\d+)?\n    )\n    \\s*\n    (?P<unit>\n        %\n        |\n        V\n        |\n        volts?\n        |\n        cycles?\n        |\n        miles?\n        |\n        mi\n        |\n        km\n        |\n        hours?\n        |\n        hrs?\n        |\n        minutes?\n        |\n        min\n        |\n        mph\n        |\n        km/h\n        |\n        kph\n    )?\n    \\s*$\n    """,\n    re.I | re.X,\n)\n\n\ndef parse_numeric_scalar(value):\n    text = norm(value)\n\n    if not text or is_missing_like(text):\n        return None, "", "missing_or_unavailable"\n\n    cleaned = text.replace(",", "")\n    match = NUMERIC_RE.fullmatch(cleaned)\n\n    if not match:\n        return None, "", "textual_or_identifier"\n\n    try:\n        number = float(match.group("num"))\n    except Exception:\n        return None, "", "numeric_parse_failed"\n\n    unit = norm(match.group("unit") or "")\n\n    return number, unit, "numeric_scalar"\n\n\ndef raw_unit_from_label(label):\n    text = norm(label)\n\n    for pattern in [\n        r"\\(([^()]*)\\)\\s*$",\n        r",\\s*([^,]+)\\s*$",\n    ]:\n        match = re.search(pattern, text)\n\n        if match:\n            candidate = norm(match.group(1))\n\n            if re.fullmatch(\n                r"(?:"\n                r"V|volts?|cycles?|miles?|mi|km|"\n                r"hours?|hrs?|minutes?|min|%|mph|km/h|kph"\n                r")",\n                candidate,\n                flags=re.I,\n            ):\n                return candidate\n\n    return ""\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=__doc__)\n\n    parser.add_argument(\n        "--audit-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_csv_audit_v1"\n        ),\n    )\n\n    parser.add_argument(\n        "--output-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_csv_structured_v1"\n        ),\n    )\n\n    args = parser.parse_args()\n\n    src = args.audit_directory\n    out = args.output_directory\n\n    accepted_path = src / "accepted_group6_fields.csv"\n    unresolved_path = src / "remaining_review_fields.csv"\n\n    if not accepted_path.exists():\n        raise FileNotFoundError(accepted_path)\n\n    if not unresolved_path.exists():\n        raise FileNotFoundError(unresolved_path)\n\n    accepted = read_csv(accepted_path)\n    unresolved = read_csv(unresolved_path)\n\n    if unresolved:\n        raise RuntimeError(\n            f"Refusing extraction: {len(unresolved)} unresolved Group 6 rows remain."\n        )\n\n    registry = []\n    values = []\n    failures = []\n\n    family_counts = Counter()\n    parse_status_counts = Counter()\n    reports = set()\n    cases = set()\n\n    for row in accepted:\n        try:\n            report_id = norm(row.get("report_id", ""))\n            case_id = norm(row.get("case_id", ""))\n            vehicle_number = norm(row.get("vehicle_number", ""))\n            export_basename = norm(row.get("export_basename", ""))\n            source_path = norm(row.get("source_path", ""))\n            source_index = norm(row.get("source_record_index", ""))\n            section = norm(row.get("source_section_heading", ""))\n            raw_label = norm(row.get("field_label_raw", ""))\n            raw_value = norm(row.get("field_value_raw", ""))\n            family = norm(row.get("audited_family", ""))\n\n            if not raw_label:\n                raise ValueError("blank field_label_raw")\n\n            if not family:\n                raise ValueError("blank audited_family")\n\n            source_candidate_id = norm(\n                row.get("group6_candidate_id", "")\n            )\n\n            technical_id = (\n                "g6csv_"\n                + stable_id(\n                    report_id,\n                    case_id,\n                    vehicle_number,\n                    export_basename,\n                    source_path,\n                    source_index,\n                    raw_label,\n                    raw_value,\n                    family,\n                )\n            )\n\n            numeric_value, value_unit, parse_status = (\n                parse_numeric_scalar(raw_value)\n            )\n\n            label_unit = raw_unit_from_label(raw_label)\n            raw_unit = value_unit or label_unit\n\n            registry.append({\n                "group6_technical_id": technical_id,\n                "source_candidate_id": source_candidate_id,\n                "report_id": report_id,\n                "case_id": case_id,\n                "vehicle_number": vehicle_number,\n                "export_basename": export_basename,\n                "source_format": "csv",\n                "source_path": source_path,\n                "source_record_index": source_index,\n                "source_section_heading": section,\n                "family": family,\n                "field_label_raw": raw_label,\n                "field_value_raw": raw_value,\n                "raw_unit": raw_unit,\n                "semantic_normalization_status": "not_normalized",\n                "unit_conversion_status": "not_converted",\n            })\n\n            values.append({\n                "group6_technical_id": technical_id,\n                "field_value_raw": raw_value,\n                "numeric_value":\n                    ""\n                    if numeric_value is None\n                    else repr(numeric_value),\n                "raw_unit": raw_unit,\n                "value_parse_status": parse_status,\n                "missing_or_unavailable":\n                    "true"\n                    if is_missing_like(raw_value)\n                    else "false",\n            })\n\n            family_counts[family] += 1\n            parse_status_counts[parse_status] += 1\n\n            if report_id:\n                reports.add(report_id)\n\n            if case_id:\n                cases.add(case_id)\n\n        except Exception as exc:\n            failures.append({\n                "report_id": norm(row.get("report_id", "")),\n                "case_id": norm(row.get("case_id", "")),\n                "vehicle_number": norm(row.get("vehicle_number", "")),\n                "export_basename": norm(row.get("export_basename", "")),\n                "group6_candidate_id":\n                    norm(row.get("group6_candidate_id", "")),\n                "field_label_raw":\n                    norm(row.get("field_label_raw", "")),\n                "field_value_raw":\n                    norm(row.get("field_value_raw", "")),\n                "error_type": type(exc).__name__,\n                "error": str(exc),\n            })\n\n    # ========================================================\n    # Validation\n    # ========================================================\n\n    checks = []\n\n    def check(\n        name,\n        condition,\n        observed,\n        expected,\n        severity="hard",\n        note="",\n    ):\n        checks.append({\n            "check": name,\n            "status": "PASS" if condition else "FAIL",\n            "severity": severity,\n            "observed": str(observed),\n            "expected": str(expected),\n            "note": note,\n        })\n\n    check(\n        "accepted_input_expected_count",\n        len(accepted) == 13202,\n        len(accepted),\n        13202,\n    )\n\n    check(\n        "structured_count_matches_input",\n        len(registry) == len(accepted),\n        len(registry),\n        len(accepted),\n    )\n\n    check(\n        "value_count_matches_registry",\n        len(values) == len(registry),\n        len(values),\n        len(registry),\n    )\n\n    check(\n        "extraction_failures_zero",\n        len(failures) == 0,\n        len(failures),\n        0,\n    )\n\n    ids = [\n        row["group6_technical_id"]\n        for row in registry\n    ]\n\n    duplicate_ids = len(ids) - len(set(ids))\n\n    check(\n        "duplicate_technical_ids",\n        duplicate_ids == 0,\n        duplicate_ids,\n        0,\n    )\n\n    value_ids = {\n        row["group6_technical_id"]\n        for row in values\n    }\n\n    check(\n        "registry_value_id_sets_equal",\n        set(ids) == value_ids,\n        len(set(ids) ^ value_ids),\n        0,\n    )\n\n    check(\n        "blank_report_ids",\n        sum(\n            1\n            for row in registry\n            if not norm(row["report_id"])\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if not norm(row["report_id"])\n        ),\n        0,\n    )\n\n    check(\n        "blank_case_ids",\n        sum(\n            1\n            for row in registry\n            if not norm(row["case_id"])\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if not norm(row["case_id"])\n        ),\n        0,\n    )\n\n    check(\n        "blank_raw_labels",\n        sum(\n            1\n            for row in registry\n            if not norm(row["field_label_raw"])\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if not norm(row["field_label_raw"])\n        ),\n        0,\n    )\n\n    check(\n        "blank_family",\n        sum(\n            1\n            for row in registry\n            if not norm(row["family"])\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if not norm(row["family"])\n        ),\n        0,\n    )\n\n    # ========================================================\n    # Write\n    # ========================================================\n\n    out.mkdir(parents=True, exist_ok=True)\n\n    write_csv(\n        out / "technical_registry.csv",\n        registry,\n        [\n            "group6_technical_id",\n            "source_candidate_id",\n            "report_id",\n            "case_id",\n            "vehicle_number",\n            "export_basename",\n            "source_format",\n            "source_path",\n            "source_record_index",\n            "source_section_heading",\n            "family",\n            "field_label_raw",\n            "field_value_raw",\n            "raw_unit",\n            "semantic_normalization_status",\n            "unit_conversion_status",\n        ],\n    )\n\n    write_csv(\n        out / "technical_values.csv",\n        values,\n        [\n            "group6_technical_id",\n            "field_value_raw",\n            "numeric_value",\n            "raw_unit",\n            "value_parse_status",\n            "missing_or_unavailable",\n        ],\n    )\n\n    write_csv(\n        out / "extraction_failures.csv",\n        failures,\n        [\n            "report_id",\n            "case_id",\n            "vehicle_number",\n            "export_basename",\n            "group6_candidate_id",\n            "field_label_raw",\n            "field_value_raw",\n            "error_type",\n            "error",\n        ],\n    )\n\n    family_summary = [\n        {\n            "family": family,\n            "technical_field_count": count,\n        }\n        for family, count\n        in family_counts.most_common()\n    ]\n\n    write_csv(\n        out / "family_summary.csv",\n        family_summary,\n        [\n            "family",\n            "technical_field_count",\n        ],\n    )\n\n    write_csv(\n        out / "validation_checks.csv",\n        checks,\n        [\n            "check",\n            "status",\n            "severity",\n            "observed",\n            "expected",\n            "note",\n        ],\n    )\n\n    hard_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "hard"\n        )\n    )\n\n    warning_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "warning"\n        )\n    )\n\n    metadata = {\n        "created_at":\n            datetime.now(timezone.utc).isoformat(),\n\n        "group":\n            "Group 6 - Other structured technical and investigation information",\n\n        "stage":\n            "CSV structured extraction",\n\n        "input_accepted_fields":\n            len(accepted),\n\n        "structured_technical_count":\n            len(registry),\n\n        "technical_value_count":\n            len(values),\n\n        "extraction_failure_count":\n            len(failures),\n\n        "reports_with_structured_technical_fields":\n            len(reports),\n\n        "cases_with_structured_technical_fields":\n            len(cases),\n\n        "family_counts":\n            dict(family_counts),\n\n        "value_parse_status_counts":\n            dict(parse_status_counts),\n\n        "numeric_value_count":\n            parse_status_counts.get("numeric_scalar", 0),\n\n        "missing_or_unavailable_count":\n            parse_status_counts.get("missing_or_unavailable", 0),\n\n        "textual_or_identifier_count":\n            parse_status_counts.get("textual_or_identifier", 0),\n\n        "validation_checks":\n            len(checks),\n\n        "hard_validation_failures":\n            hard_failures,\n\n        "warning_validation_failures":\n            warning_failures,\n\n        "scope":\n            (\n                "Structured extraction of the fully audited Group 6 CSV "\n                "population. One accepted source observation is preserved as "\n                "one structured technical/readout record. Raw labels, raw "\n                "values, source sections, source rows, source paths, families, "\n                "and provenance are retained. Numeric parsing is conservative "\n                "and limited to unambiguous scalar values. Identifiers, VINs, "\n                "serials, part numbers, software/calibration values, filenames, "\n                "configuration strings, and textual states remain raw. No "\n                "semantic normalization, unit conversion, fuzzy inference, "\n                "PDF processing, or source mutation is performed."\n            ),\n    }\n\n    tmp = out / "metadata.json.part"\n    tmp.write_text(\n        json.dumps(\n            metadata,\n            indent=2,\n            ensure_ascii=False,\n        ),\n        encoding="utf-8",\n    )\n    tmp.replace(out / "metadata.json")\n\n    print()\n    print(json.dumps(metadata, indent=2, ensure_ascii=False))\n    print()\n    print(f"Outputs: {out}")\n\n    if hard_failures:\n        print()\n        print("GROUP 6 CSV STRUCTURED EXTRACTION HAS HARD FAILURES.")\n        raise SystemExit(1)\n\n    print()\n    print("GROUP 6 CSV STRUCTURED EXTRACTION COMPLETE.")\n\n\n'

_PDF_AUDIT_SOURCE = '"""\nAudit and reconstruct Group 6 fields from PDF-only reports.\n\nWhy this stage exists\n---------------------\nThe first PDF discovery found zero candidates because the PDF text layout\ndoes not reliably preserve "label : value" delimiters. A second-pass\ndiagnostic found many Group 6 keyword-bearing lines. This audit therefore\nrescans the original PDF-only reports and accepts only exact, structurally\nrecognizable Group 6 field patterns.\n\nInputs\n------\ndata/processed/edr/group1_v4/report_index.csv\n\nOutput\n------\ndata/processed/edr/group6_pdf_audit_v1/\n\n    accepted_group6_pdf_fields.csv\n    excluded_keyword_noise.csv\n    remaining_review_fields.csv\n    family_summary.csv\n    report_coverage.csv\n    validation_checks.csv\n    metadata.json\n\nPrinciples\n----------\n- original PDFs are authoritative\n- PDF-only population only\n- no OCR\n- exact/anchored parsing only\n- preserve page, line number, source line, raw label/value\n- no semantic normalization\n- no unit conversion\n- no fuzzy inference\n- no source mutation\n"""\n\nfrom __future__ import annotations\n\nimport argparse\nimport csv\nimport hashlib\nimport json\nimport re\nfrom collections import Counter\nfrom datetime import datetime, timezone\nfrom pathlib import Path, PureWindowsPath\n\nimport pdfplumber\n\ncsv.field_size_limit(100_000_000)\n\nBASE = [\n    "report_id",\n    "case_id",\n    "vehicle_number",\n    "export_basename",\n]\n\n\ndef read_csv(path: Path):\n    with path.open(\n        encoding="utf-8-sig",\n        errors="replace",\n        newline="",\n    ) as f:\n        return list(csv.DictReader(f))\n\n\ndef write_csv(path: Path, rows: list[dict], columns: list[str]):\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_suffix(path.suffix + ".part")\n    with tmp.open("w", encoding="utf-8-sig", newline="") as f:\n        writer = csv.DictWriter(\n            f,\n            fieldnames=columns,\n            extrasaction="ignore",\n        )\n        writer.writeheader()\n        writer.writerows(rows)\n    tmp.replace(path)\n\n\ndef norm(value):\n    return re.sub(\n        r"\\s+",\n        " ",\n        str(value if value is not None else "").strip(),\n    )\n\n\ndef stable_id(*parts):\n    text = "|".join(norm(x) for x in parts)\n    return hashlib.sha256(\n        text.encode("utf-8")\n    ).hexdigest()[:24]\n\n\ndef resolve_pdf_path(row: dict, source_root: Path):\n    raw = norm(row.get("pdf_path", ""))\n\n    if raw:\n        p = Path(raw)\n\n        if p.exists():\n            return p\n\n        basename = PureWindowsPath(raw).name\n        case_id = norm(row.get("case_id", ""))\n\n        if case_id and basename:\n            case_root = source_root / case_id\n\n            if case_root.exists():\n                matches = list(case_root.rglob(basename))\n\n                if matches:\n                    return matches[0]\n\n    basename = norm(row.get("export_basename", ""))\n    case_id = norm(row.get("case_id", ""))\n\n    if basename and case_id:\n        case_root = source_root / case_id\n\n        if case_root.exists():\n            matches = list(case_root.rglob(basename + ".pdf"))\n\n            if not matches:\n                matches = list(case_root.rglob(basename + ".PDF"))\n\n            if matches:\n                return matches[0]\n\n    return None\n\n\n# ------------------------------------------------------------------\n# Exact accepted Group 6 field patterns observed in the diagnostic\n# population. Each pattern must capture LABEL and VALUE.\n# ------------------------------------------------------------------\n\nACCEPT_RULES = [\n    (\n        "ignition_cycle_readout",\n        re.compile(\n            r"^(Ignition Cycles At Investigation)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "ignition_cycle_readout",\n        re.compile(\n            r"^(Ignition Cycle at Download \\(Cycles\\))\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "ignition_cycle_readout",\n        re.compile(\n            r"^(Ignition Cycle, Download "\n            r"\\(Ignition Cycles at Investigation\\))\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "part_serial_identifier",\n        re.compile(\n            r"^(End Model Part Number)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "part_serial_identifier",\n        re.compile(\n            r"^(ESS # \\d+ Traceability Data, "\n            r"Part Number/Broadcast Code)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "part_serial_identifier",\n        re.compile(\n            r"^(Part Number, ACM)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "part_serial_identifier",\n        re.compile(\n            r"^(ECU Part Number)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "part_serial_identifier",\n        re.compile(\n            r"^(Module Serial Number)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "part_serial_identifier",\n        re.compile(\n            r"^(Restraints Control Module Part Number)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "part_serial_identifier",\n        re.compile(\n            r"^(Ford Part Number Prefix)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "module_supplier",\n        re.compile(\n            r"^(ESS # \\d+ Traceability Data, Supplier Code)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "module_supplier",\n        re.compile(\n            r"^(Supplier ID, ACM)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "production_manufacture_date",\n        re.compile(\n            r"^(Production Date, ACM)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "operating_time",\n        re.compile(\n            r"^(Operating Time \\(min\\))\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "odometer_mileage",\n        re.compile(\n            r"^(Vehicle Mileage \\(km\\))\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "odometer_mileage",\n        re.compile(\n            r"^(Odometer signal \\(miles \\[km\\]\\))\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "software_calibration_version",\n        re.compile(\n            r"^(Software Module Identifier \\d+)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "software_calibration_version",\n        re.compile(\n            r"^(Restraints Control Module "\n            r"Software Version Number)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "software_calibration_version",\n        re.compile(\n            r"^(Restraints Control Module Software Date)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "vehicle_identifier_technical",\n        re.compile(\n            r"^(Vehicle Identification Number \\(VIN\\))\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "vehicle_identifier_technical",\n        re.compile(\n            r"^(Vehicle Identification Number)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    # Additional exact technical fields exposed by neighboring lines\n    # in the diagnostic population.\n    (\n        "traceability_identifier",\n        re.compile(\n            r"^(ESS # \\d+ Traceability Data, "\n            r"Component Identifier)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "traceability_identifier",\n        re.compile(\n            r"^(ESS # \\d+ Traceability Data, "\n            r"Traceability Number)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "traceability_identifier",\n        re.compile(\n            r"^(Manufacturing Traceability Data, LineID)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "traceability_identifier",\n        re.compile(\n            r"^(Manufacturing Traceability Data, ShiftID)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n\n    (\n        "system_type",\n        re.compile(\n            r"^(System Type)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n    (\n        "edr_generation",\n        re.compile(\n            r"^(EDR Generation)\\s+(.+)$",\n            re.I,\n        ),\n    ),\n]\n\n\n# Broad keyword detector used only to retain rejected/noise evidence.\nKEYWORD_RE = re.compile(\n    r"\\b(?:"\n    r"ignition cycles?|power[- ]on cycles?|"\n    r"part number|serial number|supplier|"\n    r"software|calibration|firmware|"\n    r"vehicle identification number|vin|"\n    r"configuration|odometer|mileage|"\n    r"operating time|production date|"\n    r"manufacture date|traceability|"\n    r"module identifier|system type|edr generation"\n    r")\\b",\n    re.I,\n)\n\n\n# Explicit known cross-group / documentation exclusions.\ndef exclusion_reason(line: str):\n    text = norm(line)\n\n    if re.search(r"^User Entered VIN\\b", text, re.I):\n        return "group1_user_entered_vin"\n\n    if re.search(r"\\bVIN sequence number\\b", text, re.I):\n        return "documentation_or_record_structure"\n\n    if re.search(\n        r"\\bCRC Check Failed - Saved Without VIN Sequence Number\\b",\n        text,\n        re.I,\n    ):\n        return "group2_record_structure"\n\n    if re.search(\n        r"\\bIgnition Cycle(?:s)? at Event\\b",\n        text,\n        re.I,\n    ):\n        return "group3_event_condition"\n\n    if re.search(\n        r"\\bIgnition Cycle, Crash\\b",\n        text,\n        re.I,\n    ):\n        return "group3_event_condition"\n\n    if re.search(\n        r"\\bSIR Warning Lamp\\b",\n        text,\n        re.I,\n    ):\n        return "group3_warning_lamp"\n\n    if re.search(\n        r"\\bIgnition Cycles Since DTCs? Were Last Cleared\\b",\n        text,\n        re.I,\n    ):\n        return "diagnostic_event_status_not_group6_readout"\n\n    if re.search(\n        r"\\bIgnition Cycle Since DTC was Set\\b",\n        text,\n        re.I,\n    ):\n        return "diagnostic_event_status_not_group6_readout"\n\n    if re.search(\n        r"\\b(?:latest production release|CDR software|"\n        r"software when viewing|software and/or data|"\n        r"software or use thereof)\\b",\n        text,\n        re.I,\n    ):\n        return "documentation_software_notice"\n\n    if re.search(\n        r"\\bvehicle configuration\\b",\n        text,\n        re.I,\n    ) and len(text) > 100:\n        return "documentation_configuration_statement"\n\n    if re.search(\n        r"\\bpart number\\b",\n        text,\n        re.I,\n    ) and len(text) > 100:\n        return "documentation_part_number_statement"\n\n    return ""\n\n\ndef parse_accepted(line: str):\n    text = norm(line)\n\n    for family, pattern in ACCEPT_RULES:\n        match = pattern.fullmatch(text)\n\n        if match:\n            label = norm(match.group(1))\n            value = norm(match.group(2))\n\n            if label and value:\n                return family, label, value\n\n    return None\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=__doc__)\n\n    parser.add_argument(\n        "--report-index",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group1_v4/report_index.csv"\n        ),\n    )\n\n    parser.add_argument(\n        "--source-root",\n        type=Path,\n        default=Path("data/temp"),\n    )\n\n    parser.add_argument(\n        "--output-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_pdf_audit_v1"\n        ),\n    )\n\n    args = parser.parse_args()\n\n    report_index = read_csv(args.report_index)\n    out = args.output_directory\n    out.mkdir(parents=True, exist_ok=True)\n\n    accepted = []\n    excluded = []\n    remaining_review = []\n    coverage = []\n    errors = []\n\n    family_counts = Counter()\n\n    selected = 0\n    processed = 0\n\n    reports_with_accepted = set()\n    cases_with_accepted = set()\n\n    for row in report_index:\n        has_csv = bool(norm(row.get("csv_path", "")))\n        has_pdf = bool(norm(row.get("pdf_path", "")))\n\n        if has_csv or not has_pdf:\n            continue\n\n        selected += 1\n\n        pdf_path = resolve_pdf_path(\n            row,\n            args.source_root,\n        )\n\n        if pdf_path is None or not pdf_path.exists():\n            errors.append({\n                **{\n                    k: row.get(k, "")\n                    for k in BASE\n                },\n                "error_type": "pdf_source_not_found",\n                "pdf_path": norm(row.get("pdf_path", "")),\n                "error": "Could not resolve PDF path.",\n            })\n            continue\n\n        report_accept = 0\n        report_excluded = 0\n        report_review = 0\n\n        try:\n            with pdfplumber.open(pdf_path) as pdf:\n                for page_no, page in enumerate(\n                    pdf.pages,\n                    start=1,\n                ):\n                    text = page.extract_text() or ""\n\n                    for line_no, raw_line in enumerate(\n                        text.splitlines(),\n                        start=1,\n                    ):\n                        line = norm(raw_line)\n\n                        if not line:\n                            continue\n\n                        parsed = parse_accepted(line)\n\n                        if parsed is not None:\n                            family, label, value = parsed\n\n                            candidate_id = (\n                                "g6pdf_"\n                                + stable_id(\n                                    row.get("report_id", ""),\n                                    page_no,\n                                    line_no,\n                                    label,\n                                    value,\n                                )\n                            )\n\n                            accepted.append({\n                                **{\n                                    k: row.get(k, "")\n                                    for k in BASE\n                                },\n                                "group6_candidate_id":\n                                    candidate_id,\n                                "source_format":\n                                    "pdf",\n                                "source_path":\n                                    str(pdf_path),\n                                "pdf_page":\n                                    page_no,\n                                "pdf_line_number":\n                                    line_no,\n                                "source_line_raw":\n                                    line,\n                                "field_label_raw":\n                                    label,\n                                "field_value_raw":\n                                    value,\n                                "audited_family":\n                                    family,\n                                "audit_decision":\n                                    "accept",\n                                "audit_reason":\n                                    "exact_anchored_pdf_field_pattern",\n                                "semantic_normalization_status":\n                                    "not_normalized",\n                                "unit_conversion_status":\n                                    "not_converted",\n                            })\n\n                            family_counts[family] += 1\n                            report_accept += 1\n                            reports_with_accepted.add(\n                                row.get("report_id", "")\n                            )\n                            cases_with_accepted.add(\n                                row.get("case_id", "")\n                            )\n                            continue\n\n                        if not KEYWORD_RE.search(line):\n                            continue\n\n                        reason = exclusion_reason(line)\n\n                        evidence = {\n                            **{\n                                k: row.get(k, "")\n                                for k in BASE\n                            },\n                            "source_format":\n                                "pdf",\n                            "source_path":\n                                str(pdf_path),\n                            "pdf_page":\n                                page_no,\n                            "pdf_line_number":\n                                line_no,\n                            "source_line_raw":\n                                line,\n                        }\n\n                        if reason:\n                            excluded.append({\n                                **evidence,\n                                "audit_decision":\n                                    "exclude",\n                                "audit_reason":\n                                    reason,\n                            })\n                            report_excluded += 1\n\n                        else:\n                            remaining_review.append({\n                                **evidence,\n                                "audit_decision":\n                                    "review",\n                                "audit_reason":\n                                    "group6_keyword_but_no_exact_accepted_pattern",\n                            })\n                            report_review += 1\n\n            processed += 1\n\n        except Exception as exc:\n            errors.append({\n                **{\n                    k: row.get(k, "")\n                    for k in BASE\n                },\n                "error_type":\n                    type(exc).__name__,\n                "pdf_path":\n                    str(pdf_path),\n                "error":\n                    str(exc),\n            })\n            continue\n\n        coverage.append({\n            **{\n                k: row.get(k, "")\n                for k in BASE\n            },\n            "pdf_path":\n                str(pdf_path),\n            "accepted_count":\n                report_accept,\n            "excluded_keyword_noise_count":\n                report_excluded,\n            "remaining_review_count":\n                report_review,\n        })\n\n        if processed % 25 == 0 or processed == selected:\n            print(\n                f"Audited Group 6 PDF {processed}/{selected} reports...",\n                flush=True,\n            )\n\n    # --------------------------------------------------------\n    # Validation\n    # --------------------------------------------------------\n\n    checks = []\n\n    def check(\n        name,\n        condition,\n        observed,\n        expected,\n        severity="hard",\n        note="",\n    ):\n        checks.append({\n            "check":\n                name,\n            "status":\n                "PASS" if condition else "FAIL",\n            "severity":\n                severity,\n            "observed":\n                str(observed),\n            "expected":\n                str(expected),\n            "note":\n                note,\n        })\n\n    check(\n        "pdf_only_reports_selected",\n        selected == 181,\n        selected,\n        181,\n    )\n\n    check(\n        "pdf_only_reports_processed",\n        processed == selected,\n        processed,\n        selected,\n    )\n\n    check(\n        "source_errors_zero",\n        len(errors) == 0,\n        len(errors),\n        0,\n    )\n\n    ids = [\n        norm(row.get("group6_candidate_id", ""))\n        for row in accepted\n    ]\n\n    check(\n        "accepted_ids_unique",\n        len(ids) == len(set(ids)),\n        len(ids) - len(set(ids)),\n        0,\n    )\n\n    check(\n        "accepted_labels_nonblank",\n        all(\n            norm(row.get("field_label_raw", ""))\n            for row in accepted\n        ),\n        sum(\n            1\n            for row in accepted\n            if not norm(row.get("field_label_raw", ""))\n        ),\n        0,\n    )\n\n    check(\n        "accepted_values_nonblank",\n        all(\n            norm(row.get("field_value_raw", ""))\n            for row in accepted\n        ),\n        sum(\n            1\n            for row in accepted\n            if not norm(row.get("field_value_raw", ""))\n        ),\n        0,\n    )\n\n    check(\n        "accepted_family_accounting",\n        sum(family_counts.values()) == len(accepted),\n        sum(family_counts.values()),\n        len(accepted),\n    )\n\n    hard_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "hard"\n        )\n    )\n\n    warning_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "warning"\n        )\n    )\n\n    # --------------------------------------------------------\n    # Write\n    # --------------------------------------------------------\n\n    accepted_cols = [\n        *BASE,\n        "group6_candidate_id",\n        "source_format",\n        "source_path",\n        "pdf_page",\n        "pdf_line_number",\n        "source_line_raw",\n        "field_label_raw",\n        "field_value_raw",\n        "audited_family",\n        "audit_decision",\n        "audit_reason",\n        "semantic_normalization_status",\n        "unit_conversion_status",\n    ]\n\n    evidence_cols = [\n        *BASE,\n        "source_format",\n        "source_path",\n        "pdf_page",\n        "pdf_line_number",\n        "source_line_raw",\n        "audit_decision",\n        "audit_reason",\n    ]\n\n    write_csv(\n        out / "accepted_group6_pdf_fields.csv",\n        accepted,\n        accepted_cols,\n    )\n\n    write_csv(\n        out / "excluded_keyword_noise.csv",\n        excluded,\n        evidence_cols,\n    )\n\n    write_csv(\n        out / "remaining_review_fields.csv",\n        remaining_review,\n        evidence_cols,\n    )\n\n    write_csv(\n        out / "family_summary.csv",\n        [\n            {\n                "audited_family": family,\n                "field_count": count,\n            }\n            for family, count\n            in family_counts.most_common()\n        ],\n        [\n            "audited_family",\n            "field_count",\n        ],\n    )\n\n    write_csv(\n        out / "report_coverage.csv",\n        coverage,\n        [\n            *BASE,\n            "pdf_path",\n            "accepted_count",\n            "excluded_keyword_noise_count",\n            "remaining_review_count",\n        ],\n    )\n\n    write_csv(\n        out / "validation_checks.csv",\n        checks,\n        [\n            "check",\n            "status",\n            "severity",\n            "observed",\n            "expected",\n            "note",\n        ],\n    )\n\n    metadata = {\n        "created_at":\n            datetime.now(timezone.utc).isoformat(),\n\n        "group":\n            "Group 6 - Other structured technical and investigation information",\n\n        "stage":\n            "PDF-only exact-pattern audit",\n\n        "pdf_only_reports_selected":\n            selected,\n\n        "pdf_only_reports_processed":\n            processed,\n\n        "accepted_group6_fields":\n            len(accepted),\n\n        "excluded_keyword_noise":\n            len(excluded),\n\n        "remaining_review_fields":\n            len(remaining_review),\n\n        "reports_with_accepted_group6_fields":\n            len(reports_with_accepted),\n\n        "cases_with_accepted_group6_fields":\n            len(cases_with_accepted),\n\n        "accepted_family_counts":\n            dict(family_counts),\n\n        "source_errors":\n            len(errors),\n\n        "ocr_used":\n            False,\n\n        "validation_checks":\n            len(checks),\n\n        "hard_validation_failures":\n            hard_failures,\n\n        "warning_validation_failures":\n            warning_failures,\n\n        "scope":\n            (\n                "Exact-pattern audit and reconstruction of Group 6 fields "\n                "from the original PDF-only report population after the "\n                "diagnostic pass showed that generic label/value parsing "\n                "missed technical fields. Only anchored field patterns are "\n                "accepted. Documentation text, event-condition fields, "\n                "record-structure text, and other keyword-bearing noise are "\n                "excluded or retained for explicit review. No OCR, semantic "\n                "normalization, unit conversion, fuzzy inference, or source "\n                "mutation is performed."\n            ),\n    }\n\n    (out / "metadata.json").write_text(\n        json.dumps(\n            metadata,\n            indent=2,\n            ensure_ascii=False,\n        ),\n        encoding="utf-8",\n    )\n\n    print()\n    print(\n        json.dumps(\n            metadata,\n            indent=2,\n            ensure_ascii=False,\n        )\n    )\n    print()\n    print(f"Outputs: {out}")\n\n    if hard_failures:\n        print()\n        print("GROUP 6 PDF AUDIT HAS HARD VALIDATION FAILURES.")\n        raise SystemExit(1)\n\n    print()\n    print("GROUP 6 PDF AUDIT COMPLETE.")\n\n\n'

_PDF_RESOLVE_SOURCE = '"""\nResolve all remaining Group 6 PDF review rows after exact-pattern audit.\n\nInput\n-----\ndata/processed/edr/group6_pdf_audit_v1/\n    accepted_group6_pdf_fields.csv\n    excluded_keyword_noise.csv\n    remaining_review_fields.csv\n\nOutput\n------\ndata/processed/edr/group6_pdf_resolved_v1/\n    accepted_group6_pdf_fields.csv\n    excluded_non_group6_fields.csv\n    remaining_review_fields.csv\n    review_resolution.csv\n    family_summary.csv\n    routing_summary.csv\n    validation_checks.csv\n    metadata.json\n\nResolution of the 771 review rows\n---------------------------------\nAccepted into Group 6:\n- Ignition Cycle, Download (times) <value>\n- Manufacturing Traceability Data, Serial/Lot/BatchNumber <value>\n- Manufacturing Traceability Data, Year <value>\n- Manufacturing Traceability Data, DayOfTheYear <value>\n\nRouted to Group 3:\n- Ignition Cycles At Deployment <value>\n- Ignition Cycles At Non-Deployment <value>\n- Ignition Cycle Key On Timer at Start of Frontal/Side Event ...\n\nExcluded as documentation:\n- software licensing header/footer text\n- explanatory ignition-cycle prose\n- CDR software/version narrative notices\n- counter behavior documentation\n\nNo fuzzy inference is used.\n"""\n\nfrom __future__ import annotations\n\nimport argparse\nimport csv\nimport hashlib\nimport json\nimport re\nfrom collections import Counter\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\ncsv.field_size_limit(100_000_000)\n\n\ndef read_csv(path: Path):\n    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:\n        return list(csv.DictReader(f))\n\n\ndef write_csv(path: Path, rows: list[dict], columns: list[str]):\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_suffix(path.suffix + ".part")\n    with tmp.open("w", encoding="utf-8-sig", newline="") as f:\n        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")\n        writer.writeheader()\n        writer.writerows(rows)\n    tmp.replace(path)\n\n\ndef norm(value):\n    return re.sub(r"\\s+", " ", str(value if value is not None else "").strip())\n\n\ndef stable_id(*parts):\n    text = "|".join(norm(x) for x in parts)\n    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]\n\n\ndef union_columns(*rowsets):\n    seen = set()\n    cols = []\n    for rows in rowsets:\n        for row in rows:\n            for key in row:\n                if key not in seen:\n                    seen.add(key)\n                    cols.append(key)\n    return cols\n\n\ndef resolve_review(row):\n    line = norm(row.get("source_line_raw", ""))\n\n    m = re.fullmatch(\n        r"(Ignition Cycle, Download \\(times\\))\\s+(.+)",\n        line,\n        flags=re.I,\n    )\n    if m:\n        return {\n            "resolution": "accept",\n            "route": "group6",\n            "family": "ignition_cycle_readout",\n            "label": norm(m.group(1)),\n            "value": norm(m.group(2)),\n            "reason": "download_ignition_cycle_count",\n        }\n\n    m = re.fullmatch(\n        r"(Manufacturing Traceability Data, "\n        r"(?:Serial/Lot/BatchNumber|Year|DayOfTheYear))\\s+(.+)",\n        line,\n        flags=re.I,\n    )\n    if m:\n        return {\n            "resolution": "accept",\n            "route": "group6",\n            "family": "traceability_identifier",\n            "label": norm(m.group(1)),\n            "value": norm(m.group(2)),\n            "reason": "manufacturing_traceability_field",\n        }\n\n    if re.fullmatch(\n        r"Ignition Cycles At Deployment\\s+.+",\n        line,\n        flags=re.I,\n    ):\n        return {\n            "resolution": "exclude",\n            "route": "group3",\n            "family": "",\n            "label": "",\n            "value": "",\n            "reason": "deployment_event_ignition_cycle",\n        }\n\n    if re.fullmatch(\n        r"Ignition Cycles At Non-Deployment\\s+.+",\n        line,\n        flags=re.I,\n    ):\n        return {\n            "resolution": "exclude",\n            "route": "group3",\n            "family": "",\n            "label": "",\n            "value": "",\n            "reason": "nondeployment_event_ignition_cycle",\n        }\n\n    if re.fullmatch(\n        r"Ignition Cycle Key On Timer at Start of "\n        r"(?:Frontal|Side) Event \\(sec\\)\\s+.+",\n        line,\n        flags=re.I,\n    ):\n        return {\n            "resolution": "exclude",\n            "route": "group3",\n            "family": "",\n            "label": "",\n            "value": "",\n            "reason": "event_start_ignition_timer",\n        }\n\n    if re.match(\n        r"^(?:Reported|Imaged) with Software Licensed to",\n        line,\n        flags=re.I,\n    ):\n        return {\n            "resolution": "exclude",\n            "route": "documentation",\n            "family": "",\n            "label": "",\n            "value": "",\n            "reason": "software_license_header",\n        }\n\n    if re.search(\n        r"\\b(?:ignition cycle|ignition cycles|ignition cycle counter)\\b",\n        line,\n        flags=re.I,\n    ):\n        return {\n            "resolution": "exclude",\n            "route": "documentation",\n            "family": "",\n            "label": "",\n            "value": "",\n            "reason": "ignition_cycle_explanatory_text",\n        }\n\n    if re.search(r"\\bsoftware\\b", line, flags=re.I):\n        return {\n            "resolution": "exclude",\n            "route": "documentation",\n            "family": "",\n            "label": "",\n            "value": "",\n            "reason": "software_documentation_text",\n        }\n\n    return {\n        "resolution": "review",\n        "route": "unresolved",\n        "family": "",\n        "label": "",\n        "value": "",\n        "reason": "no_exact_resolution_rule",\n    }\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=__doc__)\n\n    parser.add_argument(\n        "--audit-directory",\n        type=Path,\n        default=Path("data/processed/edr/group6_pdf_audit_v1"),\n    )\n\n    parser.add_argument(\n        "--output-directory",\n        type=Path,\n        default=Path("data/processed/edr/group6_pdf_resolved_v1"),\n    )\n\n    args = parser.parse_args()\n\n    src = args.audit_directory\n    out = args.output_directory\n\n    accepted_path = src / "accepted_group6_pdf_fields.csv"\n    excluded_path = src / "excluded_keyword_noise.csv"\n    review_path = src / "remaining_review_fields.csv"\n\n    for path in [accepted_path, excluded_path, review_path]:\n        if not path.exists():\n            raise FileNotFoundError(path)\n\n    prior_accepted = read_csv(accepted_path)\n    prior_excluded = read_csv(excluded_path)\n    review_rows = read_csv(review_path)\n\n    if len(review_rows) != 771:\n        raise RuntimeError(\n            f"Expected 771 review rows, found {len(review_rows)}."\n        )\n\n    promoted = []\n    newly_excluded = []\n    unresolved = []\n    resolution_log = []\n\n    for row in review_rows:\n        result = resolve_review(row)\n\n        resolution_log.append({\n            **row,\n            "resolution": result["resolution"],\n            "resolution_route": result["route"],\n            "resolution_family": result["family"],\n            "resolution_reason": result["reason"],\n        })\n\n        if result["resolution"] == "accept":\n            candidate_id = (\n                "g6pdf_"\n                + stable_id(\n                    row.get("report_id", ""),\n                    row.get("pdf_page", ""),\n                    row.get("pdf_line_number", ""),\n                    result["label"],\n                    result["value"],\n                )\n            )\n\n            promoted.append({\n                "report_id": row.get("report_id", ""),\n                "case_id": row.get("case_id", ""),\n                "vehicle_number": row.get("vehicle_number", ""),\n                "export_basename": row.get("export_basename", ""),\n                "group6_candidate_id": candidate_id,\n                "source_format": "pdf",\n                "source_path": row.get("source_path", ""),\n                "pdf_page": row.get("pdf_page", ""),\n                "pdf_line_number": row.get("pdf_line_number", ""),\n                "source_line_raw": row.get("source_line_raw", ""),\n                "field_label_raw": result["label"],\n                "field_value_raw": result["value"],\n                "audited_family": result["family"],\n                "audit_decision": "accept",\n                "audit_reason": result["reason"],\n                "semantic_normalization_status": "not_normalized",\n                "unit_conversion_status": "not_converted",\n            })\n\n        elif result["resolution"] == "exclude":\n            newly_excluded.append({\n                **row,\n                "audit_decision": "exclude",\n                "audit_route": result["route"],\n                "audit_reason": result["reason"],\n            })\n\n        else:\n            unresolved.append(row)\n\n    final_accepted = prior_accepted + promoted\n\n    normalized_prior_excluded = [\n        {\n            **row,\n            "audit_route": (\n                row.get("audit_route", "")\n                or "previous_audit_exclusion"\n            ),\n        }\n        for row in prior_excluded\n    ]\n\n    final_excluded = normalized_prior_excluded + newly_excluded\n\n    family_counts = Counter(\n        norm(row.get("audited_family", ""))\n        for row in final_accepted\n    )\n\n    route_counts = Counter(\n        norm(row.get("audit_route", ""))\n        for row in final_excluded\n    )\n\n    resolution_counts = Counter(\n        row["resolution"]\n        for row in resolution_log\n    )\n\n    # Validation\n    checks = []\n\n    def check(name, condition, observed, expected, severity="hard", note=""):\n        checks.append({\n            "check": name,\n            "status": "PASS" if condition else "FAIL",\n            "severity": severity,\n            "observed": str(observed),\n            "expected": str(expected),\n            "note": note,\n        })\n\n    check("input_review_count", len(review_rows) == 771, len(review_rows), 771)\n    check("promoted_group6_count", len(promoted) == 13, len(promoted), 13)\n    check(\n        "new_group3_exclusions",\n        sum(1 for r in newly_excluded if r["audit_route"] == "group3") == 101,\n        sum(1 for r in newly_excluded if r["audit_route"] == "group3"),\n        101,\n    )\n    check(\n        "new_documentation_exclusions",\n        sum(\n            1\n            for r in newly_excluded\n            if r["audit_route"] == "documentation"\n        ) == 657,\n        sum(\n            1\n            for r in newly_excluded\n            if r["audit_route"] == "documentation"\n        ),\n        657,\n    )\n    check("remaining_review_zero", len(unresolved) == 0, len(unresolved), 0)\n    check(\n        "review_accounting_complete",\n        len(promoted) + len(newly_excluded) + len(unresolved) == 771,\n        len(promoted) + len(newly_excluded) + len(unresolved),\n        771,\n    )\n    check(\n        "final_accepted_count",\n        len(final_accepted) == 416,\n        len(final_accepted),\n        416,\n    )\n\n    ids = [\n        norm(row.get("group6_candidate_id", ""))\n        for row in final_accepted\n    ]\n    check(\n        "accepted_candidate_ids_unique",\n        len(ids) == len(set(ids)),\n        len(ids) - len(set(ids)),\n        0,\n    )\n\n    hard_failures = sum(\n        1\n        for r in checks\n        if r["status"] == "FAIL" and r["severity"] == "hard"\n    )\n\n    warning_failures = sum(\n        1\n        for r in checks\n        if r["status"] == "FAIL" and r["severity"] == "warning"\n    )\n\n    out.mkdir(parents=True, exist_ok=True)\n\n    accepted_cols = union_columns(final_accepted)\n    excluded_cols = union_columns(final_excluded)\n    resolution_cols = union_columns(resolution_log)\n\n    write_csv(\n        out / "accepted_group6_pdf_fields.csv",\n        final_accepted,\n        accepted_cols,\n    )\n\n    write_csv(\n        out / "excluded_non_group6_fields.csv",\n        final_excluded,\n        excluded_cols,\n    )\n\n    write_csv(\n        out / "remaining_review_fields.csv",\n        unresolved,\n        union_columns(review_rows),\n    )\n\n    write_csv(\n        out / "review_resolution.csv",\n        resolution_log,\n        resolution_cols,\n    )\n\n    write_csv(\n        out / "family_summary.csv",\n        [\n            {\n                "audited_family": family,\n                "field_count": count,\n            }\n            for family, count in family_counts.most_common()\n        ],\n        ["audited_family", "field_count"],\n    )\n\n    write_csv(\n        out / "routing_summary.csv",\n        [\n            {\n                "audit_route": route,\n                "field_count": count,\n            }\n            for route, count in route_counts.most_common()\n        ],\n        ["audit_route", "field_count"],\n    )\n\n    write_csv(\n        out / "validation_checks.csv",\n        checks,\n        [\n            "check",\n            "status",\n            "severity",\n            "observed",\n            "expected",\n            "note",\n        ],\n    )\n\n    reports = {\n        norm(r.get("report_id", ""))\n        for r in final_accepted\n        if norm(r.get("report_id", ""))\n    }\n\n    cases = {\n        norm(r.get("case_id", ""))\n        for r in final_accepted\n        if norm(r.get("case_id", ""))\n    }\n\n    metadata = {\n        "created_at": datetime.now(timezone.utc).isoformat(),\n        "group": "Group 6 - Other structured technical and investigation information",\n        "stage": "PDF-only residual review resolution",\n        "prior_accepted_fields": len(prior_accepted),\n        "input_remaining_review_fields": len(review_rows),\n        "promoted_to_group6": len(promoted),\n        "newly_excluded_fields": len(newly_excluded),\n        "remaining_review_fields": len(unresolved),\n        "final_accepted_group6_fields": len(final_accepted),\n        "reports_with_accepted_group6_fields": len(reports),\n        "cases_with_accepted_group6_fields": len(cases),\n        "resolution_counts": dict(resolution_counts),\n        "accepted_family_counts": dict(family_counts),\n        "new_exclusion_route_counts": dict(\n            Counter(r["audit_route"] for r in newly_excluded)\n        ),\n        "validation_checks": len(checks),\n        "hard_validation_failures": hard_failures,\n        "warning_validation_failures": warning_failures,\n        "scope": (\n            "Exact resolution of every residual Group 6 PDF review row. "\n            "Download-time ignition-cycle counts and manufacturing traceability "\n            "fields are retained in Group 6. Deployment/non-deployment ignition "\n            "cycle fields and event-start key-on timers are routed to Group 3. "\n            "Software-license headers and explanatory ignition-cycle/software "\n            "prose are excluded as documentation. No fuzzy inference, semantic "\n            "normalization, unit conversion, OCR, or source mutation is used."\n        ),\n    }\n\n    (out / "metadata.json").write_text(\n        json.dumps(metadata, indent=2, ensure_ascii=False),\n        encoding="utf-8",\n    )\n\n    print()\n    print(json.dumps(metadata, indent=2, ensure_ascii=False))\n    print()\n    print(f"Outputs: {out}")\n\n    if hard_failures:\n        print()\n        print("GROUP 6 PDF REVIEW RESOLUTION HAS HARD VALIDATION FAILURES.")\n        raise SystemExit(1)\n\n    print()\n    print("GROUP 6 PDF REVIEW RESOLUTION COMPLETE.")\n\n\n'

_PDF_EXTRACT_SOURCE = '"""\nBuild structured Group 6 PDF-only package from resolved audit fields.\n\nInput\n-----\ndata/processed/edr/group6_pdf_resolved_v1/\n    accepted_group6_pdf_fields.csv\n    remaining_review_fields.csv\n\nOutput\n------\ndata/processed/edr/group6_pdf_structured_v1/\n    technical_registry.csv\n    technical_values.csv\n    extraction_failures.csv\n    family_summary.csv\n    validation_checks.csv\n    metadata.json\n\nRules\n-----\n- One accepted PDF source observation becomes one structured Group 6 record.\n- Preserve report/case/vehicle/export provenance.\n- Preserve PDF page, line number, full source line, raw label, raw value,\n  and audited family.\n- Parse numeric scalar values conservatively.\n- Preserve identifiers, versions, VINs, serials, part numbers,\n  configuration strings, traceability values, and textual states raw.\n- No OCR.\n- No semantic normalization.\n- No unit conversion.\n- No fuzzy inference.\n- No source mutation.\n"""\n\nfrom __future__ import annotations\n\nimport argparse\nimport csv\nimport hashlib\nimport json\nimport re\nfrom collections import Counter\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\ncsv.field_size_limit(100_000_000)\n\n\ndef read_csv(path: Path):\n    with path.open(\n        encoding="utf-8-sig",\n        errors="replace",\n        newline="",\n    ) as f:\n        return list(csv.DictReader(f))\n\n\ndef write_csv(path: Path, rows: list[dict], columns: list[str]):\n    path.parent.mkdir(parents=True, exist_ok=True)\n    tmp = path.with_suffix(path.suffix + ".part")\n\n    with tmp.open(\n        "w",\n        encoding="utf-8-sig",\n        newline="",\n    ) as f:\n        writer = csv.DictWriter(\n            f,\n            fieldnames=columns,\n            extrasaction="ignore",\n        )\n        writer.writeheader()\n        writer.writerows(rows)\n\n    tmp.replace(path)\n\n\ndef norm(value):\n    return re.sub(\n        r"\\s+",\n        " ",\n        str(value if value is not None else "").strip(),\n    )\n\n\ndef stable_id(*parts):\n    text = "|".join(norm(part) for part in parts)\n    return hashlib.sha256(\n        text.encode("utf-8")\n    ).hexdigest()[:24]\n\n\nMISSING_VALUES = {\n    "",\n    "n/a",\n    "na",\n    "sna",\n    "not available",\n    "not applicable",\n    "unknown",\n    "invalid",\n    "data not available",\n    "no data",\n}\n\n\nNUMERIC_RE = re.compile(\n    r"""\n    ^\\s*\n    (?P<num>\n        [-+]?\n        (?:\n            \\d+(?:\\.\\d*)?\n            |\n            \\.\\d+\n        )\n        (?:[eE][-+]?\\d+)?\n    )\n    \\s*\n    (?P<unit>\n        %\n        |\n        V\n        |\n        volts?\n        |\n        cycles?\n        |\n        times?\n        |\n        miles?\n        |\n        mi\n        |\n        km\n        |\n        hours?\n        |\n        hrs?\n        |\n        minutes?\n        |\n        min\n        |\n        mph\n        |\n        km/h\n        |\n        kph\n    )?\n    \\s*$\n    """,\n    re.I | re.X,\n)\n\n\ndef is_missing_like(value):\n    return norm(value).casefold() in MISSING_VALUES\n\n\ndef parse_numeric_scalar(value):\n    text = norm(value)\n\n    if not text or is_missing_like(text):\n        return None, "", "missing_or_unavailable"\n\n    cleaned = text.replace(",", "")\n    match = NUMERIC_RE.fullmatch(cleaned)\n\n    if not match:\n        return None, "", "textual_or_identifier"\n\n    try:\n        number = float(match.group("num"))\n    except Exception:\n        return None, "", "numeric_parse_failed"\n\n    unit = norm(match.group("unit") or "")\n\n    return number, unit, "numeric_scalar"\n\n\ndef raw_unit_from_label(label):\n    text = norm(label)\n\n    match = re.search(r"\\(([^()]*)\\)\\s*$", text)\n\n    if not match:\n        return ""\n\n    candidate = norm(match.group(1))\n\n    if re.fullmatch(\n        r"(?:"\n        r"V|volts?|cycles?|times?|miles?|mi|km|"\n        r"hours?|hrs?|minutes?|min|%|mph|km/h|kph"\n        r")",\n        candidate,\n        flags=re.I,\n    ):\n        return candidate\n\n    return ""\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=__doc__)\n\n    parser.add_argument(\n        "--resolved-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_pdf_resolved_v1"\n        ),\n    )\n\n    parser.add_argument(\n        "--output-directory",\n        type=Path,\n        default=Path(\n            "data/processed/edr/group6_pdf_structured_v1"\n        ),\n    )\n\n    args = parser.parse_args()\n\n    src = args.resolved_directory\n    out = args.output_directory\n\n    accepted_path = src / "accepted_group6_pdf_fields.csv"\n    unresolved_path = src / "remaining_review_fields.csv"\n\n    if not accepted_path.exists():\n        raise FileNotFoundError(accepted_path)\n\n    if not unresolved_path.exists():\n        raise FileNotFoundError(unresolved_path)\n\n    accepted = read_csv(accepted_path)\n    unresolved = read_csv(unresolved_path)\n\n    if unresolved:\n        raise RuntimeError(\n            f"Refusing extraction: {len(unresolved)} unresolved Group 6 PDF rows remain."\n        )\n\n    registry = []\n    values = []\n    failures = []\n\n    family_counts = Counter()\n    parse_status_counts = Counter()\n    reports = set()\n    cases = set()\n\n    for row in accepted:\n        try:\n            report_id = norm(row.get("report_id", ""))\n            case_id = norm(row.get("case_id", ""))\n            vehicle_number = norm(row.get("vehicle_number", ""))\n            export_basename = norm(row.get("export_basename", ""))\n            source_path = norm(row.get("source_path", ""))\n            page = norm(row.get("pdf_page", ""))\n            line_no = norm(row.get("pdf_line_number", ""))\n            source_line = norm(row.get("source_line_raw", ""))\n            raw_label = norm(row.get("field_label_raw", ""))\n            raw_value = norm(row.get("field_value_raw", ""))\n            family = norm(row.get("audited_family", ""))\n\n            if not raw_label:\n                raise ValueError("blank field_label_raw")\n\n            if not family:\n                raise ValueError("blank audited_family")\n\n            source_candidate_id = norm(\n                row.get("group6_candidate_id", "")\n            )\n\n            technical_id = (\n                "g6pdf_"\n                + stable_id(\n                    report_id,\n                    case_id,\n                    vehicle_number,\n                    export_basename,\n                    source_path,\n                    page,\n                    line_no,\n                    raw_label,\n                    raw_value,\n                    family,\n                )\n            )\n\n            numeric_value, value_unit, parse_status = (\n                parse_numeric_scalar(raw_value)\n            )\n\n            label_unit = raw_unit_from_label(raw_label)\n            raw_unit = value_unit or label_unit\n\n            registry.append({\n                "group6_technical_id": technical_id,\n                "source_candidate_id": source_candidate_id,\n                "report_id": report_id,\n                "case_id": case_id,\n                "vehicle_number": vehicle_number,\n                "export_basename": export_basename,\n                "source_format": "pdf",\n                "source_path": source_path,\n                "pdf_page": page,\n                "pdf_line_number": line_no,\n                "source_line_raw": source_line,\n                "family": family,\n                "field_label_raw": raw_label,\n                "field_value_raw": raw_value,\n                "raw_unit": raw_unit,\n                "semantic_normalization_status": "not_normalized",\n                "unit_conversion_status": "not_converted",\n            })\n\n            values.append({\n                "group6_technical_id": technical_id,\n                "field_value_raw": raw_value,\n                "numeric_value":\n                    ""\n                    if numeric_value is None\n                    else repr(numeric_value),\n                "raw_unit": raw_unit,\n                "value_parse_status": parse_status,\n                "missing_or_unavailable":\n                    "true"\n                    if is_missing_like(raw_value)\n                    else "false",\n            })\n\n            family_counts[family] += 1\n            parse_status_counts[parse_status] += 1\n\n            if report_id:\n                reports.add(report_id)\n\n            if case_id:\n                cases.add(case_id)\n\n        except Exception as exc:\n            failures.append({\n                "report_id": norm(row.get("report_id", "")),\n                "case_id": norm(row.get("case_id", "")),\n                "vehicle_number": norm(row.get("vehicle_number", "")),\n                "export_basename": norm(row.get("export_basename", "")),\n                "group6_candidate_id":\n                    norm(row.get("group6_candidate_id", "")),\n                "pdf_page": norm(row.get("pdf_page", "")),\n                "pdf_line_number": norm(row.get("pdf_line_number", "")),\n                "field_label_raw":\n                    norm(row.get("field_label_raw", "")),\n                "field_value_raw":\n                    norm(row.get("field_value_raw", "")),\n                "error_type": type(exc).__name__,\n                "error": str(exc),\n            })\n\n    checks = []\n\n    def check(\n        name,\n        condition,\n        observed,\n        expected,\n        severity="hard",\n        note="",\n    ):\n        checks.append({\n            "check": name,\n            "status": "PASS" if condition else "FAIL",\n            "severity": severity,\n            "observed": str(observed),\n            "expected": str(expected),\n            "note": note,\n        })\n\n    check(\n        "accepted_input_expected_count",\n        len(accepted) == 416,\n        len(accepted),\n        416,\n    )\n\n    check(\n        "structured_count_matches_input",\n        len(registry) == len(accepted),\n        len(registry),\n        len(accepted),\n    )\n\n    check(\n        "value_count_matches_registry",\n        len(values) == len(registry),\n        len(values),\n        len(registry),\n    )\n\n    check(\n        "extraction_failures_zero",\n        len(failures) == 0,\n        len(failures),\n        0,\n    )\n\n    ids = [\n        row["group6_technical_id"]\n        for row in registry\n    ]\n\n    duplicate_ids = len(ids) - len(set(ids))\n\n    check(\n        "duplicate_technical_ids",\n        duplicate_ids == 0,\n        duplicate_ids,\n        0,\n    )\n\n    value_ids = {\n        row["group6_technical_id"]\n        for row in values\n    }\n\n    check(\n        "registry_value_id_sets_equal",\n        set(ids) == value_ids,\n        len(set(ids) ^ value_ids),\n        0,\n    )\n\n    check(\n        "blank_report_ids",\n        sum(\n            1\n            for row in registry\n            if not norm(row["report_id"])\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if not norm(row["report_id"])\n        ),\n        0,\n    )\n\n    check(\n        "blank_case_ids",\n        sum(\n            1\n            for row in registry\n            if not norm(row["case_id"])\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if not norm(row["case_id"])\n        ),\n        0,\n    )\n\n    check(\n        "blank_pdf_provenance",\n        sum(\n            1\n            for row in registry\n            if (\n                not norm(row["pdf_page"])\n                or not norm(row["pdf_line_number"])\n                or not norm(row["source_line_raw"])\n            )\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if (\n                not norm(row["pdf_page"])\n                or not norm(row["pdf_line_number"])\n                or not norm(row["source_line_raw"])\n            )\n        ),\n        0,\n    )\n\n    check(\n        "blank_raw_labels",\n        sum(\n            1\n            for row in registry\n            if not norm(row["field_label_raw"])\n        ) == 0,\n        sum(\n            1\n            for row in registry\n            if not norm(row["field_label_raw"])\n        ),\n        0,\n    )\n\n    out.mkdir(parents=True, exist_ok=True)\n\n    write_csv(\n        out / "technical_registry.csv",\n        registry,\n        [\n            "group6_technical_id",\n            "source_candidate_id",\n            "report_id",\n            "case_id",\n            "vehicle_number",\n            "export_basename",\n            "source_format",\n            "source_path",\n            "pdf_page",\n            "pdf_line_number",\n            "source_line_raw",\n            "family",\n            "field_label_raw",\n            "field_value_raw",\n            "raw_unit",\n            "semantic_normalization_status",\n            "unit_conversion_status",\n        ],\n    )\n\n    write_csv(\n        out / "technical_values.csv",\n        values,\n        [\n            "group6_technical_id",\n            "field_value_raw",\n            "numeric_value",\n            "raw_unit",\n            "value_parse_status",\n            "missing_or_unavailable",\n        ],\n    )\n\n    write_csv(\n        out / "extraction_failures.csv",\n        failures,\n        [\n            "report_id",\n            "case_id",\n            "vehicle_number",\n            "export_basename",\n            "group6_candidate_id",\n            "pdf_page",\n            "pdf_line_number",\n            "field_label_raw",\n            "field_value_raw",\n            "error_type",\n            "error",\n        ],\n    )\n\n    write_csv(\n        out / "family_summary.csv",\n        [\n            {\n                "family": family,\n                "technical_field_count": count,\n            }\n            for family, count in family_counts.most_common()\n        ],\n        [\n            "family",\n            "technical_field_count",\n        ],\n    )\n\n    write_csv(\n        out / "validation_checks.csv",\n        checks,\n        [\n            "check",\n            "status",\n            "severity",\n            "observed",\n            "expected",\n            "note",\n        ],\n    )\n\n    hard_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "hard"\n        )\n    )\n\n    warning_failures = sum(\n        1\n        for row in checks\n        if (\n            row["status"] == "FAIL"\n            and row["severity"] == "warning"\n        )\n    )\n\n    metadata = {\n        "created_at":\n            datetime.now(timezone.utc).isoformat(),\n\n        "group":\n            "Group 6 - Other structured technical and investigation information",\n\n        "stage":\n            "PDF-only structured extraction",\n\n        "input_accepted_fields":\n            len(accepted),\n\n        "structured_technical_count":\n            len(registry),\n\n        "technical_value_count":\n            len(values),\n\n        "extraction_failure_count":\n            len(failures),\n\n        "reports_with_structured_technical_fields":\n            len(reports),\n\n        "cases_with_structured_technical_fields":\n            len(cases),\n\n        "family_counts":\n            dict(family_counts),\n\n        "value_parse_status_counts":\n            dict(parse_status_counts),\n\n        "numeric_value_count":\n            parse_status_counts.get(\n                "numeric_scalar",\n                0,\n            ),\n\n        "missing_or_unavailable_count":\n            parse_status_counts.get(\n                "missing_or_unavailable",\n                0,\n            ),\n\n        "textual_or_identifier_count":\n            parse_status_counts.get(\n                "textual_or_identifier",\n                0,\n            ),\n\n        "validation_checks":\n            len(checks),\n\n        "hard_validation_failures":\n            hard_failures,\n\n        "warning_validation_failures":\n            warning_failures,\n\n        "scope":\n            (\n                "Structured extraction of the fully resolved Group 6 "\n                "PDF-only population. One accepted PDF source observation "\n                "is preserved as one structured technical/readout record. "\n                "PDF page, line number, source line, raw label, raw value, "\n                "family, report/case provenance, and source path are retained. "\n                "Numeric parsing is conservative. Identifiers and textual "\n                "technical values remain raw. No OCR, semantic normalization, "\n                "unit conversion, fuzzy inference, or source mutation is performed."\n            ),\n    }\n\n    (out / "metadata.json").write_text(\n        json.dumps(\n            metadata,\n            indent=2,\n            ensure_ascii=False,\n        ),\n        encoding="utf-8",\n    )\n\n    print()\n    print(\n        json.dumps(\n            metadata,\n            indent=2,\n            ensure_ascii=False,\n        )\n    )\n\n    print()\n    print(f"Outputs: {out}")\n\n    if hard_failures:\n        print()\n        print(\n            "GROUP 6 PDF STRUCTURED EXTRACTION HAS HARD VALIDATION FAILURES."\n        )\n        raise SystemExit(1)\n\n    print()\n    print("GROUP 6 PDF STRUCTURED EXTRACTION COMPLETE.")\n\n\n'

_CSV_DISCOVERY = _make_ns(
    "csv_discovery",
    _CSV_DISCOVERY_SOURCE,
)
_CSV_AUDIT = _make_ns(
    "csv_audit",
    _CSV_AUDIT_SOURCE,
)
_CSV_EXTRACT = _make_ns(
    "csv_extract",
    _CSV_EXTRACT_SOURCE,
)
_PDF_AUDIT = _make_ns(
    "pdf_audit",
    _PDF_AUDIT_SOURCE,
)
_PDF_RESOLVE = _make_ns(
    "pdf_resolve",
    _PDF_RESOLVE_SOURCE,
)
_PDF_EXTRACT = _make_ns(
    "pdf_extract",
    _PDF_EXTRACT_SOURCE,
)

def _identity(
    identity: dict[str, Any],
) -> dict[str, str]:
    return {
        "report_id":
            str(identity.get("report_id", "") or ""),
        "case_id":
            str(identity.get("case_id", "") or ""),
        "vehicle_number":
            str(identity.get("vehicle_number", "") or ""),
        "export_basename":
            str(identity.get("export_basename", "") or ""),
    }


def select_group6_source(
    csv_path=None,
    pdf_path=None,
):
    csv_path = (
        Path(csv_path)
        if csv_path
        else None
    )
    pdf_path = (
        Path(pdf_path)
        if pdf_path
        else None
    )

    if csv_path and csv_path.is_file():
        return "csv", csv_path

    if pdf_path and pdf_path.is_file():
        return "pdf", pdf_path

    raise FileNotFoundError(
        "No usable CSV or PDF source was found."
    )


def _build_csv_structured(
    accepted: list[dict],
):
    registry = []
    values = []
    review = []
    issues = []

    norm = _CSV_EXTRACT["norm"]
    stable_id = _CSV_EXTRACT["stable_id"]
    parse_numeric_scalar = (
        _CSV_EXTRACT["parse_numeric_scalar"]
    )
    raw_unit_from_label = (
        _CSV_EXTRACT["raw_unit_from_label"]
    )
    is_missing_like = (
        _CSV_EXTRACT["is_missing_like"]
    )

    for row in accepted:
        try:
            report_id = norm(
                row.get("report_id", "")
            )
            case_id = norm(
                row.get("case_id", "")
            )
            vehicle_number = norm(
                row.get("vehicle_number", "")
            )
            export_basename = norm(
                row.get("export_basename", "")
            )
            source_path = norm(
                row.get("source_path", "")
            )
            source_index = norm(
                row.get(
                    "source_record_index",
                    "",
                )
            )
            section = norm(
                row.get(
                    "source_section_heading",
                    "",
                )
            )
            raw_label = norm(
                row.get("field_label_raw", "")
            )
            raw_value = norm(
                row.get("field_value_raw", "")
            )
            family = norm(
                row.get("audited_family", "")
            )

            if not raw_label:
                raise ValueError(
                    "blank field_label_raw"
                )

            if not family:
                raise ValueError(
                    "blank audited_family"
                )

            source_candidate_id = norm(
                row.get(
                    "group6_candidate_id",
                    "",
                )
            )

            technical_id = (
                "g6csv_"
                + stable_id(
                    report_id,
                    case_id,
                    vehicle_number,
                    export_basename,
                    source_path,
                    source_index,
                    raw_label,
                    raw_value,
                    family,
                )
            )

            (
                numeric_value,
                value_unit,
                parse_status,
            ) = parse_numeric_scalar(
                raw_value
            )

            label_unit = (
                raw_unit_from_label(
                    raw_label
                )
            )
            raw_unit = (
                value_unit
                or label_unit
            )

            reg = {
                "group6_technical_id":
                    technical_id,
                "source_candidate_id":
                    source_candidate_id,
                "report_id":
                    report_id,
                "case_id":
                    case_id,
                "vehicle_number":
                    vehicle_number,
                "export_basename":
                    export_basename,
                "source_format":
                    "csv",
                "source_path":
                    source_path,
                "source_record_index":
                    source_index,
                "source_section_heading":
                    section,
                "family":
                    family,
                "field_label_raw":
                    raw_label,
                "field_value_raw":
                    raw_value,
                "raw_unit":
                    raw_unit,
                "semantic_normalization_status":
                    "not_normalized",
                "unit_conversion_status":
                    "not_converted",
            }

            val = {
                "group6_technical_id":
                    technical_id,
                "field_value_raw":
                    raw_value,
                "numeric_value":
                    (
                        ""
                        if numeric_value is None
                        else repr(numeric_value)
                    ),
                "raw_unit":
                    raw_unit,
                "value_parse_status":
                    parse_status,
                "missing_or_unavailable":
                    (
                        "true"
                        if is_missing_like(
                            raw_value
                        )
                        else "false"
                    ),
            }

            registry.append(reg)
            values.append(val)

            if (
                parse_status
                == "textual_or_identifier"
            ):
                review.append({
                    "group6_technical_id":
                        technical_id,
                    "report_id":
                        report_id,
                    "case_id":
                        case_id,
                    "vehicle_number":
                        vehicle_number,
                    "family":
                        family,
                    "field_label_raw":
                        raw_label,
                    "field_value_raw":
                        raw_value,
                    "review_reason":
                        "textual_or_identifier_value_preserved_raw",
                })

        except Exception as exc:
            issues.append(
                f"{row.get('report_id','')} | "
                f"{row.get('field_label_raw','')} | "
                f"{type(exc).__name__}: {exc}"
            )

    return (
        registry,
        values,
        review,
        issues,
    )


def extract_group6_csv(
    path,
    identity,
):
    path = Path(path)
    base = _identity(identity)

    rows = _CSV_DISCOVERY[
        "read_raw_csv"
    ](path)

    current_section = ""
    candidates = []
    excluded = []
    discovery_review = []

    for row_index, row in rows:
        if _CSV_DISCOVERY[
            "is_heading_row"
        ](row):
            current_section = (
                _CSV_DISCOVERY[
                    "populated"
                ](row)[0]
            )
            continue

        parsed = _CSV_DISCOVERY[
            "parse_scalar_observation"
        ](row)

        if parsed is None:
            continue

        label = parsed["label"]
        value = parsed["value"]

        result = _CSV_DISCOVERY[
            "score_field"
        ](
            label,
            value,
            current_section,
        )

        decision = result["decision"]

        if decision == "not_group6":
            continue

        candidate_id = (
            "g6csv_"
            + _CSV_DISCOVERY[
                "stable_id"
            ](
                base["report_id"],
                row_index,
                label,
                value,
            )
        )

        observation = {
            **base,
            "group6_candidate_id":
                candidate_id,
            "source_format":
                "csv",
            "source_path":
                str(path),
            "source_record_index":
                row_index,
            "source_section_heading":
                current_section,
            "field_label_raw":
                label,
            "field_value_raw":
                value,
            "value_column_index":
                parsed["value_index"],
            "populated_cell_count":
                parsed[
                    "populated_cell_count"
                ],
            "source_row_json":
                json.dumps(
                    row,
                    ensure_ascii=False,
                ),
            "candidate_family":
                result["family"],
            "candidate_score":
                result["score"],
            "discovery_decision":
                decision,
            "evidence_json":
                json.dumps(
                    result["evidence"],
                    ensure_ascii=False,
                ),
            "overlap_exclusions_json":
                json.dumps(
                    result["exclusions"],
                    ensure_ascii=False,
                ),
            "semantic_normalization_status":
                "not_normalized",
            "unit_conversion_status":
                "not_converted",
        }

        if decision == "candidate":
            candidates.append(
                observation
            )
        elif decision == "review":
            discovery_review.append(
                observation
            )
        elif decision == "excluded_overlap":
            excluded.append(
                observation
            )

    accepted = []
    unresolved = list(
        discovery_review
    )

    for row in candidates:
        (
            decision,
            family,
            route,
            reason,
        ) = _CSV_AUDIT[
            "audit_candidate"
        ](row)

        audited = {
            **row,
            "audited_family":
                family,
            "audit_decision":
                decision,
            "audit_route":
                route,
            "audit_reason":
                reason,
        }

        if decision == "accept":
            accepted.append(
                audited
            )
        elif decision == "exclude":
            excluded.append(
                audited
            )
        else:
            unresolved.append(
                audited
            )

    (
        registry,
        values,
        review,
        issues,
    ) = _build_csv_structured(
        accepted
    )

    return Group6ExtractionResult(
        source_format="csv",
        source_path=str(path),
        technical_registry=registry,
        technical_values=values,
        review_evidence=review,
        excluded=excluded,
        unresolved=unresolved,
        issues=issues,
    )


def _build_pdf_structured(
    accepted: list[dict],
):
    registry = []
    values = []
    review = []
    issues = []

    norm = _PDF_EXTRACT["norm"]
    stable_id = _PDF_EXTRACT["stable_id"]
    parse_numeric_scalar = (
        _PDF_EXTRACT[
            "parse_numeric_scalar"
        ]
    )
    raw_unit_from_label = (
        _PDF_EXTRACT[
            "raw_unit_from_label"
        ]
    )
    is_missing_like = (
        _PDF_EXTRACT[
            "is_missing_like"
        ]
    )

    for row in accepted:
        try:
            report_id = norm(
                row.get("report_id", "")
            )
            case_id = norm(
                row.get("case_id", "")
            )
            vehicle_number = norm(
                row.get("vehicle_number", "")
            )
            export_basename = norm(
                row.get("export_basename", "")
            )
            source_path = norm(
                row.get("source_path", "")
            )
            page = norm(
                row.get("pdf_page", "")
            )
            line_no = norm(
                row.get(
                    "pdf_line_number",
                    "",
                )
            )
            source_line = norm(
                row.get(
                    "source_line_raw",
                    "",
                )
            )
            raw_label = norm(
                row.get("field_label_raw", "")
            )
            raw_value = norm(
                row.get("field_value_raw", "")
            )
            family = norm(
                row.get("audited_family", "")
            )

            if not raw_label:
                raise ValueError(
                    "blank field_label_raw"
                )

            if not family:
                raise ValueError(
                    "blank audited_family"
                )

            source_candidate_id = norm(
                row.get(
                    "group6_candidate_id",
                    "",
                )
            )

            technical_id = (
                "g6pdf_"
                + stable_id(
                    report_id,
                    case_id,
                    vehicle_number,
                    export_basename,
                    source_path,
                    page,
                    line_no,
                    raw_label,
                    raw_value,
                    family,
                )
            )

            (
                numeric_value,
                value_unit,
                parse_status,
            ) = parse_numeric_scalar(
                raw_value
            )

            label_unit = (
                raw_unit_from_label(
                    raw_label
                )
            )
            raw_unit = (
                value_unit
                or label_unit
            )

            reg = {
                "group6_technical_id":
                    technical_id,
                "source_candidate_id":
                    source_candidate_id,
                "report_id":
                    report_id,
                "case_id":
                    case_id,
                "vehicle_number":
                    vehicle_number,
                "export_basename":
                    export_basename,
                "source_format":
                    "pdf",
                "source_path":
                    source_path,
                "pdf_page":
                    page,
                "pdf_line_number":
                    line_no,
                "source_line_raw":
                    source_line,
                "family":
                    family,
                "field_label_raw":
                    raw_label,
                "field_value_raw":
                    raw_value,
                "raw_unit":
                    raw_unit,
                "semantic_normalization_status":
                    "not_normalized",
                "unit_conversion_status":
                    "not_converted",
            }

            val = {
                "group6_technical_id":
                    technical_id,
                "field_value_raw":
                    raw_value,
                "numeric_value":
                    (
                        ""
                        if numeric_value is None
                        else repr(numeric_value)
                    ),
                "raw_unit":
                    raw_unit,
                "value_parse_status":
                    parse_status,
                "missing_or_unavailable":
                    (
                        "true"
                        if is_missing_like(
                            raw_value
                        )
                        else "false"
                    ),
            }

            registry.append(reg)
            values.append(val)

            if (
                parse_status
                == "textual_or_identifier"
            ):
                review.append({
                    "group6_technical_id":
                        technical_id,
                    "report_id":
                        report_id,
                    "case_id":
                        case_id,
                    "vehicle_number":
                        vehicle_number,
                    "pdf_page":
                        page,
                    "pdf_line_number":
                        line_no,
                    "family":
                        family,
                    "field_label_raw":
                        raw_label,
                    "field_value_raw":
                        raw_value,
                    "review_reason":
                        "textual_or_identifier_value_preserved_raw",
                })

        except Exception as exc:
            issues.append(
                f"{row.get('report_id','')} | "
                f"{row.get('field_label_raw','')} | "
                f"{type(exc).__name__}: {exc}"
            )

    return (
        registry,
        values,
        review,
        issues,
    )


def extract_group6_pdf(
    path,
    identity,
):
    path = Path(path)
    base = _identity(identity)

    accepted = []
    excluded = []
    review_rows = []
    unresolved = []

    pdfplumber = _PDF_AUDIT[
        "pdfplumber"
    ]

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(
            pdf.pages,
            start=1,
        ):
            text = (
                page.extract_text()
                or ""
            )

            for line_no, raw_line in enumerate(
                text.splitlines(),
                start=1,
            ):
                line = _PDF_AUDIT[
                    "norm"
                ](raw_line)

                if not line:
                    continue

                parsed = _PDF_AUDIT[
                    "parse_accepted"
                ](line)

                if parsed is not None:
                    (
                        family,
                        label,
                        value,
                    ) = parsed

                    candidate_id = (
                        "g6pdf_"
                        + _PDF_AUDIT[
                            "stable_id"
                        ](
                            base["report_id"],
                            page_no,
                            line_no,
                            label,
                            value,
                        )
                    )

                    accepted.append({
                        **base,
                        "group6_candidate_id":
                            candidate_id,
                        "source_format":
                            "pdf",
                        "source_path":
                            str(path),
                        "pdf_page":
                            page_no,
                        "pdf_line_number":
                            line_no,
                        "source_line_raw":
                            line,
                        "field_label_raw":
                            label,
                        "field_value_raw":
                            value,
                        "audited_family":
                            family,
                        "audit_decision":
                            "accept",
                        "audit_reason":
                            "exact_anchored_pdf_field_pattern",
                        "semantic_normalization_status":
                            "not_normalized",
                        "unit_conversion_status":
                            "not_converted",
                    })
                    continue

                if not _PDF_AUDIT[
                    "KEYWORD_RE"
                ].search(line):
                    continue

                reason = _PDF_AUDIT[
                    "exclusion_reason"
                ](line)

                evidence = {
                    **base,
                    "source_format":
                        "pdf",
                    "source_path":
                        str(path),
                    "pdf_page":
                        page_no,
                    "pdf_line_number":
                        line_no,
                    "source_line_raw":
                        line,
                }

                if reason:
                    excluded.append({
                        **evidence,
                        "audit_decision":
                            "exclude",
                        "audit_reason":
                            reason,
                    })
                else:
                    review_rows.append({
                        **evidence,
                        "audit_decision":
                            "review",
                        "audit_reason":
                            "group6_keyword_but_no_exact_accepted_pattern",
                    })

    for row in review_rows:
        result = _PDF_RESOLVE[
            "resolve_review"
        ](row)

        if (
            result["resolution"]
            == "accept"
        ):
            candidate_id = (
                "g6pdf_"
                + _PDF_RESOLVE[
                    "stable_id"
                ](
                    row.get(
                        "report_id",
                        "",
                    ),
                    row.get(
                        "pdf_page",
                        "",
                    ),
                    row.get(
                        "pdf_line_number",
                        "",
                    ),
                    result["label"],
                    result["value"],
                )
            )

            accepted.append({
                "report_id":
                    row.get(
                        "report_id",
                        "",
                    ),
                "case_id":
                    row.get(
                        "case_id",
                        "",
                    ),
                "vehicle_number":
                    row.get(
                        "vehicle_number",
                        "",
                    ),
                "export_basename":
                    row.get(
                        "export_basename",
                        "",
                    ),
                "group6_candidate_id":
                    candidate_id,
                "source_format":
                    "pdf",
                "source_path":
                    row.get(
                        "source_path",
                        "",
                    ),
                "pdf_page":
                    row.get(
                        "pdf_page",
                        "",
                    ),
                "pdf_line_number":
                    row.get(
                        "pdf_line_number",
                        "",
                    ),
                "source_line_raw":
                    row.get(
                        "source_line_raw",
                        "",
                    ),
                "field_label_raw":
                    result["label"],
                "field_value_raw":
                    result["value"],
                "audited_family":
                    result["family"],
                "audit_decision":
                    "accept",
                "audit_reason":
                    result["reason"],
                "semantic_normalization_status":
                    "not_normalized",
                "unit_conversion_status":
                    "not_converted",
            })

        elif (
            result["resolution"]
            == "exclude"
        ):
            excluded.append({
                **row,
                "audit_decision":
                    "exclude",
                "audit_route":
                    result["route"],
                "audit_reason":
                    result["reason"],
            })

        else:
            unresolved.append(
                row
            )

    (
        registry,
        values,
        review,
        issues,
    ) = _build_pdf_structured(
        accepted
    )

    return Group6ExtractionResult(
        source_format="pdf",
        source_path=str(path),
        technical_registry=registry,
        technical_values=values,
        review_evidence=review,
        excluded=excluded,
        unresolved=unresolved,
        issues=issues,
    )


def extract_group6_report(
    *,
    identity,
    csv_path=None,
    pdf_path=None,
):
    (
        source_format,
        source_path,
    ) = select_group6_source(
        csv_path=csv_path,
        pdf_path=pdf_path,
    )

    if source_format == "csv":
        return extract_group6_csv(
            source_path,
            identity,
        )

    return extract_group6_pdf(
        source_path,
        identity,
    )
