"""
Stage 2.1 - ICA decomposition of continuous EEG.

Input
-----
1-Hz high-pass filtered continuous EEG with manual BAD annotations.

Current validated state
-----------------------
- 128 EEG channels
- Sampling rate: 500 Hz
- EEG rank: 128
- BAD intervals are preserved in the continuous recording
- BAD intervals are excluded from ICA fitting
- No bad channels are currently marked

Purpose
-------
1. Load the annotated continuous EEG.
2. Confirm annotations and rank.
3. Fit Extended Infomax ICA on usable EEG periods.
4. Preserve all 128 ICA components.
5. Save the fitted ICA model.
6. Extract and save continuous ICA component time courses.
7. Visualize IC scalp maps and continuous IC signals.

IMPORTANT
---------
No ICA components are removed at this stage.
ICA components are NOT yet anatomical brain sources.
"""

from pathlib import Path

import mne
from mne.preprocessing import ICA


# =====================================================================
# Configuration
# =====================================================================

SUBJECT = "1"
SESSION = "0"
ACQUISITION = "train"
RUN = "0"

ICA_METHOD = "infomax"
ICA_N_COMPONENTS = 128
RANDOM_STATE = 42


# =====================================================================
# Paths
# =====================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "processed"
)

ICA_DIR = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "ica_results"
)

ICA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

subject_id = f"sub-{SUBJECT}"
session_id = f"ses-{SESSION}"

annotated_file = (
    PROCESSED_DIR
    / f"{subject_id}_{session_id}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"hp-1Hz_annotated_raw.fif"
)

ica_file = (
    ICA_DIR
    / f"{subject_id}_{session_id}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"ica.fif"
)

ica_sources_file = (
    ICA_DIR
    / f"{subject_id}_{session_id}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"ica_sources_raw.fif"
)


# =====================================================================
# Validate input
# =====================================================================

if not annotated_file.exists():
    raise FileNotFoundError(
        f"Annotated EEG file not found:\n{annotated_file}"
    )


# =====================================================================
# Load annotated EEG
# =====================================================================

print()
print("=" * 70)
print("LOADING ANNOTATED CONTINUOUS EEG")
print("=" * 70)

raw = mne.io.read_raw_fif(
    annotated_file,
    preload=True,
    verbose=False,
)

print()
print(raw)

sfreq = raw.info["sfreq"]
duration_sec = raw.n_times / sfreq

print()
print(f"Channels      : {raw.info['nchan']}")
print(f"Sampling rate : {sfreq} Hz")
print(f"Samples       : {raw.n_times:,}")
print(f"Duration      : {duration_sec / 60:.2f} min")


# =====================================================================
# Inspect BAD annotations
# =====================================================================

bad_annotations = [
    (onset, duration, description)
    for onset, duration, description in zip(
        raw.annotations.onset,
        raw.annotations.duration,
        raw.annotations.description,
    )
    if description.upper().startswith("BAD")
]

total_bad_duration = sum(
    duration
    for _, duration, _ in bad_annotations
)

usable_duration = duration_sec - total_bad_duration


print()
print("=" * 70)
print("BAD TIME SEGMENTS")
print("=" * 70)

print()
print(
    f"Number of BAD annotations : "
    f"{len(bad_annotations)}"
)

print(
    f"Total BAD duration        : "
    f"{total_bad_duration:.2f} s"
)

print(
    f"Total BAD duration        : "
    f"{total_bad_duration / 60:.2f} min"
)

print(
    f"Approx. usable duration   : "
    f"{usable_duration / 60:.2f} min"
)


# =====================================================================
# Check bad channels
# =====================================================================

print()
print("=" * 70)
print("BAD CHANNELS")
print("=" * 70)
print()

if raw.info["bads"]:
    print("Currently marked bad channels:")

    for channel in raw.info["bads"]:
        print(f"  - {channel}")

else:
    print("No channels are currently marked as bad.")


# =====================================================================
# Compute EEG rank
# =====================================================================

print()
print("=" * 70)
print("EEG RANK")
print("=" * 70)
print()

rank = mne.compute_rank(
    raw,
    rank=None,
    verbose=True,
)

eeg_rank = rank["eeg"]

print()
print(f"Estimated EEG rank: {eeg_rank}")


# =====================================================================
# Validate requested ICA dimensionality
# =====================================================================

if ICA_N_COMPONENTS > eeg_rank:
    raise ValueError(
        f"Requested {ICA_N_COMPONENTS} ICA components, "
        f"but estimated EEG rank is only {eeg_rank}."
    )

print()
print("=" * 70)
print("ICA CONFIGURATION")
print("=" * 70)

print()
print(f"Method           : Extended {ICA_METHOD}")
print(f"EEG rank         : {eeg_rank}")
print(f"ICA components   : {ICA_N_COMPONENTS}")
print(f"Random state     : {RANDOM_STATE}")
print(f"Bad channels     : {len(raw.info['bads'])}")
print(f"BAD time periods : {len(bad_annotations)}")


# =====================================================================
# Create ICA object
# =====================================================================

ica = ICA(
    n_components=ICA_N_COMPONENTS,
    method=ICA_METHOD,
    fit_params=dict(
        extended=True
    ),
    random_state=RANDOM_STATE,
    max_iter="auto",
)


# =====================================================================
# Fit ICA
# =====================================================================

print()
print("=" * 70)
print("FITTING ICA")
print("=" * 70)

print()
print(
    "ICA will be estimated from EEG data while "
    "excluding BAD annotated time intervals."
)

print()
print(
    "No ICA components will be rejected automatically."
)

print()


ica.fit(
    raw,
    picks="eeg",
    reject_by_annotation=True,
    verbose=True,
)


# =====================================================================
# ICA summary
# =====================================================================

print()
print("=" * 70)
print("ICA FIT COMPLETE")
print("=" * 70)

print()
print(ica)

print()
print(
    f"Number of ICA components: "
    f"{ica.n_components_}"
)

print(
    f"ICA iterations: "
    f"{ica.n_iter_}"
)


# =====================================================================
# Save ICA model
# =====================================================================

print()
print("=" * 70)
print("SAVING ICA MODEL")
print("=" * 70)


ica.save(
    ica_file,
    overwrite=True,
)


print()
print(f"Saved ICA model:")
print(ica_file)


# =====================================================================
# Extract continuous ICA component signals
# =====================================================================

print()
print("=" * 70)
print("EXTRACTING ICA COMPONENT SIGNALS")
print("=" * 70)


ica_sources = ica.get_sources(
    raw
)


print()
print(ica_sources)

print()
print(
    f"ICA source channels : "
    f"{ica_sources.info['nchan']}"
)

print(
    f"ICA source samples  : "
    f"{ica_sources.n_times:,}"
)

print(
    f"Sampling rate       : "
    f"{ica_sources.info['sfreq']} Hz"
)


# =====================================================================
# Source matrix
# =====================================================================

source_data = ica_sources.get_data()


print()
print(
    f"ICA source matrix shape: "
    f"{source_data.shape}"
)

print()
print(
    "Matrix dimensions:"
)

print(
    "    (ICA components, continuous time samples)"
)


# =====================================================================
# Save ICA source signals
# =====================================================================

print()
print("=" * 70)
print("SAVING ICA COMPONENT SIGNALS")
print("=" * 70)


ica_sources.save(
    ica_sources_file,
    overwrite=True,
)


print()
print(f"Saved ICA component signals:")
print(ica_sources_file)


# =====================================================================
# Confirm no ICs have been excluded
# =====================================================================

print()
print("=" * 70)
print("ICA EXCLUSION STATUS")
print("=" * 70)

print()
print(f"Excluded ICs: {ica.exclude}")

if len(ica.exclude) == 0:
    print(
        "Correct: no ICA components have been removed."
    )


# =====================================================================
# Visualize ICA scalp maps
# =====================================================================

print()
print("=" * 70)
print("ICA COMPONENT TOPOGRAPHIES")
print("=" * 70)

print()
print(
    "Inspect the spatial scalp maps."
)

print(
    "Do NOT classify or remove components yet "
    "based only on the scalp maps."
)

print()


ica.plot_components(
    inst=raw,
    show=True,
)


# =====================================================================
# Visualize continuous ICA component signals
# =====================================================================

print()
print("=" * 70)
print("ICA COMPONENT TIME COURSES")
print("=" * 70)

print()
print(
    "The following browser shows the continuous "
    "ICA component signals."
)

print(
    "Closing the browser will continue the script."
)

print()


ica.plot_sources(
    raw,
    start=0.0,
    stop=20.0,
    show_scrollbars=True,
    block=True,
)


# =====================================================================
# Final report
# =====================================================================

print()
print("=" * 70)
print("STAGE 2.1 COMPLETE")
print("=" * 70)

print()

print("Input:")
print(f"  {annotated_file}")

print()
print("Saved outputs:")

print(
    f"  ICA model:\n"
    f"  {ica_file}"
)

print()

print(
    f"  ICA component signals:\n"
    f"  {ica_sources_file}"
)

print()
print(
    f"Number of components: "
    f"{ica.n_components_}"
)

print(
    f"Excluded components: "
    f"{ica.exclude}"
)

print()
print(
    "NO ICA COMPONENTS HAVE BEEN REMOVED."
)

print()
print(
    "Next stage:"
)

print(
    "Inspect IC time courses, scalp topographies, "
    "and spectral characteristics to identify "
    "brain-related and artifact-related components."
)