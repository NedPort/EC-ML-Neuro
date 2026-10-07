"""Audit section/table structures across exported EDR CSVs, without harmonizing values."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from build_edr_collection_discovery import load_rows, clean, identity, is_heading, write_csv


def numeric_text(value):
    value = value.strip()
    value = re.sub(r'^([+-])\s+(?=\d)', r'\1', value)
    try:
        result = float(value)
        return result if abs(result) != float('inf') and result == result else None
    except ValueError:
        return None


def coordinate(value):
    # Keep annotations in the audit. Only recognize observed trigger annotation.
    v = re.sub(r'\s*\(TRG\)\s*$', '', value, flags=re.I)
    return numeric_text(v)


def time_header(label):
    return bool(re.fullmatch(r'(?:times?|time\s*stamp|elapsed time|relative time(?:\s*\(calc\.\))?)\s*(?:\([^)]*\)|\[[^]]*\])?', label.strip(), re.I))


def time_unit(label, unit_row=''):
    text = label + ' ' + unit_row
    if re.search(r'\b(ms|msec|milliseconds?)\b', text, re.I): return 'ms'
    if re.search(r'\b(s|sec|seconds?)\b', text, re.I): return 's'
    return 'unspecified'


def classify(heading):
    h = heading.upper()
    if 'PCM EDR DATA' in h: return 'pcm_measurements'
    if 'PRE-CRASH' in h or 'PRE_CRASH' in h: return 'precrash'
    if 'POST-CRASH' in h: return 'postcrash'
    if any(t in h for t in ['CRASH PULSE','VELOCITY CHANGE','ACCELERATION','ROLL RATE','ROLL ANGLE','DELTA-V','DELTA V','ROLLOVER SENSOR']): return 'crash_signal'
    if 'DIAGNOSTIC' in h or 'DTC' in h or 'FAULT' in h: return 'diagnostics'
    if 'SUMMARY' in h: return 'summary'
    return 'other'


def event_label(heading):
    match = re.search(r'\((.*)\)\s*$', heading)
    if not match: return ''
    value = re.sub(r'\s*-\s*TABLE\s+\d+\s+OF\s+\d+\s*$', '', match.group(1), flags=re.I)
    return value if re.search(r'\b(EVENT|RECORD|TRG)\b', value, re.I) else ''


def inspect_report(path):
    rows, encoding, delimiter, method, digest, warnings = load_rows(path)
    base = {**identity(path), 'source_sha256': digest}
    boundaries = [i for i,r in enumerate(rows) if is_heading(clean(r))]
    if not boundaries or boundaries[0] != 0: boundaries.insert(0,0)
    boundaries.append(len(rows))
    audits, variables = [], []
    for start,end in zip(boundaries,boundaries[1:]):
        heading = clean(rows[start])[0] if is_heading(clean(rows[start])) else 'UNASSIGNED_CONTENT'
        begin = start + 1 if heading != 'UNASSIGNED_CONTENT' else start
        category = classify(heading)
        common = {**base,'heading':heading,'reported_event_label':event_label(heading),'category':category,
                  'section_start_record':start+1,'section_end_record':end}
        content = [(i,clean(rows[i])) for i in range(begin,end) if clean(rows[i])]
        no_data = any('CONTAINS NO RECORDED DATA' in ' '.join(r).upper() for _,r in content)
        if no_data or not content:
            audits.append({**common,'layout':'no_recorded_data' if no_data else 'empty_section',
                           'review_flags':'no_samples_emitted'})
            continue
        candidates=[]
        for i,r in content:
            if len(r)<2: continue
            # Time across columns, with observed numeric/annotated coordinates.
            if time_header(r[0]) and len(r)>=3 and sum(coordinate(v) is not None for v in r[1:])>=2:
                candidates.append((i,'time_across_columns',r,[0],None))
                continue
            tis=[ci for ci,v in enumerate(r) if time_header(v)]
            if not tis: continue
            next_rows=[clean(rows[j]) for j in range(i+1,min(end,i+5)) if clean(rows[j])]
            is_pcm = 'PCM EDR DATA' in heading.upper() and r[0]=='Buffer Address'
            if is_pcm or any(any(ci<len(rr) and coordinate(rr[ci]) is not None for ci in tis) for rr in next_rows):
                candidates.append((i,'time_down_rows',r,tis,i+1 if is_pcm else None))
        if not candidates:
            audits.append({**common,'layout':'scalar_or_unrecognized_table',
                'content_record_count':len(content),
                'review_flags':'table_structure_not_resolved' if category in {'precrash','postcrash','crash_signal','pcm_measurements'} else 'scalar_or_table_review'})
            continue
        for pos,(hi,layout,header,tis,units_index) in enumerate(candidates):
            stop=candidates[pos+1][0] if pos+1<len(candidates) else end
            units=clean(rows[units_index]) if units_index is not None else []
            data_start=hi+2 if units_index is not None else hi+1
            body=[]
            for j in range(data_start,stop):
                rr=clean(rows[j])
                if not rr: break
                if layout=='time_down_rows' and units_index is None and not any(ci<len(rr) and coordinate(rr[ci]) is not None for ci in tis): break
                body.append((j,rr))
            raw_times=header[1:] if layout=='time_across_columns' else [rr[tis[0]] if tis[0]<len(rr) else '' for _,rr in body]
            times=[coordinate(v) for v in raw_times]
            known=[v for v in times if v is not None]
            flags=[]
            if len(tis)>1: flags.append('multiple_time_columns_keep_separate')
            if not known: flags.append('no_numeric_relative_time')
            if len(known)!=len(times): flags.append('missing_or_unrecognized_time_values')
            if any('(TRG)' in v.upper() for v in raw_times): flags.append('annotated_trigger_time_retained')
            if units_index is not None: flags.append('separate_units_row')
            if len(set(known))<len(known): flags.append('repeated_time_values')
            steps=[round(b-a,10) for a,b in zip(times,times[1:]) if a is not None and b is not None]
            if any(v<0 for v in steps): flags.append('nonmonotonic_time')
            if units_index is not None:
                mismatches=[j+1 for j,r in body if len(r)!=len(header)]
            else: mismatches=[j+1 for j,r in body if len(r)!=(len(header) if layout=='time_down_rows' else len(header))]
            if mismatches: flags.append('row_width_mismatch')
            tid=digest[:16]+f'-T{hi+1}'
            labels=header if layout=='time_down_rows' else [r[0] for _,r in body]
            signature=json.dumps({'layout':layout,'heading_category':category,'labels':labels,'unit_row':units},ensure_ascii=False,sort_keys=True)
            audits.append({**common,'table_id':tid,'layout':layout,'header_record':hi+1,
                'last_data_record':body[-1][0]+1 if body else '',
                'variable_count':len(header)-len(tis) if layout=='time_down_rows' else len(body),
                'sample_count':len(body) if layout=='time_down_rows' else len(raw_times),
                'content_record_count':len(body),'time_label':header[tis[0]],
                'time_unit':time_unit(header[tis[0]],units[tis[0]] if tis[0]<len(units) else ''),
                'numeric_time_count':len(known),'time_min_native':min(known) if known else '',
                'time_max_native':max(known) if known else '',
                'time_step_values_json':json.dumps(sorted(set(steps))),
                'time_reference_status':'not_aligned_across_tables',
                'time_values_raw_json':json.dumps(raw_times,ensure_ascii=False),
                'header_json':json.dumps(header,ensure_ascii=False),'unit_row_json':json.dumps(units),
                'width_mismatch_records_json':json.dumps(mismatches),
                'layout_signature':hashlib.sha256(signature.encode()).hexdigest()[:16],
                'review_flags':'|'.join(flags) or 'structure_candidate_review_required'})
            if layout=='time_down_rows':
                for ci,label in enumerate(header):
                    if ci in tis: continue
                    variables.append({**base,'table_id':tid,'heading':heading,'layout':layout,
                        'variable_label':label or f'unlabeled_column_{ci+1}',
                        'source_record':hi+1,'source_column':ci+1,
                        'separate_unit_or_code_definition':units[ci] if ci<len(units) else '',
                        'meaning_status':'source_label_only_not_harmonized'})
            else:
                for j,r in body:
                    variables.append({**base,'table_id':tid,'heading':heading,'layout':layout,
                        'variable_label':r[0],'source_record':j+1,'source_column':1,
                        'separate_unit_or_code_definition':'','meaning_status':'source_label_only_not_harmonized'})
    return audits,variables,warnings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',default='data/temp')
    parser.add_argument('--output-directory',default='data/processed/edr/table_layout_audit_v1')
    args=parser.parse_args()
    root,out=Path(args.data_root),Path(args.output_directory)
    if not root.is_dir():parser.error(f'Missing data root: {root}')
    out.mkdir(parents=True,exist_ok=True)
    paths=sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower()=='.csv' and any(a.name.casefold()=='cdr_exports' for a in p.parents))
    audits,variables,errors,warnings=[],[],[],[]
    for i,p in enumerate(paths,1):
        try:
            a,v,w=inspect_report(p);audits.extend(a);variables.extend(v)
            warnings.extend({**identity(p),**x} for x in w)
        except Exception as exc:errors.append({**identity(p),'error_type':type(exc).__name__,'error_message':str(exc)})
        if i%100==0:print(f'Audited {i}/{len(paths)} CSV reports...')
    common=['case_id','vehicle_number','csv_path','source_sha256']
    audit_fields=common+['heading','reported_event_label','category','section_start_record','section_end_record','table_id','layout','header_record','last_data_record','variable_count','sample_count','content_record_count','time_label','time_unit','numeric_time_count','time_min_native','time_max_native','time_step_values_json','time_reference_status','time_values_raw_json','header_json','unit_row_json','width_mismatch_records_json','layout_signature','review_flags']
    write_csv(out/'edr_table_layout_audit.csv',audits,audit_fields)
    write_csv(out/'edr_table_variables.csv',variables,common+['table_id','heading','layout','variable_label','source_record','source_column','separate_unit_or_code_definition','meaning_status'])
    write_csv(out/'edr_table_audit_errors.csv',errors,['case_id','vehicle_number','csv_path','error_type','error_message'])
    write_csv(out/'edr_table_parse_warnings.csv',warnings,['case_id','vehicle_number','csv_path','source_physical_line','warning_type','original_field_text','action'])
    groups={}
    for a in audits:
        if not a.get('layout_signature'):continue
        key=a['layout_signature']
        g=groups.setdefault(key,{'layout_signature':key,'layout':a['layout'],'category':a['category'],'table_count':0,'reports':set(),'representative_case_id':a['case_id'],'representative_vehicle_number':a['vehicle_number'],'representative_csv_path':a['csv_path'],'representative_header_record':a['header_record'],'header_json':a['header_json']})
        g['table_count']+=1;g['reports'].add(a['csv_path'])
    summaries=[]
    for g in groups.values():g['report_count']=len(g.pop('reports'));summaries.append(g)
    summaries.sort(key=lambda g:(-g['report_count'],g['layout_signature']))
    write_csv(out/'edr_table_layout_summary.csv',summaries,['layout_signature','layout','category','table_count','report_count','representative_case_id','representative_vehicle_number','representative_csv_path','representative_header_record','header_json'])
    meta={'created_at':datetime.now(timezone.utc).isoformat(),'csv_found':len(paths),'csv_audited':len(paths)-len(errors),'csv_failed':len(errors),'layout_counts':dict(Counter(a['layout'] for a in audits)),'distinct_layout_signatures':len(groups),'scope':'Structural audit; no PDF extraction, semantic mapping, unit conversion, or time alignment. Counts of layouts are occurrences, not unique events.'}
    temp=out/'metadata.json.part';temp.write_text(json.dumps(meta,indent=2),encoding='utf-8');temp.replace(out/'metadata.json')
    print(json.dumps(meta,indent=2));print(f'Outputs: {out}')


if __name__=='__main__':main()
