"""First Group 2 candidate extraction. CSV first; conservative PDF evidence blocks."""
from __future__ import annotations
import argparse,csv,json,re,hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import pdfplumber
from build_edr_collection_discovery import load_rows
from build_edr_group2_discovery import is_target,classify,resolve,norm,HEX
BASE=['report_id','case_id','vehicle_number','export_basename']
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,cols):
 tmp=p.with_suffix(p.suffix+'.part')
 with tmp.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
 tmp.replace(p)
def identifier(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:24]
def state(v):
 t=norm(v).casefold()
 return 'blank' if not t else 'not_available' if t in ['n/a','na','sna','not available'] else 'present'
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--index',type=Path,default=Path('data/processed/edr/group1_v4/report_index.csv'))
 ap.add_argument('--metadata',type=Path,default=Path('data/processed/edr/group1_csv_first_v1/report_metadata.csv'))
 ap.add_argument('--source-root',type=Path,default=Path('data/temp'))
 ap.add_argument('--output-directory',type=Path,default=Path('data/processed/edr/group2_extract_v2'))
 ap.add_argument('--limit',type=int)
 args=ap.parse_args()
 if args.limit is not None and args.limit<1:ap.error('--limit must be positive')
 index=read(args.index);meta={r['report_id']:r for r in read(args.metadata)}
 if len({r['report_id'] for r in index})!=len(index):raise ValueError('Duplicate report IDs')
 sections=[];fields=[];tables=[];records={};coverage=[];errors=[]
 def emit(base,fmt,p,sha,heading,rows,location,warning=''):
  scope,label,label_status=classify(heading)
  sid='g2s_'+identifier(base['report_id'],fmt,location['source_record'],location['source_page'],heading)
  rid=''
  if scope=='reported_record_candidate':
   rid='g2r_'+identifier(base['report_id'],norm(label).upper())
   records.setdefault(rid,{**base,'record_candidate_id':rid,'record_label_raw':label,'identity_status':'source_label_candidate_not_validated_event','section_count':0})['section_count']+=1
  content='\n'.join(','.join(r) for r in rows)
  availability='no_recorded_data' if re.search(r'contains no recorded data',content,re.I) else 'empty' if not content.strip() else 'content_present'
  review=(fmt=='pdf' or scope!='reported_record_candidate' or bool(warning))
  sections.append({**base,'section_id':sid,'record_candidate_id':rid,'source_format':fmt,'source_path':str(p),'source_sha256':sha,**location,'source_heading':heading,'scope_candidate':scope,'event_label_candidate':label,'availability':availability,'requires_review':review,'issue':warning,'source_rows_json':json.dumps(rows,ensure_ascii=False)})
  # PDF evidence is retained as text; do not guess field/value column splits.
  if fmt=='pdf' or availability!='content_present':return
  useful=[(i,r) for i,r in enumerate(rows) if any(c.strip() for c in r)]
  is_summary='summary' in heading.lower()
  tabular=is_summary or scope=='pcm_buffer_scope_requires_review' or any(sum(bool(c.strip()) for c in r)>2 for _,r in useful)
  if tabular:
   header=useful[0][1] if useful else []
   for i,row in useful:
    tables.append({**base,'section_id':sid,'record_candidate_id':rid,'scope_candidate':scope,'source_record':location['source_record']+i+1,'row_role':'header_candidate' if i==useful[0][0] else 'data_candidate','source_header_json':json.dumps(header,ensure_ascii=False),'source_row_json':json.dumps(row,ensure_ascii=False),'requires_review':True})
  else:
   for i,row in useful:
    if len(row)<2:
     tables.append({**base,'section_id':sid,'record_candidate_id':rid,'scope_candidate':scope,'source_record':location['source_record']+i+1,'row_role':'unresolved_text','source_header_json':'[]','source_row_json':json.dumps(row,ensure_ascii=False),'requires_review':True});continue
    label_raw=row[0];value_raw=row[1]
    fields.append({**base,'section_id':sid,'record_candidate_id':rid,'scope_candidate':scope,'source_record':location['source_record']+i+1,'field_label_raw':label_raw,'value_raw':value_raw,'value_status':state(value_raw),'requires_review':review,'semantic_status':'unmapped_source_field'})
 for number,r in enumerate(index[:args.limit] if args.limit else index,1):
  base={k:r[k] for k in BASE};report_meta=meta.get(r['report_id'],{})
  audit={**base,'selected_source':'','status':'','section_count':0,'events_recovered_text':report_meta.get('events_recovered_text',''),'issue':''}
  before=len(sections)
  success=False
  for fmt in ['csv','pdf']:
   if success:break
   p=resolve(r.get(fmt+'_path',''),args.source_root)
   if not p:continue
   snapshot=(len(sections),len(fields),len(tables),{k:dict(v) for k,v in records.items()})
   try:
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    if fmt=='csv':
     rows,_,_,_,_,warnings=load_rows(p)
     headings=[]
     intro_end=next((i for i,row in enumerate(rows) if row and norm(row[0]).upper()=='DATA LIMITATIONS'),None)
     if intro_end is None:raise ValueError('Introduction boundary not found; inspect CSV before extraction')
     for i,row in enumerate(rows):
      if i<=intro_end:continue
      filled=[norm(c) for c in row if norm(c)]
      if len(filled)==1 and (is_target(filled[0]) or HEX.search(filled[0]) or (filled[0].isupper() and len(filled[0])>5)):
       headings.append((i,filled[0]))
     for j,(start,h) in enumerate(headings):
      if not is_target(h):continue
      end=headings[j+1][0] if j+1<len(headings) else len(rows)
      emit(base,fmt,p,sha,h,rows[start+1:end],{'source_record':start+1,'source_end_record':end,'source_page':'','source_bbox_json':''},f'csv_format_warnings:{len(warnings)}' if warnings else '')
    else:
     with pdfplumber.open(p) as pdf:
      for pi,page in enumerate(pdf.pages,1):
       lines=page.extract_text_lines(layout=False,strip=True)
       # Page-local evidence only. Continuations and table geometry need evaluation.
       for j,line in enumerate(lines):
        h=norm(line['text'])
        if not is_target(h):continue
        bottom=page.height-20
        for next_line in lines[j+1:]:
         text=norm(next_line['text'])
         if is_target(text) or HEX.search(text) or re.match(r'^(?:Pre[- ]crash|Deployment (?:Data|Command)|(?:Longitudinal|Lateral|Rollover).*Data|.*Crash Pulse|Disclaimer)',text,re.I):bottom=next_line['top'];break
         if re.search(r'Page\s+\d+\s+of\s+\d+',text,re.I):bottom=next_line['top'];break
        content=[[x['text']] for x in lines[j+1:] if x['top']<bottom]
        emit(base,fmt,p,sha,h,content,{'source_record':'','source_end_record':'','source_page':pi,'source_bbox_json':json.dumps([0,line['top'],page.width,bottom])},'pdf_page_local_block_requires_layout_and_continuation_review')
    audit['selected_source']=fmt;success=True
   except Exception as exc:
    ns,nf,nt,old_records=snapshot
    del sections[ns:];del fields[nf:];del tables[nt:]
    records.clear();records.update(old_records)
    errors.append({**base,'source_format':fmt,'source_path':str(p),'error':f'{type(exc).__name__}: {exc}'})
  audit['section_count']=len(sections)-before
  audit['status']='extracted_candidates' if audit['section_count'] else 'reported_none_no_target_sections' if success and norm(audit['events_recovered_text']).lower()=='none' else 'no_target_sections_requires_review' if success else 'failed_no_readable_source'
  coverage.append(audit)
  if number%25==0 or number==len(index[:args.limit] if args.limit else index):print(f'Extracted Group 2 for {number}/{len(index[:args.limit] if args.limit else index)} reports...',flush=True)
 out=args.output_directory;out.mkdir(parents=True,exist_ok=True)
 empty_reviews=[]
 for section in sections:
  if section['availability']=='empty':
   empty_reviews.append({k:section[k] for k in BASE+['section_id','source_format','source_path','source_heading','scope_candidate','source_record','source_end_record','source_page','source_rows_json']})
 write(out/'empty_section_review.csv',empty_reviews,BASE+['section_id','source_format','source_path','source_heading','scope_candidate','source_record','source_end_record','source_page','source_rows_json'])
 write(out/'record_candidates.csv',list(records.values()),BASE+['record_candidate_id','record_label_raw','identity_status','section_count'])
 write(out/'section_evidence.csv',sections,BASE+['section_id','record_candidate_id','source_format','source_path','source_sha256','source_record','source_end_record','source_page','source_bbox_json','source_heading','scope_candidate','event_label_candidate','availability','requires_review','issue','source_rows_json'])
 write(out/'status_fields_long.csv',fields,BASE+['section_id','record_candidate_id','scope_candidate','source_record','field_label_raw','value_raw','value_status','requires_review','semantic_status'])
 write(out/'summary_and_unresolved_rows.csv',tables,BASE+['section_id','record_candidate_id','scope_candidate','source_record','row_role','source_header_json','source_row_json','requires_review'])
 write(out/'report_coverage.csv',coverage,BASE+['selected_source','status','section_count','events_recovered_text','issue'])
 write(out/'errors.csv',errors,BASE+['source_format','source_path','error'])
 summary={'created_at':datetime.now(timezone.utc).isoformat(),'reports':len(coverage),'record_candidates':len(records),'section_evidence_blocks':len(sections),'status_field_observations':len(fields),'summary_or_unresolved_rows':len(tables),'report_status_counts':dict(Counter(r['status'] for r in coverage)),'empty_sections_requires_review':len(empty_reviews),'source_errors':len(errors),'scope':'First candidate extraction. CSV raw field labels/values and tables retained; PDF page-local evidence blocks only, not structured PDF field extraction. Unresolved scope is retained. No validated event identities, cross-label merging, CISS event linkage, semantic mapping, or hex decoding.'}
 (out/'metadata.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary,indent=2));print(f'Outputs: {out}')
if __name__=='__main__':main()
