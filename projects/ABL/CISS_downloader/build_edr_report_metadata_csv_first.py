"""Build CSV-first Group 1 views from existing source-preserving v4 outputs.
No source documents are reparsed or changed. Python 3.10+, standard library only.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

IDENTITY = ['report_id', 'case_id', 'vehicle_number', 'export_basename']
FIELDS = ['vin_entered', 'user_entered', 'case_number_entered', 'imaging_date',
          'crash_date', 'source_filename', 'saved_on', 'imaging_cdr_version',
          'reporting_cdr_version', 'imaging_license_company',
          'reporting_license_company', 'edr_device_type', 'events_recovered_text',
          'acm_adapter_detected', 'restraint_deployment_signal_text']

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write(path, rows, columns):
    temporary = path.with_suffix(path.suffix + '.part')
    with temporary.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)

def choose(observations):
    """Blank/not-available CSV entries are evidence, not absent fields."""
    csv_rows = [r for r in observations if r['source_format'] == 'csv']
    pdf_rows = [r for r in observations if r['source_format'] == 'pdf']
    preferred = csv_rows or pdf_rows
    if not preferred:
        return None, 'absent', 'not_extracted'
    distinct = {(r['value_text'], r['value_status']) for r in preferred}
    if len(distinct) > 1:
        return None, preferred[0]['source_format'], 'multiple_source_values_requires_review'
    row = preferred[0]
    status = 'candidate_requires_review' if row.get('source_label_status') == 'absent_contextual_candidate' else 'selected'
    if row.get('extraction_method') == 'original_csv_intro_field' and row['value_raw'].lstrip().startswith('['):
        status = 'multivalue_requires_review'
    return row, row['source_format'], status

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-directory', type=Path, default=Path('data/processed/edr/group1_v4'))
    parser.add_argument('--output-directory', type=Path, default=Path('data/processed/edr/group1_csv_first_v1'))
    args = parser.parse_args()
    if args.input_directory.resolve() == args.output_directory.resolve():
        parser.error('Use a separate output directory to preserve the source tables.')
    metadata = read(args.input_directory / 'report_metadata_long.csv')
    comparisons = read(args.input_directory / 'field_comparison.csv')
    audits = read(args.input_directory / 'source_audit.csv')
    documentation = read(args.input_directory / 'report_documentation.csv')
    reports = {}
    for row in audits + comparisons + metadata:
        identity = {key: row[key] for key in IDENTITY}
        existing = reports.setdefault(row['report_id'], identity)
        if existing != identity:
            raise ValueError(f"Conflicting report identity: {row['report_id']}")
    grouped = defaultdict(list)
    for row in metadata:
        grouped[row['report_id'], row['field_name']].append(row)
    comparison_lookup = {(r['report_id'], r['field_name']): r['agreement_status'] for r in comparisons}
    audit_lookup = {(r['report_id'], r['source_format']): r for r in audits}
    fields = FIELDS + sorted({r['field_name'] for r in metadata} - set(FIELDS))
    wide, long, counts = [], [], Counter()
    for report_id, identity in sorted(reports.items()):
        flat = dict(identity)
        review_fields = 0
        for field in fields:
            observations = grouped[report_id, field]
            chosen, source, selection = choose(observations)
            agreement = comparison_lookup.get((report_id, field), 'not_compared')
            source_issue = audit_lookup.get((report_id, source), {}).get('issue', '')
            review = ('requires_review' in selection or agreement == 'source_difference_requires_review'
                      or bool(source_issue))
            review_fields += int(review)
            counts[f'{source}:{selection}'] += 1
            value = chosen['value_text'] if chosen else ''
            state = chosen['value_status'] if chosen else ('ambiguous' if observations else 'absent')
            flat[field] = value
            flat[field + '__source'] = source
            flat[field + '__status'] = state
            flat[field + '__review'] = review
            long.append({**identity, 'field_name': field, 'value_text': value,
                         'value_raw': chosen['value_raw'] if chosen else '',
                         'value_status': state, 'selected_source': source,
                         'selection_status': selection, 'agreement_status': agreement,
                         'requires_review': review, 'selected_source_issue': source_issue,
                         'selected_evidence_json': json.dumps(chosen, ensure_ascii=False) if chosen else '',
                         'all_source_evidence_json': json.dumps(observations, ensure_ascii=False)})
        flat['review_field_count'] = review_fields
        wide.append(flat)
    # Intro PDF documentation is retained independently of metadata preference.
    docs = [r for r in documentation if r['source_format'] == 'pdf'
            and r['documentation_category'] != 'file_information_source_text']
    for row in docs:
        row['text_quality_status'] = ('font_encoding_artifact_requires_review'
                                      if '(cid:' in row['text_raw'] else 'extracted_text_candidate')
    out = args.output_directory
    out.mkdir(parents=True, exist_ok=True)
    wide_columns = IDENTITY + [c for field in fields for c in
        [field, field + '__source', field + '__status', field + '__review']] + ['review_field_count']
    long_columns = IDENTITY + ['field_name', 'value_text', 'value_raw', 'value_status',
        'selected_source', 'selection_status', 'agreement_status', 'requires_review',
        'selected_source_issue', 'selected_evidence_json', 'all_source_evidence_json']
    doc_columns = list(documentation[0]) + ['text_quality_status'] if documentation else ['report_id', 'text_raw', 'text_quality_status']
    write(out / 'report_metadata.csv', wide, wide_columns)
    write(out / 'report_metadata_selected_long.csv', long, long_columns)
    write(out / 'report_documentation_pdf.csv', docs, doc_columns)
    summary = {'created_at': datetime.now(timezone.utc).isoformat(), 'reports': len(wide),
        'selected_field_rows': len(long), 'pdf_documentation_blocks': len(docs),
        'selection_counts': dict(counts), 'input_directory': str(args.input_directory),
        'rule': 'Prefer existing CSV field evidence, including blanks and explicit unavailable values. PDF fallback only when CSV field evidence is absent. Conflicting same-source values remain unselected. Preserve both sources and review flags.',
        'scope': 'Derived Group 1 candidate views; no event IDs, semantic event equivalence, date interpretation, OCR or measurement extraction. Source audit flags are conservatively propagated.'}
    temporary = out / 'metadata.json.part'
    temporary.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    temporary.replace(out / 'metadata.json')
    print(json.dumps(summary, indent=2))
    print(f'Outputs: {out}')

if __name__ == '__main__':
    main()
