# ICEC Graph Construction

A graph-based neuroimaging framework for effective connectivity analysis and unsupervised EEG channel selection using the proposed ICEC (Importance of Channels based on Effective Connectivity) criterion.

This project focuses on quantifying the importance of EEG channels based on the intensity of directional interactions among brain regions using effective connectivity (EC) analysis.

The framework combines:

* Effective connectivity modeling
* Graph construction methods
* Unsupervised channel selection
* Time-frequency EEG analysis
* Brain network visualization
* CSP-based feature extraction
* Machine learning for EEG decoding

---

## Overview

High-dimensional EEG recordings often contain redundant or less informative channels. This project introduces the ICEC criterion to quantify the importance of EEG electrodes based on effective connectivity interactions.

The proposed method:

* Identifies the most informative EEG channels
* Reduces computational complexity
* Preserves classification performance
* Supports interpretable brain network analysis

Unlike supervised channel selection methods, ICEC operates in an unsupervised manner and does not require labeled trials for channel ranking.

---

## Methodology

The framework includes:

* Adaptive multivariate autoregressive (AMVAR) modeling
* Effective connectivity estimation
* 4D connectivity matrix construction
* Graph-based node importance analysis
* Channel ranking using ICEC
* EEG channel subset selection

Five effective connectivity metrics are supported:

* PDC
* GPDC
* RPDC
* DTF
* dDTF

The framework analyzes interactions across multiple frequency bands including:

* Theta
* Mu
* Low-beta
* High-beta
* Gamma
* 8–30 Hz
* 1–40 Hz

---

## Graph Construction

The project constructs graph representations from effective connectivity matrices where:

* Nodes represent EEG channels
* Directed edges represent information flow
* Edge weights represent interaction intensity

The ICEC criterion quantifies:

* Node importance
* Connectivity intensity
* Temporal interaction consistency
* Channel relevance within brain networks

The framework also supports:

* Topographic visualization
* Time-frequency interaction analysis
* Dynamic brain network visualization
* Connectivity-based graph interpretation

---

## Datasets

The proposed method was evaluated using multiple well-known EEG motor imagery datasets including:

* BCI Competition IV Dataset 2a
* BCI Competition IV Dataset 1
* BCI Competition III Dataset IVa

The datasets include:

* 22-channel EEG recordings
* 59-channel EEG recordings
* 118-channel EEG recordings

---

## Results

The proposed ICEC-based framework demonstrated:

* Improved classification performance
* Significant reduction in selected EEG channels
* Robust channel selection across participants
* Consistent performance across multiple datasets

Reported results include:

* 82% accuracy using 13 out of 22 channels
* 86.01% accuracy using 29 out of 59 channels
* 87.56% accuracy using 48 out of 118 channels

The framework achieved competitive performance compared to multiple state-of-the-art CSP-based channel selection methods.

---

## Applications

Potential applications include:

* Brain-computer interfaces (BCI)
* EEG channel optimization
* Neuroimaging analysis
* Brain connectivity visualization
* Real-time EEG systems
* Wearable neurotechnology
* Computational neuroscience research

---

## Current Status

This work has been accepted for publication in the:

Journal of Medical Signals & Sensors

The project currently includes:

* Connectivity analysis workflows
* ICEC graph construction methods
* EEG channel ranking pipelines
* Visualization and analysis tools

Additional modules and implementations may be added progressively.

---

## Reference

Abdollahpour, N., Artan, N. S., Daly, I., Yazdchi, M., & Baharlouei, Z.
Effective Connectivity-Based Unsupervised Channel Selection Method for EEG.
Accepted for publication in the Journal of Medical Signals & Sensors.
