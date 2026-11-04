"""
Clean visualization of RAW EEG with task intervals.

No preprocessing is applied:
    - no filtering
    - no re-referencing
    - no ICA
    - no artifact rejection
    - no normalization

The only numerical conversion is:
    volts -> microvolts

Each selected EEG channel is displayed in its own subplot so that
signals cannot visually overlap.

Task visualization:
    - colored shaded region = task duration
    - solid colored line = task START
    - dashed colored line = task END
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import mne
import numpy as np
import pandas as pd


# =====================================================================
# Configuration
# =====================================================================

SUBJECT = "1"
SESSION = "0"
ACQUISITION = "train"
RUN = "0"


# ---------------------------------------------------------------------
# Time window
# ---------------------------------------------------------------------

START_TIME = 45.0
END_TIME = 55.0


# ---------------------------------------------------------------------
# Sensorimotor channels to inspect
# ---------------------------------------------------------------------

CHANNELS_TO_PLOT = [
    "FC3",
    "FC4",
    "C3",
    "Cz",
    "C4",
    "CP3",
    "CP4",
]


# ---------------------------------------------------------------------
# Event colors
# ---------------------------------------------------------------------

EVENT_COLORS = {
    "rest": "tab:green",
    "feet": "tab:blue",
    "left_hand": "tab:orange",
    "right_hand": "tab:purple",
}


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
# Load RAW EEG
# =====================================================================

print()
print("=" * 70)
print("Loading RAW EEG")
print("=" * 70)

raw = mne.io.read_raw_bdf(
    eeg_path,
    preload=False,
    verbose=False,
)

events = pd.read_csv(
    events_path,
    sep="\t",
)


# =====================================================================
# Basic recording information
# =====================================================================

sfreq = float(
    raw.info["sfreq"]
)

recording_duration = (
    raw.n_times
    / sfreq
)

print(
    f"Subject       : {subject_id}"
)

print(
    f"Acquisition   : {ACQUISITION}"
)

print(
    f"Run           : {RUN}"
)

print(
    f"Sampling rate : {sfreq} Hz"
)

print(
    f"Channels      : {raw.info['nchan']}"
)

print(
    f"Samples       : {raw.n_times}"
)

print(
    f"Duration      : {recording_duration:.2f} s"
)

print(
    f"Events        : {len(events)}"
)


# =====================================================================
# Validate time window
# =====================================================================

if START_TIME < 0:

    raise ValueError(
        "START_TIME cannot be negative."
    )


if END_TIME <= START_TIME:

    raise ValueError(
        "END_TIME must be greater than START_TIME."
    )


if END_TIME > recording_duration:

    raise ValueError(
        f"END_TIME ({END_TIME} s) exceeds "
        f"recording duration "
        f"({recording_duration:.2f} s)."
    )


# =====================================================================
# Validate requested channels
# =====================================================================

missing_channels = [
    channel
    for channel in CHANNELS_TO_PLOT
    if channel not in raw.ch_names
]


if missing_channels:

    raise ValueError(
        "The following channels were not found:\n"
        f"{missing_channels}"
    )


# =====================================================================
# Select channels explicitly by name
# =====================================================================

raw_selected = (
    raw.copy()
    .pick(CHANNELS_TO_PLOT)
)


# IMPORTANT:
# Use MNE's actual returned order.

plot_channel_names = (
    raw_selected.ch_names
)


print()
print("=" * 70)
print("Channels actually being plotted")
print("=" * 70)

for index, channel_name in enumerate(
    plot_channel_names
):

    print(
        f"{index + 1:2d}. {channel_name}"
    )


# =====================================================================
# Convert time window to sample indices
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


print()
print("=" * 70)
print("Selected time window")
print("=" * 70)

print(
    f"Start time   : {START_TIME:.3f} s"
)

print(
    f"End time     : {END_TIME:.3f} s"
)

print(
    f"Duration     : "
    f"{END_TIME - START_TIME:.3f} s"
)

print(
    f"Start sample : {start_sample}"
)

print(
    f"End sample   : {end_sample}"
)


# =====================================================================
# Extract RAW EEG
# =====================================================================

data, times = raw_selected[
    :,
    start_sample:end_sample
]


# =====================================================================
# Convert V -> µV
# =====================================================================

# MNE returns EEG data in volts.
#
# Multiplying by 1e6 is ONLY a unit conversion for visualization.
# This does not alter the EEG signal structure.

data_uv = (
    data
    * 1e6
)


# =====================================================================
# Verify extracted data
# =====================================================================

if (
    data_uv.shape[0]
    != len(plot_channel_names)
):

    raise RuntimeError(
        "Number of EEG signals does not match "
        "the number of channel labels."
    )


print()
print("=" * 70)
print("Extracted RAW EEG")
print("=" * 70)

print(
    f"Data shape : {data_uv.shape}"
)

print(
    "Structure  : "
    "(channels, samples)"
)

print(
    f"Expected samples for this window : "
    f"{int((END_TIME - START_TIME) * sfreq)}"
)


# =====================================================================
# Find events visible in this time window
# =====================================================================

event_end_times = (
    events["onset"]
    + events["duration"]
)

visible_events = events[
    (events["onset"] < END_TIME)
    &
    (event_end_times > START_TIME)
].copy()


print()
print("=" * 70)
print("Events visible in this window")
print("=" * 70)


if visible_events.empty:

    print(
        "No task events occur in this window."
    )

else:

    for _, event in visible_events.iterrows():

        event_start = float(
            event["onset"]
        )

        event_end = (
            event_start
            + float(
                event["duration"]
            )
        )

        print(
            f"{event['trial_type']:12s} | "
            f"{event_start:8.3f} "
            f"-> "
            f"{event_end:8.3f} s"
        )


# =====================================================================
# Create figure
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


# If only one channel is selected,
# make axes iterable.

if n_channels == 1:
    axes = [axes]


# =====================================================================
# Plot each EEG channel separately
# =====================================================================

for (
    ax,
    channel_name,
    channel_data,
) in zip(
    axes,
    plot_channel_names,
    data_uv,
):

    # -----------------------------------------------------------------
    # Draw task intervals
    # -----------------------------------------------------------------

    for _, event in visible_events.iterrows():

        event_start = float(
            event["onset"]
        )

        event_end = (
            event_start
            + float(
                event["duration"]
            )
        )

        trial_type = str(
            event["trial_type"]
        )

        color = EVENT_COLORS.get(
            trial_type,
            "gray",
        )

        # --------------------------------------------------------------
        # Task duration
        # --------------------------------------------------------------

        ax.axvspan(
            event_start,
            event_end,
            color=color,
            alpha=0.10,
            zorder=0,
        )

        # --------------------------------------------------------------
        # Task START
        # --------------------------------------------------------------

        ax.axvline(
            event_start,
            color=color,
            linewidth=1.3,
            linestyle="-",
            alpha=0.9,
            zorder=1,
        )

        # --------------------------------------------------------------
        # Task END
        # --------------------------------------------------------------

        ax.axvline(
            event_end,
            color=color,
            linewidth=1.3,
            linestyle="--",
            alpha=0.9,
            zorder=1,
        )


    # -----------------------------------------------------------------
    # Plot RAW EEG signal
    # -----------------------------------------------------------------

    ax.plot(
        times,
        channel_data,
        color="black",
        linewidth=0.7,
        zorder=2,
    )


    # -----------------------------------------------------------------
    # Zero-amplitude reference
    # -----------------------------------------------------------------

    ax.axhline(
        0.0,
        color="gray",
        linewidth=0.5,
        alpha=0.4,
        zorder=1,
    )


    # -----------------------------------------------------------------
    # Channel name
    # -----------------------------------------------------------------

    ax.set_ylabel(
        channel_name,
        rotation=0,
        labelpad=30,
        fontsize=10,
        fontweight="bold",
        verticalalignment="center",
    )


    # -----------------------------------------------------------------
    # Grid
    # -----------------------------------------------------------------

    ax.grid(
        axis="x",
        alpha=0.15,
    )


# =====================================================================
# Add task labels to TOP subplot only
# =====================================================================

top_ax = axes[0]

top_y_min, top_y_max = (
    top_ax.get_ylim()
)

label_y = (
    top_y_max
    - 0.08
    * (
        top_y_max
        - top_y_min
    )
)


for _, event in visible_events.iterrows():

    event_start = float(
        event["onset"]
    )

    event_end = (
        event_start
        + float(
            event["duration"]
        )
    )

    trial_type = str(
        event["trial_type"]
    )

    color = EVENT_COLORS.get(
        trial_type,
        "gray",
    )

    event_middle = (
        event_start
        + event_end
    ) / 2.0

    top_ax.text(
        event_middle,
        label_y,
        trial_type.replace(
            "_",
            " ",
        ),
        color=color,
        fontsize=10,
        fontweight="bold",
        horizontalalignment="center",
        verticalalignment="top",
        zorder=3,
    )


# =====================================================================
# X-axis configuration
# =====================================================================

axes[-1].set_xlim(
    START_TIME,
    END_TIME,
)


# Tick every 0.5 seconds

axes[-1].set_xticks(
    np.arange(
        START_TIME,
        END_TIME + 0.001,
        0.5,
    )
)


axes[-1].set_xlabel(
    "Time (s)",
    fontsize=11,
)


# =====================================================================
# Common amplitude label
# =====================================================================

fig.text(
    0.012,
    0.5,
    "Raw EEG amplitude (µV)",
    rotation="vertical",
    verticalalignment="center",
    fontsize=11,
)


# =====================================================================
# Figure title
# =====================================================================

fig.suptitle(
    f"{subject_id} | RAW EEG before preprocessing\n"
    f"Solid line = task START | "
    f"Dashed line = task END",
    fontsize=14,
)


# =====================================================================
# Legend
# =====================================================================

legend_handles = []

for (
    trial_type,
    color,
) in EVENT_COLORS.items():

    legend_handles.append(
        Line2D(
            [0],
            [0],
            color=color,
            linewidth=6,
            alpha=0.5,
            label=trial_type.replace(
                "_",
                " ",
            ),
        )
    )


fig.legend(
    handles=legend_handles,
    loc="upper right",
    bbox_to_anchor=(
        0.985,
        0.965,
    ),
    title="Task",
)


# =====================================================================
# Layout
# =====================================================================

plt.tight_layout(
    rect=[
        0.035,
        0.035,
        1.0,
        0.94,
    ]
)


# =====================================================================
# Final report
# =====================================================================

print()
print("=" * 70)
print("RAW EEG visualization")
print("=" * 70)

print(
    f"Time window : "
    f"{START_TIME:.1f} "
    f"- "
    f"{END_TIME:.1f} s"
)

print(
    f"Channels    : "
    f"{', '.join(plot_channel_names)}"
)

print()
print(
    "Solid colored line  = task START"
)

print(
    "Dashed colored line = task END"
)

print(
    "Shaded region       = task duration"
)

print()
print(
    "No EEG preprocessing has been applied."
)

print(
    "The only numerical conversion is "
    "volts -> microvolts for visualization."
)


# =====================================================================
# Display figure
# =====================================================================

plt.show()