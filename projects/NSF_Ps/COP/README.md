# COP Pipeline — Quick Run Commands

Run all commands from the COP project root:

```powershell
cd projects/NSF_Ps/COP
```

## Stage 1 — Virtual Head Geometry

### Create Head / Brain Geometry
```powershell
uv run python -m stage_1_virtual_geometry.head.create_head
```

### Brain Surface
```powershell
uv run python -m stage_1_virtual_geometry.head.brain_surface
```

### Scalp Surface
```powershell
uv run python -m stage_1_virtual_geometry.head.scalp_surface
```

### Cortical Parcellation
```powershell
uv run python -m stage_1_virtual_geometry.head.parcellation
```

### Optode Placement
```powershell
uv run python -m stage_1_virtual_geometry.optode_placement
```

---

## Stage 2 — EEG-Driven Functional Brain

### EEG Preprocessing
```powershell
uv run python -m stage_2_functional_brain.eeg.preprocessing
```

### ICA Decomposition
```powershell
uv run python -m stage_2_functional_brain.eeg.ica
```

> ICA is computationally expensive. Do not rerun if the saved ICA model already exists.

### Inspect Saved ICA
Loads the existing ICA model, restores CapTrak electrode geometry, and displays IC topographies and time courses.

```powershell
uv run python -m stage_2_functional_brain.eeg.inspect_ica
```

### ICLabel Classification
Loads the existing ICA model and classifies the 128 ICs into Brain, Muscle, Eye, Heart, Line Noise, Channel Noise, and Other.

```powershell
uv run python -m stage_2_functional_brain.eeg.classify_ica
```

This stage does **not** refit ICA or remove components. It generates classification probabilities for subsequent KEEP / REJECT / REVIEW decisions.


## Current Pipeline

```text
Virtual Head Geometry
        ↓
EEG Preprocessing
        ↓
Manual BAD Annotation
        ↓
Extended Infomax ICA
        ↓
ICA Inspection + CapTrak Topographies
        ↓
ICLabel Classification
        ↓
KEEP / REJECT / REVIEW
        ↓
[Next] Brain-IC Selection
        ↓
[Next] Source Localization
        ↓
[Next] 3-D Functional Brain
        ↓
[Next] Neurovascular / Hemodynamic Model
        ↓
[Next] Virtual fNIRS Optical Simulation
```