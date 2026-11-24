# CISS Acquisition Framework

A configurable framework for acquiring, organizing, and auditing crash investigation data from the National Highway Traffic Safety Administration (NHTSA) Crash Investigation Sampling System (CISS).

## Overview

Describe the framework's purpose, supported data sources, and research applications.

## Features

- Case-level CISS data acquisition
- Selective downloading of investigation assets
- Resumable acquisition workflows
- CDRX discovery and inventory generation
- Support for externally generated Bosch CDR PDF/CSV reports
- Automated acquisition-integrity auditing
- Structured provenance and audit reporting

## Repository Structure

Describe the source code, configuration, data directories, and output artifacts.

## Requirements

Document supported Python versions, dependency management, operating systems, and optional external software.

## Installation

Provide repository cloning and `uv` installation instructions.

## Configuration

Explain how to customize directories, acquisition options, and optional licensed-software integration.

## Usage

### CISS Case Discovery and Inventory

Document `count_all_ciss_cdrx.py`.

### Case Acquisition

Document the acquisition entry point and supported options.

### Licensed CDR Export

Explain the optional external conversion workflow.

### Acquisition Auditing

Document `audit_all.py`, its command-line options, and output reports.

## Precomputed Results

Describe the released CISS inventory, its coverage, generation date, and reproducibility instructions.

## Data Organization

Explain the existing raw, temporary, and processed data directories.

## Validation and Limitations

Describe acquisition verification, file-presence checks, and limitations of downstream semantic validation.

## Reproducibility

Provide the commands and configuration needed to reproduce the published experiments.

## Data Access and Licensing

Describe NHTSA data access, external software requirements, and the repository's software license.

## Citation

Provide citation information for the associated publication.

## Contact and Contributions

Provide project-maintainer and contribution information.
