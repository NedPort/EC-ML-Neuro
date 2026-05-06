# Effective Connectivity-Based Mental Fatigue Analysis using fNIRS

This project investigates how mental fatigue alters directional brain connectivity using functional Near-Infrared Spectroscopy (fNIRS) and effective connectivity (EC) analysis.

The framework focuses on modeling causal interactions among cortical regions during sustained cognitive tasks using generalized partial directed coherence (GPDC) and graph-based analysis methods.

The associated study is published in *Frontiers in Electronics*:

> Abdollahpour N., Artan N.S.  
> *Effective connectivity-based recognition of mental fatigue patterns using functional near-infrared spectroscopy*  
> Frontiers in Electronics, 2025. :contentReference[oaicite:0]{index=0}

---

# Overview

Mental fatigue affects attention, executive control, reaction time, and cognitive performance. While many previous studies focused on signal-level analysis or undirected functional connectivity, this project investigates directional interactions between brain regions through effective connectivity modeling.

The proposed framework analyzes:
- Temporal evolution of cortical connectivity
- Directed information flow between brain regions
- Fatigue-related network reorganization
- Changes in prefrontal and motor connectivity patterns
- Graph-theoretical characteristics of fatigue-related brain dynamics

The project combines:
- fNIRS preprocessing
- MVAR-based connectivity estimation
- GPDC analysis
- Graph construction
- Statistical analysis
- Brain network visualization

---

# Dataset

The project utilizes a publicly available multimodal EEG-fNIRS dataset collected during a Stroop task experiment involving sustained cognitive workload. :contentReference[oaicite:1]{index=1}

Dataset characteristics:
- 21 healthy participants
- Continuous EEG and fNIRS recordings
- Stroop-task paradigm
- Frontal and parietal cortical coverage
- Cognitive conflict and fatigue induction setup

The recordings include:
- Resting-state periods
- Neutral-task conditions
- Incongruent-task conditions
- Continuous hemodynamic measurements

---

# Methodology

The analysis pipeline consists of several stages:

## 1. Signal Preprocessing

Raw fNIRS signals are processed through:
- Optical density conversion
- Modified Beer-Lambert Law (MBLL)
- Baseline correction
- Bandpass filtering
- HbO/HbR extraction

The preprocessing pipeline is designed to preserve slow hemodynamic oscillations relevant to fatigue-related cortical activity. :contentReference[oaicite:2]{index=2}

---

## 2. Effective Connectivity Estimation

Effective connectivity is estimated using:
- Adaptive Multivariate Autoregressive (AMVAR) modeling
- Generalized Partial Directed Coherence (GPDC)

The framework models directional interactions among cortical regions and captures frequency-specific information flow within brain networks. :contentReference[oaicite:3]{index=3}

Key features include:
- Sliding-window EC analysis
- Time-resolved connectivity tracking
- Frequency-domain causal modeling
- Stability analysis for MVAR estimation
- Surrogate-based statistical validation

---

## 3. Graph-Based Brain Network Modeling

Connectivity matrices are transformed into directed brain graphs where:
- Nodes represent fNIRS channels
- Edges represent directional information flow
- Edge weights reflect GPDC intensity

Graph-based metrics are then used to analyze:
- Network density
- Inflow/outflow characteristics
- Connectivity variability
- Fatigue-related network flexibility

The framework also supports:
- BrainNet Viewer integration
- 3D brain network visualization
- Topographic significance mapping

---

# Main Findings

The study revealed several fatigue-related neural patterns:

- Progressive reduction in HbO amplitude during prolonged task performance
- Transition from distributed connectivity to more rigid network organization
- Increased involvement of prefrontal and motor regions
- Strong fatigue-related effects in right-hemispheric cortical areas
- Reduced network flexibility under sustained cognitive load

The findings suggest that mental fatigue alters not only activation levels but also the directional organization of cortical communication networks. :contentReference[oaicite:4]{index=4}

---

# Brain Regions Involved

Significant fatigue-related EC changes were observed in:
- Prefrontal cortex
- Premotor cortex
- Motor cortex
- Superior temporal regions
- Frontal executive-control networks

Particularly affected channels included:
- Right anterior prefrontal cortex
- Right premotor cortex
- Right middle frontal gyrus
- Medial motor cortex

These regions are associated with:
- Executive control
- Sustained attention
- Cognitive regulation
- Motor planning

:contentReference[oaicite:5]{index=5}

---

# Applications

Potential applications of this framework include:
- Real-time fatigue monitoring
- Neuroergonomics
- Human-machine interaction
- Brain-computer interfaces (BCI)
- Cognitive workload analysis
- Safety-critical monitoring systems
- Neurorehabilitation research

---

# Current Status

This repository currently focuses on:
- Research implementation
- Connectivity analysis pipelines
- Visualization tools
- Statistical analysis workflows
- Experimental neuroimaging methodologies

Additional modules and expanded implementations may be added progressively.

---

# Citation

If you use this work, please cite:

Abdollahpour, N., & Artan, N. S. (2025). Effective connectivity-based recognition of mental fatigue patterns using functional near-infrared spectroscopy. Frontiers in Electronics, 6, 1668332.