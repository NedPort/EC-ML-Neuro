"""
Load and inspect EEG data from the Schirrmeister High-Gamma Dataset.

Current stage:
    1. Load one continuous BDF EEG recording.
    2. Inspect channel metadata.
    3. Inspect electrode coordinates.
    4. Inspect the electrode coordinate system.
    5. Verify consistency between BDF channels and metadata.
    6. Load and validate task events.
    7. Identify right-hand movement trials.

No filtering, preprocessing, ICA, epoching, or source localization
is performed at this stage.
"""

from pathlib import Path
import json

import mne
import pandas as pd


# =====================================================================
# Project paths
# =====================================================================

# Expected location of this file:
#
# COP/
# └── stage_2_functional_brain/
#     └── eeg/
#         └── load_eeg.py
#
# Therefore parents[2] corresponds to COP/.

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EEG_DATA_ROOT = PROJECT_ROOT / "eeg_data"


# =====================================================================
# Helper: construct EEG directory
# =====================================================================

def get_eeg_directory(
    subject: str,
    session: str,
) -> Path:
    """
    Return the EEG directory for one subject and session.

    Parameters
    ----------
    subject : str
        Subject number, e.g. "1", "2", ..., "14".

    session : str
        Session number, currently "0".

    Returns
    -------
    Path
        Path to the subject/session EEG directory.
    """

    subject_id = f"sub-{subject}"
    session_id = f"ses-{session}"

    eeg_dir = (
        EEG_DATA_ROOT
        / subject_id
        / session_id
        / "eeg"
    )

    if not eeg_dir.exists():
        raise FileNotFoundError(
            f"EEG directory not found:\n{eeg_dir}"
        )

    return eeg_dir


# =====================================================================
# Load raw EEG
# =====================================================================

def load_eeg(
    subject: str = "1",
    session: str = "0",
    acquisition: str = "train",
    run: str = "0",
):
    """
    Load one raw EEG recording from the High-Gamma Dataset.

    Parameters
    ----------
    subject : str
        Subject number, e.g. "1", "2", ..., "14".

    session : str
        Session number.

    acquisition : str
        Acquisition type, e.g. "train" or "test".

    run : str
        Run number, e.g. "0" or "1".

    Returns
    -------
    raw : mne.io.Raw
        Raw continuous EEG recording.
    """

    subject_id = f"sub-{subject}"
    session_id = f"ses-{session}"

    eeg_dir = get_eeg_directory(
        subject=subject,
        session=session,
    )

    eeg_filename = (
        f"{subject_id}_{session_id}_"
        f"task-imagery_"
        f"acq-{acquisition}_"
        f"run-{run}_eeg.bdf"
    )

    eeg_path = eeg_dir / eeg_filename

    if not eeg_path.exists():
        raise FileNotFoundError(
            f"EEG file not found:\n{eeg_path}"
        )

    # -----------------------------------------------------------------
    # Load BDF
    # -----------------------------------------------------------------

    print()
    print("=" * 70)
    print("Loading EEG recording")
    print("=" * 70)

    print(f"Subject     : {subject_id}")
    print(f"Session     : {session_id}")
    print(f"Acquisition : {acquisition}")
    print(f"Run         : {run}")
    print(f"EEG file    : {eeg_path.name}")

    raw = mne.io.read_raw_bdf(
        eeg_path,
        preload=False,
        verbose=False,
    )

    # -----------------------------------------------------------------
    # Basic recording information
    # -----------------------------------------------------------------

    sfreq = raw.info["sfreq"]
    n_channels = raw.info["nchan"]
    n_samples = raw.n_times

    duration_seconds = n_samples / sfreq
    duration_minutes = duration_seconds / 60.0

    print()
    print("=" * 70)
    print("Recording information")
    print("=" * 70)

    print(f"Number of channels : {n_channels}")
    print(f"Sampling frequency : {sfreq} Hz")
    print(f"Number of samples  : {n_samples}")
    print(f"Duration           : {duration_seconds:.2f} s")
    print(f"Duration           : {duration_minutes:.2f} min")

    print()
    print("Channel names:")
    print(raw.ch_names)

    return raw


# =====================================================================
# Inspect channel and electrode metadata
# =====================================================================

def inspect_electrode_metadata(
    subject: str = "1",
    session: str = "0",
    acquisition: str = "train",
    run: str = "0",
):
    """
    Inspect BIDS channel and electrode metadata for one recording.

    Reads:
        *_channels.tsv
        *_electrodes.tsv
        *_coordsystem.json

    Returns
    -------
    channels : pandas.DataFrame
        Channel metadata.

    electrodes : pandas.DataFrame
        Electrode positions.

    coordsystem : dict
        BIDS coordinate-system metadata.
    """

    subject_id = f"sub-{subject}"
    session_id = f"ses-{session}"

    eeg_dir = get_eeg_directory(
        subject=subject,
        session=session,
    )

    # -----------------------------------------------------------------
    # Construct metadata paths
    # -----------------------------------------------------------------

    channels_filename = (
        f"{subject_id}_{session_id}_"
        f"task-imagery_"
        f"acq-{acquisition}_"
        f"run-{run}_channels.tsv"
    )

    electrodes_filename = (
        f"{subject_id}_{session_id}_"
        f"space-CapTrak_electrodes.tsv"
    )

    coordsystem_filename = (
        f"{subject_id}_{session_id}_"
        f"space-CapTrak_coordsystem.json"
    )

    channels_path = eeg_dir / channels_filename
    electrodes_path = eeg_dir / electrodes_filename
    coordsystem_path = eeg_dir / coordsystem_filename

    # -----------------------------------------------------------------
    # Check files
    # -----------------------------------------------------------------

    required_files = [
        channels_path,
        electrodes_path,
        coordsystem_path,
    ]

    for path in required_files:
        if not path.exists():
            raise FileNotFoundError(
                f"Required metadata file not found:\n{path}"
            )

    # -----------------------------------------------------------------
    # Load metadata
    # -----------------------------------------------------------------

    channels = pd.read_csv(
        channels_path,
        sep="\t",
    )

    electrodes = pd.read_csv(
        electrodes_path,
        sep="\t",
    )

    with open(
        coordsystem_path,
        "r",
        encoding="utf-8",
    ) as f:
        coordsystem = json.load(f)

    # -----------------------------------------------------------------
    # Channel metadata
    # -----------------------------------------------------------------

    print()
    print("=" * 70)
    print("Channel metadata")
    print("=" * 70)

    print(f"File                   : {channels_path.name}")
    print(f"Number of channel rows : {len(channels)}")
    print(f"Columns                : {list(channels.columns)}")

    print()
    print("First 10 channel rows:")
    print()

    print(
        channels.head(10).to_string(
            index=False
        )
    )

    # -----------------------------------------------------------------
    # Channel type summary
    # -----------------------------------------------------------------

    if "type" in channels.columns:

        print()
        print("Channel type counts:")
        print()

        print(
            channels["type"]
            .value_counts(dropna=False)
            .to_string()
        )

    # -----------------------------------------------------------------
    # Channel status summary
    # -----------------------------------------------------------------

    if "status" in channels.columns:

        print()
        print("Channel status counts:")
        print()

        print(
            channels["status"]
            .value_counts(dropna=False)
            .to_string()
        )

    # -----------------------------------------------------------------
    # Electrode metadata
    # -----------------------------------------------------------------

    print()
    print("=" * 70)
    print("Electrode metadata")
    print("=" * 70)

    print(f"File                 : {electrodes_path.name}")
    print(f"Number of electrodes : {len(electrodes)}")
    print(f"Columns              : {list(electrodes.columns)}")

    print()
    print("First 10 electrode rows:")
    print()

    print(
        electrodes.head(10).to_string(
            index=False
        )
    )

    # -----------------------------------------------------------------
    # Missing coordinate check
    # -----------------------------------------------------------------

    coordinate_columns = [
        column
        for column in ["x", "y", "z", "X", "Y", "Z"]
        if column in electrodes.columns
    ]

    if coordinate_columns:

        print()
        print("Missing coordinate values:")
        print()

        print(
            electrodes[coordinate_columns]
            .isna()
            .sum()
            .to_string()
        )

    # -----------------------------------------------------------------
    # Coordinate system
    # -----------------------------------------------------------------

    print()
    print("=" * 70)
    print("Coordinate system")
    print("=" * 70)

    print(f"File : {coordsystem_path.name}")
    print()

    for key, value in coordsystem.items():
        print(f"{key}: {value}")

    return channels, electrodes, coordsystem


# =====================================================================
# Compare raw EEG channels with metadata
# =====================================================================

def compare_channel_names(
    raw,
    channels: pd.DataFrame,
    electrodes: pd.DataFrame,
):
    """
    Compare channel names across:

        1. BDF recording
        2. channels.tsv
        3. electrodes.tsv
    """

    print()
    print("=" * 70)
    print("Channel/electrode consistency check")
    print("=" * 70)

    raw_names = set(raw.ch_names)

    # -----------------------------------------------------------------
    # BDF vs channels.tsv
    # -----------------------------------------------------------------

    if "name" in channels.columns:

        channel_names = set(
            channels["name"].astype(str)
        )

        missing_from_channels = (
            raw_names - channel_names
        )

        extra_in_channels = (
            channel_names - raw_names
        )

        print()
        print("BDF vs channels.tsv")
        print("-" * 70)

        print(
            f"BDF channels         : {len(raw_names)}"
        )

        print(
            f"channels.tsv entries : {len(channel_names)}"
        )

        print(
            "BDF names missing from channels.tsv : "
            f"{sorted(missing_from_channels)}"
        )

        print(
            "Extra names in channels.tsv         : "
            f"{sorted(extra_in_channels)}"
        )

    else:

        print()
        print(
            "channels.tsv does not contain a "
            "'name' column."
        )

    # -----------------------------------------------------------------
    # BDF vs electrodes.tsv
    # -----------------------------------------------------------------

    if "name" in electrodes.columns:

        electrode_names = set(
            electrodes["name"].astype(str)
        )

        missing_from_electrodes = (
            raw_names - electrode_names
        )

        extra_electrodes = (
            electrode_names - raw_names
        )

        print()
        print("BDF vs electrodes.tsv")
        print("-" * 70)

        print(
            f"BDF channels          : {len(raw_names)}"
        )

        print(
            f"Electrode entries     : {len(electrode_names)}"
        )

        print(
            "BDF names without electrode coordinates : "
            f"{sorted(missing_from_electrodes)}"
        )

        print(
            "Extra electrode names                    : "
            f"{sorted(extra_electrodes)}"
        )

    else:

        print()
        print(
            "electrodes.tsv does not contain a "
            "'name' column."
        )


# =====================================================================
# Inspect and validate task events
# =====================================================================

def inspect_events(
    subject: str = "1",
    session: str = "0",
    acquisition: str = "train",
    run: str = "0",
    sfreq: float = 500.0,
):
    """
    Inspect and validate task events for one EEG recording.

    Checks:
        - Total number of events
        - Trial counts for each condition
        - Event-value mapping
        - Trial durations
        - Onset-to-sample consistency
        - Duplicate events
        - Temporal ordering
        - Right-hand trial locations

    Parameters
    ----------
    subject : str
        Subject number.

    session : str
        Session number.

    acquisition : str
        Acquisition type.

    run : str
        Run number.

    sfreq : float
        EEG sampling frequency in Hz.

    Returns
    -------
    events : pandas.DataFrame
        Event table with calculated sample information.
    """

    subject_id = f"sub-{subject}"
    session_id = f"ses-{session}"

    eeg_dir = get_eeg_directory(
        subject=subject,
        session=session,
    )

    events_filename = (
        f"{subject_id}_{session_id}_"
        f"task-imagery_"
        f"acq-{acquisition}_"
        f"run-{run}_events.tsv"
    )

    events_path = eeg_dir / events_filename

    if not events_path.exists():
        raise FileNotFoundError(
            f"Events file not found:\n{events_path}"
        )

    # -----------------------------------------------------------------
    # Load events
    # -----------------------------------------------------------------

    events = pd.read_csv(
        events_path,
        sep="\t",
    )

    print()
    print("=" * 70)
    print("Task event structure")
    print("=" * 70)

    print(f"File         : {events_path.name}")
    print(f"Total events : {len(events)}")
    print(f"Columns      : {list(events.columns)}")

    # -----------------------------------------------------------------
    # Trial counts
    # -----------------------------------------------------------------

    print()
    print("Trial counts:")
    print("-" * 70)

    trial_counts = (
        events["trial_type"]
        .value_counts()
        .sort_index()
    )

    print(trial_counts.to_string())

    # -----------------------------------------------------------------
    # Event-value mapping
    # -----------------------------------------------------------------

    print()
    print("Event-value mapping:")
    print("-" * 70)

    event_mapping = (
        events[["trial_type", "value"]]
        .drop_duplicates()
        .sort_values("value")
    )

    print(
        event_mapping.to_string(
            index=False
        )
    )

    # -----------------------------------------------------------------
    # Duration check
    # -----------------------------------------------------------------

    print()
    print("Trial duration check:")
    print("-" * 70)

    duration_counts = (
        events["duration"]
        .value_counts()
        .sort_index()
    )

    print(duration_counts.to_string())

    unique_durations = sorted(
        events["duration"].unique()
    )

    print()
    print(
        f"Unique durations : {unique_durations}"
    )

    # -----------------------------------------------------------------
    # Verify onset -> sample conversion
    # -----------------------------------------------------------------

    calculated_samples = (
        events["onset"] * sfreq
    ).round().astype(int)

    sample_difference = (
        events["sample"].astype(int)
        - calculated_samples
    )

    events = events.copy()

    events["calculated_sample"] = calculated_samples
    events["sample_difference"] = sample_difference

    print()
    print("Onset/sample consistency:")
    print("-" * 70)

    print(
        f"Maximum absolute difference : "
        f"{sample_difference.abs().max()} samples"
    )

    inconsistent = events[
        sample_difference != 0
    ]

    print(
        f"Inconsistent events          : "
        f"{len(inconsistent)}"
    )

    if len(inconsistent) > 0:

        print()
        print("Inconsistent rows:")

        print(
            inconsistent[
                [
                    "onset",
                    "trial_type",
                    "sample",
                    "calculated_sample",
                    "sample_difference",
                ]
            ].to_string(index=False)
        )

    # -----------------------------------------------------------------
    # Duplicate event check
    # -----------------------------------------------------------------

    print()
    print("Duplicate event check:")
    print("-" * 70)

    duplicate_mask = events.duplicated(
        subset=[
            "onset",
            "sample",
            "trial_type",
        ],
        keep=False,
    )

    n_duplicates = int(
        duplicate_mask.sum()
    )

    print(
        f"Duplicate events : {n_duplicates}"
    )

    if n_duplicates > 0:

        print()

        print(
            events.loc[
                duplicate_mask,
                [
                    "onset",
                    "duration",
                    "trial_type",
                    "value",
                    "sample",
                ],
            ].to_string(index=False)
        )

    # -----------------------------------------------------------------
    # Temporal ordering
    # -----------------------------------------------------------------

    print()
    print("Temporal ordering:")
    print("-" * 70)

    onset_sorted = (
        events["onset"]
        .is_monotonic_increasing
    )

    sample_sorted = (
        events["sample"]
        .is_monotonic_increasing
    )

    print(
        f"Onsets monotonically increasing  : {onset_sorted}"
    )

    print(
        f"Samples monotonically increasing : {sample_sorted}"
    )

    # -----------------------------------------------------------------
    # First and last events
    # -----------------------------------------------------------------

    first_event = events.iloc[0]
    last_event = events.iloc[-1]

    print()
    print("Recording event range:")
    print("-" * 70)

    print(
        f"First event : "
        f"{first_event['trial_type']} "
        f"at {first_event['onset']:.3f} s "
        f"(sample {int(first_event['sample'])})"
    )

    print(
        f"Last event  : "
        f"{last_event['trial_type']} "
        f"at {last_event['onset']:.3f} s "
        f"(sample {int(last_event['sample'])})"
    )

    last_event_end = (
        float(last_event["onset"])
        + float(last_event["duration"])
    )

    print(
        f"Last event ends at : "
        f"{last_event_end:.3f} s"
    )

    # -----------------------------------------------------------------
    # Right-hand trials
    # -----------------------------------------------------------------

    right_hand_events = events[
        events["trial_type"] == "right_hand"
    ].copy()

    print()
    print("=" * 70)
    print("Right-hand trials")
    print("=" * 70)

    print(
        f"Number of right-hand trials : "
        f"{len(right_hand_events)}"
    )

    print()

    print(
        right_hand_events[
            [
                "onset",
                "duration",
                "value",
                "sample",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )

    return events


# =====================================================================
# Main
# =====================================================================

if __name__ == "__main__":

    # -----------------------------------------------------------------
    # Current controlled experiment
    # -----------------------------------------------------------------

    SUBJECT = "1"
    SESSION = "0"
    ACQUISITION = "train"
    RUN = "0"

    # -----------------------------------------------------------------
    # Step 1
    # Load continuous EEG
    # -----------------------------------------------------------------

    raw = load_eeg(
        subject=SUBJECT,
        session=SESSION,
        acquisition=ACQUISITION,
        run=RUN,
    )

    # -----------------------------------------------------------------
    # Step 2
    # Inspect channel/electrode metadata
    # -----------------------------------------------------------------

    channels, electrodes, coordsystem = inspect_electrode_metadata(
        subject=SUBJECT,
        session=SESSION,
        acquisition=ACQUISITION,
        run=RUN,
    )

    # -----------------------------------------------------------------
    # Step 3
    # Verify channel/electrode consistency
    # -----------------------------------------------------------------

    compare_channel_names(
        raw=raw,
        channels=channels,
        electrodes=electrodes,
    )

    # -----------------------------------------------------------------
    # Step 4
    # Inspect and validate task events
    # -----------------------------------------------------------------

    events = inspect_events(
        subject=SUBJECT,
        session=SESSION,
        acquisition=ACQUISITION,
        run=RUN,
        sfreq=raw.info["sfreq"],
    )