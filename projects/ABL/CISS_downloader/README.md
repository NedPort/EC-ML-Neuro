# ABL CISS Data Pipeline

## Purpose

This project builds a reproducible, provenance-rich CISS crash database for
crash-mechanics and injury research.  It preserves raw CISS source records,
validates each downloaded case, creates linked master tables, and produces
task-specific machine-learning datasets without deleting the original evidence.

The initial modelling objective is event-level prediction of:

- total, longitudinal, and lateral Delta-V;
- principal direction of force (PDOF).

The pipeline is designed to scale from the current pilot cohort to thousands
of CISS cases.  CDRX, BLZ, and NIK files are preserved as assets when present;
their contents are not inferred or treated as extracted data until a validated
parser is available.

## Source-of-Truth Rule

Raw CISS records are the source of truth:

1. `metadata.json` and `export.xlsx` provide structured case, vehicle, event,
   roadway, damage, and CDC data.
2. `assets.json` and `navigation_tree.json` describe downloadable evidence and
   case structure.
3. `case_audit.json` validates and summarizes the raw records.  It does not
   replace them.

## Per-Case Raw Package

Each downloaded case is stored under `data/raw/<case_id>/`:

```text
data/raw/<case_id>/
  metadata.json
  export.xlsx
  assets.json
  navigation_tree.json
  manifest.json
```

The initial scalable acquisition profile downloads the core structured package
first.  Large images, sketches, and documents can be downloaded selectively
afterward for visual-evidence modelling.

## End-to-End Workflow

```text
CISS API case discovery
  -> select next unprocessed case IDs
  -> download core raw package
  -> validate files and create manifest
  -> run raw-data audit
  -> rebuild linked master tables
  -> rebuild Model 1 context and target cohorts
  -> report coverage, errors, and eligibility
```

The desired single-command interface is:

```powershell
uv run python main.py --limit 500 --profile core
```

This means: select the next 500 unprocessed eligible case IDs, download the
core package for each, resume safely after interruption, validate and audit
the completed cases, rebuild downstream tables, and write a run report.

`--limit 500` is a count of *new successfully processed cases*, not a fixed
case-ID range.  Existing completed cases are never overwritten.  Failed cases
are recorded for retry rather than silently skipped.

## Linked Master Tables

The pipeline uses linked tables rather than one universal table because CISS
has different entity levels.

| Table | Row unit | Current purpose |
|---|---|---|
| `case_index` | one crash case | case-level conditions, counts, audit status |
| `vehicle_index` | one vehicle within a case | intrinsic vehicle information |
| `vehicle_event_index` | one vehicle-event | collision, event, label, and evidence linkage |
| `occupant_index` | one occupant | future occupant modelling |
| `injury_index` | one injury record | future injury-outcome modelling |
| `edr_summary_index` | one EDR summary | future validated EDR linkage |
| `edr_event_index` | one EDR event | future event-specific EDR data |
| `asset_index` | one evidence asset | image, sketch, document, and file provenance |
| `feature_registry` | one data feature | semantic/model-use decision record |
| `audit_index` | one audit result | quality-control history |

Currently implemented and validated:

- `case_index`: 100 cases;
- `vehicle_index`: 196 vehicles;
- `vehicle_event_index`: 226 vehicle-events;
- event-coverage audit and data dictionaries;
- Model 1 context candidate and target-specific cohorts.

## Current Model 1 Data Views

The rich flat table is never overwritten.  It is the provenance-rich source
for task-specific views.

```text
model1_delta_v_pdof_candidate_flat.parquet
  -> model1_context_candidate_v1.parquet
  -> target-specific cohorts
```

The context-only view contains non-duplicated predictors from four groups:

1. subject-vehicle information;
2. collision configuration;
3. event sequence and crash complexity;
4. roadway and pre-impact context.

It excludes direct Delta-V/PDOF fields, CDC reconstruction outputs, post-crash
injury outcomes, narrative text, audit/path fields, and unvalidated EDR/VLM
features.  Post-crash damage and crush evidence will form a separate expanded
evidence view.

## Data-Growth Principle

Feature decisions must be scalable.  A feature that is constant or missing in
the current 100-case pilot is not deleted from the rich dataset.  It is marked
as inactive for the current cohort and re-evaluated after each larger batch.

One physical concept should have one canonical modelling predictor, while all
source-specific copies remain in the rich table for provenance and agreement
checks.  For example, a standardized Excel vehicle-specification measurement
may be the canonical predictor, while the equivalent metadata value remains
available for traceability.

## Download Profiles

### `core` profile (default for scaling)

Download and validate:

- case metadata;
- Excel export;
- navigation tree;
- asset registry;
- manifest and audit files.

This profile supports case, vehicle, vehicle-event, and initial Model 1 data
construction without downloading every image.

### `assets` profile (later)

Download selected evidence assets after the core package is valid.  This is for
post-crash damage, sketch, scene, and validated VLM evidence studies.

### `full` profile (later)

Download all eligible assets.  This profile should be used only after storage,
bandwidth, retry, and duplicate-handling behavior have been validated on
smaller batches.

## Required Run Ledger

Every batch run must produce a durable ledger containing:

- run ID and start/end time;
- requested number of cases;
- selected case IDs;
- completed, skipped, failed, and retryable case IDs;
- source-file availability;
- audit status counts;
- linked-table row counts;
- Model 1 target availability after rebuild.

This makes every download batch reproducible and prevents accidental duplicate
work.

## Safety Rules

- Never overwrite an existing validated raw package without an explicit
  refresh option.
- Write files atomically using temporary files before renaming.
- Record failures and continue the batch when safe.
- Validate Excel files before treating them as valid sources.
- Keep raw values and source copies; standardize into separate derived fields.
- Split machine-learning data by `case_id`, never by individual vehicle-event
  row.
- Do not use labels, label-derived fields, or CDC Delta-V/PDOF reconstruction
  outputs as Model 1 predictors.

## Next Implementation Step

Implement the orchestration entry point in `main.py` with:

```text
main.py
  --limit <number of new cases>
  --profile core|assets|full
  --resume
  --rebuild-linked-tables
  --rebuild-model1
```

Before writing that entry point, inspect the current case-search and downloader
modules so the orchestrator calls the existing API and storage code rather
than duplicating it.

uv run python pilot_main.py --discover-cases #
uv run python pilot_main.py --run --limit #
uv run python audit_all.py

# 1. Discover and download new cases
uv run python pilot_main.py --discover-cases 20 --headless
uv run python pilot_main.py --run --limit 20 --headless

# 2. Refresh all audits
uv run python audit_all.py

# 3. Rebuild the standardized vehicle-event base table
uv run python standardize_main.py --output-directory data/processed/standardized

# 4. Rebuild the rich evidence table
uv run python enrich_metadata_main.py
uv run python enrich_excel_main.py
uv run python enrich_evidence_main.py

# 5. Rebuild linked master tables
uv run python build_linked_tables_main.py

# 6. Rebuild Model 1 candidate flat table
uv run python Build_model1_flat_table.py

# 7. Refresh the Model 1 feature registry
uv run python build_model1_feature_registry.py

# 8. Rebuild the non-duplicated context-only Model 1 dataset
uv run python build_model1_context_view.py

# 9. Rebuild the four target-specific Model 1 cohorts
uv run python build_model1_target_cohorts.py

# 10. Refresh the feature-quality diagnostic
uv run python build_model1_feature_quality_audit.py

