# NHTSA Crash Test Downloader

A Python toolkit for downloading and organizing crash test data from the
National Highway Traffic Safety Administration (NHTSA) Research & Testing
Database.

The project provides a simple interface for retrieving crash test metadata and
associated engineering data files, including EV, UDS, ABF, ISO, and TDMS
formats. Downloaded files are automatically organized into folders by crash
test number, making them easy to use for biomechanics, crashworthiness,
machine learning, and data analysis research.

## Features

- Download crash test metadata in JSON format.
- Download EV (engineering value) signal files.
- Download Universal Data Set (UDS) files.
- Download ATB Binary Format (ABF) files when available.
- Download ISO measurement files when available.
- Download National Instruments TDMS files when available.
- Automatically organize downloads by crash test number.
- Skip previously downloaded files to support interrupted downloads.
- Optionally overwrite existing files.
- Download individual crash tests or the entire NHTSA database.

## Project Structure

```text
nhtsa_downloader/
├── data/          # Downloaded crash test data
├── src/           # Source code
├── tests/         # Unit tests
├── notebooks/     # Analysis notebooks
├── main.py        # Example entry point
└── README.md
```

## Example

```python
from src.downloader import download_all_tests

download_all_tests(max_tests=100)
```

This downloads the first 100 crash tests (or fewer if the database contains fewer records).

## Data Source

National Highway Traffic Safety Administration (NHTSA)

Research & Testing Database:
https://www.nhtsa.gov/research-data/research-testing-databases
