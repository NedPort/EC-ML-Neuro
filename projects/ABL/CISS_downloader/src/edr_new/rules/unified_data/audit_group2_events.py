"""ABLs Group 2: conservative automated event-candidate identification audit.

Run: uv run --active python -m src.edr_new.rules.unified_data.audit_group2_events
Uses unified Group 2 v1 evidence; does NOT declare source labels to be unique physical events.
"""
import argparse
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_IN = ROOT / 'data/processed/edr_new/unified/group2'
DEFAULT_OUT = DEFAULT_IN / 'event_audit_v1'

def read(path):
    if not path.is_file():
        raise FileNotFoundError(f'Missing required file: {path}')
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')

def save(df, path):
    df.to_csv(path, index=False, encoding='utf-8-sig')

def check(df, cols, name):
    missing = sorted(set(cols) - set(df.columns))
    if missing:
        raise ValueError(f'{name}: missing columns {missing}')

def is_true(x):
    return str(x).strip().lower() in {'true','1','yes','y'}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', type=Path, default=DEFAULT_IN)
    p.add_argument('--output-dir', type=Path, default=DEFAULT_OUT)
    a = p.parse_args()
    inp, out = a.input_dir.resolve(), a.output_dir.resolve()
    print('ABLs Group 2 — Event candidate audit', flush=True)
    print(f'Input: {inp}\nOutput: {out}', flush=True)
    cand = read(inp/'group2_evidence_record_candidates.csv')
    summary = read(inp/'group2_evidence_summary_rows.csv')
    check(cand, ['report_id','record_candidate_id','record_label_raw','identity_status'], 'record_candidates')
    check(summary, ['report_id','summary_row_id','linked_record_candidate_id','link_status','link_candidate_count','reported_record_label','reported_trigger_reference','requires_review'], 'summary_rows')
    if cand['record_candidate_id'].eq('').any() or cand['record_candidate_id'].duplicated().any():
        raise ValueError('Candidate IDs must be nonempty and unique; inspect source before proceeding.')
    if cand['report_id'].eq('').any():
        raise ValueError('Blank report IDs in candidates.')
    if summary['summary_row_id'].eq('').any() or summary['summary_row_id'].duplicated().any():
        raise ValueError('Summary row IDs must be nonempty and unique.')
    out.mkdir(parents=True,exist_ok=True)
    ids = set(cand['record_candidate_id'])
    report_for_id = dict(zip(cand.record_candidate_id, cand.report_id))
    link_rows=[]
    for r in summary.to_dict('records'):
        cid=r['linked_record_candidate_id']; target_exists=cid in ids if cid else False
        same_report=bool(target_exists and report_for_id[cid]==r['report_id'])
        linked=r['link_status'].startswith('linked_')
        unique=r['link_candidate_count'].strip()=='1'
        review=is_true(r['requires_review'])
        if linked and target_exists and same_report and unique and not review:
            audit='supported_unique_source_link'
        elif linked and not same_report:
            audit='invalid_or_cross_report_link'
        elif linked:
            audit='linked_requires_review'
        else:
            audit='unlinked_or_ambiguous'
        link_rows.append({**r, 'audit_link_status':audit, 'target_exists':target_exists,'target_same_report':same_report})
    links=pd.DataFrame(link_rows)
    save(links,out/'group2_summary_link_audit.csv')
    link_groups={cid:grp for cid,grp in links[links.linked_record_candidate_id.ne('')].groupby('linked_record_candidate_id')}
    per_report=cand.groupby('report_id').size().to_dict()
    rows=[]
    for r in cand.to_dict('records'):
        cid=r['record_candidate_id']; g=link_groups.get(cid)
        supported=0 if g is None else int((g.audit_link_status=='supported_unique_source_link').sum())
        questionable=0 if g is None else int((g.audit_link_status!='supported_unique_source_link').sum())
        count=0 if g is None else len(g)
        # Supported summary association is NOT confirmation of unique physical event.
        if supported and not questionable:
            state='candidate_with_supported_summary_link'
        elif supported and questionable:
            state='candidate_with_mixed_link_evidence'
        elif questionable:
            state='candidate_with_uncertain_summary_link'
        else:
            state='candidate_without_summary_link'
        rows.append({**r, 'report_candidate_count':per_report[r['report_id']],
                     'linked_summary_row_count':count,'supported_summary_link_count':supported,
                     'questionable_summary_link_count':questionable,
                     'association_audit_status':state,
                     'distinct_physical_event_confirmed':'no',
                     'manual_event_identity_review':'pending'})
    audit=pd.DataFrame(rows)
    save(audit,out/'group2_record_candidate_event_audit.csv')
    sr=summary.groupby('report_id').size().to_dict()
    uncertain=links[links.audit_link_status!='supported_unique_source_link'].groupby('report_id').size().to_dict()
    rep=[]
    for report_id,grp in audit.groupby('report_id',sort=True):
        rep.append({'report_id':report_id,'case_id':grp.iloc[0].get('case_id',''),
                    'vehicle_number':grp.iloc[0].get('vehicle_number',''),
                    'export_basename':grp.iloc[0].get('export_basename',''),
                    'record_candidate_count':len(grp),
                    'summary_row_count':sr.get(report_id,0),
                    'uncertain_summary_link_count':uncertain.get(report_id,0),
                    'candidate_without_supported_link_count':int((grp.supported_summary_link_count==0).sum()),
                    'candidate_label_count':grp.record_label_raw.nunique(),
                    'event_identity_validated':'no'})
    reports=pd.DataFrame(rep)
    save(reports,out/'group2_report_event_overview.csv')
    # Queue prioritizes ambiguous associations and multiple candidates, but also provides a mix of cases.
    reports['review_priority_score']=(reports.uncertain_summary_link_count*10 +
                                     reports.candidate_without_supported_link_count*3 +
                                     (reports.record_candidate_count>1).astype(int)*2)
    reports['review_reason']=reports.apply(lambda r: '; '.join(x for x,flag in [
        ('uncertain summary association',r.uncertain_summary_link_count>0),
        ('candidate without supported summary link',r.candidate_without_supported_link_count>0),
        ('multiple candidates',r.record_candidate_count>1)] if flag) or 'baseline single-candidate review',axis=1)
    reports['manual_review_status']='Not Started'
    queue=reports.sort_values(['review_priority_score','record_candidate_count','report_id'],ascending=[False,False,True])
    save(queue,out/'group2_event_manual_review_queue.csv')
    # Source identity label repetition is a flag, not proof of duplicate physical events.
    dup=(cand.groupby(['report_id','record_label_raw']).size().reset_index(name='candidate_count'))
    save(dup[dup.candidate_count>1],out/'group2_repeated_labels_within_report.csv')
    counts={str(k):int(v) for k,v in audit.association_audit_status.value_counts().items()}
    link_counts={str(k):int(v) for k,v in links.audit_link_status.value_counts().items()}
    result={'candidate_rows':len(cand),'reports_with_candidates':len(reports),'summary_rows':len(summary),
            'candidate_audit_status_counts':counts,'summary_link_audit_counts':link_counts,
            'repeated_report_label_pairs':int((dup.candidate_count>1).sum()),
            'unique_physical_events_confirmed':0,
            'caution':'No unique physical event identities are asserted; summary links are source associations only. Review original CSV/PDF and section provenance before merging records.',
            'files':['group2_record_candidate_event_audit.csv','group2_summary_link_audit.csv','group2_report_event_overview.csv','group2_event_manual_review_queue.csv','group2_repeated_labels_within_report.csv']}
    (out/'group2_event_audit_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    main()
