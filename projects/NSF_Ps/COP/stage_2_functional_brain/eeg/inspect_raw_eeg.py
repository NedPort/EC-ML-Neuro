"""
Interactive inspection of the complete continuous RAW EEG recording.

Purpose
-------
This script is for visual quality control BEFORE preprocessing and ICA.

It allows interactive inspection of:
    - all EEG channels
    - the entire continuous recording
    - large spikes
    - unusually noisy channels
    - flat channels
    - electrode shifts / jumps
    - movement artifacts
    - other abnormal signal periods

No preprocessing is applied:
    - no filtering
    - no re-referencing
    - no ICA
    - no artifact rejection
    - no normalization

The EEG remains exactly as stored in the BDF file.
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


# ---------------------------------------------------------------------
# Initial browser settings
#
# These settings ONLY control what is initially visible.
# The complete recording and all 128 channels remain available.
# ---------------------------------------------------------------------

START_TIME = 0.0

# Number of seconds initially visible
WINDOW_DURATION = 10.0

# Number of channels initially visible
N_CHANNELS_DISPLAY = 30


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
# File paths
# =====================================================================

eeg_filename = (
    f"{subject_id}_{session_id}_"
    f"task-imagery_"
    f"acq-{ACQUISITION}_"
    f"run-{RUN}_eeg.bdf"
)

events_filename = (
    f"{subject_id}_{session_id}_"
    f"task-imagery_"
    f"acq-{ACQUISITION}_"
    f"run-{RUN}_events.tsv"
)

eeg_path = (
    eeg_dir
    / eeg_filename
)

events_path = (
    eeg_dir
    / events_filename
)


# =====================================================================
# Validate files
# =====================================================================

if not eeg_path.exists():

    raise FileNotFoundError(
        f"EEG file not found:\n{eeg_path}"
    )


if not events_path.exists():

    raise FileNotFoundError(
        f"Events file not found:\n{events_path}"
    )


# =====================================================================
# Load continuous RAW EEG
# =====================================================================

print()
print("=" * 70)
print("Loading continuous RAW EEG")
print("=" * 70)

raw = mne.io.read_raw_bdf(
    eeg_path,
    preload=False,
    verbose=False,
)


# =====================================================================
# Load experimental events
# =====================================================================

events = pd.read_csv(
    events_path,
    sep="\t",
)


# =====================================================================
# Recording information
# =====================================================================

sfreq = float(
    raw.info["sfreq"]
)

n_channels = int(
    raw.info["nchan"]
)

n_samples = int(
    raw.n_times
)

duration_seconds = (
    n_samples
    / sfreq
)

duration_minutes = (
    duration_seconds
    / 60.0
)


print(
    f"Subject       : {subject_id}"
)

print(
    f"Session       : {session_id}"
)

print(
    f"Acquisition   : {ACQUISITION}"
)

print(
    f"Run           : {RUN}"
)

print()

print(
    f"Sampling rate : {sfreq:.1f} Hz"
)

print(
    f"Channels      : {n_channels}"
)

print(
    f"Samples       : {n_samples:,}"
)

print(
    f"Duration      : {duration_seconds:.2f} s"
)

print(
    f"Duration      : {duration_minutes:.2f} min"
)

print(
    f"Events        : {len(events)}"
)


# =====================================================================
# Print event summary
# =====================================================================

print()
print("=" * 70)
print("Event summary")
print("=" * 70)

if "trial_type" in events.columns:

    event_counts = (
        events["trial_type"]
        .value_counts()
        .sort_index()
    )

    for trial_type, count in event_counts.items():

        print(
            f"{trial_type:15s}: {count}"
        )


# =====================================================================
# Print channel list
# =====================================================================

print()
print("=" * 70)
print("EEG channels")
print("=" * 70)

for index, channel_name in enumerate(
    raw.ch_names,
    start=1,
):

    print(
        f"{index:3d}. {channel_name}"
    )


# =====================================================================
# Browser instructions
# =====================================================================

print()
print("=" * 70)
print("Opening interactive RAW EEG browser")
print("=" * 70)

print()
print(
    "This is the ORIGINAL continuous EEG."
)

print(
    "No preprocessing has been applied."
)

print()

print(
    f"Initial time window : "
    f"{WINDOW_DURATION:.1f} seconds"
)

print(
    f"Initial channels    : "
    f"{N_CHANNELS_DISPLAY}"
)

print()

print(
    "Use the browser to move through:"
)

print(
    "  - time"
)

print(
    "  - channels"
)

print(
    "  - the entire recording"
)

print()

print(
    "Look for:"
)

print(
    "  - very large spikes"
)

print(
    "  - sudden jumps"
)

print(
    "  - flat channels"
)

print(
    "  - persistently noisy channels"
)

print(
    "  - large slow drifts"
)

print(
    "  - high-frequency bursts"
)

print(
    "  - artifacts appearing across many channels"
)

print()

print(
    "IMPORTANT:"
)

print(
    "Do not decide that a channel is bad only because "
    "its baseline or amplitude differs from another channel."
)

print(
    "At this stage we are visually inspecting the raw data."
)

print()


# =====================================================================
# Open interactive browser
# =====================================================================

raw.plot(
    start=START_TIME,

    # Seconds displayed at one time
    duration=WINDOW_DURATION,

    # Channels displayed at one time
    n_channels=N_CHANNELS_DISPLAY,

    # Automatically choose an initial visual scale
    scalings="auto",

    # Keep the scrollbars so we can navigate
    # both time and channels.
    show_scrollbars=True,

    # Display channel names
    show_options=True,

    # Keep Python running while the browser is open
    block=True,
)