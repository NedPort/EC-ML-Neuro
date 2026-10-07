"""Extract source-preserving EDR observations. Semantic harmonization is deferred."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from build_edr_collection_discovery import load_rows, identity, clean
from build_edr_table_layout_audit import inspect_report, coordinate, numeric_text

BASE=['report_id','case_id','vehicle_number','csv_path','source_sha256','reported_event_label','section_id','source_heading','table_id']
OBS=BASE+['source_record','source_column','sample_index','field_label_raw','value_raw','value_numeric','value_status','unit_source_text','time_raw','time_native','time_unit','time_reference_status','review_flags']
SCALAR=BASE+['source_record','source_column','field_label_raw','value_raw','value_numeric','value_status','unit_source_text','review_flags']
REVIEW=BASE+['source_record','source_column','value_raw','reason']
REPORT=['report_id','case_id','vehicle_number','csv_path','source_sha256','source_record_count','device_type_raw','events_recovered_raw','parse_warning_count','status']
SECTION=BASE+['section_start_record','section_end_record','layout','status']
AUDIT=['report_id','source_nonempty_cells','classified_nonempty_cells','review_nonempty_cells','excluded_encoded_cells','unaccounted_nonempty_cells','status']


def unit_label(label):
    # Source text only; a candidate, never an inferred physical unit.
    parts=re.findall(r'\(([^()]*)\)|\[([^\[\]]*)\]',label)
    return '|'.join(a or b for a,b in parts if re.search(r'km/h|mph|msec|\bms\b|sec|\bg\b|%|percent|rpm|deg|m/sec|n-m|nm|kpa|mpa|psi|lb-ft',a or b,re.I))


def value_fields(raw):
    value=raw.strip();number=numeric_text(value)
    states={'':'blank','n/a':'not_available','sna':'source_sna','invalid':'invalid','data not available':'not_available','contains no recorded data':'no_recorded_data'}
    state=states.get(value.casefold(),'numeric' if number is not None else 'text')
    return {'value_raw':raw,'value_numeric':number if number is not None else '', 'value_status':state}


def extract_report(path):
    rows,encoding,delimiter,method,digest,warnings=load_rows(path)
    audited,variables,_=inspect_report(path)
    ident=identity(path)
    rid='report_'+hashlib.sha256((ident['case_id']+'|'+ident['vehicle_number']+'|'+path.name+'|'+digest).encode()).hexdigest()[:24]
    base={**ident,'report_id':rid,'source_sha256':digest}
    output={name:[] for name in ['reports','sections','scalars','event_summaries','timeseries','ordered_measurements','review','coverage']}
    used=set();classified=set();reviewed=set();excluded=set()
    def mark(ri,ci,destination):
        used.add((ri,ci))
        if ci<len(rows[ri]) and rows[ri][ci]!='':destination.add((ri,ci))
    def context(a):
        return {**base,'reported_event_label':a.get('reported_event_label',''),
                'section_id':rid+'-S'+str(a['section_start_record']),
                'source_heading':a['heading'],'table_id':rid+'-T'+str(a['header_record']) if a.get('header_record') else ''}
    sections={}
    for a in audited:sections.setdefault((a['section_start_record'],a['section_end_record']),[]).append(a)
    for (start,end),audits in sections.items():
        first=audits[0];ctx=context(first)
        output['sections'].append({**ctx,'section_start_record':start,'section_end_record':end,'layout':'|'.join(dict.fromkeys(a['layout'] for a in audits)),'status':'source_structure_provisional'})
        # Section heading is structural; leave introductory content for review.
        if first['heading']!='UNASSIGNED_CONTENT':
            for ci in range(len(rows[start-1])):mark(start-1,ci,classified)
        for a in audits:
            if not a.get('table_id'):continue
            ctx=context(a);hi=int(a['header_record'])-1
            last=int(a['last_data_record']) if a['last_data_record'] else hi+1
            header=rows[hi];trimmed=clean(header)
            flags=a['review_flags'];layout=a['layout']
            body_start=hi+2 if 'separate_units_row' in flags else hi+1
            if any(flag in flags for flag in ['row_width_mismatch','multiple_time_columns_keep_separate']):
                for ri in range(hi,last):
                    for ci,raw in enumerate(rows[ri]):
                        if raw!='':output['review'].append({**ctx,'source_record':ri+1,'source_column':ci+1,'value_raw':raw,'reason':'table_requires_review:'+flags});mark(ri,ci,reviewed)
                continue
            for ri in range(hi,body_start):
                for ci in range(len(rows[ri])):mark(ri,ci,classified)
            if layout=='time_across_columns':
                for ri in range(body_start,last):
                    label=rows[ri][0] if rows[ri] else ''
                    mark(ri,0,classified)
                    for ci in range(1,len(trimmed)):
                        raw=rows[ri][ci] if ci<len(rows[ri]) else ''
                        traw=header[ci];t=coordinate(traw)
                        output['timeseries'].append({**ctx,'source_record':ri+1,'source_column':ci+1,'sample_index':ci,
                            'field_label_raw':label,**value_fields(raw),'unit_source_text':unit_label(label),
                            'time_raw':traw,'time_native':t if t is not None else '', 'time_unit':a['time_unit'],
                            'time_reference_status':'source_clock_not_aligned','review_flags':flags})
                        mark(ri,ci,classified)
            else:
                # Sampling coordinate is identified by exact header label.
                ti=trimmed.index(a['time_label'])
                is_summary=a['category']=='summary' or 'Events Recorded' in trimmed
                units=rows[hi+1] if 'separate_units_row' in flags else []
                no_clock='no_numeric_relative_time' in flags
                for sample,ri in enumerate(range(body_start,last),1):
                    traw=rows[ri][ti] if ti<len(rows[ri]) else '';t=coordinate(traw)
                    mark(ri,ti,classified)
                    for ci,label in enumerate(header):
                        if ci==ti:continue
                        raw=rows[ri][ci] if ci<len(rows[ri]) else ''
                        if not label.strip():continue
                        if label.strip().casefold()=='buffer address':
                            mark(ri,ci,excluded);continue
                        name='event_summaries' if is_summary else ('ordered_measurements' if no_clock else 'timeseries')
                        output[name].append({**ctx,'source_record':ri+1,'source_column':ci+1,'sample_index':sample,
                            'field_label_raw':label,**value_fields(raw),
                            'unit_source_text':units[ci] if ci<len(units) else unit_label(label),
                            'time_raw':traw,'time_native':t if t is not None else '', 'time_unit':a['time_unit'],
                            'time_reference_status':'event_summary_relative_time' if is_summary else ('relative_time_unavailable' if no_clock else 'source_clock_not_aligned'),
                            'review_flags':flags})
                        mark(ri,ci,classified)
        ctx=context(first)
        for ri in range(start-1,end):
            if not rows[ri]:continue
            rr=clean(rows[ri])
            if len(rr)==2 and rows[ri][0].strip() and all((ri,ci) not in used for ci in range(len(rows[ri]))):
                # Unresolved two-column signal tables can look like scalar rows.
                # Numeric first cells are never treated as field names.
                if numeric_text(rr[0]) is None:
                    output['scalars'].append({**ctx,'table_id':'','source_record':ri+1,'source_column':2,
                        'field_label_raw':rows[ri][0],**value_fields(rows[ri][1]),
                        'unit_source_text':unit_label(rows[ri][0]),'review_flags':'key_value_candidate_source_label_only'})
                    for ci in range(len(rows[ri])):mark(ri,ci,classified)
            for ci,raw in enumerate(rows[ri]):
                if raw!='' and (ri,ci) not in used:
                    reason='explicit_no_recorded_data' if raw.strip().casefold()=='contains no recorded data' else 'unresolved_content_preserved'
                    output['review'].append({**ctx,'table_id':'','source_record':ri+1,'source_column':ci+1,'value_raw':raw,'reason':reason});mark(ri,ci,reviewed)
    nonempty={(ri,ci) for ri,row in enumerate(rows) for ci,raw in enumerate(row) if raw!=''}
    unaccounted=nonempty-(classified|reviewed|excluded)
    if unaccounted:raise RuntimeError(f'{len(unaccounted)} source cells unaccounted for')
    def field(label):return next((row[1] for row in rows if len(row)>=2 and row[0].strip().casefold()==label.casefold()),'')
    output['reports'].append({**base,'source_record_count':len(rows),'device_type_raw':field('EDR Device Type'),'events_recovered_raw':field('Event(s) recovered'),'parse_warning_count':len(warnings),'status':'extracted_source_structure_not_semantically_validated'})
    output['coverage'].append({'report_id':rid,'source_nonempty_cells':len(nonempty),'classified_nonempty_cells':len(classified),'review_nonempty_cells':len(reviewed),'excluded_encoded_cells':len(excluded),'unaccounted_nonempty_cells':0,'status':'cell_accounting_passed_not_semantic_validation'})
    return output,warnings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',default='data/temp')
    parser.add_argument('--output-directory',default='data/processed/edr/csv_extraction_v1')
    parser.add_argument('--limit',type=int,default=None,help='Optional number of CSV reports, for a small test run')
    args=parser.parse_args();root=Path(args.data_root);out=Path(args.output_directory)
    if not root.is_dir():parser.error(f'Missing source directory: {root}')
    if args.limit is not None and args.limit<1:parser.error('--limit must be positive')
    out.mkdir(parents=True,exist_ok=True)
    paths=sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower()=='.csv' and any(a.name.casefold()=='cdr_exports' for a in p.parents))
    selected=paths[:args.limit] if args.limit else paths
    schemas={'reports':REPORT,'sections':SECTION,'scalars':SCALAR,'event_summaries':OBS,'timeseries':OBS,'ordered_measurements':OBS,'review':REVIEW,'coverage':AUDIT}
    counts=Counter();errors=[];warnings=[];successful=0
    with ExitStack() as stack:
        writers={}
        for name,schema in schemas.items():
            f=stack.enter_context((out/(name+'.csv.part')).open('w',newline='',encoding='utf-8-sig'))
            writers[name]=csv.DictWriter(f,fieldnames=schema);writers[name].writeheader()
        for i,path in enumerate(selected,1):
            try:
                extracted,w=extract_report(path)
                for name,records in extracted.items():writers[name].writerows(records);counts[name]+=len(records)
                warnings.extend({**identity(path),**x} for x in w);successful+=1
            except Exception as exc:errors.append({**identity(path),'error_type':type(exc).__name__,'error_message':str(exc)})
            if i%100==0:print(f'Extracted {i}/{len(selected)} CSV reports...')
    for name in schemas:(out/(name+'.csv.part')).replace(out/(name+'.csv'))
    for name,records,schema in [('errors',errors,['case_id','vehicle_number','csv_path','error_type','error_message']),('parse_warnings',warnings,['case_id','vehicle_number','csv_path','source_physical_line','warning_type','original_field_text','action'])]:
        with (out/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=schema);w.writeheader();w.writerows(records)
    meta={'created_at':datetime.now(timezone.utc).isoformat(),'csv_found':len(paths),'csv_selected':len(selected),'csv_extracted':successful,'csv_failed':len(errors),'output_rows':dict(counts),'scope':'Source-preserving CSV extraction candidates. No semantic harmonization, unit conversion, resampling, CISS event linkage or PDF processing. Cell accounting is not extraction-accuracy validation.'}
    temp=out/'metadata.json.part';temp.write_text(json.dumps(meta,indent=2),encoding='utf-8');temp.replace(out/'metadata.json')
    print(json.dumps(meta,indent=2));print(f'Outputs: {out}')


if __name__=='__main__':main()
