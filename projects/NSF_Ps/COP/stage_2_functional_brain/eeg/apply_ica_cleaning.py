"""
Stage 2.5 - Apply manually reviewed ICA decisions.

This script:
1. Loads the annotated EEG.
2. Loads the existing fitted ICA model.
3. Loads the saved ICLabel/manual-review CSV.
4. Reads the FINAL ManualDecision column.
5. Verifies:
       44 KEEP
       84 REMOVE
       0 REVIEW
       0 UNDECIDED
6. Extracts and saves the 44 retained ICA source time series.
7. Removes the 84 manually rejected ICs from a COPY of the EEG.
8. Reconstructs and saves the cleaned sensor EEG.

IMPORTANT
---------
- ICA is NOT refitted.
- ICLabel is NOT rerun.
- The original annotated EEG is NOT overwritten.
- The original ICA model is NOT overwritten.
- Manual decisions are read directly from the saved CSV.
"""

from pathlib import Path

import mne
import pandas as pd


# =====================================================================
# Configuration
# =====================================================================

SUBJECT = "1"
SESSION = "0"
ACQUISITION = "train"
RUN = "0"

EXPECTED_N_COMPONENTS = 128
EXPECTED_KEEP = 44
EXPECTED_REMOVE = 84


# =====================================================================
# Project paths
# =====================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE_DIR = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "eeg"
)

PROCESSED_DIR = (
    BASE_DIR
    / "processed"
)

ICA_DIR = (
    BASE_DIR
    / "ica_results"
)


# =====================================================================
# Input files
# =====================================================================

RAW_PATH = (
    PROCESSED_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"hp-1Hz_annotated_raw.fif"
)

ICA_PATH = (
    ICA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"ica.fif"
)

# This is the ACTUAL CSV created by classify_ica.py
# and updated by inspect_ica.py during manual review.
ICLABEL_CSV = (
    ICA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"iclabel.csv"
)


# =====================================================================
# Output files
# =====================================================================

CLEAN_RAW_PATH = (
    PROCESSED_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"ica-clean_raw.fif"
)

KEEP_SOURCES_PATH = (
    ICA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"keep-ics_raw.fif"
)


# =====================================================================
# Helper
# =====================================================================

def print_header(title):

    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


# =====================================================================
# Check input files
# =====================================================================

print_header(
    "CHECKING INPUT FILES"
)

required_files = [
    RAW_PATH,
    ICA_PATH,
    ICLABEL_CSV,
]

for path in required_files:

    print(path)

    if not path.exists():

        raise FileNotFoundError(
            f"\nRequired file was not found:\n{path}"
        )

print()
print(
    "All required input files found."
)


# =====================================================================
# Load manual ICA decisions FIRST
# =====================================================================

print_header(
    "LOADING MANUAL ICA DECISIONS"
)

decisions = pd.read_csv(
    ICLABEL_CSV
)

print()
print(
    f"CSV rows: {len(decisions)}"
)

print()
print(
    "CSV columns:"
)

for column in decisions.columns:

    print(
        f"  - {column}"
    )


# =====================================================================
# Validate required decision columns
# =====================================================================

required_columns = {
    "IC",
    "IC_index",
    "Decision",
    "ManualDecision",
}


missing_columns = (
    required_columns
    - set(decisions.columns)
)


if missing_columns:

    raise RuntimeError(
        "\nManual review CSV is missing columns:\n"
        f"{sorted(missing_columns)}"
    )


# =====================================================================
# Normalize component indices
# =====================================================================

decisions[
    "IC_index"
] = pd.to_numeric(
    decisions[
        "IC_index"
    ],
    errors="raise",
).astype(int)


# =====================================================================
# Normalize manual decisions
# =====================================================================

decisions[
    "ManualDecision"
] = (
    decisions[
        "ManualDecision"
    ]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)


# =====================================================================
# Check number of rows
# =====================================================================

if len(decisions) != EXPECTED_N_COMPONENTS:

    raise RuntimeError(
        f"\nExpected {EXPECTED_N_COMPONENTS} rows "
        f"in the manual review CSV, "
        f"but found {len(decisions)}."
    )


# =====================================================================
# Check duplicate component indices
# =====================================================================

duplicate_mask = (
    decisions[
        "IC_index"
    ]
    .duplicated()
)


if duplicate_mask.any():

    duplicates = (
        decisions.loc[
            duplicate_mask,
            "IC_index",
        ]
        .tolist()
    )

    raise RuntimeError(
        f"\nDuplicate ICA indices found:\n"
        f"{duplicates}"
    )


# =====================================================================
# Verify all 0-127 components exist
# =====================================================================

expected_indices = set(
    range(
        EXPECTED_N_COMPONENTS
    )
)

actual_indices = set(
    decisions[
        "IC_index"
    ]
    .tolist()
)


missing_indices = sorted(
    expected_indices
    - actual_indices
)

extra_indices = sorted(
    actual_indices
    - expected_indices
)


if missing_indices:

    raise RuntimeError(
        "\nMissing ICA components in CSV:\n"
        f"{missing_indices}"
    )


if extra_indices:

    raise RuntimeError(
        "\nInvalid ICA component indices "
        "in CSV:\n"
        f"{extra_indices}"
    )


# =====================================================================
# Extract manual decisions
# =====================================================================

keep_ics = sorted(
    decisions.loc[
        decisions[
            "ManualDecision"
        ]
        == "KEEP",
        "IC_index",
    ]
    .tolist()
)


remove_ics = sorted(
    decisions.loc[
        decisions[
            "ManualDecision"
        ]
        == "REMOVE",
        "IC_index",
    ]
    .tolist()
)


review_ics = sorted(
    decisions.loc[
        decisions[
            "ManualDecision"
        ]
        == "REVIEW",
        "IC_index",
    ]
    .tolist()
)


undecided_ics = sorted(
    decisions.loc[
        decisions[
            "ManualDecision"
        ]
        == "",
        "IC_index",
    ]
    .tolist()
)


# =====================================================================
# Detect unexpected decision labels
# =====================================================================

valid_manual_labels = {
    "",
    "KEEP",
    "REMOVE",
    "REVIEW",
}


unexpected_labels = sorted(
    set(
        decisions[
            "ManualDecision"
        ]
        .unique()
    )
    - valid_manual_labels
)


if unexpected_labels:

    raise RuntimeError(
        "\nUnexpected ManualDecision values:\n"
        f"{unexpected_labels}"
    )


# =====================================================================
# Report final decisions
# =====================================================================

print_header(
    "FINAL MANUAL ICA DECISIONS"
)

print()
print(
    f"KEEP      : {len(keep_ics)}"
)

print(
    f"REMOVE    : {len(remove_ics)}"
)

print(
    f"REVIEW    : {len(review_ics)}"
)

print(
    f"UNDECIDED : {len(undecided_ics)}"
)


print()
print(
    f"KEEP ({len(keep_ics)}):"
)

print(
    keep_ics
)


print()
print(
    f"REMOVE ({len(remove_ics)}):"
)

print(
    remove_ics
)


# =====================================================================
# Strict validation BEFORE changing anything
# =====================================================================

print_header(
    "VALIDATING MANUAL REVIEW"
)


if review_ics:

    raise RuntimeError(
        "\nSome components are still REVIEW:\n"
        f"{review_ics}"
    )


if undecided_ics:

    raise RuntimeError(
        "\nSome components are still UNDECIDED:\n"
        f"{undecided_ics}"
    )


if len(keep_ics) != EXPECTED_KEEP:

    raise RuntimeError(
        f"\nExpected {EXPECTED_KEEP} KEEP components, "
        f"but found {len(keep_ics)}."
    )


if len(remove_ics) != EXPECTED_REMOVE:

    raise RuntimeError(
        f"\nExpected {EXPECTED_REMOVE} REMOVE components, "
        f"but found {len(remove_ics)}."
    )


if (
    len(keep_ics)
    + len(remove_ics)
    != EXPECTED_N_COMPONENTS
):

    raise RuntimeError(
        "\nKEEP + REMOVE does not equal "
        f"{EXPECTED_N_COMPONENTS}."
    )


overlap = sorted(
    set(keep_ics)
    & set(remove_ics)
)


if overlap:

    raise RuntimeError(
        "\nComponents appear in both "
        "KEEP and REMOVE:\n"
        f"{overlap}"
    )


print()
print(
    "Manual review is internally consistent."
)

print(
    f"{len(keep_ics)} KEEP + "
    f"{len(remove_ics)} REMOVE = "
    f"{EXPECTED_N_COMPONENTS} components."
)


# =====================================================================
# Load annotated EEG
# =====================================================================

print_header(
    "LOADING ANNOTATED EEG"
)


raw = mne.io.read_raw_fif(
    RAW_PATH,
    preload=True,
    verbose=False,
)


print()
print(
    raw
)


print()
print(
    f"Channels      : "
    f"{len(raw.ch_names)}"
)

print(
    f"Samples       : "
    f"{raw.n_times:,}"
)

print(
    f"Sampling rate : "
    f"{raw.info['sfreq']} Hz"
)

print(
    f"Duration      : "
    f"{raw.n_times / raw.info['sfreq'] / 60:.2f} min"
)

print(
    f"Annotations   : "
    f"{len(raw.annotations)}"
)


# =====================================================================
# Load existing ICA
# =====================================================================

print_header(
    "LOADING EXISTING ICA"
)


ica = mne.preprocessing.read_ica(
    ICA_PATH,
    verbose=False,
)


print()
print(
    ica
)


print()
print(
    f"ICA components : "
    f"{ica.n_components_}"
)

print(
    f"Current exclusions before cleaning: "
    f"{ica.exclude}"
)


if ica.n_components_ != EXPECTED_N_COMPONENTS:

    raise RuntimeError(
        f"\nExpected {EXPECTED_N_COMPONENTS} "
        f"ICA components, but found "
        f"{ica.n_components_}."
    )


# =====================================================================
# Verify ICA / Raw channels
# =====================================================================

print_header(
    "VERIFYING ICA / RAW CHANNELS"
)


if list(
    ica.ch_names
) != list(
    raw.ch_names
):

    raise RuntimeError(
        "\nICA and Raw channel names/order "
        "do not match."
    )


print()
print(
    "ICA and Raw channel names/order "
    "match exactly."
)


# =====================================================================
# Extract ALL ICA source signals
# =====================================================================

print_header(
    "EXTRACTING ICA SOURCE SIGNALS"
)


ica_sources = (
    ica.get_sources(
        raw
    )
)


print()
print(
    ica_sources
)


source_shape = (
    len(
        ica_sources.ch_names
    ),
    ica_sources.n_times,
)


print()
print(
    f"ICA source matrix shape: "
    f"{source_shape}"
)


if len(
    ica_sources.ch_names
) != EXPECTED_N_COMPONENTS:

    raise RuntimeError(
        "\nICA source object does not "
        "contain 128 components."
    )


# =====================================================================
# Determine names of KEEP components
# =====================================================================

keep_channel_names = [
    ica_sources.ch_names[
        index
    ]
    for index in keep_ics
]


print()
print(
    "KEEP ICA source channels:"
)

print(
    keep_channel_names
)


# =====================================================================
# Create retained source dataset
# =====================================================================

print_header(
    "CREATING RETAINED ICA SOURCE DATASET"
)


keep_sources = (
    ica_sources.copy()
    .pick(
        keep_channel_names
    )
)


print()
print(
    keep_sources
)


print()
print(
    f"Retained ICA components : "
    f"{len(keep_sources.ch_names)}"
)

print(
    f"Samples                 : "
    f"{keep_sources.n_times:,}"
)

print(
    f"Sampling rate           : "
    f"{keep_sources.info['sfreq']} Hz"
)


if len(
    keep_sources.ch_names
) != EXPECTED_KEEP:

    raise RuntimeError(
        "\nRetained source dataset "
        "does not contain 44 ICs."
    )


if keep_sources.n_times != raw.n_times:

    raise RuntimeError(
        "\nRetained source time axis "
        "does not match original EEG."
    )


# =====================================================================
# Save retained ICA sources
# =====================================================================

print_header(
    "SAVING RETAINED ICA SOURCES"
)


keep_sources.save(
    KEEP_SOURCES_PATH,
    overwrite=True,
)


print()
print(
    f"Saved retained ICA sources:\n"
    f"{KEEP_SOURCES_PATH}"
)


# =====================================================================
# Prepare ICA exclusion
# =====================================================================

print_header(
    "PREPARING ICA EXCLUSION"
)


print()
print(
    "Components marked for removal:"
)

print(
    remove_ics
)


# Set exclusions in memory only.
# The original ICA file is NOT overwritten.

ica.exclude = list(
    remove_ics
)


print()
print(
    f"ica.exclude now contains "
    f"{len(ica.exclude)} components."
)


if sorted(
    ica.exclude
) != remove_ics:

    raise RuntimeError(
        "\nica.exclude does not match "
        "the manual REMOVE list."
    )


# =====================================================================
# Reconstruct cleaned sensor EEG
# =====================================================================

print_header(
    "RECONSTRUCTING CLEANED SENSOR EEG"
)


# IMPORTANT:
# Work on a COPY.
#
# raw remains the original annotated EEG
# loaded into memory.

raw_clean = (
    raw.copy()
)


ica.apply(
    raw_clean,
    exclude=remove_ics,
    verbose=True,
)


print()
print(
    "ICA reconstruction complete."
)


# =====================================================================
# Verify cleaned EEG structure
# =====================================================================

print_header(
    "VERIFYING CLEANED EEG"
)


print()
print(
    raw_clean
)


print()
print(
    f"Channels      : "
    f"{len(raw_clean.ch_names)}"
)

print(
    f"Samples       : "
    f"{raw_clean.n_times:,}"
)

print(
    f"Sampling rate : "
    f"{raw_clean.info['sfreq']} Hz"
)

print(
    f"Duration      : "
    f"{raw_clean.n_times / raw_clean.info['sfreq'] / 60:.2f} min"
)

print(
    f"Annotations   : "
    f"{len(raw_clean.annotations)}"
)


# =====================================================================
# Structural checks
# =====================================================================

if raw_clean.n_times != raw.n_times:

    raise RuntimeError(
        "\nSample count changed during "
        "ICA reconstruction."
    )


if raw_clean.ch_names != raw.ch_names:

    raise RuntimeError(
        "\nEEG channel order changed during "
        "ICA reconstruction."
    )


if raw_clean.info["sfreq"] != raw.info["sfreq"]:

    raise RuntimeError(
        "\nSampling rate changed during "
        "ICA reconstruction."
    )


if len(
    raw_clean.annotations
) != len(
    raw.annotations
):

    raise RuntimeError(
        "\nAnnotation count changed during "
        "ICA reconstruction."
    )


print()
print(
    "Sample count preserved."
)

print(
    "Channel order preserved."
)

print(
    "Sampling rate preserved."
)

print(
    "Annotations preserved."
)


# =====================================================================
# Save cleaned EEG
# =====================================================================

print_header(
    "SAVING CLEANED SENSOR EEG"
)


raw_clean.save(
    CLEAN_RAW_PATH,
    overwrite=True,
)


print()
print(
    f"Saved cleaned EEG:\n"
    f"{CLEAN_RAW_PATH}"
)


# =====================================================================
# Verify output files exist
# =====================================================================

print_header(
    "VERIFYING SAVED OUTPUTS"
)


if not CLEAN_RAW_PATH.exists():

    raise RuntimeError(
        "\nCleaned EEG file was not saved."
    )


if not KEEP_SOURCES_PATH.exists():

    raise RuntimeError(
        "\nKEEP-IC source file was not saved."
    )


print()
print(
    "Cleaned EEG file exists."
)

print(
    "Retained ICA source file exists."
)


# =====================================================================
# Final summary
# =====================================================================

print_header(
    "ICA CLEANING COMPLETE"
)


print()
print(
    "ICA decomposition:"
)

print(
    f"  Total components : "
    f"{EXPECTED_N_COMPONENTS}"
)

print()
print(
    "Final manual decisions:"
)

print(
    f"  KEEP             : "
    f"{len(keep_ics)}"
)

print(
    f"  REMOVE           : "
    f"{len(remove_ics)}"
)

print(
    f"  REVIEW           : "
    f"{len(review_ics)}"
)

print(
    f"  UNDECIDED        : "
    f"{len(undecided_ics)}"
)


print()
print(
    "Output 1 — Cleaned sensor EEG:"
)

print(
    CLEAN_RAW_PATH
)


print()
print(
    "Output 2 — Retained ICA source signals:"
)

print(
    KEEP_SOURCES_PATH
)


print()
print(
    "Retained ICA source matrix:"
)

print(
    f"  Components : "
    f"{len(keep_sources.ch_names)}"
)

print(
    f"  Samples    : "
    f"{keep_sources.n_times:,}"
)


print()
print("=" * 72)
print("IMPORTANT")
print("=" * 72)

print()
print(
    "The original annotated EEG was NOT overwritten."
)

print(
    "The original fitted ICA model was NOT overwritten."
)

print(
    "ICA was NOT refitted."
)

print(
    "ICLabel was NOT rerun."
)

print()
print(
    "The cleaned EEG contains the reconstructed "
    "sensor signals after removing the 84 manually "
    "rejected ICA components."
)

print()
print(
    "The retained source file contains the continuous "
    "time series of the 44 manually retained ICA "
    "components for the next source-localization stage."
)