# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfplumber"]
# ///
"""Group 1: report metadata and introductory documentation, preserving source evidence."""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
import pdfplumber
from build_edr_collection_discovery import load_rows

LABELS = {
 'User Entered VIN':'vin_entered', 'User Entered VIN/Frame Number':'vin_entered',
 'User':'user_entered', 'Case Number':'case_number_entered',
 'EDR Data Imaging Date':'imaging_date', 'Crash Date':'crash_date',
 'Filename':'source_filename', 'Saved on':'saved_on',
 'Imaged with CDR version':'imaging_cdr_version',
 'Reported with CDR version':'reporting_cdr_version',
 'Imaged with Software Licensed to (Company Name)':'imaging_license_company',
 'Reported with Software Licensed to (Company Name)':'reporting_license_company',
 'EDR Device Type':'edr_device_type', 'Event(s) recovered':'events_recovered_text',
 'ACM Adapter Detected During Download':'acm_adapter_detected',
 'Restraint Deployment Signal Received':'restraint_deployment_signal_text',
}
CORE = ['vin_entered','source_filename','imaging_cdr_version','reporting_cdr_version','edr_device_type']
BODY = re.compile(r'^(?:System Status|System Configuration|PCM Module Information|PCM EDR Data|Event Record Summary|Front/Rear Event Record Summary|Event Data\s*\(|Status of the Data|Deployment (?:Data|Command)|Pre[-_ ]Crash Data|Longitudinal(?:/Lateral)? Crash Pulse|Lateral Crash Pulse|Rollover Crash Pulse|Hexadecimal Data\s*$)',re.I)
# Hexadecimal Data: within limitations explains the raw section; it is documentation,
# not the byte block. A heading without the colon outside documentation is a stop.
DOC_HEAD = re.compile(r'^(?:Comments|Data Limitations|Data Source|PCM Data Source|Data Element Sign Convention|Recorded Crash Events|Data|Hexadecimal Data):?$',re.I)
BASE = ['report_id','case_id','vehicle_number','export_basename']
FIELD = BASE+['source_format','source_path','source_sha256','source_page','source_record','source_record_end','source_cells_json','source_bbox_json','field_name','field_label_raw','value_raw','value_text','value_status','extraction_method']
DOC = BASE+['source_format','source_path','source_sha256','source_page','source_record','documentation_category','text_raw','extraction_status']
AUDIT = BASE+['source_format','source_path','status','metadata_field_count','documentation_block_count','intro_pages','body_boundary','issue']
INDEX = BASE+['csv_path','pdf_path','csv_status','pdf_status','metadata_status','documentation_status']
COMPARE = BASE+['field_name','csv_status','csv_value_text','pdf_status','pdf_value_text','agreement_status']

def norm(s):return re.sub(r'\s+',' ',s).strip()
def key(s):return norm(s).casefold()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def value_state(s):
 t=norm(s)
 if not t:return 'blank'
 if t.casefold() in {'n/a','na','not available'}:return 'not_available'
 return 'present'
def canonical(label):
 return next((v for k,v in LABELS.items() if key(k)==key(label)), 'unmapped:'+norm(label))
def read_csv(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_csv(p,rows,cols):
 temp=p.with_suffix(p.suffix+'.part')
 with temp.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
 temp.replace(p)
def evidence(base,fmt,path,sha,label,value,**location):
 return {**base,'source_format':fmt,'source_path':str(path),'source_sha256':sha,
  'source_page':'','source_record':'','source_record_end':'','source_cells_json':'','source_bbox_json':'','field_name':canonical(label),
  'field_label_raw':label,'value_raw':value,'value_text':norm(value),
  'value_status':value_state(value),**location}

def csv_intro(path,base):
 loaded=load_rows(path);rows=loaded[0];sha=digest(path);fields=[];docs=[];issues=[]
 # Retain warnings returned by the source-preserving CSV reader.
 warnings=loaded[-1] if isinstance(loaded[-1],list) else []
 if warnings:issues.append(f'csv_format_warnings:{len(warnings)}')
 start=next((i for i,r in enumerate(rows) if r and key(r[0])=='cdr file information'),None)
 if start is None:raise ValueError('CDR FILE INFORMATION heading not found')
 end=start+1
 while end<len(rows):
  rr=rows[end];filled=[v for v in rr if v.strip()]
  if len(filled)==1 and (DOC_HEAD.fullmatch(filled[0].strip()) or (filled[0].isupper() and len(rr)<3)):
   break
  if rr and rr[0].strip():
   label=rr[0]
   continuation=re.fullmatch(r'(?:Event Record \d+|Record \d+|Event \d+|(?:First|Second|Third) Record|Most Recent Event|\d+(?:st|nd|rd|th) Prior Event)(?:\s*\([^\n]*\))?\s*,?',norm(label),re.I)
   previous=fields[-1] if fields else None
   if len(filled)==1 and continuation and previous and previous['field_name']=='events_recovered_text' and int(previous['source_record_end'])==end:
    previous['value_raw']+='\n'+label
    previous['value_text']=norm(previous['value_raw'])
    previous['source_record_end']=end+1
    cells=json.loads(previous['source_cells_json'])
    cells.extend({'record':end+1,'column':ci+1,'value_raw':v} for ci,v in enumerate(rr))
    previous['source_cells_json']=json.dumps(cells,ensure_ascii=False)
    previous['extraction_method']='original_csv_intro_field_with_verified_event_continuation'
   elif len(rr)>1:
    if len(rr)>2 and any(v.strip() for v in rr[2:]):
     value=json.dumps(rr[1:],ensure_ascii=False);issues.append('multivalue_intro_field_preserved_as_json')
    else:value=rr[1]
    cells=[{'record':end+1,'column':ci+1,'value_raw':v} for ci,v in enumerate(rr) if ci>0]
    fields.append(evidence(base,'csv',path,sha,label,value,source_record=end+1,source_record_end=end+1,source_cells_json=json.dumps(cells,ensure_ascii=False),extraction_method='original_csv_intro_field'))
   elif key(label).startswith('system:'):
    fields.append(evidence(base,'csv',path,sha,'System',label.split(':',1)[1],source_record=end+1,extraction_method='original_csv_system_label'))
   elif label.strip():
    # Only a verified event-label pattern may extend the immediately preceding
    # events-recovered field. Unknown single-cell text remains documented.
    continuation=re.fullmatch(r'(?:Event Record \d+|Record \d+|Event \d+|(?:First|Second|Third) Record|Most Recent Event|\d+(?:st|nd|rd|th) Prior Event)(?:\s*\([^\n]*\))?\s*,?',norm(label),re.I)
    previous=fields[-1] if fields else None
    if continuation and previous and previous['field_name']=='events_recovered_text' and int(previous['source_record_end'])==end:
     previous['value_raw']+='\n'+label
     previous['value_text']=norm(previous['value_raw'])
     previous['source_record_end']=end+1
     cells=json.loads(previous['source_cells_json']);cells.append({'record':end+1,'column':1,'value_raw':label})
     previous['source_cells_json']=json.dumps(cells,ensure_ascii=False)
     previous['extraction_method']='original_csv_intro_field_with_verified_event_continuation'
    else:
     issues.append('unrecognized_single_cell_intro_content')
     docs.append({**base,'source_format':'csv','source_path':str(path),'source_sha256':sha,'source_page':'','source_record':end+1,'documentation_category':'unresolved_introductory_content','text_raw':label,'extraction_status':'unresolved_source_text_preserved'})
  end+=1
 # System labels can precede CDR FILE INFORMATION.
 for ri,r in enumerate(rows[:start]):
  if r and key(r[0]).startswith('system:'):
   fields.append(evidence(base,'csv',path,sha,'System',r[0].split(':',1)[1],source_record=ri+1,extraction_method='original_csv_system_label'))
 # Only comments/limitations directly after the intro are Group 1.
 j=end;category='';buffer=[];first=j+1
 def flush():
  if buffer:docs.append({**base,'source_format':'csv','source_path':str(path),'source_sha256':sha,'source_page':'','source_record':first,'documentation_category':category,'text_raw':'\n'.join(buffer),'extraction_status':'source_text_preserved'})
 while j<len(rows):
  r=rows[j];filled=[v for v in r if v.strip()];text=','.join(r)
  if filled and key(filled[0]) in {'pidsstart','hexadecimal data'}:break
  if len(filled)==1:
   t=filled[0].strip()
   if key(t) in {'comments','data limitations'}:
    flush();buffer=[];category='comments' if key(t)=='comments' else 'limitations';first=j+1
   elif category and t.isupper() and not DOC_HEAD.fullmatch(t):break
   elif not category and t:break
  if category:buffer.append(text)
  j+=1
 flush()
 return fields,docs,{'intro_pages':'','body_boundary':'csv_intro_heading_boundary','issue':'|'.join(sorted(set(issues)))}

def page_lines(page):
 # Geometry keeps metadata field names separate from right-column values.
 return page.extract_text_lines(layout=False,strip=True)

def pdf_intro(path,base,max_pages):
 sha=digest(path);fields=[];docs=[];issues=[];boundary='';pages=0;in_info=False;info_seen=False
 doccat='notice';buffer=[];block_page=1
 with pdfplumber.open(path) as pdf:
  for pi,page in enumerate(pdf.pages[:max_pages]):
   pages=pi+1;lines=page_lines(page)
   # Exclude the footer, whose printed date is not a crash or imaging date.
   footer=[l['top'] for l in lines if re.search(r'Page\s+\d+\s+of\s+\d+',l['text'],re.I)]
   cutoff=min(footer) if footer else page.height-20
   lines=[l for l in lines if l['top']<cutoff and norm(l['text']) not in {'BOSCH','CRASH DATA RETRIEVAL'}]
   header_i=next((i for i,l in enumerate(lines) if key(l['text'])=='cdr file information'),None)
   meta_end=None
   if header_i is not None:
    info_seen=True
    meta_end=next((i for i in range(header_i+1,len(lines)) if key(lines[i]['text']) in {'comments','data limitations'}),len(lines))
    # Locate the value column from the VIN or Filename row, not a hard-coded x.
    anchors=[]
    for l in lines[header_i+1:meta_end]:
     for label in ['User Entered VIN/Frame Number','User Entered VIN','Filename','EDR Device Type']:
      if key(l['text']).startswith(key(label)+' '):
       words=page.extract_words(x_tolerance=2,y_tolerance=2)
       row=[w for w in words if abs(w['top']-l['top'])<2]
       count=len(label.split())
       if len(row)>count:anchors.append(row[count]['x0'])
    split_x=sorted(anchors)[len(anchors)//2]-1 if anchors else None
    if split_x is None:issues.append('metadata_value_column_not_identified')
    else:
     starts=[]
     labels=sorted(LABELS,key=len,reverse=True)
     for l in lines[header_i+1:meta_end]:
      if l['x0']>=split_x:continue
      label=next((a for a in labels if key(l['text']).startswith(key(a)) or (a.endswith('Name)') and key(l['text']).startswith(key(a.rsplit(' Name)',1)[0])))),None)
      if label:starts.append((l,label))
     for n,(l,label) in enumerate(starts):
      bottom=starts[n+1][0]['top']-0.1 if n+1<len(starts) else (lines[meta_end]['top']-0.1 if meta_end<len(lines) else cutoff)
      top=l['top']-1
      # A wrapped value can start ABOVE its vertically centered label.
      # Prefer the actual metadata table row borders when present.
      rules=sorted(set(line['top'] for line in page.lines if abs(line['top']-line['bottom'])<0.1 and line['x0']<=split_x<=line['x1'] and line['x1']-line['x0']>80))
      above=[y for y in rules if y<=l['top']]
      below=[y for y in rules if y>l['top']]
      if above and below and sum(max(above)<=other['top']<min(below) for other,_ in starts)==1:
       top=max(above)+1.3;bottom=min(below)+1.3
      box=(split_x,top,page.width,bottom)
      v=page.crop(box).extract_text(x_tolerance=2,y_tolerance=2) or ''
      fields.append(evidence(base,'pdf',path,sha,label,v,source_page=pi+1,source_bbox_json=json.dumps(box),extraction_method='pdf_text_geometry_candidate'))
     if not starts:issues.append('metadata_fields_not_recognized')
    docs.append({**base,'source_format':'pdf','source_path':str(path),'source_sha256':sha,'source_page':pi+1,'source_record':'','documentation_category':'file_information_source_text','text_raw':'\n'.join(l['text'] for l in lines[header_i:meta_end]),'extraction_status':'pdf_text_candidate_not_semantically_validated'})
   def flush():
    if buffer:docs.append({**base,'source_format':'pdf','source_path':str(path),'source_sha256':sha,'source_page':block_page,'source_record':'','documentation_category':doccat,'text_raw':'\n'.join(buffer),'extraction_status':'pdf_text_candidate_not_semantically_validated'})
   # Keep documentation page-local, including continuation pages and sign tables.
   buffer=[];block_page=pi+1
   for li,l in enumerate(lines):
    t=l['text']
    if header_i is not None and header_i<=li<(meta_end if meta_end is not None else len(lines)):
     if li==header_i:flush();buffer=[]
     continue
    if BODY.match(t) and not (doccat=='limitations' and t.strip().endswith(':') and key(t).startswith('hexadecimal data')):
     flush();buffer=[];boundary=t;break
    if key(t) in {'comments','data limitations'}:
     flush();buffer=[];doccat='comments' if key(t)=='comments' else 'limitations'
    buffer.append(t)
   flush()
   if boundary:break
  if not boundary:issues.append('intro_boundary_not_confirmed' if len(pdf.pages)<=max_pages else 'intro_page_limit_reached')
  if not info_seen:issues.append('cdr_file_information_heading_not_found')
  if not fields:issues.append('no_metadata_fields_extracted')
  if not docs:issues.append('no_introductory_text_extracted_possible_image_only_pdf')
  present={x['field_name'] for x in fields}
  if set(CORE)-present:issues.append('core_metadata_fields_not_extracted:'+','.join(sorted(set(CORE)-present)))
  if any('(cid:' in d['text_raw'] for d in docs):issues.append('pdf_text_contains_font_encoding_artifacts')
  # Release per-page caches during large collection runs.
 return fields,docs,{'intro_pages':pages,'body_boundary':boundary,'issue':'|'.join(sorted(set(issues)))}

def resolve(raw,root):
 if not raw:return None
 p=Path(raw)
 if p.is_file():return p
 parts=list(PureWindowsPath(raw).parts) if '\\' in raw else list(Path(raw).parts)
 # Relocate a Windows inventory onto the same data/temp tree if necessary.
 for j in range(len(parts)-1):
  if parts[j].casefold()=='data' and parts[j+1].casefold()=='temp':
   candidate=root.joinpath(*parts[j+2:])
   if candidate.is_file():return candidate
 return p


def event_list_equivalent(left,right):
 # Ignore comma/newline presentation only for explicit numbered Event Record
 # lists. Do not equate First Record, deployment types or different orders.
 pattern=r'(?:Event Record|Record) \d+(?:\s*\([^()]*\))?'
 def parse(value):
  items=re.findall(pattern,value,re.I)
  remaining=re.sub(pattern,'',value,flags=re.I)
  return [x.casefold() for x in items] if items and not remaining.strip(' ,\n\r\t') else None
 a,b=parse(left),parse(right)
 return a is not None and a==b

def compare_fields(base,fields):
 grouped=defaultdict(lambda:defaultdict(list))
 for f in fields:grouped[f['field_name']][f['source_format']].append(f)
 result=[]
 for name in sorted(set(LABELS.values())|set(grouped)):
  by=grouped[name];vals={}
  for fmt in ['csv','pdf']:
   records=by.get(fmt,[]);values=list(dict.fromkeys(x['value_text'] for x in records))
   vals[fmt]=('absent','') if not records else (('ambiguous' if len(values)>1 else value_state(values[0])),json.dumps(values,ensure_ascii=False) if len(values)>1 else values[0])
  cs,cv=vals['csv'];ps,pv=vals['pdf']
  if 'ambiguous' in {cs,ps}:status='multiple_values_require_review'
  elif cs=='absent' and ps=='absent':status='not_extracted_in_either_source'
  elif cs=='absent' or ps=='absent':status='single_source_evidence'
  elif cv==pv:status='agree_after_whitespace_normalization'
  elif name=='edr_device_type' and cv.casefold()==pv.casefold():status='agree_after_device_type_case_normalization'
  elif name=='events_recovered_text' and event_list_equivalent(cv,pv):status='agree_after_verified_event_list_format_normalization'
  else:status='source_difference_requires_review'
  result.append({**base,'field_name':name,'csv_status':cs,'csv_value_text':cv,'pdf_status':ps,'pdf_value_text':pv,'agreement_status':status})
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--inventory',default='data/processed/edr/edr_export_inventory.csv')
 p.add_argument('--reports',default='data/processed/edr/csv_extraction_v1/reports.csv')
 p.add_argument('--source-root',default='data/temp')
 p.add_argument('--output-directory',default='data/processed/edr/group1_v3')
 p.add_argument('--max-intro-pages',type=int,default=15)
 p.add_argument('--limit',type=int)
 a=p.parse_args()
 if a.limit is not None and a.limit<1:p.error('--limit must be positive')
 if a.max_intro_pages<1:p.error('--max-intro-pages must be positive')
 inventory=read_csv(Path(a.inventory));root=Path(a.source_root);out=Path(a.output_directory);out.mkdir(parents=True,exist_ok=True)
 old=read_csv(Path(a.reports)) if Path(a.reports).is_file() else []
 bypath={x['csv_path']:x for x in old};index=[];allfields=[];alldocs=[];audit=[];comparisons=[];errors=[]
 keys=[(x['case_id'],x['vehicle_number'],x['export_basename']) for x in inventory]
 if len(set(keys))!=len(keys):p.error('Duplicate case/vehicle/export-basename entries in inventory; resolve before extraction')
 selected=inventory[:a.limit] if a.limit else inventory
 for n,row in enumerate(selected,1):
  prior=bypath.get(row.get('csv_export_path',''),{})
  rid=prior.get('report_id') or 'report_group1_'+hashlib.sha256('|'.join([row['case_id'],row['vehicle_number'],row['export_basename']]).encode()).hexdigest()[:24]
  base={'report_id':rid,**{k:row[k] for k in BASE[1:]}};localfields=[];localdocs=[];statuses={}
  for fmt in ['csv','pdf']:
   raw=row.get(fmt+'_export_path','');path=resolve(raw,root)
   if not raw:statuses[fmt]='not_available';continue
   try:
    if path is None or not path.is_file():raise FileNotFoundError(f'Source file not found: {raw}')
    expected=row.get(fmt+'_sha256','')
    if expected and digest(path)!=expected:raise ValueError('Source hash differs from inventory; refresh inventory before extraction')
    fs,ds,detail=csv_intro(path,base) if fmt=='csv' else pdf_intro(path,base,a.max_intro_pages)
    status='extracted_needs_review' if detail['issue'] else 'extracted_candidate'
    statuses[fmt]=status;localfields.extend(fs);localdocs.extend(ds)
    audit.append({**base,'source_format':fmt,'source_path':str(path),'status':status,'metadata_field_count':len(fs),'documentation_block_count':len(ds),**detail})
   except Exception as e:
    statuses[fmt]='failed';errors.append({**base,'source_format':fmt,'source_path':str(path),'error_type':type(e).__name__,'error_message':str(e)})
    audit.append({**base,'source_format':fmt,'source_path':str(path),'status':'failed','metadata_field_count':0,'documentation_block_count':0,'intro_pages':'','body_boundary':'','issue':str(e)})
  allfields.extend(localfields);alldocs.extend(localdocs);comparisons.extend(compare_fields(base,localfields))
  index.append({**base,'csv_path':row.get('csv_export_path',''),'pdf_path':row.get('pdf_export_path',''),'csv_status':statuses['csv'],'pdf_status':statuses['pdf'],'metadata_status':'candidate_available' if localfields else 'not_extracted','documentation_status':'candidate_available' if localdocs else 'not_extracted'})
  if n%100==0:print(f'Processed Group 1 for {n}/{len(selected)} reports...',flush=True)
 write_csv(out/'report_index.csv',index,INDEX)
 write_csv(out/'report_metadata_long.csv',allfields,FIELD)
 write_csv(out/'report_documentation.csv',alldocs,DOC)
 write_csv(out/'field_comparison.csv',comparisons,COMPARE)
 write_csv(out/'source_audit.csv',audit,AUDIT)
 write_csv(out/'errors.csv',errors,BASE+['source_format','source_path','error_type','error_message'])
 summary={'created_at':datetime.now(timezone.utc).isoformat(),'inventory_reports':len(inventory),'selected_reports':len(selected),'metadata_observations':len(allfields),'documentation_blocks':len(alldocs),'source_status_counts':dict(Counter(x['status'] for x in audit)),'failed_sources':len(errors),'field_agreement_counts':dict(Counter(x['agreement_status'] for x in comparisons)),'scope':'Group 1 introduction candidates only. No event measurements, raw-byte blocks, OCR, semantic interpretation of limitations, unit conversion or time alignment. PDF text is preserved as extracted, not guaranteed character-perfect. Missing metadata fields are not inferred. All reported outcomes require collection evaluation.'}
 temp=out/'metadata.json.part';temp.write_text(json.dumps(summary,indent=2),encoding='utf-8');temp.replace(out/'metadata.json')
 print(json.dumps(summary,indent=2));print(f'Outputs: {out}')

if __name__=='__main__':main()
