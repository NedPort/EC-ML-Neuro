"""Conservative, non-destructive Group 2 unifier. Requires pandas."""
import argparse, json, re, shutil
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd

FILES = {'record_candidates':'record_candidates.csv','record_status':'record_status.csv','retrieval_status':'retrieval_status.csv','context_status':'context_status.csv','summary_rows':'summary_rows.csv','summary_cells':'summary_cells.csv','retrieval_event_descriptors':'retrieval_event_descriptors.csv','pdf_fields':'pdf_fields.csv','pdf_unresolved':'pdf_unresolved.csv'}
KEY=['report_id','case_id','vehicle_number','export_basename']
def clean(x): return '' if pd.isna(x) else str(x).strip()
def load(p): return pd.read_csv(p,dtype=str,keep_default_na=False,encoding='utf-8-sig')
def j(x): return json.dumps(x,ensure_ascii=False,separators=(',',':'))
def label(s):
    s=re.sub(r'[^a-z0-9]+','_',clean(s).lower()).strip('_')
    return s[:72] or 'unnamed'
def pack_fields(g):
    # Lossless per-source row details; do not overwrite duplicate field labels.
    return j([{'field_label_raw':r['field_label_raw'],'value_raw':r['value_raw'],'value_status':r['value_status'],'section_id':r['section_id'],'source_record':r['source_record'],'source_heading':r['source_heading'],'source_format':r['source_format']} for _,r in g.iterrows()])
def dictionary(df,level,source_notes):
    rows=[]
    for c in df.columns:
        vals=df[c].astype(str)
        rows.append({'group_id':'G2','table_level':level,'column_name':c,'definition':source_notes.get(c,'Source-derived value; inspect original evidence for precise semantics.'),'data_type':'json_array' if c.endswith('_json') else 'string','role':'identifier' if c in KEY or c=='record_candidate_id' else ('evidence' if c.endswith('_json') else 'context_or_feature_candidate'),'nonblank_rows':int(vals.ne('').sum()),'blank_rows':int(vals.eq('').sum()),'source_validation':'pending_manual_review'})
    return pd.DataFrame(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-dir',required=True);ap.add_argument('--output-dir',required=True);args=ap.parse_args()
    inp,out=Path(args.input_dir),Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    data={k:load(inp/v) for k,v in FILES.items()}
    for name,d in data.items():
        if not set(KEY).issubset(d):raise ValueError(f'{name} missing identity columns')
    cand=data['record_candidates'].copy()
    if cand.record_candidate_id.eq('').any() or cand.record_candidate_id.duplicated().any():raise ValueError('record candidate IDs blank or duplicated')
    if cand.report_id.eq('').any():raise ValueError('blank report IDs in candidates')
    reportmeta=pd.concat([d[KEY] for d in data.values()],ignore_index=True).drop_duplicates()
    conflicts=reportmeta.groupby('report_id',dropna=False)[KEY[1:]].nunique()
    if (conflicts>1).any().any():raise ValueError('Conflicting report_id identity metadata; review inputs')
    reports=reportmeta.drop_duplicates('report_id').sort_values('report_id').reset_index(drop=True)
    reports['record_candidate_count']=reports.report_id.map(cand.groupby('report_id').size()).fillna(0).astype(int).astype(str)
    records=cand.sort_values(['report_id','record_candidate_id']).reset_index(drop=True)
    notes={**{k:'Source report identity; retained for cross-group joins.' for k in KEY},'record_candidate_id':'Candidate ID only; does not prove event identity.','record_candidate_count':'Count of extracted candidate records per report.'}
    for name in ['retrieval_status','context_status','retrieval_event_descriptors','pdf_fields','pdf_unresolved','summary_rows','summary_cells','record_status']:
        d=data[name]
        counts=d.groupby('report_id').size()
        col=name+'_row_count';reports[col]=reports.report_id.map(counts).fillna(0).astype(int).astype(str)
        notes[col]=f'Number of original {name} evidence rows for this report.'
    # Record-level fields retained as JSON array to prevent silent collisions or overwriting duplicate labels.
    status=data['record_status']; valid=status[status.record_candidate_id.ne('')]
    known=set(cand.record_candidate_id)
    dangling=valid[~valid.record_candidate_id.isin(known)]
    matched=valid[valid.record_candidate_id.isin(known)]
    recordpack=matched.groupby('record_candidate_id',sort=False).apply(pack_fields,include_groups=False).to_dict()
    records['record_status_fields_json']=records.record_candidate_id.map(recordpack).fillna('[]')
    records['record_status_row_count']=records.record_candidate_id.map(matched.groupby('record_candidate_id').size()).fillna(0).astype(int).astype(str)
    notes['record_status_fields_json']='All record-status source field rows, with labels, values, and source references; duplicate labels preserved.'
    notes['record_status_row_count']='Count of source status rows explicitly associated with this candidate.'
    # Only explicitly linked summary rows may be assigned; preserve link status/method for adjudication.
    summaries=data['summary_rows']; linked=summaries[summaries.linked_record_candidate_id.isin(known) & summaries.linked_record_candidate_id.ne('')]
    linked=linked[linked.link_status.isin(['linked_exact_label_trigger','linked_unique_label'])]
    def summary_pack(g):
        return j([{'summary_row_id':r.summary_row_id,'reported_record_label':r.reported_record_label,'reported_trigger_reference':r.reported_trigger_reference,'row_values_json':r.row_values_json,'link_status':r.link_status,'link_method':r.link_method,'requires_review':r.requires_review} for r in g.itertuples(index=False)])
    packs={k:summary_pack(g) for k,g in linked.groupby('linked_record_candidate_id')}
    records['linked_summary_rows_json']=records.record_candidate_id.map(packs).fillna('[]')
    records['linked_summary_count']=records.record_candidate_id.map(linked.groupby('linked_record_candidate_id').size()).fillna(0).astype(int).astype(str)
    notes['linked_summary_rows_json']='Summary rows with explicit extraction links; link provenance included. Do not treat as independently validated event identity.'
    notes['linked_summary_count']='Number of summary rows explicitly linked to this candidate.'
    # Retrieval fields are report-scoped and remain in a lossless array, not a pivot with collisions.
    retrieval=data['retrieval_status'];retrieval_packs={k:pack_fields(g) for k,g in retrieval.groupby('report_id')}
    reports['retrieval_fields_json']=reports.report_id.map(retrieval_packs).fillna('[]')
    notes['retrieval_fields_json']='All retrieval-status source fields, with original labels, values, and provenance.'
    # Report-level descriptors are unlinked evidence; do not assign to candidate IDs.
    desc=data['retrieval_event_descriptors']
    desc_packs={k:j([{'descriptor_raw':r.descriptor_raw,'descriptor_normalized':r.descriptor_normalized,'descriptor_type':r.descriptor_type,'descriptor_subtype':r.descriptor_subtype,'record_storage_status':r.record_storage_status,'source_record':r.source_record} for r in g.itertuples(index=False)]) for k,g in desc.groupby('report_id')}
    reports['retrieval_descriptors_json']=reports.report_id.map(desc_packs).fillna('[]')
    notes['retrieval_descriptors_json']='Report retrieval descriptors; not assumed to identify specific record candidates.'
    # Evidence stays complete and unchanged in separately copied files.
    for name,d in data.items():d.to_csv(out/f'group2_evidence_{name}.csv',index=False,encoding='utf-8-sig')
    reports.to_csv(out/'group2_unified_reports.csv',index=False,encoding='utf-8-sig')
    records.to_csv(out/'group2_unified_records.csv',index=False,encoding='utf-8-sig')
    dr=dictionary(reports,'report',notes);dc=dictionary(records,'record_candidate',notes)
    dr.to_csv(out/'group2_reports_data_dictionary.csv',index=False,encoding='utf-8-sig')
    dc.to_csv(out/'group2_records_data_dictionary.csv',index=False,encoding='utf-8-sig')
    exceptions=[]
    for r in dangling.itertuples(index=False):exceptions.append({'type':'record_status_unknown_candidate','report_id':r.report_id,'record_candidate_id':r.record_candidate_id,'detail':r.field_label_raw})
    for r in summaries.itertuples(index=False):
        if r.linked_record_candidate_id not in known or r.link_status not in ['linked_exact_label_trigger','linked_unique_label']:
            exceptions.append({'type':'summary_not_safely_linked','report_id':r.report_id,'record_candidate_id':r.linked_record_candidate_id,'detail':r.link_status})
    for r in data['pdf_unresolved'].itertuples(index=False):exceptions.append({'type':'pdf_unresolved','report_id':r.report_id,'record_candidate_id':r.record_candidate_id,'detail':r.reason})
    pd.DataFrame(exceptions,columns=['type','report_id','record_candidate_id','detail']).to_csv(out/'group2_review_queue.csv',index=False,encoding='utf-8-sig')
    summary={'input_rows':{k:len(v) for k,v in data.items()},'report_rows':len(reports),'record_candidate_rows':len(records),'report_dictionary_columns':len(dr),'record_dictionary_columns':len(dc),'dictionaries_match_columns':list(dr.column_name)==list(reports.columns) and list(dc.column_name)==list(records.columns),'record_status_rows_with_unknown_candidate':len(dangling),'linked_summary_rows':len(linked),'unlinked_or_uncertain_summary_rows':len(summaries)-len(linked),'pdf_unresolved_rows':len(data['pdf_unresolved']),'review_queue_rows':len(exceptions),'notes':['Original files remain unchanged.','Record status and retrieval status values are kept as source-faithful JSON arrays, not forced into one scalar per field.','PDF fields are preserved as evidence and not automatically promoted to standardized ML predictors.','Record candidates are not necessarily unique validated events.','Report IDs may be different across extraction groups; cross-group joins require validation.']}
    (out/'group2_unification_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
