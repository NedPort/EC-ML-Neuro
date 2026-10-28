"""Group 2 structural discovery: candidate event/status headings, not validated events."""
from __future__ import annotations
import argparse,csv,json,re,hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import pdfplumber
from build_edr_collection_discovery import load_rows

IDENTITY=['report_id','case_id','vehicle_number','export_basename']
COLUMNS=IDENTITY+['source_format','source_path','source_sha256','source_record','source_page','source_bbox_json','source_heading','scope_candidate','event_label_candidate','label_status','content_preview_json','discovery_status']
# These are provisional recognition rules. Other headings remain in the review inventory.
TARGET=re.compile(r'^(?:system status|status (?:at|of)|event (?:record )?summary|front/?rear event record summary|event data|crash event data|record status|event record(?: information| status)?\b|impact event record\b|pcm module information|pcm edr data)',re.I)
EVENT=re.compile(r'(?:most recent|\d+(?:st|nd|rd|th) prior|prior|first|second|third|\d+)\s+(?:frontal\s*/\s*rear\s+)?(?:event|record)|(?:impact )?event record\s*\d+|record\s*\d+|event\s*\d+|rollover event record|TRG INVALID\s*#\d+',re.I)
HEX=re.compile(r'^(?:pidsstart|pidsend|hexadecimal data|raw (?:hex|byte))\b',re.I)

def is_target(heading):
 if not TARGET.search(heading):return False
 # Obvious narrative and key/value lines are not section headings.
 if re.search(r'\b(?:section of the report|reflects the|experienced from|refer to|indicates that)\b',heading,re.I):return False
 if re.match(r'^Event Record Type\b',heading,re.I):return False
 if len(heading)>180:return False
 if re.match(r'^(?:Impact )?Event Record\b',heading,re.I):
  return bool(re.fullmatch(r'(?:Impact )?Event Record(?:\s+#?\d+|\s+(?:Information|Status)|\s+Summary(?:\s+At\s+Retrieval)?)(?:\s*\([^)]*\))?',heading,re.I))
 return True

def norm(s):return re.sub(r'\s+',' ',s).strip()
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,cols):
 tmp=p.with_suffix(p.suffix+'.part')
 with tmp.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
 tmp.replace(p)
def resolve(value,root):
 if not value:return None
 p=Path(value)
 if p.is_file():return p
 parts=value.replace('\\','/').split('/')
 for i in range(len(parts)-1):
  if parts[i:i+2]==['data','temp']:
   candidate=root.joinpath(*parts[i+2:])
   if candidate.is_file():return candidate
 return p

def classify(heading):
 if re.fullmatch(r'PCM MODULE INFORMATION',heading,re.I):return 'module_level','', 'not_event_specific'
 if re.fullmatch(r'PCM EDR DATA',heading,re.I):return 'pcm_buffer_scope_requires_review','', 'buffer_not_assumed_event'
 if re.search(r'retrieval|download|current',heading,re.I):return 'retrieval_level','', 'not_event_specific'
 if re.search(r'event.*summary|summary.*event',heading,re.I):return 'record_summary_scope_requires_review','', 'summary_not_one_event'
 # Keep the full parenthesized text, including trigger/record modifiers.
 match=re.search(r'\((.*)\)',heading)
 label=match.group(1) if match and EVENT.search(match.group(1)) else ''
 if not label:
  m=EVENT.search(heading)
  if m:label=m.group(0)
 return ('reported_record_candidate',label,'provisional_source_label') if label else ('scope_requires_review','','unspecified')

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--index',type=Path,default=Path('data/processed/edr/group1_v4/report_index.csv'))
 ap.add_argument('--source-root',type=Path,default=Path('data/temp'))
 ap.add_argument('--output-directory',type=Path,default=Path('data/processed/edr/group2_discovery_csv_first_v3'))
 ap.add_argument('--limit',type=int)
 ap.add_argument('--pdf-mode',choices=['all','pdf-only'],default='pdf-only',help='Default: CSV first, PDF when CSV is absent or fails. all scans both sources.')
 args=ap.parse_args()
 if args.limit is not None and args.limit<1:ap.error('--limit must be positive')
 index=read(args.index)
 if len({r['report_id'] for r in index})!=len(index):raise ValueError('Duplicate report IDs in index')
 selected=index[:args.limit] if args.limit else index
 candidates=[];reviews=[];coverage=[];errors=[]
 for number,r in enumerate(selected,1):
  base={k:r[k] for k in IDENTITY}
  csv_scanned_successfully=False
  for fmt in ['csv','pdf']:
   value=r.get(fmt+'_path','');path=resolve(value,args.source_root)
   audit={**base,'source_format':fmt,'source_path':str(path or ''),'status':'absent','candidate_count':0,'review_heading_count':0,'issue':''}
   if fmt=='pdf' and args.pdf_mode=='pdf-only' and csv_scanned_successfully:
    audit['status']='not_scanned_by_policy';coverage.append(audit);continue
   if not value:coverage.append(audit);continue
   try:
    if not path.is_file():raise FileNotFoundError(str(path))
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    def add(heading,record='',page='',bbox='',preview=None):
     scope,label,labelstatus=classify(heading)
     item={**base,'source_format':fmt,'source_path':str(path),'source_sha256':sha,'source_record':record,'source_page':page,'source_bbox_json':bbox,'source_heading':heading,'scope_candidate':scope,'event_label_candidate':label,'label_status':labelstatus,'content_preview_json':json.dumps(preview or [],ensure_ascii=False),'discovery_status':'structural_candidate_requires_evaluation'}
     if is_target(heading):candidates.append(item);audit['candidate_count']+=1
     else:reviews.append(item);audit['review_heading_count']+=1
    if fmt=='csv':
     rows,_,_,_,_,warnings=load_rows(path)
     heads=[]
     for i,row in enumerate(rows):
      cells=[norm(c) for c in row if norm(c)]
      if len(cells)==1 and (is_target(cells[0]) or (cells[0].isupper() and len(cells[0])>5)):
       heads.append((i,cells[0]))
     for n,(i,heading) in enumerate(heads):
      if HEX.search(heading):continue
      end=heads[n+1][0] if n+1<len(heads) else len(rows)
      if is_target(heading) or EVENT.search(heading):
       # Short preview only: no hex/PID blocks or full signal extraction.
       preview=[]
       for row in rows[i+1:min(end,i+9)]:
        if row and HEX.search(norm(row[0])):break
        preview.append(row)
       add(heading,record=i+1,preview=preview)
     audit['issue']=f'csv_format_warnings:{len(warnings)}' if warnings else ''
    else:
     with pdfplumber.open(path) as pdf:
      for pi,page in enumerate(pdf.pages,1):
       for line in page.extract_text_lines(layout=False,strip=True):
        heading=norm(line['text'])
        if HEX.search(heading) or re.search(r'Page\s+\d+\s+of\s+\d+',heading,re.I):continue
        # A line is only a heading candidate, not proof of a table boundary.
        if is_target(heading) or (heading.isupper() and EVENT.search(heading)):
         add(heading,page=pi,bbox=json.dumps([line['x0'],line['top'],line['x1'],line['bottom']]))
    audit['status']='scanned_candidates' if audit['candidate_count'] else 'scanned_no_recognized_target_headings'
    if fmt=='csv':csv_scanned_successfully=True
   except Exception as exc:
    audit['status']='failed';audit['issue']=f'{type(exc).__name__}: {exc}'
    errors.append({**base,'source_format':fmt,'source_path':str(path),'error':audit['issue']})
   coverage.append(audit)
  if number%25==0 or number==len(selected):print(f'Discovered Group 2 for {number}/{len(selected)} reports...',flush=True)
 out=args.output_directory;out.mkdir(parents=True,exist_ok=True)
 write(out/'section_candidates.csv',candidates,COLUMNS)
 write(out/'other_event_heading_candidates.csv',reviews,COLUMNS)
 write(out/'source_coverage.csv',coverage,IDENTITY+['source_format','source_path','status','candidate_count','review_heading_count','issue'])
 write(out/'errors.csv',errors,IDENTITY+['source_format','source_path','error'])
 counts=Counter((r['source_format'],r['source_heading']) for r in candidates)
 summary=[{'source_format':fmt,'source_heading':heading,'occurrence_count':n,'report_count':len({r['report_id'] for r in candidates if r['source_format']==fmt and r['source_heading']==heading})} for (fmt,heading),n in counts.most_common()]
 write(out/'heading_summary.csv',summary,['source_format','source_heading','occurrence_count','report_count'])
 meta={'created_at':datetime.now(timezone.utc).isoformat(),'inventory_reports':len(index),'selected_reports':len(selected),'pdf_mode':args.pdf_mode,'source_policy':'CSV first; PDF fallback when CSV absent or failed. Zero recognized CSV headings stay in review coverage and do not establish complete extraction.','source_status_counts':dict(Counter(r['status'] for r in coverage)),'section_candidates':len(candidates),'other_event_heading_candidates':len(reviews),'failed_sources':len(errors),'scope':'Structural discovery only. Heading counts are occurrences, not validated events. No event linkage, numeric status interpretation, full table extraction, OCR, measurements or hex/PID decoding. PDFs may contain wrapped, repeated or missed headings; collection evaluation required.'}
 tmp=out/'metadata.json.part';tmp.write_text(json.dumps(meta,indent=2),encoding='utf-8');tmp.replace(out/'metadata.json')
 print(json.dumps(meta,indent=2));print(f'Outputs: {out}')
if __name__=='__main__':main()
