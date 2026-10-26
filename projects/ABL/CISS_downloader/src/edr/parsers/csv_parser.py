from __future__ import annotations

import csv
from pathlib import Path

from src.edr.parsers.observation_parser import (
    Observation,
    parse_rows,
)


csv.field_size_limit(100_000_000)


def read_csv_rows(
    path: str | Path,
) -> list[list[str]]:
    """
    Read an EDR CSV file without changing the original values.
    """

    path = Path(path)

    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline="",
    ) as f:

        reader = csv.reader(f)

        return [
            [
                "" if value is None else str(value)
                for value in row
            ]
            for row in reader
        ]


def parse_csv_file(
    path: str | Path,
) -> list[Observation]:
    """
    Parse one EDR CSV file into generalized observations.

    Section context and structural interpretation are handled
    by observation_parser.parse_rows().
    """

    rows = read_csv_rows(
        path
    )

    return parse_rows(
        rows
    )