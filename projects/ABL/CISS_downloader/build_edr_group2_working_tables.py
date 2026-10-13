"""Build source-preserving Group 2 CSV working views; record links remain candidates."""
import argparse,csv,json,hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from build_edr_group2_field_audit import route
csv.field_size_limit(10000000)
BASE=['report_id','case_id','vehicle_number','export_basename']
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,cols):
 tmp=p.with_suffix(p.suffix+'.part')
 with tmp.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
 tmp.replace(p)
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--input-directory',type=Path,default=Path('data/processed/edr/group2_extract_v2'))
 ap.add_argument('--output-directory',type=Path,default=Path('data/processed/edr/group2_working_v1'))
 args=ap.parse_args();src=args.input_directory;out=args.output_directory
 if src.resolve()==out.resolve():ap.error('Preserve extraction outputs in a separate directory')
 sections=read(src/'section_evidence.csv');fields=read(src/'status_fields_long.csv');tables=read(src/'summary_and_unresolved_rows.csv');records=read(src/'record_candidates.csv');coverage=read(src/'report_coverage.csv')
 lookup={s['section_id']:s for s in sections};dest={'record_status_long':[],'retrieval_status_long':[],'unresolved_status_long':[],'other_group_fields_long':[]}
 columns=list(fields[0])+['source_format','source_path','source_sha256','source_heading','proposed_group','routing_reason'] if fields else BASE
 for field in fields:
  s=lookup[field['section_id']];group,reason=route(field['field_label_raw'])
  item={**field,**{k:s[k] for k in ['source_format','source_path','source_sha256','source_heading']},'proposed_group':group,'routing_reason':reason}
  bucket='other_group_fields_long' if group!='group2_status_context' else 'record_status_long' if field['scope_candidate']=='reported_record_candidate' else 'retrieval_status_long' if field['scope_candidate']=='retrieval_level' else 'unresolved_status_long'
  dest[bucket].append(item)
 summary_rows=[];cells=[];pending=[];buffers=[]
 for r in tables:
  s=lookup[r['section_id']]
  if s['scope_candidate']=='pcm_buffer_scope_requires_review':buffers.append(r);continue
  if 'summary' not in s['source_heading'].lower():pending.append(r);continue
  if r['row_role']!='data_candidate':continue
  header=json.loads(r['source_header_json']);values=json.loads(r['source_row_json'])
  sid='g2summary_'+hashlib.sha256((r['section_id']+'|'+r['source_record']).encode()).hexdigest()[:24]
  label='';trigger=''
  for i,h in enumerate(header):
   if i>=len(values):continue
   if h.strip().lower() in ['events recorded','event recorded','event record','event']:label=values[i]
   if h.strip().lower() in ['trg count','trigger count']:trigger=values[i]
  summary_rows.append({**{k:r[k] for k in BASE},'summary_row_id':sid,'section_id':r['section_id'],'source_record':r['source_record'],'reported_record_label':label,'reported_trigger_reference':trigger,'source_path':s['source_path'],'source_sha256':s['source_sha256'],'source_heading':s['source_heading'],'row_values_json':r['source_row_json'],'link_status':'not_linked_to_record_candidate','requires_review':True})
  for i,v in enumerate(values):
   h=header[i] if i<len(header) else ''
   # Ignore blank padding; retain unlabeled nonempty cells explicitly.
   if not h.strip() and not v.strip():continue
   cells.append({**{k:r[k] for k in BASE},'summary_row_id':sid,'section_id':r['section_id'],'source_record':r['source_record'],'source_column_index':i+1,'source_column_name':h,'value_raw':v,'value_status':'blank' if not v.strip() else 'present','requires_review':True})
 out.mkdir(parents=True,exist_ok=True)
 for name,rows in dest.items():write(out/(name+'.csv'),rows,columns)
 write(out/'retrieval_summary_rows.csv',summary_rows,list(summary_rows[0]) if summary_rows else BASE+['summary_row_id'])
 write(out/'retrieval_summary_cells_long.csv',cells,list(cells[0]) if cells else BASE+['summary_row_id'])
 tablecols=list(tables[0]) if tables else BASE
 write(out/'pcm_buffer_rows.csv',buffers,tablecols);write(out/'unresolved_table_rows.csv',pending,tablecols)
 write(out/'record_candidates.csv',records,list(records[0]) if records else BASE)
 write(out/'report_coverage.csv',coverage,list(coverage[0]) if coverage else BASE)
 # PDF and unresolved/empty sections remain explicit evidence; no completeness claim.
 pending_sections=[s for s in sections if s['source_format']=='pdf' or s['scope_candidate'] not in ['reported_record_candidate','retrieval_level'] or s['availability']!='content_present']
 write(out/'pending_section_evidence.csv',pending_sections,list(sections[0]) if sections else BASE)
 summary={'created_at':datetime.now(timezone.utc).isoformat(),'reports':len(coverage),'record_candidates':len(records),'field_view_counts':{k:len(v) for k,v in dest.items()},'summary_rows':len(summary_rows),'summary_cells':len(cells),'pcm_buffer_rows':len(buffers),'unresolved_table_rows':len(pending),'pending_section_evidence':len(pending_sections),'all_field_observations_preserved':sum(map(len,dest.values()))==len(fields),'scope':'CSV working views with provisional routing. Summary references are not matched to event identities. Original names, raw values and units remain unchanged. PDF structured extraction, unresolved scopes and final validation remain pending.'}
 p=out/'metadata.json.part';p.write_text(json.dumps(summary,indent=2),encoding='utf-8');p.replace(out/'metadata.json');print(json.dumps(summary,indent=2));print(f'Outputs: {out}')
if __name__=='__main__':main()
