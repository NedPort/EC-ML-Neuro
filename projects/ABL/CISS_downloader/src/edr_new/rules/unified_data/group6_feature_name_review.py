"""Group 6 dictionary-first, human-approved feature naming review.

Run without arguments from anywhere. Requires pandas (already used in the project).
Does NOT modify unified data or automatically merge columns.
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd

# Script lives at src/edr_new/rules/unified_data/group6_feature_name_review.py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
GROUP6_DIR = PROJECT_ROOT / 'data' / 'processed' / 'edr_new' / 'unified' / 'group6'
DICTIONARY = GROUP6_DIR / 'group6_complete_dictionary.csv'
WIDE = GROUP6_DIR / 'group6_unified_wide.csv'
OUTPUT_DIR = GROUP6_DIR / 'feature_name_review'

# Conservative suggestions only: never automatically merge approximate matches.
SIMILARITY_THRESHOLD = 0.86


def normalize_label(value: object) -> str:
    s = str(value or '').casefold().strip()
    s = re.sub(r'(?<=\w)#(?=\d)', '', s)
    s = re.sub(r'\bno\.?\s*(?=\d)', 'number ', s)
    s = re.sub(r'\bnumber\s*(?=\d)', '', s)
    s = re.sub(r'[^\w]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def snake(value: str) -> str:
    return normalize_label(value).replace(' ', '_') or 'unnamed_feature'


def context_hint(section: object) -> str:
    s = normalize_label(section)
    if not s:
        return 'unknown'
    if 'retrieval' in s or 'download' in s:
        return 'retrieval_or_download'
    if 'event' in s or 'deployment' in s or 'non deployment' in s:
        return 'event_review_specific_event'
    return 'other_review'


def main() -> None:
    if not DICTIONARY.exists() or not WIDE.exists():
        raise FileNotFoundError(f'Expected inputs:\n{DICTIONARY}\n{WIDE}')
    dictionary = pd.read_csv(DICTIONARY, dtype=str, keep_default_na=False)
    wide_columns = pd.read_csv(WIDE, nrows=0).columns.tolist()
    required = {'column_name', 'source_label', 'family', 'source_section_example'}
    if not required.issubset(dictionary.columns):
        raise ValueError(f'Missing dictionary columns: {required - set(dictionary.columns)}')
    if dictionary['column_name'].duplicated().any():
        raise ValueError('Dictionary contains duplicate column_name entries')
    if set(dictionary.column_name) != set(wide_columns):
        raise ValueError('Dictionary and wide-data columns do not match exactly')

    rows = dictionary.copy()
    rows['is_metadata'] = ~rows.column_name.str.startswith('g6_')
    rows['cleaned_title'] = rows.apply(
        lambda r: normalize_label(r.source_label if r.source_label else r.column_name), axis=1)
    rows['proposed_short_name'] = rows.cleaned_title.map(snake)
    rows['context_hint'] = rows.source_section_example.map(context_hint)
    # Exact normalized titles form candidate groups, regardless of context;
    # context is displayed for human review and must be approved before merging.
    rows['candidate_group_id'] = rows.apply(
        lambda r: 'META' if r.is_metadata else 'G6_' + hashlib.sha1(r.cleaned_title.encode()).hexdigest()[:10], axis=1)
    counts = rows.loc[~rows.is_metadata].groupby('candidate_group_id').size()
    rows['group_size'] = rows.candidate_group_id.map(counts).fillna(1).astype(int)
    rows['proposed_action'] = rows.apply(
        lambda r: 'KEEP_METADATA' if r.is_metadata else
        ('REVIEW_POSSIBLE_DUPLICATE' if r.group_size > 1 else 'KEEP'), axis=1)
    rows['similar_titles_to_review'] = ''

    # Find near-duplicate titles within family, but do not assert equivalence.
    unique = rows.loc[~rows.is_metadata, ['family', 'cleaned_title']].drop_duplicates()
    for family, part in unique.groupby('family', sort=True):
        titles = sorted(part.cleaned_title.tolist())
        for i, a in enumerate(titles):
            matches = []
            for b in titles:
                if a == b or abs(len(a) - len(b)) > max(12, int(max(len(a), len(b)) * .25)):
                    continue
                if a[:1] != b[:1]:
                    continue
                if SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD:
                    matches.append(b)
            if matches:
                mask = (rows.family == family) & (rows.cleaned_title == a)
                rows.loc[mask, 'similar_titles_to_review'] = ' | '.join(matches[:8])

    # Editable columns: no automatic approvals.
    rows['review_decision'] = ''  # APPROVE / KEEP_SEPARATE / RENAME / NEEDS_REVIEW
    rows['approved_feature_name'] = ''
    rows['review_notes'] = ''
    rows = rows.sort_values(
        ['is_metadata', 'cleaned_title', 'context_hint', 'source_label', 'column_name'],
        ascending=[True, True, True, True, True], kind='stable')
    order = ['candidate_group_id', 'group_size', 'cleaned_title', 'source_label',
             'proposed_short_name', 'family', 'source_section_example', 'context_hint',
             'column_name', 'non_null_count', 'example_value', 'proposed_action',
             'similar_titles_to_review', 'review_decision', 'approved_feature_name',
             'review_notes', 'is_metadata']
    rows = rows[[c for c in order if c in rows.columns]]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / 'group6_alphabetical_feature_review.csv'
    rows.to_csv(output, index=False, encoding='utf-8-sig')
    print(f'Dictionary columns: {len(rows)}')
    print(f'Technical columns: {(~rows.is_metadata).sum()}')
    print(f'Exact-title candidate groups with >1 column: {(counts > 1).sum()}')
    print(f'Columns in those groups: {int(counts[counts > 1].sum())}')
    print(f'Output: {output}')
    print('No unified data changed. All suggested merges require manual approval.')


if __name__ == '__main__':
    main()
