from __future__ import annotations

from pathlib import Path

from src.edr.parsers.observation_parser import Observation


def parse_pdf_file(
    path: str | Path,
) -> list[Observation]:
    """
    Unified interface for PDF-only EDR reports.

    IMPORTANT
    ---------
    This function must eventually call the validated EDR PDF
    extraction logic already developed for the project.

    We intentionally do NOT implement a generic PDF text parser
    here because doing so could bypass the validated table and
    structural extraction logic used for Groups 1-6.
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"PDF file not found: {path}"
        )

    raise NotImplementedError(
        "Validated EDR PDF extraction adapter has not yet "
        "been connected."
    )