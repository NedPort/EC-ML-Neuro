"""Group 6 v2.3: lossless long + report-wide unification and exact column dictionary.
Requires pandas. Run from CISS_downloader: uv run --active python src/edr_new/rules/unified_data/unify_group6.py
"""
import argparse, hashlib, json, re
from pathlib import Path
import pandas as pd

KEYS = ['report_id','case_id','vehicle_number','export_basename']
QC = ['has_unresolved_issues','unresolved_issue_count','unresolved_issue_types','case_has_unresolved_issues','case_unresolved_issue_count']

def slug(s):
    x=re.sub(r'[^a-z0-9]+','_',str(s).lower()).strip('_')
    return (x[:55].rstrip('_') or 'field')

def run(registry, values, unresolved, out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    r=pd.read_csv(registry,dtype=str,keep_default_na=False)
    v=pd.read_csv(values,dtype=str,keep_default_na=False)
    u=pd.read_csv(unresolved,dtype=str,keep_default_na=False)
    assert all(c in r for c in KEYS+['group6_technical_id','family','field_label_raw','field_value_raw'])
    assert all(c in u for c in KEYS+['audit_reason'])
    assert r.group6_technical_id.is_unique and v.group6_technical_id.is_unique
    missing=set(r.group6_technical_id)-set(v.group6_technical_id)
    if missing: raise ValueError(f'{len(missing)} v2.3 registry IDs missing from values file; supply matching values file')
    v=v[v.group6_technical_id.isin(r.group6_technical_id)]
    joined=r.merge(v,on='group6_technical_id',how='left',validate='one_to_one',suffixes=('','_values'))
    for c in ['field_value_raw','raw_unit']:
        if c+'_values' in joined:
            mismatches=(joined[c]!=joined[c+'_values']).sum()
            if mismatches: raise ValueError(f'{mismatches} mismatched {c} values; versions not compatible')
            joined=joined.drop(columns=c+'_values')
    # Explicitly preserve all records and report order; do not collapse duplicate labels.
    joined['_order']=range(len(joined))
    joined=joined.sort_values(KEYS+['_order'],kind='stable')
    joined['field_occurrence']=joined.groupby(KEYS+['family','field_label_raw'],dropna=False).cumcount()+1
    # Hash disambiguates labels which normalize to the same slug.
    pairs=joined[['family','field_label_raw']].drop_duplicates().sort_values(['family','field_label_raw'])
    mapping={}
    for fam,label in pairs.itertuples(index=False,name=None):
        digest=hashlib.sha1((fam+'\x1f'+label).encode()).hexdigest()[:8]
        mapping[(fam,label)]=f'g6_{slug(fam)}__{slug(label)}_{digest}'
    joined['feature_base']=[mapping[(f,l)] for f,l in zip(joined.family,joined.field_label_raw)]
    joined['feature_column']=joined.feature_base+'__'+joined.field_occurrence.astype(str)
    assert not joined.duplicated(KEYS+['feature_column']).any()
    report_meta=r[KEYS].drop_duplicates()
    if report_meta.report_id.duplicated().any(): raise ValueError('report_id maps to multiple case/vehicle identities')
    # Report-level and case-level QC are distinct; do not use issue flags as model predictors.
    ur=u.groupby('report_id',dropna=False).agg(unresolved_issue_count=('report_id','size'),unresolved_issue_types=('audit_reason',lambda x:'; '.join(sorted(set(filter(None,x)))))).reset_index()
    uc=u.groupby('case_id',dropna=False).size().rename('case_unresolved_issue_count').reset_index()
    report_meta=report_meta.merge(ur,on='report_id',how='left',validate='one_to_one').merge(uc,on='case_id',how='left',validate='many_to_one')
    for c in ['unresolved_issue_count','case_unresolved_issue_count']:
        report_meta[c]=report_meta[c].fillna(0).astype(int)
    report_meta['unresolved_issue_types']=report_meta.unresolved_issue_types.fillna('')
    report_meta['has_unresolved_issues']=report_meta.unresolved_issue_count.gt(0)
    report_meta['case_has_unresolved_issues']=report_meta.case_unresolved_issue_count.gt(0)
    report_meta=report_meta[KEYS+QC]
    joined=joined.merge(report_meta[['report_id']+QC],on='report_id',how='left',validate='many_to_one').drop(columns='_order')
    wide_values=joined.pivot(index='report_id',columns='feature_column',values='field_value_raw').reset_index()
    wide=report_meta.merge(wide_values,on='report_id',how='left',validate='one_to_one')
    assert len(joined)==len(r) and len(wide)==r.report_id.nunique()
    # Dictionary includes *every* wide column, including IDs and QC.
    details=joined[['feature_column','family','field_label_raw','raw_unit','source_section_heading']].drop_duplicates('feature_column')
    info=details.set_index('feature_column').to_dict('index')
    rows=[]
    for c in wide.columns:
        s=wide[c]
        if c in KEYS: role='join_key'
        elif c in QC: role='quality_control_exclude_from_predictors'
        else: role='candidate_review_required'
        d=info.get(c,{})
        nonempty=s.notna() & s.astype(str).ne('')
        rows.append({'column_name':c,'ml_role':role,'family':d.get('family',''),'source_label':d.get('field_label_raw',''),
                     'source_section_example':d.get('source_section_heading',''),'raw_unit_example':d.get('raw_unit',''),
                     'data_type':str(s.dtype),'non_null_count':int(nonempty.sum()),'unique_non_null_count':int(s[nonempty].nunique()),
                     'example_value':str(s[nonempty].iloc[0]) if nonempty.any() else '',
                     'selection_reason':'QC only; exclude from predictors' if c in QC else ('join/split only; exclude from predictors' if c in KEYS else 'Not yet selected for ML')})
    dictionary=pd.DataFrame(rows)
    assert list(dictionary.column_name)==list(wide.columns)
    joined.to_csv(out/'group6_unified_long.csv',index=False)
    wide.to_csv(out/'group6_unified_wide.csv',index=False)
    dictionary.to_csv(out/'group6_complete_dictionary.csv',index=False)
    u.to_csv(out/'group6_unresolved_issues.csv',index=False)
    # Explicit QC report, including unresolved reports absent from accepted registry.
    unmatched=u[~u.report_id.isin(r.report_id)]
    summary={'registry_rows':len(r),'long_rows':len(joined),'reports':len(wide),'cases':r.case_id.nunique(),
             'wide_columns':len(wide.columns),'dictionary_rows':len(dictionary),
             'unresolved_observations':len(u),'unresolved_reports':u.report_id.nunique(),
             'unresolved_cases':u.case_id.nunique(),'unresolved_reports_without_accepted_records':unmatched.report_id.nunique(),
             'duplicate_field_occurrences_preserved':int((joined.field_occurrence>1).sum()),
             'values_rows_ignored_not_in_registry':int(pd.read_csv(values,usecols=['group6_technical_id']).shape[0]-len(v)),
             'status':'unified_not_yet_manually_frozen'}
    (out/'group6_unification_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__ == '__main__':
    # Paths are reproducible and independent of the current working directory.
    PROJECT_ROOT = Path(__file__).resolve().parents[4]
    INPUT_DIR = PROJECT_ROOT / 'data' / 'processed' / 'edr_new' / 'group6_v2_3'
    OUTPUT_DIR = PROJECT_ROOT / 'data' / 'processed' / 'edr_new' / 'unified' / 'group6'

    REGISTRY = INPUT_DIR / 'technical_registry.csv'
    VALUES = INPUT_DIR / 'technical_values.csv'
    UNRESOLVED = INPUT_DIR / 'unresolved.csv'

    # Optional overrides; no command-line arguments are required.
    p = argparse.ArgumentParser(description='Reproducible Group 6 v2.3 unification')
    p.add_argument('--registry', type=Path, default=REGISTRY)
    p.add_argument('--values', type=Path, default=VALUES)
    p.add_argument('--unresolved', type=Path, default=UNRESOLVED)
    p.add_argument('--output-dir', type=Path, default=OUTPUT_DIR)
    a = p.parse_args()
    for label, path in [('registry', a.registry), ('values', a.values), ('unresolved', a.unresolved)]:
        if not path.is_file():
            raise FileNotFoundError(f'{label} not found: {path}\nEdit INPUT_DIR/filenames at the bottom of this script.')
    run(a.registry, a.values, a.unresolved, a.output_dir)
