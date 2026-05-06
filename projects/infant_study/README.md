# Infant Bilingualism and Effective Connectivity using Resting-State fNIRS

This project investigates how early bilingual exposure influences infant brain connectivity using resting-state functional near-infrared spectroscopy (fNIRS) and effective connectivity (EC) analysis.

The framework combines graph-based connectivity modeling with fNIRS neuroimaging to study directional information flow in the developing infant brain during resting state conditions.

The associated study is published in *Neurophotonics*.

---

# Overview

Early language exposure plays an important role in shaping infant brain development and neural organization. While previous studies primarily focused on undirected functional connectivity, this project investigates directional cortical interactions using effective connectivity analysis.

The study examines:
- Resting-state brain connectivity in 4-month-old infants
- Differences between bilingual and monolingual environments
- Temporal evolution of connectivity patterns
- Frontal and opercular network organization
- Directional information flow across cortical regions

The framework integrates:
- Resting-state fNIRS analysis
- Effective connectivity modeling
- Adaptive MVAR-based GPDC estimation
- Graph construction techniques
- ICEC (Importance of Channels using Effective Connectivity)
- Statistical and topographic analysis

---

# Dataset

This project utilizes a publicly available resting-state infant fNIRS dataset including:

- 99 infants (4 months old)
- Bilingual and monolingual groups
- Resting-state recordings during sleep
- Full-head cortical coverage
- 52 fNIRS channels (46 channels used after quality control)

The dataset includes:
- Basque–Spanish bilingual infants
- Spanish monolingual infants
- Basque monolingual infants

The recordings were acquired using a NIRScout fNIRS system following the international 10–20 positioning system.

---

# Methodology

## 1. Signal Preprocessing

The preprocessing pipeline includes:
- Optical density conversion
- Motion artifact correction
- Spline and wavelet correction
- HbO/HbR computation
- COE (Cerebral Oxygen Exchange) calculation
- Channel quality filtering

The analysis focuses on:
- Oxygenated hemoglobin (HbO)
- Cerebral oxygen exchange (COE)

---

## 2. Effective Connectivity Analysis

Effective connectivity is estimated using:
- Adaptive Multivariate Autoregressive (AMVAR) modeling
- Generalized Partial Directed Coherence (GPDC)

The framework captures:
- Directed cortical interactions
- Frequency-specific information flow
- Temporal evolution of resting-state connectivity
- Source and sink behavior of brain regions

Connectivity analysis is performed within the frequency range:
- 0.02–0.06 Hz

---

## 3. ICEC Framework

The project employs the proposed:
- Importance of Channels using Effective Connectivity (ICEC)

ICEC is a graph-based framework designed to:
- Quantify channel importance
- Identify source and sink regions
- Rank connectivity significance
- Improve interpretability of EC networks

The method combines:
- Edge-based EC quantification
- Node-level importance analysis
- Temporal network characterization
- Statistical validation with surrogate testing

---

# Main Findings

The study revealed anatomically specific differences between bilingual and monolingual infants.

Major observations include:
- Increased opercular connectivity in bilingual infants
- Stronger frontal-temporal interactions
- Dynamic temporal evolution of EC patterns
- Reorganization of information flow across resting periods
- Distinct source and sink behavior in opercular regions

The findings suggest that early bilingual exposure may influence the organization of large-scale cortical communication networks even during resting state.

---

# Brain Regions Involved

Significant effects were observed in:
- Superior frontal gyrus (SFG)
- Superior temporal gyrus
- Rolandic operculum
- Inferior frontal operculum
- Temporal cortical regions

The operculum regions demonstrated:
- Persistent activity across resting intervals
- Increased connectivity in bilingual infants
- Dynamic inflow and outflow behavior

---

# Temporal Analysis

The project also investigates longitudinal changes during resting state by analyzing:
- Early resting intervals
- Middle resting intervals
- Late resting intervals

Results suggest that:
- Early rest is dominated by frontal-opercular inflow
- Later periods shift toward temporal and opercular outflow
- Connectivity organization evolves dynamically over time

---

# Visualization

The framework supports:
- Topographic visualization
- BrainNet Viewer integration
- Inter-hemispheric EC visualization
- Axial and sagittal brain network rendering
- Temporal EC evolution plots

---

# Applications

Potential applications include:
- Developmental neuroscience
- Early language development research
- Infant neuroimaging
- Brain connectivity analysis
- Early biomarkers of neurodevelopment
- Resting-state network modeling

---

# Current Status

This repository currently includes:
- Connectivity analysis workflows
- Graph construction methods
- Statistical analysis pipelines
- Visualization tools
- Resting-state fNIRS methodologies

Additional modules and experimental extensions may be added progressively.

---

# References

1. Abdollahpour, N., & Artan, N. S. (2025).  
   *Significant interactions in infant operculum regions when exposed to a bilingual environment: a resting-state fNIRS study*.  
   Neurophotonics, 12(4), 045012.  
   DOI: https://doi.org/10.1117/1.NPh.12.4.045012

2. Blanco, B., et al.  
   *Open-access resting-state fNIRS dataset of monolingual and bilingual infants*.  
   OSF Repository.  
   DOI: https://doi.org/10.17605/OSF.IO/7FZKM

3. Baccalá, L. A., & Sameshima, K. (2001).  
   *Partial directed coherence: A new concept in neural structure determination*.  
   Biological Cybernetics, 84, 463–474.  
   DOI: https://doi.org/10.1007/PL00007990