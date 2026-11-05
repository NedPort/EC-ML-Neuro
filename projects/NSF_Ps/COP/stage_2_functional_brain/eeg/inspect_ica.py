"""
Stage 2.4 - ICA inspection, ICLabel review, and manual annotation.

IMPORTANT
---------
ICA is NOT fitted again.
ICLabel is NOT run again.
NO ICA components are removed in this script.

This script:
1. Loads the saved annotated EEG.
2. Loads the saved ICLabel classification CSV.
3. Restores subject-specific CapTrak electrode geometry.
4. Loads the already-fitted ICA model.
5. Verifies ICA / EEG / electrode correspondence.
6. Displays all ICA scalp topographies.
7. Allows detailed inspection of individual ICs.
8. Adds ICLabel probabilities to the detailed MNE properties figure.
9. Allows manual annotation:
       KEEP
       REMOVE
       REVIEW
       SKIP
10. Saves every manual decision immediately to the CSV.

The automatic ICLabel screening decision and the final manual
decision remain separate.

NO ICA exclusion is applied here.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import mne


# =====================================================================
# Configuration
# =====================================================================

SUBJECT = "1"
SESSION = "0"
ACQUISITION = "train"
RUN = "0"

COMPONENTS_PER_PAGE = 20


# =====================================================================
# Project paths
# =====================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EEG_DATA_DIR = (
    PROJECT_ROOT
    / "eeg_data"
    / f"sub-{SUBJECT}"
    / f"ses-{SESSION}"
    / "eeg"
)

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


# =====================================================================
# Input files
# =====================================================================

annotated_file = (
    PROCESSED_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"hp-1Hz_annotated_raw.fif"
)

ica_file = (
    ICA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"ica.fif"
)

iclabel_file = (
    ICA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"iclabel.csv"
)

electrodes_file = (
    EEG_DATA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"space-CapTrak_electrodes.tsv"
)

coordsystem_file = (
    EEG_DATA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"space-CapTrak_coordsystem.json"
)


# =====================================================================
# Validate input files
# =====================================================================

print()
print("=" * 72)
print("VALIDATING INPUT FILES")
print("=" * 72)

required_files = [
    annotated_file,
    ica_file,
    iclabel_file,
    electrodes_file,
    coordsystem_file,
]

for path in required_files:

    print(path)

    if not path.exists():

        raise FileNotFoundError(
            f"\nRequired file not found:\n{path}"
        )

print()
print("All required files found.")


# =====================================================================
# Load ICLabel classification
# =====================================================================

print()
print("=" * 72)
print("LOADING ICLABEL CLASSIFICATION RESULTS")
print("=" * 72)

iclabel = pd.read_csv(
    iclabel_file
)


# =====================================================================
# Validate ICLabel columns
# =====================================================================

required_iclabel_columns = {
    "IC",
    "IC_index",
    "Brain",
    "Muscle",
    "Eye",
    "Heart",
    "LineNoise",
    "ChannelNoise",
    "Other",
    "PredictedClass",
    "Confidence",
    "Decision",
}


missing_iclabel_columns = (
    required_iclabel_columns
    - set(iclabel.columns)
)


if missing_iclabel_columns:

    raise RuntimeError(
        "\nICLabel CSV is missing required columns:\n"
        f"{sorted(missing_iclabel_columns)}"
    )


# =====================================================================
# Prepare manual decision columns
# =====================================================================

if "ManualDecision" not in iclabel.columns:

    iclabel[
        "ManualDecision"
    ] = ""


if "ManualReason" not in iclabel.columns:

    iclabel[
        "ManualReason"
    ] = ""


iclabel[
    "ManualDecision"
] = (
    iclabel[
        "ManualDecision"
    ]
    .fillna("")
    .astype(str)
)


iclabel[
    "ManualReason"
] = (
    iclabel[
        "ManualReason"
    ]
    .fillna("")
    .astype(str)
)


iclabel[
    "IC_index"
] = (
    iclabel[
        "IC_index"
    ]
    .astype(int)
)


# =====================================================================
# ICLabel lookup
# =====================================================================

iclabel_lookup = (
    iclabel
    .set_index(
        "IC_index"
    )
)


print()
print(
    f"Loaded ICLabel results for "
    f"{len(iclabel)} components."
)


print()
print("ICLabel predicted classes:")

print(
    iclabel[
        "PredictedClass"
    ]
    .value_counts()
)


print()
print("Automatic screening decisions:")

print(
    iclabel[
        "Decision"
    ]
    .value_counts()
)


# =====================================================================
# Existing manual decisions
# =====================================================================

manual_existing = (
    iclabel[
        "ManualDecision"
    ]
    .str.strip()
    != ""
)


print()
print(
    f"Components already manually reviewed: "
    f"{manual_existing.sum()}"
)

print(
    f"Components still undecided: "
    f"{len(iclabel) - manual_existing.sum()}"
)


if manual_existing.any():

    print()
    print("Existing manual decisions:")

    print(
        iclabel.loc[
            manual_existing,
            "ManualDecision"
        ]
        .value_counts()
    )


# =====================================================================
# Load annotated EEG
# =====================================================================

print()
print("=" * 72)
print("LOADING ANNOTATED EEG")
print("=" * 72)

raw = mne.io.read_raw_fif(
    annotated_file,
    preload=False,
    verbose=False,
)


print()
print(raw)


print()
print(
    f"EEG channels  : "
    f"{raw.info['nchan']}"
)

print(
    f"Sampling rate : "
    f"{raw.info['sfreq']} Hz"
)

print(
    f"Samples       : "
    f"{raw.n_times:,}"
)


duration_min = (
    raw.n_times
    / raw.info["sfreq"]
    / 60
)


print(
    f"Duration      : "
    f"{duration_min:.2f} min"
)


# =====================================================================
# Load coordinate-system information
# =====================================================================

print()
print("=" * 72)
print("LOADING CAPTRAK COORDINATE SYSTEM")
print("=" * 72)


with open(
    coordsystem_file,
    "r",
    encoding="utf-8",
) as f:

    coord_info = json.load(f)


coordinate_system = (
    coord_info.get(
        "EEGCoordinateSystem"
    )
)

coordinate_units = (
    coord_info.get(
        "EEGCoordinateUnits"
    )
)

coordinate_description = (
    coord_info.get(
        "EEGCoordinateSystemDescription"
    )
)


print()
print(
    f"Coordinate system : "
    f"{coordinate_system}"
)

print(
    f"Coordinate units  : "
    f"{coordinate_units}"
)


print()
print("Description:")

print(
    coordinate_description
)


if coordinate_units != "m":

    raise ValueError(
        "\nExpected CapTrak coordinates "
        "in meters.\n"
        f"Found: {coordinate_units}"
    )


# =====================================================================
# Load electrode coordinates
# =====================================================================

print()
print("=" * 72)
print("LOADING CAPTRAK ELECTRODE COORDINATES")
print("=" * 72)


electrodes = pd.read_csv(
    electrodes_file,
    sep="\t",
)


required_columns = {
    "name",
    "x",
    "y",
    "z",
}


missing_columns = (
    required_columns
    - set(
        electrodes.columns
    )
)


if missing_columns:

    raise ValueError(
        "\nElectrode TSV is missing "
        "required columns:\n"
        f"{sorted(missing_columns)}"
    )


xyz = (
    electrodes[
        ["x", "y", "z"]
    ]
    .to_numpy(
        dtype=float
    )
)


if not np.isfinite(
    xyz
).all():

    raise ValueError(
        "\nNon-finite electrode "
        "coordinates detected."
    )


print()
print(
    f"Electrode-coordinate rows: "
    f"{len(electrodes)}"
)

print(
    "All electrode coordinates are finite."
)


# =====================================================================
# EEG / CapTrak channel correspondence
# =====================================================================

print()
print("=" * 72)
print("CHECKING EEG / CAPTRAK CHANNEL CORRESPONDENCE")
print("=" * 72)


raw_names = list(
    raw.ch_names
)

raw_name_set = set(
    raw_names
)


electrode_names = (
    electrodes[
        "name"
    ]
    .astype(str)
    .tolist()
)


electrode_name_set = set(
    electrode_names
)


missing_coordinates = sorted(
    raw_name_set
    - electrode_name_set
)


extra_coordinates = sorted(
    electrode_name_set
    - raw_name_set
)


print()
print(
    f"EEG channels              : "
    f"{len(raw_names)}"
)

print(
    f"CapTrak electrode entries : "
    f"{len(electrode_names)}"
)

print(
    f"Missing coordinates       : "
    f"{len(missing_coordinates)}"
)

print(
    f"Extra coordinate entries  : "
    f"{len(extra_coordinates)}"
)


if missing_coordinates:

    print()
    print(
        "EEG channels without coordinates:"
    )

    for channel in missing_coordinates:

        print(
            f"  - {channel}"
        )

    raise RuntimeError(
        "\nSome EEG channels do not have "
        "CapTrak coordinates."
    )


# =====================================================================
# Construct channel-position dictionary
# =====================================================================

ch_pos = {}


for _, row in electrodes.iterrows():

    name = str(
        row["name"]
    )

    if name not in raw_name_set:

        continue


    ch_pos[
        name
    ] = np.array(
        [
            float(
                row["x"]
            ),
            float(
                row["y"]
            ),
            float(
                row["z"]
            ),
        ],
        dtype=float,
    )


print()
print(
    f"Prepared positions for "
    f"{len(ch_pos)} EEG channels."
)


# =====================================================================
# Fiducials
# =====================================================================

print()
print("=" * 72)
print("LOADING CAPTRAK FIDUCIALS")
print("=" * 72)


fiducials = (
    coord_info.get(
        "FiducialsCoordinates",
        {},
    )
)


required_fiducials = [
    "NAS",
    "LPA",
    "RPA",
]


missing_fiducials = [
    key
    for key in required_fiducials
    if key not in fiducials
]


if missing_fiducials:

    raise ValueError(
        "\nMissing fiducials:\n"
        f"{missing_fiducials}"
    )


nasion = np.asarray(
    fiducials[
        "NAS"
    ],
    dtype=float,
)

lpa = np.asarray(
    fiducials[
        "LPA"
    ],
    dtype=float,
)

rpa = np.asarray(
    fiducials[
        "RPA"
    ],
    dtype=float,
)


print()
print(
    f"NAS : {nasion}"
)

print(
    f"LPA : {lpa}"
)

print(
    f"RPA : {rpa}"
)


# =====================================================================
# Create montage
# =====================================================================

print()
print("=" * 72)
print("CREATING SUBJECT-SPECIFIC CAPTRAK MONTAGE")
print("=" * 72)


montage = (
    mne.channels.make_dig_montage(
        ch_pos=ch_pos,
        nasion=nasion,
        lpa=lpa,
        rpa=rpa,
        coord_frame="head",
    )
)


# =====================================================================
# Attach montage to Raw
# =====================================================================

raw.set_montage(
    montage,
    match_case=True,
    on_missing="raise",
)


print()
print(
    "Subject-specific CapTrak montage "
    "attached to Raw EEG."
)


# =====================================================================
# Verify Raw positions
# =====================================================================

print()
print("=" * 72)
print("VERIFYING RAW EEG ELECTRODE POSITIONS")
print("=" * 72)


raw_eeg_picks = (
    mne.pick_types(
        raw.info,
        eeg=True,
        exclude=[],
    )
)


raw_positions = np.array(
    [
        raw.info[
            "chs"
        ][pick][
            "loc"
        ][:3]

        for pick
        in raw_eeg_picks
    ]
)


raw_finite = (
    np.isfinite(
        raw_positions
    )
    .all(
        axis=1
    )
)


raw_nonzero = (
    np.linalg.norm(
        raw_positions,
        axis=1,
    )
    > 0
)


print()
print(
    "Raw EEG channels with finite positions: "
    f"{raw_finite.sum()} / "
    f"{len(raw_eeg_picks)}"
)

print(
    "Raw EEG channels with non-zero positions: "
    f"{raw_nonzero.sum()} / "
    f"{len(raw_eeg_picks)}"
)


if not raw_finite.all():

    raise RuntimeError(
        "Some Raw EEG positions are not finite."
    )


if not raw_nonzero.all():

    raise RuntimeError(
        "Some Raw EEG positions are zero."
    )


# =====================================================================
# Load saved ICA
# =====================================================================

print()
print("=" * 72)
print("LOADING SAVED ICA MODEL")
print("=" * 72)


ica = (
    mne.preprocessing.read_ica(
        ica_file,
        verbose=False,
    )
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
    f"Excluded ICs   : "
    f"{ica.exclude}"
)


# =====================================================================
# Validate ICA / ICLabel correspondence
# =====================================================================

print()
print("=" * 72)
print("CHECKING ICA / ICLABEL CORRESPONDENCE")
print("=" * 72)


if len(
    iclabel
) != ica.n_components_:

    raise RuntimeError(
        "\nICLabel row count does not match "
        "ICA component count.\n"
        f"ICA components : {ica.n_components_}\n"
        f"ICLabel rows   : {len(iclabel)}"
    )


expected_indices = set(
    range(
        ica.n_components_
    )
)


actual_indices = set(
    iclabel[
        "IC_index"
    ]
    .astype(int)
)


if actual_indices != expected_indices:

    raise RuntimeError(
        "\nICLabel component indices "
        "do not match ICA components."
    )


print()
print(
    "ICA and ICLabel components "
    "correspond correctly."
)


# =====================================================================
# Verify ICA / Raw channel correspondence
# =====================================================================

print()
print("=" * 72)
print("CHECKING ICA / RAW CHANNEL CORRESPONDENCE")
print("=" * 72)


ica_channels = list(
    ica.ch_names
)


print()
print(
    f"ICA channels : "
    f"{len(ica_channels)}"
)

print(
    f"Raw channels : "
    f"{len(raw.ch_names)}"
)


if ica_channels != raw.ch_names:

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
# Attach montage to ICA
# =====================================================================

print()
print("=" * 72)
print("ATTACHING CAPTRAK MONTAGE TO ICA")
print("=" * 72)


ica.info.set_montage(
    montage,
    match_case=True,
    on_missing="raise",
)


print()
print(
    "Subject-specific CapTrak montage "
    "attached to ICA info."
)


# =====================================================================
# Verify ICA electrode positions
# =====================================================================

print()
print("=" * 72)
print("VERIFYING ICA ELECTRODE POSITIONS")
print("=" * 72)


ica_eeg_picks = (
    mne.pick_types(
        ica.info,
        eeg=True,
        exclude=[],
    )
)


ica_positions = np.array(
    [
        ica.info[
            "chs"
        ][pick][
            "loc"
        ][:3]

        for pick
        in ica_eeg_picks
    ]
)


ica_finite = (
    np.isfinite(
        ica_positions
    )
    .all(
        axis=1
    )
)


ica_nonzero = (
    np.linalg.norm(
        ica_positions,
        axis=1,
    )
    > 0
)


print()
print(
    "ICA channels with finite positions: "
    f"{ica_finite.sum()} / "
    f"{len(ica_eeg_picks)}"
)

print(
    "ICA channels with non-zero positions: "
    f"{ica_nonzero.sum()} / "
    f"{len(ica_eeg_picks)}"
)


ica_dig_count = (
    len(
        ica.info[
            "dig"
        ]
    )
    if ica.info[
        "dig"
    ] is not None
    else 0
)


print(
    f"ICA digitization points: "
    f"{ica_dig_count}"
)


if not ica_finite.all():

    raise RuntimeError(
        "Some ICA EEG positions are not finite."
    )


if not ica_nonzero.all():

    raise RuntimeError(
        "Some ICA EEG positions are zero."
    )


# =====================================================================
# Sample electrode positions
# =====================================================================

print()
print("=" * 72)
print("SAMPLE ELECTRODE POSITIONS")
print("=" * 72)


sample_channels = [
    "Fp1",
    "Fp2",
    "Fz",
    "C3",
    "Cz",
    "C4",
]


for channel in sample_channels:

    if channel not in raw.ch_names:

        continue


    idx = (
        raw.ch_names.index(
            channel
        )
    )


    position = (
        raw.info[
            "chs"
        ][idx][
            "loc"
        ][:3]
    )


    print(
        f"{channel:5s}: "
        f"x={position[0]: .5f}, "
        f"y={position[1]: .5f}, "
        f"z={position[2]: .5f}"
    )


# =====================================================================
# Helper: refresh lookup
# =====================================================================

def refresh_iclabel_lookup():

    global iclabel_lookup

    iclabel_lookup = (
        iclabel
        .set_index(
            "IC_index"
        )
    )


# =====================================================================
# Helper: save CSV
# =====================================================================

def save_iclabel_csv():

    iclabel.to_csv(
        iclabel_file,
        index=False,
    )


# =====================================================================
# Helper: ICLabel information
# =====================================================================

def get_iclabel_text(
    component_index
):

    row = (
        iclabel_lookup.loc[
            component_index
        ]
    )


    manual_decision = str(
        row[
            "ManualDecision"
        ]
    ).strip()


    if manual_decision == "":

        manual_decision = (
            "UNDECIDED"
        )


    return (
        "ICLabel Classification\n"
        "----------------------\n"
        f"Brain         : "
        f"{row['Brain']:.3f}\n"
        f"Muscle        : "
        f"{row['Muscle']:.3f}\n"
        f"Eye           : "
        f"{row['Eye']:.3f}\n"
        f"Heart         : "
        f"{row['Heart']:.3f}\n"
        f"Line Noise    : "
        f"{row['LineNoise']:.3f}\n"
        f"Channel Noise : "
        f"{row['ChannelNoise']:.3f}\n"
        f"Other         : "
        f"{row['Other']:.3f}\n"
        "\n"
        f"Predicted     : "
        f"{row['PredictedClass']}\n"
        f"Confidence    : "
        f"{row['Confidence']:.1%}\n"
        f"Screening     : "
        f"{row['Decision']}\n"
        f"Manual        : "
        f"{manual_decision}"
    )


# =====================================================================
# Helper: save manual decision
# =====================================================================

def save_manual_decision(
    component_index,
    decision,
    reason="",
):

    mask = (
        iclabel[
            "IC_index"
        ]
        == component_index
    )


    if not mask.any():

        raise RuntimeError(
            f"ICA{component_index:03d} "
            "not found in ICLabel table."
        )


    iclabel.loc[
        mask,
        "ManualDecision"
    ] = decision


    iclabel.loc[
        mask,
        "ManualReason"
    ] = reason


    save_iclabel_csv()

    refresh_iclabel_lookup()


    print()
    print(
        f"ICA{component_index:03d} "
        f"manually marked as: "
        f"{decision}"
    )

    if reason:

        print(
            f"Reason: {reason}"
        )


    print(
        "Decision saved immediately "
        "to ICLabel CSV."
    )


# =====================================================================
# Helper: clear manual decision
# =====================================================================

def clear_manual_decision(
    component_index
):

    mask = (
        iclabel[
            "IC_index"
        ]
        == component_index
    )


    iclabel.loc[
        mask,
        "ManualDecision"
    ] = ""


    iclabel.loc[
        mask,
        "ManualReason"
    ] = ""


    save_iclabel_csv()

    refresh_iclabel_lookup()


    print()
    print(
        f"Manual decision cleared for "
        f"ICA{component_index:03d}."
    )


# =====================================================================
# Detailed component inspector
# =====================================================================

def inspect_component(
    component_index
):

    row = (
        iclabel_lookup.loc[
            component_index
        ]
    )


    print()
    print("=" * 72)

    print(
        f"INSPECTING "
        f"ICA{component_index:03d}"
    )

    print("=" * 72)

    print()
    print(
        get_iclabel_text(
            component_index
        )
    )


    # -------------------------------------------------------------
    # Standard MNE properties figure
    # -------------------------------------------------------------

    figures = (
        ica.plot_properties(
            raw,
            picks=[
                component_index
            ],
            show=False,
        )
    )


    if not isinstance(
        figures,
        (list, tuple),
    ):

        figures = [
            figures
        ]


    # -------------------------------------------------------------
    # Current manual status
    # -------------------------------------------------------------

    manual_decision = str(
        row[
            "ManualDecision"
        ]
    ).strip()


    if manual_decision == "":

        manual_decision = (
            "UNDECIDED"
        )


    # -------------------------------------------------------------
    # Modify MNE figure
    # -------------------------------------------------------------

    for fig in figures:

        # Make room on right side
        # for ICLabel information.

        fig.subplots_adjust(
            right=0.72
        )


        fig.suptitle(
            f"ICA{component_index:03d}"
            f" | "
            f"{row['PredictedClass']}"
            f" {row['Confidence']:.1%}"
            f" | AUTO: "
            f"{row['Decision']}"
            f" | MANUAL: "
            f"{manual_decision}",
            fontsize=12,
            fontweight="bold",
        )


        fig.text(
            0.745,
            0.77,
            get_iclabel_text(
                component_index
            ),
            fontsize=9.3,
            verticalalignment="top",
            horizontalalignment="left",
            family="monospace",
            bbox=dict(
                boxstyle="round,pad=0.6",
                facecolor="white",
                edgecolor="black",
                alpha=0.95,
            ),
        )


        fig.canvas.draw_idle()


    plt.show(
        block=False
    )


# =====================================================================
# Sensor geometry
# =====================================================================

print()
print("=" * 72)
print("PLOTTING SENSOR GEOMETRY")
print("=" * 72)


print()
print(
    "Verify the electrode geometry."
)

print(
    "Fp1/Fp2/Fpz should be anterior."
)

print(
    "C3 should be left, "
    "C4 right, and Cz central."
)

print()


raw.plot_sensors(
    kind="topomap",
    show_names=True,
    show=True,
)


# =====================================================================
# Plot ALL ICA component topographies
# =====================================================================

print()
print("=" * 72)
print("PLOTTING ALL ICA COMPONENT TOPOGRAPHIES")
print("=" * 72)


print()
print(
    "Displaying all ICA scalp topographies."
)

print(
    "These overview plots are for visual screening."
)

print(
    "Close the overview windows when ready "
    "to continue to detailed manual review."
)

print()


for start in range(
    0,
    ica.n_components_,
    COMPONENTS_PER_PAGE,
):

    stop = min(
        start
        + COMPONENTS_PER_PAGE,
        ica.n_components_,
    )


    picks = list(
        range(
            start,
            stop,
        )
    )


    ica.plot_components(
        picks=picks,
        inst=raw,
        show=False,
    )


plt.show(
    block=True
)


# =====================================================================
# ICLabel summary
# =====================================================================

print()
print("=" * 72)
print("ICA + ICLABEL SUMMARY")
print("=" * 72)


summary_table = (
    iclabel[
        [
            "IC",
            "Brain",
            "Muscle",
            "Eye",
            "Heart",
            "LineNoise",
            "ChannelNoise",
            "Other",
            "PredictedClass",
            "Confidence",
            "Decision",
            "ManualDecision",
        ]
    ]
    .copy()
)


print()

print(
    summary_table.to_string(
        index=False,
        float_format=lambda x: (
            f"{x:.3f}"
        ),
    )
)


# =====================================================================
# Review progress helper
# =====================================================================

def print_review_progress():

    reviewed_mask = (
        iclabel[
            "ManualDecision"
        ]
        .str.strip()
        != ""
    )


    reviewed = int(
        reviewed_mask.sum()
    )


    remaining = (
        len(iclabel)
        - reviewed
    )


    print()
    print("-" * 72)
    print("MANUAL REVIEW PROGRESS")
    print("-" * 72)

    print(
        f"Reviewed  : "
        f"{reviewed} / "
        f"{len(iclabel)}"
    )

    print(
        f"Remaining : "
        f"{remaining}"
    )


    if reviewed > 0:

        print()

        counts = (
            iclabel.loc[
                reviewed_mask,
                "ManualDecision"
            ]
            .value_counts()
        )


        for decision, count in (
            counts.items()
        ):

            print(
                f"{decision:10s}: "
                f"{count}"
            )


# =====================================================================
# Review priorities
# =====================================================================

print()
print("=" * 72)
print("REVIEW PRIORITIES")
print("=" * 72)


# ---------------------------------------------------------------------
# Priority 1: Borderline Brain
# ---------------------------------------------------------------------

borderline_brain = (
    iclabel[
        (
            iclabel[
                "Brain"
            ]
            >= 0.50
        )
        &
        (
            iclabel[
                "Brain"
            ]
            < 0.80
        )
    ]
    .sort_values(
        "Brain",
        ascending=False,
    )
)


print()
print(
    "PRIORITY 1 — BORDERLINE BRAIN"
)

print(
    "Brain >= 0.50 and < 0.80"
)

print()


if len(
    borderline_brain
) > 0:

    print(
        borderline_brain[
            [
                "IC",
                "Brain",
                "PredictedClass",
                "Confidence",
                "Decision",
                "ManualDecision",
            ]
        ]
        .to_string(
            index=False,
            float_format=lambda x: (
                f"{x:.3f}"
            ),
        )
    )

else:

    print(
        "None."
    )


# ---------------------------------------------------------------------
# Priority 2: Borderline Artifact
# ---------------------------------------------------------------------

artifact_columns = [
    "Muscle",
    "Eye",
    "Heart",
    "LineNoise",
    "ChannelNoise",
]


artifact_max = (
    iclabel[
        artifact_columns
    ]
    .max(
        axis=1
    )
)


borderline_artifact = (
    iclabel[
        (
            artifact_max
            >= 0.50
        )
        &
        (
            artifact_max
            < 0.80
        )
    ]
    .copy()
)


borderline_artifact[
    "ArtifactMax"
] = (
    artifact_max.loc[
        borderline_artifact.index
    ]
)


borderline_artifact = (
    borderline_artifact
    .sort_values(
        "ArtifactMax",
        ascending=False,
    )
)


print()
print(
    "PRIORITY 2 — BORDERLINE ARTIFACT"
)

print(
    "Strongest artifact probability "
    ">= 0.50 and < 0.80"
)

print()


if len(
    borderline_artifact
) > 0:

    print(
        borderline_artifact[
            [
                "IC",
                "Brain",
                "PredictedClass",
                "Confidence",
                "ArtifactMax",
                "Decision",
                "ManualDecision",
            ]
        ]
        .to_string(
            index=False,
            float_format=lambda x: (
                f"{x:.3f}"
            ),
        )
    )

else:

    print(
        "None."
    )


# =====================================================================
# Initial progress
# =====================================================================

print_review_progress()


# =====================================================================
# Interactive manual inspection
# =====================================================================

print()
print("=" * 72)
print("INTERACTIVE ICA MANUAL REVIEW")
print("=" * 72)


print()
print(
    "Enter an ICA component number "
    "to inspect."
)


print()
print(
    "Examples:"
)

print(
    "  1   -> ICA001"
)

print(
    "  91  -> ICA091"
)

print(
    "  121 -> ICA121"
)


print()
print(
    "After inspecting the component:"
)

print(
    "  k = KEEP"
)

print(
    "  r = REMOVE"
)

print(
    "  v = REVIEW / uncertain"
)

print(
    "  s = SKIP / decide later"
)

print(
    "  c = CLEAR previous manual decision"
)


print()
print(
    "Type 'status' to show review progress."
)

print(
    "Type 'remaining' to show undecided ICs."
)

print(
    "Type 'q' when finished."
)


# =====================================================================
# Interactive loop
# =====================================================================

while True:

    print()

    user_input = input(
        "ICA component [0-127], "
        "status, remaining, or q: "
    ).strip()


    # -----------------------------------------------------------------
    # Quit
    # -----------------------------------------------------------------

    if user_input.lower() in {
        "q",
        "quit",
        "exit",
    }:

        break


    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------

    if user_input.lower() == "status":

        print_review_progress()

        continue


    # -----------------------------------------------------------------
    # Remaining undecided components
    # -----------------------------------------------------------------

    if user_input.lower() == "remaining":

        remaining_mask = (
            iclabel[
                "ManualDecision"
            ]
            .str.strip()
            == ""
        )


        remaining = (
            iclabel.loc[
                remaining_mask,
                [
                    "IC",
                    "Brain",
                    "PredictedClass",
                    "Confidence",
                    "Decision",
                ],
            ]
        )


        print()
        print(
            "UNDECIDED COMPONENTS"
        )

        print("-" * 72)


        if len(
            remaining
        ) == 0:

            print(
                "All components have a "
                "manual decision."
            )

        else:

            print(
                remaining.to_string(
                    index=False,
                    float_format=lambda x: (
                        f"{x:.3f}"
                    ),
                )
            )


        continue


    # -----------------------------------------------------------------
    # Parse component index
    # -----------------------------------------------------------------

    try:

        component_index = int(
            user_input
        )

    except ValueError:

        print(
            "Please enter a valid component "
            "number, status, remaining, or q."
        )

        continue


    if not (
        0
        <= component_index
        < ica.n_components_
    ):

        print(
            f"Component must be between "
            f"0 and "
            f"{ica.n_components_ - 1}."
        )

        continue


    # -----------------------------------------------------------------
    # Show existing manual decision
    # -----------------------------------------------------------------

    current_row = (
        iclabel_lookup.loc[
            component_index
        ]
    )


    current_manual = str(
        current_row[
            "ManualDecision"
        ]
    ).strip()


    if current_manual:

        print()
        print(
            f"ICA{component_index:03d} "
            f"already has manual decision: "
            f"{current_manual}"
        )


        current_reason = str(
            current_row[
                "ManualReason"
            ]
        ).strip()


        if current_reason:

            print(
                f"Reason: "
                f"{current_reason}"
            )


    # -----------------------------------------------------------------
    # Inspect component
    # -----------------------------------------------------------------

    inspect_component(
        component_index
    )


    # -----------------------------------------------------------------
    # Manual annotation
    # -----------------------------------------------------------------

    print()
    print(
        f"Manual decision for "
        f"ICA{component_index:03d}:"
    )


    print()
    print(
        "  k = KEEP"
    )

    print(
        "  r = REMOVE"
    )

    print(
        "  v = REVIEW"
    )

    print(
        "  s = SKIP"
    )

    print(
        "  c = CLEAR previous decision"
    )


    manual_input = input(
        "\nDecision [k/r/v/s/c]: "
    ).strip().lower()


    decision_map = {
        "k": "KEEP",
        "r": "REMOVE",
        "v": "REVIEW",
    }


    # -----------------------------------------------------------------
    # KEEP / REMOVE / REVIEW
    # -----------------------------------------------------------------

    if manual_input in decision_map:

        manual_decision = (
            decision_map[
                manual_input
            ]
        )


        reason = input(
            "Reason (optional): "
        ).strip()


        save_manual_decision(
            component_index,
            manual_decision,
            reason,
        )


    # -----------------------------------------------------------------
    # Skip
    # -----------------------------------------------------------------

    elif manual_input == "s":

        print()
        print(
            f"ICA{component_index:03d} "
            "left unchanged."
        )


    # -----------------------------------------------------------------
    # Clear
    # -----------------------------------------------------------------

    elif manual_input == "c":

        clear_manual_decision(
            component_index
        )


    # -----------------------------------------------------------------
    # Invalid
    # -----------------------------------------------------------------

    else:

        print()
        print(
            "No valid decision entered."
        )

        print(
            "Component left unchanged."
        )


    # -----------------------------------------------------------------
    # Progress
    # -----------------------------------------------------------------

    print_review_progress()


# =====================================================================
# Final save
# =====================================================================

save_iclabel_csv()


# =====================================================================
# Final review report
# =====================================================================

print()
print("=" * 72)
print("FINAL MANUAL REVIEW STATUS")
print("=" * 72)


print_review_progress()


# =====================================================================
# Final KEEP list
# =====================================================================

keep_components = (
    iclabel.loc[
        iclabel[
            "ManualDecision"
        ]
        == "KEEP",
        "IC_index",
    ]
    .astype(int)
    .tolist()
)


# =====================================================================
# Final REMOVE list
# =====================================================================

remove_components = (
    iclabel.loc[
        iclabel[
            "ManualDecision"
        ]
        == "REMOVE",
        "IC_index",
    ]
    .astype(int)
    .tolist()
)


# =====================================================================
# REVIEW list
# =====================================================================

review_components = (
    iclabel.loc[
        iclabel[
            "ManualDecision"
        ]
        == "REVIEW",
        "IC_index",
    ]
    .astype(int)
    .tolist()
)


# =====================================================================
# Undecided list
# =====================================================================

undecided_components = (
    iclabel.loc[
        iclabel[
            "ManualDecision"
        ]
        .str.strip()
        == "",
        "IC_index",
    ]
    .astype(int)
    .tolist()
)


print()
print(
    f"KEEP   ({len(keep_components)}):"
)

print(
    keep_components
)


print()
print(
    f"REMOVE ({len(remove_components)}):"
)

print(
    remove_components
)


print()
print(
    f"REVIEW ({len(review_components)}):"
)

print(
    review_components
)


print()
print(
    f"UNDECIDED ({len(undecided_components)}):"
)

print(
    undecided_components
)


# =====================================================================
# Safety confirmation
# =====================================================================

print()
print("=" * 72)
print("IMPORTANT")
print("=" * 72)


print()
print(
    "Manual decisions have been saved "
    "to the ICLabel CSV."
)


print()
print(
    "NO ICA COMPONENTS WERE REMOVED."
)

print(
    "ica.exclude remains:"
)

print(
    ica.exclude
)


print()
print(
    "The REMOVE list is only an annotation "
    "at this stage."
)


print()
print(
    "After manual review is complete, "
    "the REMOVE list can be verified one "
    "final time before applying ICA exclusion."
)