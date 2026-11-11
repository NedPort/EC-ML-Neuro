"""
Stage 2.3 - Automatic ICA component classification using ICLabel.

IMPORTANT
---------
This script DOES NOT:
- fit ICA again
- remove ICA components
- modify the saved ICA model
- reconstruct cleaned EEG

It loads the already-fitted ICA decomposition and uses MNE-ICALabel
to estimate class probabilities for each independent component.

ICLabel classes:
    Brain
    Muscle Artifact
    Eye Blink
    Heart Beat
    Line Noise
    Channel Noise
    Other

The probabilities are used as decision support only.

Output:
    stage_2_functional_brain/eeg/ica_results/
        sub-1_ses-0_acq-train_run-0_iclabel.csv
"""

from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd
import mne

from mne_icalabel.iclabel import iclabel_label_components


# =====================================================================
# Configuration
# =====================================================================

SUBJECT = "1"
SESSION = "0"
ACQUISITION = "train"
RUN = "0"


# ---------------------------------------------------------------------
# Decision thresholds
#
# These are OUR screening thresholds, not ICLabel's own labels.
# They are intentionally conservative.
# ---------------------------------------------------------------------

BRAIN_KEEP_THRESHOLD = 0.80
ARTIFACT_REJECT_THRESHOLD = 0.80


# =====================================================================
# Paths
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

output_csv = (
    ICA_DIR
    / f"sub-{SUBJECT}_ses-{SESSION}_"
      f"acq-{ACQUISITION}_run-{RUN}_"
      f"iclabel.csv"
)


# =====================================================================
# Validate files
# =====================================================================

print()
print("=" * 72)
print("VALIDATING INPUT FILES")
print("=" * 72)

required_files = [
    annotated_file,
    ica_file,
    electrodes_file,
    coordsystem_file,
]

for path in required_files:

    if not path.exists():
        raise FileNotFoundError(
            f"Required file not found:\n{path}"
        )

    print(f"FOUND: {path}")


# =====================================================================
# Load annotated EEG
# =====================================================================

print()
print("=" * 72)
print("LOADING ANNOTATED EEG")
print("=" * 72)

raw = mne.io.read_raw_fif(
    annotated_file,
    preload=True,
    verbose=False,
)

print()
print(raw)

print()
print(f"Channels      : {raw.info['nchan']}")
print(f"Sampling rate : {raw.info['sfreq']} Hz")
print(f"Samples       : {raw.n_times:,}")


# =====================================================================
# Load CapTrak electrode information
# =====================================================================

print()
print("=" * 72)
print("LOADING CAPTRAK GEOMETRY")
print("=" * 72)

electrodes = pd.read_csv(
    electrodes_file,
    sep="\t",
)

with open(
    coordsystem_file,
    "r",
    encoding="utf-8",
) as f:

    coord_info = json.load(f)


coordinate_units = coord_info.get(
    "EEGCoordinateUnits"
)

if coordinate_units != "m":

    raise ValueError(
        "Expected electrode coordinates in meters. "
        f"Found: {coordinate_units}"
    )


# =====================================================================
# Construct channel-position dictionary
# =====================================================================

raw_names = set(
    raw.ch_names
)

electrode_names = set(
    electrodes["name"].astype(str)
)

missing_coordinates = sorted(
    raw_names - electrode_names
)

if missing_coordinates:

    raise RuntimeError(
        "The following EEG channels do not have "
        "CapTrak coordinates:\n"
        + "\n".join(missing_coordinates)
    )


ch_pos = {}

for _, row in electrodes.iterrows():

    name = str(
        row["name"]
    )

    if name not in raw_names:
        continue

    ch_pos[name] = np.array(
        [
            float(row["x"]),
            float(row["y"]),
            float(row["z"]),
        ],
        dtype=float,
    )


# =====================================================================
# Fiducials
# =====================================================================

fiducials = coord_info.get(
    "FiducialsCoordinates",
    {}
)

for required in [
    "NAS",
    "LPA",
    "RPA",
]:

    if required not in fiducials:

        raise RuntimeError(
            f"Missing fiducial: {required}"
        )


nasion = np.asarray(
    fiducials["NAS"],
    dtype=float,
)

lpa = np.asarray(
    fiducials["LPA"],
    dtype=float,
)

rpa = np.asarray(
    fiducials["RPA"],
    dtype=float,
)


# =====================================================================
# Create montage
# =====================================================================

montage = mne.channels.make_dig_montage(
    ch_pos=ch_pos,
    nasion=nasion,
    lpa=lpa,
    rpa=rpa,
    coord_frame="head",
)


raw.set_montage(
    montage,
    match_case=True,
    on_missing="raise",
)


print()
print(
    f"Montage attached to Raw: "
    f"{len(ch_pos)} EEG positions"
)


# =====================================================================
# Load existing ICA
# =====================================================================

print()
print("=" * 72)
print("LOADING EXISTING ICA")
print("=" * 72)

ica = mne.preprocessing.read_ica(
    ica_file,
    verbose=False,
)

print()
print(ica)

print()
print(
    f"ICA components : {ica.n_components_}"
)

print(
    f"Existing exclusions : {ica.exclude}"
)


# =====================================================================
# Verify channel correspondence
# =====================================================================

if list(ica.ch_names) != list(raw.ch_names):

    raise RuntimeError(
        "ICA and Raw channel names/order do not match."
    )


print()
print(
    "ICA and Raw channel order match exactly."
)


# =====================================================================
# Attach montage to ICA info
# =====================================================================

ica.info.set_montage(
    montage,
    match_case=True,
    on_missing="raise",
)

print(
    "CapTrak montage attached to ICA info."
)


# =====================================================================
# IMPORTANT ICLabel preprocessing warning
# =====================================================================

print()
print("=" * 72)
print("ICLABEL METHODOLOGICAL NOTE")
print("=" * 72)

print()
print(
    "ICLabel probabilities are being used as "
    "SCREENING / DECISION-SUPPORT information."
)

print()
print(
    "The existing ICA was fitted using our current "
    "EEG preprocessing pipeline."
)

print(
    "We are NOT refitting ICA solely to optimize "
    "ICLabel classification."
)

print()
print(
    "Therefore, automated labels will NOT be used "
    "as the sole basis for component rejection."
)


# =====================================================================
# Run ICLabel and obtain FULL 7-class probability matrix
# =====================================================================

print()
print("=" * 72)
print("RUNNING ICLabel")
print("=" * 72)

print()
print("Classifying all ICA components...")
print("Requesting full 7-class probability matrix.")
print()


with warnings.catch_warnings():

    warnings.simplefilter("always")

    probabilities = iclabel_label_components(
        raw,
        ica,
        inplace=False,
    )


# =====================================================================
# Validate returned probability matrix
# =====================================================================

print()
print("=" * 72)
print("ICLABEL RETURNED")
print("=" * 72)

probabilities = np.asarray(
    probabilities,
    dtype=float,
)

print()
print(
    f"Probability array shape: "
    f"{probabilities.shape}"
)


# =====================================================================
# ICLabel class order
# =====================================================================

class_names = [
    "Brain",
    "Muscle",
    "Eye",
    "Heart",
    "LineNoise",
    "ChannelNoise",
    "Other",
]


expected_shape = (
    ica.n_components_,
    len(class_names),
)


if probabilities.shape != expected_shape:

    raise RuntimeError(
        "\nUnexpected ICLabel probability matrix shape.\n"
        f"Expected: {expected_shape}\n"
        f"Found:    {probabilities.shape}\n"
    )


print()
print(
    "Full ICLabel probability matrix "
    "successfully obtained."
)


# =====================================================================
# Check probability sums
# =====================================================================

probability_sums = probabilities.sum(
    axis=1
)


print()
print(
    "Probability-sum range:"
)

print(
    f"  minimum = "
    f"{probability_sums.min():.6f}"
)

print(
    f"  maximum = "
    f"{probability_sums.max():.6f}"
)


if not np.allclose(
    probability_sums,
    1.0,
    atol=1e-3,
):

    print()
    print(
        "WARNING: Some ICLabel class probabilities "
        "do not sum approximately to 1."
    )


# =====================================================================
# Build classification table
# =====================================================================

print()
print("=" * 72)
print("BUILDING CLASSIFICATION TABLE")
print("=" * 72)


artifact_classes = [
    "Muscle",
    "Eye",
    "Heart",
    "LineNoise",
    "ChannelNoise",
]


rows = []


for component_index in range(
    ica.n_components_
):

    component_name = (
        f"ICA{component_index:03d}"
    )


    # -------------------------------------------------------------
    # Full seven-class probability vector
    # -------------------------------------------------------------

    probs = probabilities[
        component_index,
        :
    ]


    probability_dict = {
        class_name: float(probability)
        for class_name, probability
        in zip(
            class_names,
            probs,
        )
    }


    # -------------------------------------------------------------
    # Predicted class
    # -------------------------------------------------------------

    max_index = int(
        np.argmax(probs)
    )

    predicted_class = (
        class_names[max_index]
    )

    confidence = float(
        probs[max_index]
    )


    # -------------------------------------------------------------
    # Brain probability
    # -------------------------------------------------------------

    brain_probability = float(
        probability_dict[
            "Brain"
        ]
    )


    # -------------------------------------------------------------
    # Strongest explicit artifact probability
    # -------------------------------------------------------------

    strongest_artifact_class = max(
        artifact_classes,
        key=lambda cls: probability_dict[cls],
    )

    strongest_artifact_probability = float(
        probability_dict[
            strongest_artifact_class
        ]
    )


    # -------------------------------------------------------------
    # Screening decision
    #
    # IMPORTANT:
    #
    # These are candidate decisions only.
    # Nothing is removed here.
    #
    # Other is NOT automatically rejected.
    # -------------------------------------------------------------

    if (
        brain_probability
        >= BRAIN_KEEP_THRESHOLD
    ):

        decision = (
            "KEEP_CANDIDATE"
        )

        decision_reason = (
            f"Brain >= "
            f"{BRAIN_KEEP_THRESHOLD:.2f}"
        )


    elif (
        strongest_artifact_probability
        >= ARTIFACT_REJECT_THRESHOLD
    ):

        decision = (
            "REJECT_CANDIDATE"
        )

        decision_reason = (
            f"{strongest_artifact_class} >= "
            f"{ARTIFACT_REJECT_THRESHOLD:.2f}"
        )


    else:

        decision = (
            "REVIEW"
        )

        decision_reason = (
            "No high-confidence brain "
            "or artifact classification"
        )


    # -------------------------------------------------------------
    # Store result
    # -------------------------------------------------------------

    rows.append(
        {
            "IC":
                component_name,

            "IC_index":
                component_index,

            "Brain":
                probability_dict["Brain"],

            "Muscle":
                probability_dict["Muscle"],

            "Eye":
                probability_dict["Eye"],

            "Heart":
                probability_dict["Heart"],

            "LineNoise":
                probability_dict["LineNoise"],

            "ChannelNoise":
                probability_dict["ChannelNoise"],

            "Other":
                probability_dict["Other"],

            "PredictedClass":
                predicted_class,

            "Confidence":
                confidence,

            "StrongestArtifactClass":
                strongest_artifact_class,

            "StrongestArtifactProbability":
                strongest_artifact_probability,

            "Decision":
                decision,

            "DecisionReason":
                decision_reason,

            # Reserved for our later manual inspection
            "ManualDecision":
                "",

            "ManualReason":
                "",
        }
    )


results = pd.DataFrame(
    rows
)


# =====================================================================
# Save complete classification table
# =====================================================================

ICA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


results.to_csv(
    output_csv,
    index=False,
)


print()
print(
    f"Saved classification table:\n"
    f"{output_csv}"
)


# =====================================================================
# Predicted-class summary
# =====================================================================

print()
print("=" * 72)
print("ICLABEL CLASSIFICATION SUMMARY")
print("=" * 72)

print()
print("Predicted classes:")
print()


predicted_counts = (
    results[
        "PredictedClass"
    ]
    .value_counts()
)


for label, count in predicted_counts.items():

    print(
        f"  {label:15s}: "
        f"{count}"
    )


# =====================================================================
# Screening-decision summary
# =====================================================================

print()
print("Screening decisions:")
print()


decision_counts = (
    results[
        "Decision"
    ]
    .value_counts()
)


for decision, count in decision_counts.items():

    print(
        f"  {decision:18s}: "
        f"{count}"
    )


# =====================================================================
# Brain candidates
# =====================================================================

brain_candidates = (
    results[
        results["Decision"]
        == "KEEP_CANDIDATE"
    ]
    .sort_values(
        "Brain",
        ascending=False,
    )
)


print()
print("=" * 72)
print("HIGH-CONFIDENCE BRAIN CANDIDATES")
print("=" * 72)


if len(brain_candidates) == 0:

    print()
    print(
        "No components exceeded "
        "the current brain threshold."
    )

else:

    print()

    print(
        brain_candidates[
            [
                "IC",
                "Brain",
                "PredictedClass",
                "Confidence",
            ]
        ]
        .to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )


# =====================================================================
# Artifact candidates
# =====================================================================

artifact_candidates = (
    results[
        results["Decision"]
        == "REJECT_CANDIDATE"
    ]
    .sort_values(
        "StrongestArtifactProbability",
        ascending=False,
    )
)


print()
print("=" * 72)
print("HIGH-CONFIDENCE ARTIFACT CANDIDATES")
print("=" * 72)


if len(artifact_candidates) == 0:

    print()
    print(
        "No components exceeded "
        "the current artifact threshold."
    )

else:

    print()

    print(
        artifact_candidates[
            [
                "IC",
                "Brain",
                "StrongestArtifactClass",
                "StrongestArtifactProbability",
                "PredictedClass",
                "Confidence",
            ]
        ]
        .to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )


# =====================================================================
# Components requiring manual review
# =====================================================================

review_components = (
    results[
        results["Decision"]
        == "REVIEW"
    ]
    .sort_values(
        "Confidence",
        ascending=False,
    )
)


print()
print("=" * 72)
print("COMPONENTS REQUIRING MANUAL REVIEW")
print("=" * 72)

print()
print(
    f"Number requiring review: "
    f"{len(review_components)}"
)


if len(review_components) > 0:

    print()

    print(
        review_components[
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
            ]
        ]
        .to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}",
        )
    )


# =====================================================================
# Final safety confirmation
# =====================================================================

print()
print("=" * 72)
print("CLASSIFICATION COMPLETE")
print("=" * 72)

print()
print(
    "NO ICA COMPONENTS WERE REMOVED."
)

print(
    "NO CLEANED EEG WAS CREATED."
)

print(
    "THE SAVED ICA MODEL WAS NOT MODIFIED."
)

print()
print(
    "ICLabel probabilities are being used "
    "as screening information only."
)

print()
print(
    f"Classification results saved to:\n"
    f"{output_csv}"
)