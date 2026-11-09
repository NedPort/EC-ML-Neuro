"""Non-destructive Group 1 report-level unification and field dictionary.
Run from CISS_downloader root with --fields, --documentation, --output-dir.
Requires Python standard library only. Never modifies input files.
"""
import argparse,csv,json,collections,hashlib
from pathlib import Path

ID=['report_id','case_id','vehicle_number','export_basename']
PROV=['source_format','source_path','source_sha256','rule_version']
DEFS={
'vin_entered':('VIN/frame number entered in CDR report','identifier'),
'user_entered':('User recorded in CDR report','metadata'),
'case_number_entered':('Case number entered in CDR report; not necessarily CISS case_id','metadata'),
'imaging_date':('EDR data imaging date as reported','date_text'),
'crash_date':('Crash date as reported','date_text'),
'source_filename':('Filename recorded within CDR report; distinct from source_path','metadata'),
'saved_on':('Report save timestamp as reported','date_text'),
'imaging_cdr_version':('CDR version used for imaging','metadata'),
'reporting_cdr_version':('CDR version used for reporting','metadata'),
'imaging_license_company':('Company named in imaging software license','metadata'),
'reporting_license_company':('Company named in reporting software license','metadata'),
'edr_device_type':('EDR device type as reported','metadata'),
'events_recovered_text':('Report-level source description of recovered events; NOT a validated event ID','report_text'),
'acm_adapter_detected':('ACM adapter detection value as reported','metadata'),
'restraint_deployment_signal_text':('Restraint deployment signal source text','report_text'),
'unmapped:System':('Unmapped system label; meaning requires source-level review','unmapped')}

def read(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(path,rows,cols):
 with open(path,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument('--fields',required=True);p.add_argument('--documentation',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args()
 fields=read(a.fields);docs=read(a.documentation);out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
 if not fields:raise ValueError('No field rows')
 for c in ID+PROV+['field_name','field_label_raw','value_text','value_raw','source_record','source_page']:
  if c not in fields[0]:raise ValueError('Missing required fields column: '+c)
 grouped=collections.defaultdict(list);errors=[];coverage=collections.defaultdict(set);labels=collections.defaultdict(set);counts=collections.Counter();statuses=collections.defaultdict(collections.Counter)
 for i,r in enumerate(fields,2):
  rid=r['report_id'];field=r['field_name'];grouped[rid].append(r);coverage[field].add(rid);labels[field].add(r['field_label_raw']);counts[field]+=1;statuses[field][r.get('value_status','')]+=1
 docgroup=collections.defaultdict(list)
 for d in docs:docgroup[d['report_id']].append(d)
 names=sorted(counts,key=lambda x:(x not in DEFS,list(DEFS).index(x) if x in DEFS else x))
 unified=[]
 for rid,rows in sorted(grouped.items()):
  first=rows[0];record={c:first.get(c,'') for c in ID+PROV}
  for r in rows[1:]:
   for c in ID+PROV:
    if r.get(c,'')!=first.get(c,''):errors.append({'report_id':rid,'field_name':r['field_name'],'issue':'inconsistent_'+c,'detail':r.get(c,'')})
  by=collections.defaultdict(list)
  for r in rows:by[r['field_name']].append(r)
  for name in names:
   rr=by.get(name,[])
   if len(rr)>1:
    errors.append({'report_id':rid,'field_name':name,'issue':'duplicate_field','detail':str(len(rr))})
    # Preserve all in evidence; do not choose an arbitrary value.
    record[name]='';continue
   record[name]=rr[0]['value_text'] if rr else ''
  record['metadata_field_count']=len(rows)
  record['documentation_record_count']=len(docgroup[rid])
  unified.append(record)
 for rid,ds in docgroup.items():
  if rid not in grouped:errors.append({'report_id':rid,'field_name':'','issue':'documentation_without_metadata_report','detail':str(len(ds))})
 cols=ID+PROV+names+['metadata_field_count','documentation_record_count']
 write(out/'group1_unified.csv',unified,cols)
 write(out/'group1_field_evidence.csv',fields,list(fields[0]))
 write(out/'group1_documentation.csv',docs,list(docs[0]) if docs else ID+['documentation_category','text_raw'])
 dictionary=[]
 for n in names:
  definition,role=DEFS.get(n,('Unmapped field; manual definition required','unmapped'))
  dictionary.append({'group_id':'G1','field_name':n,'definition':definition,'data_type':'string','unit':'not_applicable','record_level':'report','role':role,'source_labels_json':json.dumps(sorted(labels[n]),ensure_ascii=False),'report_count':len(coverage[n]),'record_count':counts[n],'missing_report_count':len(grouped)-len(coverage[n]),'value_status_counts_json':json.dumps(statuses[n],sort_keys=True),'definition_status':'requires_source_verification' if role=='unmapped' else 'code_defined_not_manually_verified','source_table':'fields.csv','source_value_column':'value_text','provenance_table':'group1_field_evidence.csv'})
 # Full schema dictionary: exactly one entry for every unified CSV column.
 full=[]
 id_defs={'report_id':'Unique EDR report identifier','case_id':'CISS crash case identifier','vehicle_number':'Vehicle number associated with the report','export_basename':'Export file basename'}
 prov_defs={'source_format':'Selected original source format (CSV or PDF)','source_path':'Path of selected original source file','source_sha256':'SHA-256 checksum of selected original source file','rule_version':'Version of Group 1 extraction rules'}
 count_defs={'metadata_field_count':'Number of metadata evidence records for this report','documentation_record_count':'Number of linked documentation records for this report'}
 feature_dict={d['field_name']:d for d in dictionary}
 for c in cols:
  is_feature=c in feature_dict
  d=feature_dict.get(c,{})
  if c in id_defs: role='identifier'; desc=id_defs[c]; dtype='string'
  elif c in prov_defs: role='provenance'; desc=prov_defs[c]; dtype='string'
  elif c in count_defs: role='record_count'; desc=count_defs[c]; dtype='integer'
  else: role='extracted_feature'; desc=d['definition']; dtype=d['data_type']
  nonempty=sum(bool(str(r.get(c,'')).strip()) for r in unified)
  full.append({'group_id':'G1','column_name':c,'definition':desc,'data_type':dtype,'unit':d.get('unit','not_applicable'),'record_level':'report','column_role':role,'nonempty_report_count':nonempty,'empty_report_count':len(unified)-nonempty,'source_table':d.get('source_table','fields.csv' if is_feature else 'fields.csv / documentation.csv' if c=='documentation_record_count' else 'fields.csv'),'source_value_column':d.get('source_value_column','value_text' if is_feature else c),'source_labels_json':d.get('source_labels_json',''),'definition_status':d.get('definition_status','pipeline_defined_not_source_verified' if is_feature else 'pipeline_defined'),'provenance_table':'group1_field_evidence.csv' if is_feature else 'group1_field_evidence.csv / group1_documentation.csv' if c=='documentation_record_count' else 'group1_field_evidence.csv'})
 assert len(full)==len(cols)==len({d['column_name'] for d in full})
 assert [d['column_name'] for d in full]==cols
 write(out/'group1_data_dictionary.csv',full,list(full[0]))
 write(out/'group1_feature_dictionary.csv',dictionary,list(dictionary[0]))
 docdict=[]
 for cat,n in sorted(collections.Counter(d['documentation_category'] for d in docs).items()):
  docdict.append({'group_id':'G1','documentation_category':cat,'description':'Source introductory text retained verbatim; review for scientific meaning','record_level':'report_documentation_block','record_count':n,'report_count':len({d['report_id'] for d in docs if d['documentation_category']==cat}),'source_table':'documentation.csv','source_value_column':'text_raw','validation_status':'not_manually_verified'})
 write(out/'group1_documentation_dictionary.csv',docdict,list(docdict[0]) if docdict else ['group_id','documentation_category'])
 write(out/'group1_unification_exceptions.csv',errors,['report_id','field_name','issue','detail'])
 summary={'unique_reports':len(grouped),'unique_cases':len({r['case_id'] for r in fields}),'field_records':len(fields),'documentation_records':len(docs),'dictionary_fields':len(cols),'extracted_feature_fields':len(names),'dictionary_matches_unified_columns':True,'exceptions':len(errors),'input_files':{str(a.fields):hashlib.sha256(Path(a.fields).read_bytes()).hexdigest(),str(a.documentation):hashlib.sha256(Path(a.documentation).read_bytes()).hexdigest()},'notes':'Unification integrity only; source-level accuracy not established. Blank values do not distinguish absent from blank in wide view; consult evidence table.'}
 (out/'group1_unification_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
