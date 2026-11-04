from pathlib import Path
import mne


# =====================================================================
# Load saved cleaned/annotated EEG
# =====================================================================

PROJECT_ROOT = Path.cwd()

annotated_file = (
    PROJECT_ROOT
    / "stage_2_functional_brain"
    / "eeg"
    / "processed"
    / "sub-1_ses-0_acq-train_run-0_hp-1Hz_annotated_raw.fif"
)

raw_annotated = mne.io.read_raw_fif(
    annotated_file,
    preload=True,
    verbose=False,
)


# =====================================================================
# Check annotations
# =====================================================================

print(raw_annotated)
print()
print("Annotations:")
print(raw_annotated.annotations)


# =====================================================================
# Reopen interactive EEG browser
# =====================================================================

raw_annotated.plot(
    start=0.0,
    duration=10.0,
    n_channels=30,
    scalings="auto",
    show_scrollbars=True,
    show_options=True,
    block=True,
)