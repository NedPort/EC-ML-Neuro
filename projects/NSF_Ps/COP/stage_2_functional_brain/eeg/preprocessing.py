"""
Stage 2 EEG preprocessing.

Current preprocessing:
    1. Load continuous RAW EEG.
    2. Preserve the original RAW object.
    3. Create a working copy.
    4. Apply ONLY a 1 Hz high-pass filter.
    5. Compare RAW vs HP EEG.
    6. Open interactive browser for manual BAD annotations.
    7. Save the HP EEG WITH all manual annotations.

No samples are deleted.

BAD annotations identify corrupted periods while preserving
the complete continuous EEG timeline.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import mne
import numpy as np


# =====================================================================
# Configuration
# =====================================================================

SUBJECT = "1"
SESSION = "0"
ACQUISITION = "train"
RUN = "0"

HIGH_PASS_HZ = 1.0


# =====================================================================
# Comparison window
# =====================================================================

START_TIME = 45.0
END_TIME = 55.0


# =====================================================================
# Channels for RAW vs HP comparison
# =====================================================================

CHANNELS_TO_PLOT = [
    "FC3",
    "FC4",
    "C3",
    "Cz",
    "C4",
    "CP3",
    "CP4",
]


# =====================================================================
# Project paths
# =====================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EEG_DATA_ROOT = (
    PROJECT_ROOT
    / "eeg_data"
)

subject_id = f"sub-{SUBJECT}"
session_id = f"ses-{SESSION}"

eeg_dir = (
    EEG_DATA_ROOT
    / subject_id
    / session_id
    / "eeg"
)


# =====================================================================
# Input EEG file
# =====================================================================

eeg_filename = (
    f"{subject_id}_{session_id}_"
    f"task-imagery_"
    f"acq-{ACQUISITION}_"
    f"run-{RUN}_eeg.bdf"
)

eeg_path = (
    eeg_dir
    / eeg_filename
)


# =====================================================================
# Validate input
# =====================================================================

if not eeg_path.exists():

    raise FileNotFoundError(
        f"EEG file not found:\n{eeg_path}"
    )


# =====================================================================
# Load ORIGINAL continuous RAW EEG
# =====================================================================

print()
print("=" * 70)
print("Loading ORIGINAL continuous RAW EEG")
print("=" * 70)
print(eeg_path)

raw = mne.io.read_raw_bdf(
    eeg_path,
    preload=False,
    verbose=False,
)


sfreq = float(
    raw.info["sfreq"]
)

duration_seconds = (
    raw.n_times
    / sfreq
)


print()
print(f"Subject       : {subject_id}")
print(f"Sampling rate : {sfreq:.1f} Hz")
print(f"Channels      : {raw.info['nchan']}")
print(f"Samples       : {raw.n_times:,}")
print(f"Duration      : {duration_seconds:.2f} s")
print(f"Duration      : {duration_seconds / 60:.2f} min")


# =====================================================================
# Validate comparison channels
# =====================================================================

missing_channels = [
    channel
    for channel in CHANNELS_TO_PLOT
    if channel not in raw.ch_names
]

if missing_channels:

    raise ValueError(
        "The following requested channels were not found:\n"
        f"{missing_channels}"
    )


# =====================================================================
# Create preprocessing copy
# =====================================================================

print()
print("=" * 70)
print("Creating preprocessing copy")
print("=" * 70)

raw_hp = (
    raw.copy()
    .load_data()
)

print("Original RAW EEG preserved.")
print("Filtering will be applied only to raw_hp.")


# =====================================================================
# Apply ONLY 1 Hz high-pass filter
# =====================================================================

print()
print("=" * 70)
print("Applying high-pass filter")
print("=" * 70)

print(f"High-pass cutoff : {HIGH_PASS_HZ:.1f} Hz")
print("Low-pass cutoff  : None")
print()


raw_hp.filter(
    l_freq=HIGH_PASS_HZ,
    h_freq=None,
    picks="eeg",
    method="fir",
    phase="zero",
    verbose=True,
)


print()
print("1 Hz high-pass filtering complete.")


# =====================================================================
# Verify filter information
# =====================================================================

print()
print("=" * 70)
print("Filter information")
print("=" * 70)

print(
    f"Original raw high-pass : "
    f"{raw.info['highpass']} Hz"
)

print(
    f"Filtered high-pass     : "
    f"{raw_hp.info['highpass']} Hz"
)

print(
    f"Sampling rate          : "
    f"{raw_hp.info['sfreq']} Hz"
)


# =====================================================================
# Extract same interval from RAW and HP data
# =====================================================================

start_sample = int(
    round(
        START_TIME
        * sfreq
    )
)

end_sample = int(
    round(
        END_TIME
        * sfreq
    )
)


# =====================================================================
# Select identical channels
# =====================================================================

raw_compare = (
    raw.copy()
    .pick(CHANNELS_TO_PLOT)
)

hp_compare = (
    raw_hp.copy()
    .pick(CHANNELS_TO_PLOT)
)


# =====================================================================
# Extract RAW data
# =====================================================================

raw_data, raw_times = raw_compare[
    :,
    start_sample:end_sample
]


# =====================================================================
# Extract HP data
# =====================================================================

hp_data, hp_times = hp_compare[
    :,
    start_sample:end_sample
]


# =====================================================================
# Convert V -> µV for visualization ONLY
# =====================================================================

raw_data_uv = (
    raw_data
    * 1e6
)

hp_data_uv = (
    hp_data
    * 1e6
)


# =====================================================================
# Sanity checks
# =====================================================================

if raw_data_uv.shape != hp_data_uv.shape:

    raise RuntimeError(
        "RAW and filtered data shapes do not match."
    )


if not np.allclose(
    raw_times,
    hp_times,
):

    raise RuntimeError(
        "RAW and filtered time axes do not match."
    )


plot_channel_names = (
    raw_compare.ch_names
)


print()
print("=" * 70)
print("RAW vs HP comparison")
print("=" * 70)

print(
    f"Time window : "
    f"{START_TIME:.1f} - {END_TIME:.1f} s"
)

print(
    f"Data shape  : "
    f"{raw_data_uv.shape}"
)

print(
    f"Channels    : "
    f"{', '.join(plot_channel_names)}"
)


# =====================================================================
# Create RAW vs HP comparison figure
# =====================================================================

n_channels = len(
    plot_channel_names
)

fig, axes = plt.subplots(
    n_channels,
    1,
    figsize=(18, 12),
    sharex=True,
)


if n_channels == 1:
    axes = [axes]


# =====================================================================
# Plot each channel
# =====================================================================

for (
    ax,
    channel_name,
    raw_channel,
    hp_channel,
) in zip(
    axes,
    plot_channel_names,
    raw_data_uv,
    hp_data_uv,
):

    # RAW EEG
    ax.plot(
        raw_times,
        raw_channel,
        linewidth=0.8,
        alpha=0.65,
        label="RAW",
    )

    # 1-Hz high-pass EEG
    ax.plot(
        hp_times,
        hp_channel,
        linewidth=0.8,
        alpha=0.85,
        label="HP 1 Hz",
    )

    # Zero reference
    ax.axhline(
        0.0,
        linewidth=0.5,
        alpha=0.3,
    )

    # Channel name
    ax.set_ylabel(
        channel_name,
        rotation=0,
        labelpad=30,
        fontweight="bold",
        verticalalignment="center",
    )

    ax.grid(
        axis="x",
        alpha=0.15,
    )


# =====================================================================
# Comparison plot formatting
# =====================================================================

axes[-1].set_xlim(
    START_TIME,
    END_TIME,
)

axes[-1].set_xticks(
    np.arange(
        START_TIME,
        END_TIME + 0.001,
        0.5,
    )
)

axes[-1].set_xlabel(
    "Time (s)"
)

axes[0].legend(
    loc="upper right"
)

fig.text(
    0.012,
    0.5,
    "EEG amplitude (µV)",
    rotation="vertical",
    verticalalignment="center",
)

fig.suptitle(
    f"{subject_id} | RAW EEG vs 1 Hz High-Pass EEG\n"
    f"No other preprocessing applied",
    fontsize=14,
)

plt.tight_layout(
    rect=[
        0.035,
        0.035,
        1.0,
        0.94,
    ]
)


# =====================================================================
# Display comparison plot
# =====================================================================

plt.show()


# =====================================================================
# INTERACTIVE MANUAL CLEANING
# =====================================================================

print()
print("=" * 70)
print("INTERACTIVE MANUAL EEG INSPECTION")
print("=" * 70)

print()
print("This is the 1-Hz high-pass filtered EEG.")
print()
print("Mark gross corrupted periods using BAD annotations.")
print()
print("When you are COMPLETELY FINISHED:")
print("    CLOSE the interactive EEG browser.")
print()
print(
    "After the browser closes, the SAME raw_hp object "
    "will be saved automatically."
)
print()


raw_hp.plot(
    start=0.0,
    duration=10.0,
    n_channels=30,
    scalings="auto",
    show_scrollbars=True,
    show_options=True,
    block=True,
)


# =====================================================================
# IMPORTANT:
#
# Execution reaches this point only AFTER the interactive browser
# has been closed.
#
# raw_hp now contains all manual annotations created in the browser.
# =====================================================================


print()
print("=" * 70)
print("MANUAL INSPECTION FINISHED")
print("=" * 70)


# =====================================================================
# Collect BAD annotations
# =====================================================================

bad_annotations = []

for onset, duration, description in zip(
    raw_hp.annotations.onset,
    raw_hp.annotations.duration,
    raw_hp.annotations.description,
):

    if description.startswith("BAD"):

        bad_annotations.append(
            (
                onset,
                duration,
                description,
            )
        )


# =====================================================================
# Report BAD annotations
# =====================================================================

print()
print(
    f"Number of BAD segments: "
    f"{len(bad_annotations)}"
)
print()


for i, (
    onset,
    duration,
    description,
) in enumerate(
    bad_annotations,
    start=1,
):

    print(
        f"{i:3d}. "
        f"{description:20s} "
        f"start={onset:9.3f} s   "
        f"end={onset + duration:9.3f} s   "
        f"duration={duration:8.3f} s"
    )


# =====================================================================
# Calculate total BAD duration
# =====================================================================

total_bad_duration = sum(
    duration
    for _, duration, _ in bad_annotations
)

print()
print(
    f"Total BAD duration : "
    f"{total_bad_duration:.3f} s"
)

print(
    f"Recording duration : "
    f"{duration_seconds:.3f} s"
)

print(
    f"BAD percentage     : "
    f"{100 * total_bad_duration / duration_seconds:.2f}%"
)


# =====================================================================
# Output directory
# =====================================================================

PROCESSED_DIR = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "processed"
)

PROCESSED_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =====================================================================
# Output file
# =====================================================================

cleaned_path = (
    PROCESSED_DIR
    / f"{subject_id}_{session_id}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"hp-1Hz_annotated_raw.fif"
)


# =====================================================================
# Save filtered EEG + ALL annotations
# =====================================================================

print()
print("=" * 70)
print("SAVING FILTERED EEG + MANUAL ANNOTATIONS")
print("=" * 70)

print()
print(cleaned_path)
print()


raw_hp.save(
    cleaned_path,
    overwrite=True,
)


# =====================================================================
# Verify saved file
# =====================================================================

print()
print("=" * 70)
print("VERIFYING SAVED FILE")
print("=" * 70)


check_raw = mne.io.read_raw_fif(
    cleaned_path,
    preload=False,
    verbose=False,
)


saved_bad_annotations = [
    (
        onset,
        duration,
        description,
    )
    for onset, duration, description in zip(
        check_raw.annotations.onset,
        check_raw.annotations.duration,
        check_raw.annotations.description,
    )
    if description.startswith("BAD")
]


print()
print(
    f"BAD annotations before saving : "
    f"{len(bad_annotations)}"
)

print(
    f"BAD annotations after saving  : "
    f"{len(saved_bad_annotations)}"
)


# =====================================================================
# Verification
# =====================================================================

if len(saved_bad_annotations) != len(bad_annotations):

    raise RuntimeError(
        "ERROR: Number of BAD annotations changed during saving."
    )


# =====================================================================
# Final report
# =====================================================================

print()
print("=" * 70)
print("SAVE SUCCESSFUL")
print("=" * 70)

print()
print("Saved file:")
print(cleaned_path)

print()
print(
    "The complete continuous EEG is preserved."
)

print(
    "BAD periods have NOT been deleted."
)

print(
    "Manual BAD annotations are stored inside the FIF file."
)

print()
print(
    "This file should be used as the input "
    "for the next preprocessing stage."
)