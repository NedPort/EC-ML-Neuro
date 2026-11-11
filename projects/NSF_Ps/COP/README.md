<!-- # COP Pipeline — Quick Run Commands

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






## linux env

wsl -d Ubuntu-24.04

cd ~/bem_mne
source .venv/bin/activate

export FREESURFER_HOME=/usr/local/freesurfer/8.2.0
source $FREESURFER_HOME/SetUpFreeSurfer.sh
export FS_LICENSE=$FREESURFER_HOME/license.txt



cd /mnt/c/Users/nedpo/Desktop/Software/VS_Docs/neda-codebase/neda-codebase/projects/NSF_Ps/COP/stage_2_functional_brain/source_model/bem


##
 -->




# COP Pipeline — Quick Run Commands

This README is a **run guide** for reproducing the COP pipeline for a new subject.

Run commands from the COP project root unless otherwise specified.

```powershell
cd projects/NSF_Ps/COP
```

---

# Stage 1 — Virtual Head Geometry

These steps build the common virtual anatomy. They do **not** need to be repeated for every EEG subject unless the anatomy/model changes.

## 1. Create Head / Brain Geometry

```powershell
uv run python -m stage_1_virtual_geometry.head.create_head
```

Creates the virtual head/brain geometry.

## 2. Brain Surface

```powershell
uv run python -m stage_1_virtual_geometry.head.brain_surface
```

Creates/visualizes the cortical brain surface.

## 3. Scalp Surface

```powershell
uv run python -m stage_1_virtual_geometry.head.scalp_surface
```

Creates/visualizes the scalp surface.

## 4. Cortical Parcellation

```powershell
uv run python -m stage_1_virtual_geometry.head.parcellation
```

Maps cortical vertices to cortical parcels.

## 5. Optode Placement

```powershell
uv run python -m stage_1_virtual_geometry.optode_placement
```

Creates the initial virtual optode-placement geometry.

---

# Stage 2 — EEG-Driven Functional Brain

For a new subject, update the subject/session/run settings in the relevant EEG scripts before running them.

---

## 1. EEG Preprocessing

```powershell
uv run python -m stage_2_functional_brain.eeg.preprocessing
```

**Does:** loads raw EEG, applies preprocessing/filtering, restores sensor geometry, and prepares the EEG for ICA.

Manual BAD-segment review is performed during this stage.

---

## 2. Run ICA

```powershell
uv run python -m stage_2_functional_brain.eeg.ica
```

**Does:** runs Extended Infomax ICA on the preprocessed EEG.

> Do not rerun if a valid saved ICA model already exists.

---

## 3. Inspect ICA

```powershell
uv run python -m stage_2_functional_brain.eeg.inspect_ica
```

**Does:** loads the saved ICA model and displays IC scalp topographies and time courses.

Use this for manual component inspection.

---

## 4. ICLabel

```powershell
uv run python -m stage_2_functional_brain.eeg.classify_ica
```

**Does:** classifies ICs into Brain, Muscle, Eye, Heart, Line Noise, Channel Noise, and Other.

This does **not** automatically remove components.

---

## 5. Manual IC Selection

Review the ICA/ICLabel outputs and assign:

```text
KEEP
REMOVE
REVIEW
```

The retained ICs become the neural components used for source localization.

---

# EEG Source Localization

Source-model scripts are located in:

```text
stage_2_functional_brain/source_model/bem/
```

The BEM/anatomical model is common and should **not** be rebuilt for every subject unless the head model itself changes.

---

## 6. Register Subject EEG Sensors

```bash
cd stage_2_functional_brain/source_model/bem
python register_captrak_to_virtual_head.py
```

**Does:** rigidly registers the subject's CapTrak EEG sensor coordinates to the MNI152 virtual head.

Produces the registered electrode geometry used for source modeling.

---

## 7. Build HEAD → MRI Transform

```bash
python build_head_mri_transform.py
```

**Does:** converts the validated CapTrak → MNI registration into the MNE HEAD → MRI transformation required by the forward model.

For a new subject, this transform is **subject-specific**.

---

## 8. Forward Geometry QC

```bash
python visualize_forward_geometry.py
```

**Does:** visualizes the subject's transformed EEG electrodes together with the cortex, BEM surfaces, and source space.

Check that:

```text
electrodes align with scalp
no gross translation
no rotation error
no left/right reflection
```

Do this before building the subject's forward model.

---

# Common BEM Model

The following BEM files are already built and normally **reused across subjects**:

```text
icbm152-ico4-bem.fif
icbm152-ico4-bem-sol.fif
```

Do not rebuild them for Subject 2 unless the virtual head model changes.

---

# Common Cortical Source Spaces

The nested cortical candidate spaces are already built:

```text
source_space_candidates/
├── source_space_p2500.csv
├── source_space_p5000.csv
└── source_space_p10000.csv
```

The corresponding MNE source spaces are:

```text
icbm152-discrete-p2500-src.fif
icbm152-discrete-p5000-src.fif
icbm152-discrete-p10000-src.fif
```

These are common cortical geometry and normally **do not need to be rebuilt for each subject**.

If they must be regenerated:

```bash
python build_source_space_p2500.py
```

Set inside the script:

```python
P = 2500
```

or:

```python
P = 5000
```

or:

```python
P = 10000
```

**Does:** converts an existing cortical candidate CSV into an MNE discrete source-space FIF.

---

## 9. Visualize Source Spaces

```bash
python visualize_source_space_p.py
```

**Does:** visualizes the cortical source locations and saves QC views.

This is primarily geometry QC and normally does not need to be repeated for every subject.

---

# Build Subject Forward Models

## 10. Build P = 2500 Forward Model

In:

```text
build_forward_p2500.py
```

set:

```python
P = 2500
```

then run:

```bash
python build_forward_p2500.py
```

**Does:** combines:

```text
subject EEG electrodes
        +
subject HEAD → MRI transform
        +
common BEM
        +
P=2500 cortical source space
        ↓
subject EEG forward model
```

Expected gain-matrix size:

```text
128 × 7500
```

---

## 11. Build P = 5000 Forward Model

Change:

```python
P = 5000
```

then:

```bash
python build_forward_p2500.py
```

Expected:

```text
128 × 15000
```

---

## 12. Build P = 10000 Forward Model

Change:

```python
P = 10000
```

then:

```bash
python build_forward_p2500.py
```

Expected:

```text
128 × 30000
```

---

# Quick Subject Workflow

For **Subject 2**, the practical workflow is:

```text
Subject 2 raw EEG
        ↓
preprocessing.py
        ↓
ica.py
        ↓
inspect_ica.py
        ↓
classify_ica.py
        ↓
Manual KEEP / REMOVE
        ↓
register_captrak_to_virtual_head.py
        ↓
build_head_mri_transform.py
        ↓
visualize_forward_geometry.py
        ↓
build_forward_p2500.py
    P=2500
        ↓
build_forward_p2500.py
    P=5000
        ↓
build_forward_p2500.py
    P=10000
        ↓
Subject 2 forward models
```

### Reuse — Do NOT Rebuild for Every Subject

```text
✓ MNI152 anatomy
✓ cortical meshes
✓ ico4 BEM geometry
✓ ico4 BEM numerical solution
✓ 2500 source-space geometry
✓ 5000 source-space geometry
✓ 10000 source-space geometry
```

### Repeat for Every Subject

```text
✓ EEG preprocessing
✓ ICA
✓ ICA inspection / ICLabel
✓ manual IC selection
✓ CapTrak registration
✓ HEAD → MRI transform
✓ electrode/geometry QC
✓ subject-specific forward models
```

---

# Current Pipeline Status

```text
Virtual Head Geometry
        ↓
EEG Preprocessing
        ↓
Manual BAD Annotation
        ↓
ICA
        ↓
IC Inspection + ICLabel
        ↓
Manual IC Selection
        ↓
CapTrak Registration
        ↓
HEAD → MRI Transform
        ↓
Forward Geometry QC
        ↓
P=2500 Forward Model
        ↓
P=5000 Forward Model
        ↓
P=10000 Forward Model
        ↓
[CURRENT]
        ↓
[Next] Inverse Source Localization
        ↓
[Next] Cortical IC Maps
        ↓
[Next] Source-Density Convergence
        ↓
[Later] Neural Field N(r,t)
        ↓
[Later] Hemodynamic Model
        ↓
[Later] Virtual fNIRS Simulation
```

---

# Linux / WSL Environment

Enter Ubuntu:

```powershell
wsl -d Ubuntu-24.04
```

Activate environment:

```bash
cd ~/bem_mne
source .venv/bin/activate
```

Set FreeSurfer:

```bash
export FREESURFER_HOME=/usr/local/freesurfer/8.2.0
source $FREESURFER_HOME/SetUpFreeSurfer.sh
export FS_LICENSE=$FREESURFER_HOME/license.txt
```

Go to BEM/source-model directory:

```bash
cd /mnt/c/Users/nedpo/Desktop/Software/VS_Docs/neda-codebase/neda-codebase/projects/NSF_Ps/COP/stage_2_functional_brain/source_model/bem
```