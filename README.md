# EC-ML-Neuro

A research framework for neuroimaging analysis combining:

- Brain connectivity modeling
- Machine learning for fNIRS/EEG
- Optode design and spatial configuration

## Projects

- fatigue_detection → ML pipeline for fatigue analysis using neuroimaging signals, including preprocessing, connectivity analysis, feature extraction, Patter Recognition and statistical evaluation.

- ec_transformer → transformer-based connectivity modeling framework integrating temporal and effective connectivity representations for fNIRS analysis. The project includes adaptive gating mechanisms for combining multiple physiological representations. The associated manuscript is currently under second-round revision in the *IEEE Journal of Biomedical and Health Informatics (JBHI Ref: JBHI-06874-2025.R1)*. Due to the ongoing review process, the implementation is not publicly released at this stage.

- optode_design → tools for source-detector configuration, full-head optode placement, and spatial validation for fNIRS acquisition systems. The project includes development of full-head configurations aligned with standard EEG positioning systems, distance validation between sources and detectors, and ongoing fabrication of a custom cap using 3D printing technologies for future recording experiments and data acquisition studies.

- infant_study → pattern recognition and statistical analysis framework for infant neuroimaging studies, including dependency-aware statistical modeling, analysis of correlated variables, experimental task design, and IRB-related study preparation.

- ICEC_graph_construction → graph-based effective connectivity framework for unsupervised EEG channel selection and neuroimaging analysis. The project introduces the ICEC (Importance of Channels based on Effective Connectivity) criterion for quantifying directional interactions among EEG channels using multiple effective connectivity measures including PDC, GPDC, RPDC, DTF, and dDTF. The framework supports graph construction, time-frequency connectivity analysis, topographic visualization, and channel optimization for EEG decoding tasks. The associated manuscript has been accepted for publication in the *Journal of Medical Signals & Sensors*.