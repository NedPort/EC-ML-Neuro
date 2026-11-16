"""Build conservative Group 6 name mappings from the original review and dictionary.
Run from project root: uv run python src/edr_new/rules/unified_data/build_group6_mapping.py
No original data is changed. Outputs CSVs under group6/feature_name_review.
"""
from pathlib import Path
import csv, re, collections

ROOT=Path('data/processed/edr_new/unified/group6')
IN=ROOT/'feature_name_review'/'group6_alphabetical_feature_review.csv'
DICT=ROOT/'group6_complete_dictionary.csv'
OUT=ROOT/'feature_name_review'

def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,fields):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def slug(s):
    s=re.sub(r'[^a-z0-9]+','_',s.casefold()).strip('_')
    return s or 'unnamed'
def context(x):
    h=x['context_hint']
    return {'event_review_specific_event':'event','retrieval_or_download':'retrieval','other_review':'other','unknown':'unknown'}.get(h,'unknown')
def occurrence(s):
    m=re.search(r'__(\d+)$',s)
    return int(m.group(1)) if m else 0

def main():
    review=read(IN);dictionary=read(DICT)
    d={x['column_name']:x for x in dictionary}
    assert len(review)==len(dictionary)==665 and len(d)==665
    assert {x['column_name'] for x in review}==set(d)
    # Same title and context alone is insufficient: repeated occurrence slots are distinct.
    groups=collections.defaultdict(list)
    for x in review:
        if x['is_metadata'].lower()=='true':continue
        groups[(slug(x['cleaned_title']),context(x),occurrence(x['column_name']),x['family'])].append(x)
    result=[]
    for x in review:
        meta=x['is_metadata'].lower()=='true'; ctx=context(x); occ=occurrence(x['column_name'])
        key=(slug(x['cleaned_title']),ctx,occ,x['family'])
        peers=groups.get(key,[])
        # Never silently merge: even obvious label aliases are suggestions until
        # conflicts are checked against the original wide table.
        action='KEEP_METADATA' if meta else ('PROPOSE_MERGE_REVIEW' if len(peers)>1 else 'KEEP_DISTINCT')
        proposed=x['column_name'] if meta else f"g6_{slug(x['family'])}__{key[0]}__{ctx}__{occ}"
        result.append({
          'cleaned_title':x['cleaned_title'], 'original_column':x['column_name'],
          'source_label':x['source_label'], 'source_section':x['source_section_example'],
          'context':ctx,'occurrence_slot':occ,'family':x['family'],
          'non_null_count':x['non_null_count'],'example_value':x['example_value'],
          'candidate_group_id':x['candidate_group_id'],
          'same_title_context_slot_count':len(peers),
          'suggested_feature_name':proposed,'action':action,
          'review_decision':'','approved_feature_name':'','notes':''})
    fields=list(result[0]);write(OUT/'group6_conservative_mapping.csv',result,fields)
    decisions=[]
    for key,items in sorted(groups.items()):
        if len(items)<2:continue
        decisions.append({'cleaned_title':items[0]['cleaned_title'],'context':key[1],
         'occurrence_slot':key[2],'family':key[3],'candidate_columns':len(items),
         'original_columns':' | '.join(x['column_name'] for x in items),
         'source_labels':' | '.join(dict.fromkeys(x['source_label'] for x in items)),
         'source_sections':' | '.join(dict.fromkeys(x['source_section_example'] for x in items)),
         'decision':'','notes':''})
    if decisions:write(OUT/'group6_merge_decisions.csv',decisions,list(decisions[0]))
    print(f'Original columns: {len(result)}; proposed same-context/slot groups: {len(decisions)}; columns involved: {sum(int(x["candidate_columns"]) for x in decisions)}')
    print('Wrote:',OUT/'group6_conservative_mapping.csv', 'and',OUT/'group6_merge_decisions.csv')
if __name__=='__main__':main()
