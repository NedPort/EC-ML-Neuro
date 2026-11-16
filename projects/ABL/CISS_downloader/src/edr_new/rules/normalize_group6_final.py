"""Conservative Group 6 normalization. Run from CISS_downloader project root.

Inputs are read-only. Output is written to group6/normalized/.
Requires pandas (available in the project's uv environment).
"""
from pathlib import Path
import json
import re
import pandas as pd

ROOT = Path('data/processed/edr_new/unified/group6')
REVIEW = ROOT / 'feature_name_review'
WIDE = ROOT / 'group6_unified_wide.csv'
DICTIONARY = ROOT / 'group6_complete_dictionary.csv'
MAPPING = REVIEW / 'group6_conservative_mapping.csv'
MERGES = REVIEW / 'group6_merge_decisions.csv'
OUTPUT = ROOT / 'normalized'


def filled(s):
    return s.fillna('').astype('string').str.strip().ne('')


def main():
    for path in (WIDE, DICTIONARY, MAPPING, MERGES):
        if not path.is_file():
            raise FileNotFoundError(f'Required input missing: {path}')

    wide = pd.read_csv(WIDE, dtype='string', keep_default_na=False)
    dictionary = pd.read_csv(DICTIONARY, dtype='string', keep_default_na=False)
    mapping = pd.read_csv(MAPPING, dtype='string', keep_default_na=False)
    merges = pd.read_csv(MERGES, dtype='string', keep_default_na=False)

    original = wide.columns.tolist()
    if len(original) != 665 or len(set(original)) != 665:
        raise ValueError(f'Expected 665 unique original columns; got {len(original)}')
    if len(dictionary) != 665 or set(dictionary.column_name) != set(original):
        raise ValueError('Original dictionary does not match the original wide columns')
    if len(mapping) != 665 or set(mapping.original_column) != set(original) or mapping.original_column.duplicated().any():
        raise ValueError('Mapping does not contain exactly one entry for each original column')
    if len(merges) != 31:
        raise ValueError(f'Expected 31 merge candidates; found {len(merges)}')

    map_by_col = mapping.set_index('original_column')
    groups = {}
    used = set()
    audit = []
    for idx, row in merges.iterrows():
        cols = [x.strip() for x in row.original_columns.split('|')]
        if len(cols) < 2 or len(set(cols)) != len(cols):
            raise ValueError(f'Invalid merge group on row {idx + 2}')
        if not set(cols) <= set(original) or used.intersection(cols):
            raise ValueError(f'Missing or multiply grouped original columns on row {idx + 2}')
        used.update(cols)
        subset_map = map_by_col.loc[cols]
        if not (subset_map.action == 'PROPOSE_MERGE_REVIEW').all():
            raise ValueError(f'Merge columns not marked for review: {cols}')
        for key in ('family', 'context', 'occurrence_slot', 'cleaned_title'):
            if subset_map[key].nunique() != 1 or str(subset_map[key].iloc[0]) != str(row[key]):
                raise ValueError(f'Inconsistent {key} for merge group: {cols}')
        names = subset_map.suggested_feature_name.unique().tolist()
        if len(names) != 1:
            raise ValueError(f'Merge group has inconsistent target names: {cols}')
        target = names[0]
        if not target or target in groups:
            raise ValueError(f'Duplicate or blank target: {target}')
        groups[target] = cols

    expected_merge_cols = set(mapping.loc[mapping.action == 'PROPOSE_MERGE_REVIEW', 'original_column'])
    if used != expected_merge_cols:
        raise ValueError('Merge candidates and mapping disagree')

    # Use approved/provisional conservative targets for all feature columns.
    # Metadata keeps its original names. Each source column belongs to exactly one target.
    target_to_sources = {}
    for col in original:
        item = map_by_col.loc[col]
        target = col if item.action == 'KEEP_METADATA' else str(item.suggested_feature_name).strip()
        if not target:
            raise ValueError(f'Empty normalized name for {col}')
        target_to_sources.setdefault(target, []).append(col)

    if len(target_to_sources) != len(original) - sum(len(v)-1 for v in groups.values()):
        raise ValueError("Unexpected target count after initial conservative mapping")
    for target, sources in target_to_sources.items():
        if len(sources) > 1 and (target not in groups or set(groups[target]) != set(sources)):
            raise ValueError(f'Unapproved target collision: {target}')

    # Additional repeated-slot consolidation. Never collapse event-specific slots.
    # A repeated title is not enough: require identical source label/section,
    # same family/context, and positive, conflict-free within-report overlap.
    # Unknown context is permitted ONLY for the explicit repeated VIN label.
    extra_audit = []
    candidate_sets = {}
    for col in original:
        item = map_by_col.loc[col]
        if item.action == 'KEEP_METADATA':
            continue
        key = (str(item.family), str(item.context), str(item.cleaned_title),
               str(item.source_label).strip().casefold(),
               str(item.source_section).strip().casefold())
        candidate_sets.setdefault(key, []).append(col)

    for (family, context, title, label, section), cols in candidate_sets.items():
        if len(cols) < 2 or context == 'event':
            continue
        is_vin = (family == 'vehicle_identifier_technical' and
                  label == 'vehicle identification number (vin)')
        if context == 'unknown' and not is_vin:
            continue
        if context not in ('retrieval', 'other', 'unknown'):
            continue
        # Do not combine already distinct members of an approved group with
        # other targets; this pass only handles singleton columns.
        targets = [next(t for t, sources in target_to_sources.items() if c in sources)
                   for c in cols]
        if len(set(targets)) != len(targets) or any(len(target_to_sources[t]) != 1 for t in targets):
            continue
        part = wide[cols].apply(lambda s: s.str.strip().replace('', pd.NA))
        overlaps = part.notna().sum(axis=1).ge(2)
        conflicts = overlaps & part.nunique(axis=1, dropna=True).gt(1)
        if not overlaps.any() or conflicts.any():
            continue
        # Merge only genuinely repeated occurrence slots, not multiple
        # unrelated labels sharing the same title.
        slots = {str(map_by_col.loc[c, 'occurrence_slot']) for c in cols}
        if len(slots) < 2:
            continue
        first_target = targets[0]
        target_to_sources[first_target] = cols
        for t in targets[1:]:
            del target_to_sources[t]
        extra_audit.append({
            'normalized_column': first_target,
            'original_columns': ' | '.join(cols),
            'source_column_count': len(cols),
            'rows_with_any_value': int(part.notna().any(axis=1).sum()),
            'rows_with_overlap': int(overlaps.sum()),
            'rows_with_conflict': 0,
            'status': 'PROVISIONAL_REPEATED_SLOT_MERGE',
        })

    normalized = pd.DataFrame(index=wide.index)
    for target, sources in target_to_sources.items():
        if len(sources) == 1:
            normalized[target] = wide[sources[0]]
            continue
        part = wide[sources].apply(lambda s: s.str.strip().replace('', pd.NA))
        conflicts = part.nunique(axis=1, dropna=True).gt(1)
        overlaps = part.notna().sum(axis=1).ge(2)
        audit.append({
            'normalized_column': target,
            'original_columns': ' | '.join(sources),
            'source_column_count': len(sources),
            'rows_with_any_value': int(part.notna().any(axis=1).sum()),
            'rows_with_overlap': int(overlaps.sum()),
            'rows_with_conflict': int(conflicts.sum()),
            'status': 'BLOCKED_CONFLICT' if conflicts.any() else 'PROVISIONAL_MERGE',
        })
        if conflicts.any():
            raise ValueError(f'Conflicting nonblank values in {target}: {int(conflicts.sum())} rows. No outputs written.')
        # Preserve original text; strip only for blank detection.
        value = wide[sources[0]].copy()
        for source in sources[1:]:
            value = value.mask(~filled(value), wide[source])
        normalized[target] = value

    # Repeated-slot merges are already included in the final target audit above.
    # Do not append them a second time; each target must appear once.
    if len({a["normalized_column"] for a in audit}) != len(audit):
        raise ValueError("Duplicate normalized targets in merge audit")
    if len(extra_audit) != 1 or extra_audit[0]["normalized_column"] not in {a["normalized_column"] for a in audit}:
        raise ValueError("Unexpected repeated-slot merge audit state")

    # Losslessness: every populated source value must match its output target.
    for target, sources in target_to_sources.items():
        for source in sources:
            present = filled(wide[source])
            mismatch = present & wide[source].str.strip().ne(normalized[target].str.strip())
            if mismatch.any():
                raise ValueError(f'Value preservation failed: {source} -> {target}')
    if len(normalized) != len(wide):
        raise ValueError('Row count changed')

    dict_by_col = dictionary.set_index('column_name')
    dictionary_rows = []
    lineage_rows = []
    for target, sources in target_to_sources.items():
        entries = dict_by_col.loc[sources]
        if isinstance(entries, pd.Series):
            entries = entries.to_frame().T
        primary = entries.iloc[0].to_dict()
        primary['column_name'] = target
        primary['non_null_count'] = str(int(filled(normalized[target]).sum()))
        vals = normalized[target][filled(normalized[target])]
        primary['unique_non_null_count'] = str(int(vals.nunique()))
        primary['source_label'] = ' | '.join(dict.fromkeys(x for x in entries.source_label if x))
        primary['source_section_example'] = ' | '.join(dict.fromkeys(x for x in entries.source_section_example if x))
        primary['selection_reason'] = 'PROVISIONAL_MERGE' if len(sources) > 1 else primary.get('selection_reason', '')
        dictionary_rows.append(primary)
        for source in sources:
            lineage_rows.append({
                'original_column': source, 'normalized_column': target,
                'action': 'PROVISIONAL_MERGE' if len(sources) > 1 else 'RENAME_OR_KEEP',
                'source_label': str(dict_by_col.loc[source, 'source_label']),
                'source_section': str(dict_by_col.loc[source, 'source_section_example']),
            })

    nd = pd.DataFrame(dictionary_rows)
    if nd.column_name.tolist() != normalized.columns.tolist():
        raise ValueError('Normalized dictionary columns do not match normalized wide data')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(OUTPUT / 'group6_normalized_wide.csv', index=False)
    nd.to_csv(OUTPUT / 'group6_normalized_dictionary.csv', index=False)
    pd.DataFrame(lineage_rows).to_csv(OUTPUT / 'group6_column_lineage.csv', index=False)
    pd.DataFrame(audit).to_csv(OUTPUT / 'group6_merge_audit.csv', index=False)
    summary = {
        'original_rows': len(wide), 'normalized_rows': len(normalized),
        'original_columns': len(original), 'normalized_columns': len(normalized.columns),
        'merged_groups': len(audit), 'source_columns_in_merged_groups': sum(len(v) for v in target_to_sources.values() if len(v)>1),
        'additional_repeated_slot_merges': len(extra_audit),
        'merge_overlap_rows': sum(a['rows_with_overlap'] for a in audit),
        'merge_conflict_rows': sum(a['rows_with_conflict'] for a in audit),
        'status': 'PROVISIONAL_PENDING_MANUAL_SOURCE_VALIDATION',
        'original_files_modified': False,
    }
    (OUTPUT / 'group6_normalization_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(f'Outputs: {OUTPUT}')


if __name__ == '__main__':
    main()
