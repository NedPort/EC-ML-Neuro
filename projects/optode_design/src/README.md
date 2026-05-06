# Optode Design for Full-Head fNIRS Coverage

## Overview

This module focuses on the design, validation, and optimization of source–detector (optode) configurations for full-head fNIRS data acquisition. The workflow combines AtlasViewer (HOMER3), MATLAB/Python-based spatial analysis, and computational validation to ensure anatomically consistent placement, valid channel geometry, and reliable signal acquisition before physical fabrication.

The project also includes preparation for custom cap fabrication using 3D printing technologies for future experimental recordings.

---

## Methodology

### 1. Optode Layout Design (AtlasViewer)

* Used AtlasViewer to construct and visualize full-head probe geometries
* Defined anchor points based on the international 10–20 / 10–10 EEG positioning systems (e.g., Cz, C3, C4, Fz, Pz)
* Positioned sources and detectors such that resulting fNIRS channels align with standardized cortical locations
* Applied spring-relaxation modeling within AtlasViewer to:

  * Maintain stable spacing between optodes
  * Distribute optodes uniformly across the scalp
  * Reduce unrealistic clustering or geometric distortion
  * Improve full-head cortical coverage

---

### 2. Spatial Coordinate Processing

* Exported probe geometry files (`probe_reg.txt`) from AtlasViewer
* Parsed the 3D spatial coordinates of sources and detectors:

  * x-coordinate
  * y-coordinate
  * z-coordinate
* Constructed source–detector neighbor mappings and channel relationships
* Processed full-head coordinate structures for computational validation and visualization

---

### 3. 3D Distance Validation

For each source–detector pair, Euclidean distance was computed in 3D space using the x, y, and z coordinates of each optode.

The validation process ensured that channels remained within physiologically acceptable ranges for reliable fNIRS acquisition.

Typical acceptable source–detector distance:

* 25–35 mm (~3 cm)

Channels were flagged as:

* Too short → limited cortical penetration depth
* Too long → reduced signal quality and low signal-to-noise ratio (SNR)

---

### 4. Iterative Layout Optimization

The design was iteratively refined to:

* Improve anatomical alignment with cortical regions
* Maximize valid channel coverage
* Reduce invalid source–detector distances
* Preserve full-head spatial consistency
* Improve feasibility for wearable acquisition systems

This workflow enabled systematic optimization before fabrication and experimental deployment.

---

### 5. Fabrication Preparation

The final validated layouts are being prepared for:

* Custom wearable cap development
* 3D printing integration
* Experimental fNIRS acquisition studies
* Full-head neuroimaging experiments

This stage bridges computational neuroimaging design with physical implementation.

---

## Outcome

* Full-head optode configurations aligned with standard cortical landmarks
* Validated 3D source–detector distances
* Computationally optimized probe geometries
* Physically realizable layouts suitable for fabrication and experimental use
* Integration-ready designs for future neuroimaging studies

---

## Notes

This workflow bridges:

* Neuroanatomical design
* Computational geometry validation
* Neuroengineering implementation

The framework combines:

* AtlasViewer / HOMER3
* MATLAB/Python spatial analysis
* 3D coordinate processing
* Experimental acquisition preparation

The goal is to ensure both:

* Biological and anatomical relevance
* Engineering feasibility and acquisition reliability
