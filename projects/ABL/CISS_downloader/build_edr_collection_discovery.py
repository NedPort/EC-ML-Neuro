"""Conservative CSV content discovery, not a validated semantic parser.
Run from CISS_downloader. Standard library only. Originals are read-only.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def write_csv(path, rows, fields):
    temporary = path.with_suffix(path.suffix + '.part')
    with temporary.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_rows(path):
    data = path.read_bytes()
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if '\x00' in text:
        raise ValueError('NUL bytes: inspect encoding or file type')
    try:
        delimiter = csv.Sniffer().sniff(text[:50000], delimiters=',\t;|').delimiter
        delimiter_method = 'sniffer'
    except csv.Error:
        # Ragged sectioned reports often defeat Sniffer. Use parsed records,
        # not raw character counts, so quoted delimiters do not dominate.
        scores = {}
        for candidate in (',', '\t', ';', '|'):
            parsed = csv.reader(io.StringIO(text, newline=''), delimiter=candidate)
            scores[candidate] = sum(len(r) > 1 for r in parsed)
        delimiter = max(scores, key=scores.get)
        delimiter_method = 'most_multicell_records_fallback_review'
    warnings = []
    try:
        rows = list(csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True))
    except csv.Error:
        if delimiter != ',':
            raise
        # Observed Bosch syntax: "OFF" (Brake not activated). Quote the
        # entire field while retaining its original literal content.
        pattern = re.compile(r'(?<=,)"([^"\r\n]*)"([ \t]+\([^"\r\n,]*\))(?=,|\r|\n|$)')
        def repair(match):
            line_number = len(re.findall(r'\r\n|\r|\n', text[:match.start()])) + 1
            warnings.append({'source_physical_line': line_number,
                             'warning_type': 'quoted_value_with_unquoted_parenthetical',
                             'original_field_text': match.group(0),
                             'action': 'quoted_entire_field_in_memory_original_text_retained'})
            return '"' + match.group(0).replace('"', '""') + '"'
        # Another observed Bosch scalar: "On" or "Blinking".
        # Retain the quotes and words as literal cell content.
        alternatives = re.compile(r'(?<=,)"[^"\r\n,]*"[ \t]+or[ \t]+"[^"\r\n,]*"(?=,|\r|\n|$)')
        matches = list(pattern.finditer(text)) + list(alternatives.finditer(text))
        repaired = text
        for match in sorted(matches, key=lambda m: m.start(), reverse=True):
            replacement = repair(match)
            warnings[-1]['warning_type'] = ('quoted_alternatives_outside_field' if ' or ' in match.group(0) else 'quoted_value_with_unquoted_parenthetical')
            repaired = repaired[:match.start()] + replacement + repaired[match.end():]
        warnings.reverse()
        if not warnings:
            raise
        rows = list(csv.reader(io.StringIO(repaired, newline=''), delimiter=delimiter, strict=True))
    return rows, encoding, delimiter, delimiter_method, hashlib.sha256(data).hexdigest(), warnings


def clean(row):
    row = [value.strip() for value in row]
    while row and not row[-1]:
        row.pop()
    return row


def identity(path):
    case_id = vehicle_number = ''
    for parent in path.parents:
        match = re.fullmatch(r'Vehicle\s+(\d+)', parent.name, flags=re.I)
        if match and not vehicle_number:
            vehicle_number = match.group(1)
        if parent.name.casefold() == 'extracted' and parent.parent.name.isdigit():
            case_id = parent.parent.name
    return {'case_id': case_id, 'vehicle_number': vehicle_number,
            'csv_path': str(path.resolve())}


def category(heading):
    h = re.sub(r'[_\s]+', ' ', heading.upper()).strip()
    if h.startswith('POST-CRASH') or h.startswith('POST CRASH'):
        return 'postcrash'
    if any(v in h for v in ('ACCELERATION', 'DELTA-V', 'ROLL ANGLE', 'ROLLOVER SENSOR', 'ANGULAR RATE')) and ('(' in h or 'CRASH' in h):
        return 'crash_signal'
    if h.startswith('EVENT DATA'):
        return 'event_data'
    if 'CONFIGURATION' in h:
        return 'configuration'
    if 'CRASH PULSE' in h:
        return 'crash_signal'
    if h.startswith('DELTA-V') or h.startswith('DELTA V'):
        return 'crash_signal'
    if h.startswith(('PRE-CRASH', 'PRE CRASH')):
        return 'precrash'
    if h.startswith('CDR FILE INFORMATION'):
        return 'report_information'
    if 'LIMITATION' in h:
        return 'limitations'
    if 'DEPLOYMENT' in h:
        return 'deployment'
    if 'DTC' in h or 'FAULT' in h:
        return 'diagnostics'
    if 'STATUS' in h or 'SUMMARY' in h:
        return 'status_or_summary'
    return 'unclassified'


def is_heading(row):
    cells = [v for v in row if v]
    if len(cells) != 1:
        return False
    text = cells[0]
    if text.upper() in {'CONTAINS NO RECORDED DATA', 'N/A', 'SNA', 'NO DATA'}:
        return False
    # Candidate headings remain provisional; preserve all cells separately.
    letters = re.sub('[^A-Za-z]', '', text)
    return len(letters) >= 5 and letters.upper() == letters


def unit_hint(label):
    # Label text only. No unit inference from section title or numeric values.
    patterns = [('km/h', r'km\s*/\s*h'), ('mph', r'\bmph\b'),
                ('ms', r'\b(?:ms|msec)\b'), ('s', r'\bsec(?:ond)?s?\b'),
                ('g', r'\(\s*g\s*\)'), ('%', r'%|percent'),
                ('deg/s', r'deg\s*/\s*s(?:ec)?'), ('deg', r'\bdeg(?:rees)?\b'),
                ('rpm', r'\brpm\b'), ('kPa', r'\bkpa\b')]
    return '|'.join(unit for unit, pattern in patterns if re.search(pattern, label, re.I))


def is_time_coordinate(label):
    value = label.strip()
    return bool(re.fullmatch(
        r"(?:time(?: stamp|stamp)?|elapsed time)\s*(?:\([^)]*\)|\[[^]]*\])?",
        value, re.I))


def number(value):
    try:
        result = float(value)
        return result if result == result and abs(result) != float('inf') else None
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', default='data/temp')
    parser.add_argument('--output-directory', default='data/processed/edr/discovery_v3')
    args = parser.parse_args()
    root, out = Path(args.data_root), Path(args.output_directory)
    if not root.is_dir():
        parser.error(f'Source directory does not exist: {root}')
    out.mkdir(parents=True, exist_ok=True)
    files, sections, fields, errors, parse_warnings = [], [], [], [], []
    cells_path = out / 'csv_cells_preserved.csv'
    cells_temp = cells_path.with_suffix('.csv.part')
    cell_fields = ['case_id', 'vehicle_number', 'csv_path', 'source_record_number',
                   'source_column_index', 'value_raw']
    csv_paths = sorted(p for p in root.rglob('*') if p.is_file()
                       and p.suffix.lower() == '.csv'
                       and any(a.name.casefold() == 'cdr_exports' for a in p.parents))
    with cells_temp.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=cell_fields)
        writer.writeheader()
        for index, path in enumerate(csv_paths, 1):
            base = identity(path)
            try:
                rows, encoding, delimiter, method, digest, warnings = load_rows(path)
                parse_warnings.extend({**base, **w} for w in warnings)
                for ri, row in enumerate(rows, 1):
                    for ci, value in enumerate(row, 1):
                        if value != '':
                            writer.writerow({**base, 'source_record_number': ri,
                                             'source_column_index': ci, 'value_raw': value})
                boundaries = [i for i, row in enumerate(rows) if is_heading(clean(row))]
                if not boundaries or boundaries[0] != 0:
                    boundaries.insert(0, 0)
                boundaries.append(len(rows))
                signatures = []
                for start, end in zip(boundaries, boundaries[1:]):
                    heading = clean(rows[start])[0] if rows and is_heading(clean(rows[start])) else 'UNASSIGNED_CONTENT'
                    content_start = start + 1 if heading != 'UNASSIGNED_CONTENT' else start
                    content = [(i, clean(rows[i])) for i in range(content_start, end) if clean(rows[i])]
                    cat = category(heading)
                    no_data = any('CONTAINS NO RECORDED DATA' in ' '.join(row).upper() for _, row in content)
                    section_id = f'{digest[:16]}-R{start + 1}'
                    sections.append({**base, 'section_id': section_id,
                        'heading_candidate': heading, 'category_candidate': cat,
                        'start_record': start + 1, 'end_record': end,
                        'availability_candidate': 'no_recorded_data' if no_data else ('content_present' if content else 'empty'),
                        'classification_status': 'provisional_review_required'})
                    signatures.append(cat)
                    # Recognize each timed header independently: repeated tables may
                    # have different sampling rates within the same section.
                    headers = []
                    for i, row in content:
                        # A time column must be a sampling coordinate, not a
                        # scalar such as deployment time or maximum-Delta-V time.
                        time_columns = [ci for ci, label in enumerate(row)
                                        if is_time_coordinate(label)]
                        if len(row) < 2 or not time_columns:
                            continue
                        following = [clean(rows[j]) for j in range(i + 1, min(i + 6, end))
                                     if clean(rows[j])]
                        if any(any(ci < len(r) and number(r[ci]) is not None
                                   for ci in time_columns) for r in following):
                            headers.append((i, row))
                    header_indices = {i for i, _ in headers}
                    for position, (hi, header) in enumerate(headers):
                        stop = headers[position + 1][0] if position + 1 < len(headers) else end
                        time_columns = [ci for ci, label in enumerate(header) if is_time_coordinate(label)]
                        body = []
                        for bi in range(hi + 1, stop):
                            candidate = clean(rows[bi])
                            if not candidate:
                                break
                            if not any(ci < len(candidate) and number(candidate[ci]) is not None for ci in time_columns):
                                break
                            body.append(candidate)
                        for ci, label in enumerate(header):
                            vals = [number(r[ci]) for r in body if ci < len(r)]
                            numeric = [v for v in vals if v is not None]
                            is_time = is_time_coordinate(label)
                            fields.append({**base, 'section_id': section_id,
                                'heading_candidate': heading, 'layout_candidate': 'timed_table',
                                'field_record': hi + 1, 'column_index': ci + 1,
                                'field_label': label or f'unlabeled_column_{ci + 1}',
                                'unit_hint': unit_hint(label), 'is_time_candidate': is_time,
                                'numeric_count': len(numeric),
                                'time_min_native': min(numeric) if numeric and is_time else '',
                                'time_max_native': max(numeric) if numeric and is_time else ''})
                    if not headers:
                        for ri, row in content:
                            if len(row) >= 2 and row[0] and number(row[0]) is None and row[0].upper() not in {'NO', 'YES', 'N/A', 'SNA', 'DATA NOT AVAILABLE', 'ON', 'OFF'}:
                                fields.append({**base, 'section_id': section_id,
                                    'heading_candidate': heading, 'layout_candidate': 'key_value_or_untimed_table_review',
                                    'field_record': ri + 1, 'column_index': 1,
                                    'field_label': row[0], 'unit_hint': unit_hint(row[0]),
                                    'is_time_candidate': False, 'numeric_count': '',
                                    'time_min_native': '', 'time_max_native': ''})
                family_key = '|'.join(dict.fromkeys(signatures))
                files.append({**base, 'encoding': encoding, 'delimiter': repr(delimiter),
                    'delimiter_method': method, 'sha256': digest, 'record_count': len(rows),
                    'section_candidate_count': len(boundaries) - 1,
                    'section_signature': family_key,
                    'stable_section_group': 'group_' + hashlib.sha256(family_key.encode()).hexdigest()[:12],
                    'parser_warning_count': len(warnings),
                    'events_recovered_raw': next((' | '.join(row[1:]).strip() for row in rows if row and row[0].strip().casefold() == 'event(s) recovered'), ''),
                    'status': 'scanned_not_semantically_validated'})
            except Exception as exc:
                errors.append({**base, 'error_type': type(exc).__name__, 'error_message': str(exc)})
            if index % 100 == 0:
                print(f'Scanned {index}/{len(csv_paths)} CSV reports...')
    cells_temp.replace(cells_path)
    base_fields = ['case_id', 'vehicle_number', 'csv_path']
    write_csv(out / 'csv_report_catalog.csv', files, base_fields + ['encoding', 'delimiter', 'delimiter_method', 'sha256', 'record_count', 'section_candidate_count', 'section_signature', 'stable_section_group', 'parser_warning_count', 'events_recovered_raw', 'status'])
    write_csv(out / 'csv_section_catalog.csv', sections, base_fields + ['section_id', 'heading_candidate', 'category_candidate', 'start_record', 'end_record', 'availability_candidate', 'classification_status'])
    write_csv(out / 'csv_field_catalog.csv', fields, base_fields + ['section_id', 'heading_candidate', 'layout_candidate', 'field_record', 'column_index', 'field_label', 'unit_hint', 'is_time_candidate', 'numeric_count', 'time_min_native', 'time_max_native'])
    write_csv(out / 'csv_parse_warnings.csv', parse_warnings, base_fields + ['source_physical_line', 'warning_type', 'original_field_text', 'action'])
    write_csv(out / 'csv_discovery_errors.csv', errors, base_fields + ['error_type', 'error_message'])
    pdfs = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() == '.pdf' and any(a.name.casefold() == 'cdr_exports' for a in p.parents))
    write_csv(out / 'pdf_review_queue.csv', [{**identity(p), 'csv_path': '', 'pdf_path': str(p.resolve()), 'review_status': 'contents_not_scanned'} for p in pdfs], base_fields + ['pdf_path', 'review_status'])
    metadata = {'created_at': datetime.now(timezone.utc).isoformat(), 'source_root': str(root.resolve()),
        'csv_found': len(csv_paths), 'csv_scanned': len(files), 'csv_failed': len(errors),
        'csv_reports_with_parse_warnings': sum(bool(f['parser_warning_count']) for f in files), 'parse_warning_count': len(parse_warnings),
        'pdf_review_queue': len(pdfs), 'section_candidates': len(sections), 'field_candidates': len(fields),
        'scope': 'CSV structural discovery only; PDF contents not extracted; categories and headers provisional',
        'category_counts': dict(Counter(s['category_candidate'] for s in sections))}
    temp = out / 'discovery_metadata.json.part'
    temp.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    temp.replace(out / 'discovery_metadata.json')
    print(json.dumps(metadata, indent=2))
    print(f'Outputs: {out}')


if __name__ == '__main__':
    main()
