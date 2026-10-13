"""Evaluate Group 2 candidate extraction; proposed routing is not semantic validation."""
import argparse,csv,json,re
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
csv.field_size_limit(10000000)
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,cols):
 tmp=p.with_suffix(p.suffix+'.part')
 with tmp.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
 tmp.replace(p)
def route(label):
 t=label.lower()
 if re.search(r'warning lamp|indicator|dtc|diagnostic|part number|serial number|supplier|configuration|vin|voltage|software|hardware|system type|component identifier|traceability',t):return 'group6_diagnostics_configuration_candidate','indicator_diagnostic_or_module_identifier'
 if re.search(r'event record type|algorithm active|event severity status|life\s*time counter|operation.*time|record.*status|recording status|complete.*record|record.*complete|locked|freeze signal|data (?:sent|recorded|available)|concurrent event|event (?:counter|number|type)|crash type|trg count|number of events|ignition cycle|timer|time from event|time from pre-crash|linked.*page|event recorded last',t):return 'group2_status_context','record_status_counter_or_reference_pattern'
 if re.search(r'air.?bag|pretension|belt|restraint|occupan|seat|deployment loop|squib|loop commanded|roof rail|head curtain',t):return 'group3_restraint_candidate','restraint_or_occupant_status_pattern'
 if re.search(r'delta.?v|velocity change|acceleration|roll angle|roll rate|angular velocity|pressure',t):return 'group5_crash_measurement_candidate','measurement_word_requires_definition_review'
 if re.search(r'speed|rpm|throttle|accelerator|brak|steer|gear|cruise|engine torque',t):return 'group4_vehicle_measurement_candidate','vehicle_parameter_requires_time_scope_review'
 return 'unclassified_requires_review','no_rule_matched'
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--input-directory',type=Path,default=Path('data/processed/edr/group2_extract_v1'))
 ap.add_argument('--output-directory',type=Path,default=Path('data/processed/edr/group2_field_audit_v2'))
 a=ap.parse_args();src=a.input_directory;out=a.output_directory
 if src.resolve()==out.resolve():ap.error('Use a separate output directory')
 fields=read(src/'status_fields_long.csv');sections=read(src/'section_evidence.csv');records=read(src/'record_candidates.csv');coverage=read(src/'report_coverage.csv')
 section_by_id={r['section_id']:r for r in sections};recordids={r['record_candidate_id'] for r in records}
 grouped=defaultdict(list);annotated=[];duplicate_groups=defaultdict(list)
 for r in fields:
  section=section_by_id[r['section_id']];group,reason=route(r['field_label_raw'])
  item={**r,'source_format':section['source_format'],'source_path':section['source_path'],'source_heading':section['source_heading'],'proposed_group':group,'routing_reason':reason,'routing_status':'provisional_requires_review'}
  annotated.append(item);grouped[r['field_label_raw']].append(item)
  if r['record_candidate_id']:duplicate_groups[r['record_candidate_id'],r['field_label_raw']].append(r)
 registry=[]
 for label,rows in sorted(grouped.items()):
  vals=list(dict.fromkeys(r['value_raw'] for r in rows))[:5];group,reason=route(label)
  registry.append({'field_label_raw':label,'proposed_group':group,'routing_reason':reason,'observation_count':len(rows),'report_count':len({r['report_id'] for r in rows}),'scopes_json':json.dumps(sorted({r['scope_candidate'] for r in rows})),'value_status_counts_json':json.dumps(dict(Counter(r['value_status'] for r in rows))),'example_values_json':json.dumps(vals,ensure_ascii=False),'example_case_id':rows[0]['case_id'],'example_vehicle_number':rows[0]['vehicle_number'],'source_heading':rows[0]['source_heading'],'routing_status':'provisional_requires_review'})
 repeats=[]
 for (rid,label),rows in duplicate_groups.items():
  if len(rows)>1:repeats.append({'record_candidate_id':rid,'field_label_raw':label,'observation_count':len(rows),'distinct_raw_value_count':len({r['value_raw'] for r in rows}),'case_id':rows[0]['case_id'],'vehicle_number':rows[0]['vehicle_number'],'section_ids_json':json.dumps([r['section_id'] for r in rows]),'values_json':json.dumps([r['value_raw'] for r in rows],ensure_ascii=False),'interpretation':'repeated_evidence_not_automatically_error'})
 queue=[]
 for s in sections:
  if s['scope_candidate'] not in ['reported_record_candidate','retrieval_level','module_level'] or s['source_format']=='pdf' or s['availability']=='empty':
   queue.append({k:s[k] for k in ['report_id','case_id','vehicle_number','section_id','source_format','source_path','source_heading','scope_candidate','availability','source_page','source_record','issue']})
 boundary=[]
 for s in sections:
  if s['availability']=='empty':
   suspected_intro=s['source_format']=='csv' and bool(re.fullmatch(r'Event Record \d+(?:\s*\([^)]*\))?',s['source_heading'],re.I)) and s['source_record'] in ['13','15']
   boundary.append({**{k:s[k] for k in ['report_id','case_id','vehicle_number','section_id','source_heading','source_record','source_end_record']},'boundary_assessment':'suspected_intro_continuation_not_body_section' if suspected_intro else 'empty_body_section_requires_original_check','assessment_status':'provisional_source_check_required','source_rows_json':s['source_rows_json']})
 out.mkdir(parents=True,exist_ok=True)
 write(out/'empty_section_boundary_review.csv',boundary,list(boundary[0]) if boundary else ['section_id'])

 write(out/'field_registry.csv',registry,list(registry[0]) if registry else ['field_label_raw'])
 write(out/'fields_routed_long.csv',annotated,list(annotated[0]) if annotated else ['field_label_raw'])
 write(out/'repeated_record_fields.csv',repeats,list(repeats[0]) if repeats else ['record_candidate_id','field_label_raw'])
 write(out/'section_review_queue.csv',queue,list(queue[0]) if queue else ['section_id'])
 summary={'created_at':datetime.now(timezone.utc).isoformat(),'reports':len(coverage),'field_observations':len(fields),'distinct_field_labels':len(registry),'proposed_group_counts':dict(Counter(r['proposed_group'] for r in annotated)),'repeated_record_field_groups':len(repeats),'section_review_queue':len(queue),'missing_record_links':sum(bool(s['record_candidate_id']) and s['record_candidate_id'] not in recordids for s in sections),'scope':'Audits existing candidates without reparsing sources. Routing rules are provisional. Repeated values may describe different references; no deletion, conversion or automatic conflict resolution. PDF structured extraction and summary-table record identities remain pending.'}
 p=out/'metadata.json.part';p.write_text(json.dumps(summary,indent=2),encoding='utf-8');p.replace(out/'metadata.json');print(json.dumps(summary,indent=2));print(f'Outputs: {out}')
if __name__=='__main__':main()
