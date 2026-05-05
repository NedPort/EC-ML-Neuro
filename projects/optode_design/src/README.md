# Optode Design for Full-Head fNIRS Coverage

## Overview
This module focuses on designing and validating source–detector (optode) configurations for full-head fNIRS data acquisition. The workflow combines AtlasViewer (HOMER3) and MATLAB-based analysis to ensure anatomically consistent placement and reliable channel quality before physical implementation (e.g., 3D printing).

---

## Methodology

### 1. Optode Layout Design (AtlasViewer)
- Used AtlasViewer to construct a full-head probe geometry.
- Defined **anchor points** based on the international 10–20 / 10–10 EEG system (e.g., Cz, C3, C4, etc.).
- Positioned sources and detectors such that resulting channels align with these standardized cortical locations.
- Applied **spring-relaxation modeling** within AtlasViewer to:
  - Maintain stable spacing between optodes
  - Distribute them evenly across the scalp
  - Avoid unrealistic clustering or distortion

---

### 2. Export and Processing (MATLAB)
- Exported probe geometry (`probe_reg.txt`) and neighbor relationships.
- Parsed spatial coordinates of sources and detectors.
- Constructed neighbor mappings between optodes (source–detector pairs).

---

### 3. Distance Validation (Python/MATLAB Code)
- Computed Euclidean distances between each source–detector pair:
  
  \[
  d = \| \mathbf{s} - \mathbf{d} \|
  \]

- Verified that all channels fall within the **physiologically valid range**:
  - Typical acceptable range: **25–35 mm (~3 cm)**

- Flagged:
  - **Too short distances** → poor penetration depth
  - **Too long distances** → weak signal quality

---

### 4. Quality Assurance Before Fabrication
- Identified and corrected problematic optode pairs
- Iteratively refined layout to maximize:
  - Coverage of cortical regions
  - Channel validity
- Ensured that the final design meets constraints **before 3D printing**

---

## Outcome
- Full-head optode configuration aligned with standard brain regions
- Validated channel distances across all source–detector pairs
- A physically realizable design suitable for fabrication and experimental use

---

## Notes
- This process bridges **neuroanatomical design (AtlasViewer)** and **computational validation (code)**  
- Ensures both **biological relevance** and **engineering feasibility**