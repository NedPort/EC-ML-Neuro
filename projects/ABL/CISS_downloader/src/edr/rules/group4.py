from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from src.edr.parsers.observation_parser import (
    Observation,
    normalize_text,
)


# ============================================================
# Group definition
# ============================================================

GROUP_NAME = "group4"
RULE_VERSION = "1.1"


# ============================================================
# Result models
# ============================================================

@dataclass
class Group4RuleResult:
    matched: bool
    destination: str
    family: str
    orientation: str
    axis_type: str
    confidence: str
    reason: str
    requires_review: bool = False
    review_reason: str = ""
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "destination": self.destination,
            "family": self.family,
            "orientation": self.orientation,
            "axis_type": self.axis_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "requires_review": self.requires_review,
            "review_reason": self.review_reason,
            "rule_version": self.rule_version,
        }


@dataclass
class Group4TableResult:
    matched: bool
    destination: str
    family: str
    orientation: str
    axis_type: str
    confidence: str
    reason: str
    requires_review: bool = False
    review_reason: str = ""


# ============================================================
# Missing / unavailable values
# ============================================================

MISSING_VALUES = {
    "",
    "n/a",
    "na",
    "sna",
    "not available",
    "not applicable",
    "unknown",
    "not recorded",
    "data not available",
    "invalid",
}


def is_missing_or_na(
    value: str,
) -> bool:
    return (
        normalize_text(
            value
        )
        in MISSING_VALUES
    )


# ============================================================
# Basic helpers
# ============================================================

def is_numeric(
    value: str,
) -> bool:
    text = str(
        value or ""
    ).strip()

    if not text:
        return False

    return bool(
        re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?",
            text,
        )
    )


def populated(
    row: Iterable[str],
) -> list[str]:
    return [
        str(value).strip()
        for value in row
        if str(value).strip()
    ]


# ============================================================
# Axis recognition
# ============================================================

AXIS_PATTERNS = (
    r"^time\b",
    r"^times\b",
    r"^relative time\b",
    r"^sample\b",
    r"^sample number\b",
    r"^sample index\b",
    r"^index\b",
    r"^buffer address\b",
    r"^buffer order\b",
    r"^sequence\b",
)


def is_axis_header_text(
    value: str,
) -> bool:
    text = normalize_text(
        value
    )

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE,
        )
        for pattern in AXIS_PATTERNS
    )


def classify_axis_label(
    label: str,
) -> str:
    text = normalize_text(
        label
    )

    if re.search(
        r"\btime\b|\btimes\b",
        text,
        re.I,
    ):
        return "relative_time"

    if re.search(
        r"\bbuffer\b",
        text,
        re.I,
    ):
        return "buffer_order"

    if re.search(
        r"\bsample\b",
        text,
        re.I,
    ):
        return "sample_index"

    if re.search(
        r"\bindex\b|\bsequence\b",
        text,
        re.I,
    ):
        return "ordered_index"

    return "ordered_axis"


# ============================================================
# PID / raw-hex exclusion
# ============================================================

PID_HEX_PATTERNS = (
    r"^pidsstart\b",
    r"^pidsend\b",
    r"^hexadecimal data\b",
    r"^raw hex\b",
    r"^raw byte\b",
)


def is_pid_or_hex_marker(
    value: str,
) -> bool:
    text = str(
        value or ""
    ).strip()

    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern
        in PID_HEX_PATTERNS
    )


# ============================================================
# Group 4 companion metadata
# ============================================================

CRASH_PULSE_COMPANION_PATTERNS = (
    r"Recording Status.*Time Series",
    r"Time from TRG to Next Sample",
    r"Maximum Delta-V",
    r"Time,\s*Maximum Delta-V",
    r"Clipping Time",
    r"Length of Delta-V",
    r"RollAngle Peak",
    r"Roll Angle at the Time of TRG",
)


def is_crash_pulse_scalar_companion(
    heading: str,
    rows: list[list[str]],
) -> bool:
    """
    Scalar information describing a sampled crash-pulse record
    is Group 4 companion metadata, not a sampled series itself.
    """

    if (
        "crash pulse"
        not in str(
            heading or ""
        ).casefold()
    ):
        return False

    useful = [
        populated(row)
        for row in rows
        if populated(row)
    ]

    if not useful:
        return False

    max_width = max(
        len(row)
        for row in useful
    )

    # Companion context is scalar / key-value structure.
    if max_width > 2:
        return False

    text = " ".join(
        " ".join(row)
        for row in useful
    )

    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern
        in CRASH_PULSE_COMPANION_PATTERNS
    )


# ============================================================
# Samples-by-rows recognition
# ============================================================

def detect_samples_by_rows(
    rows: list[list[str]],
) -> tuple[
    bool,
    int | None,
    int | None,
    str,
]:
    """
    Example:

        Time | Speed | Brake
        -5   | 10    | Off
        -4   | 12    | Off
        -3   | 15    | On
    """

    if len(rows) < 3:
        return (
            False,
            None,
            None,
            "",
        )

    for header_index, row in enumerate(
        rows[:10]
    ):
        nonblank = populated(
            row
        )

        if len(nonblank) < 2:
            continue

        for axis_col, cell in enumerate(
            row
        ):
            if not is_axis_header_text(
                cell
            ):
                continue

            axis_values = []

            for data_row in rows[
                header_index + 1:
            ]:
                if (
                    axis_col
                    >= len(data_row)
                ):
                    continue

                value = str(
                    data_row[
                        axis_col
                    ]
                ).strip()

                if not value:
                    continue

                if (
                    is_numeric(value)
                    or is_missing_or_na(
                        value
                    )
                ):
                    axis_values.append(
                        value
                    )

            if len(
                axis_values
            ) >= 2:
                return (
                    True,
                    header_index,
                    axis_col,
                    classify_axis_label(
                        cell
                    ),
                )

    return (
        False,
        None,
        None,
        "",
    )


# ============================================================
# Samples-by-columns recognition
# ============================================================

def detect_samples_by_columns(
    rows: list[list[str]],
) -> tuple[
    bool,
    int | None,
    str,
]:
    """
    Example:

        Time  | -5 | -4 | -3
        Speed | 10 | 12 | 15
        Brake |  0 |  0 |  1
    """

    if len(rows) < 2:
        return (
            False,
            None,
            "",
        )

    for row_index, row in enumerate(
        rows[:50]
    ):
        if not row:
            continue

        first_nonblank = ""

        for value in row:
            if str(
                value
            ).strip():
                first_nonblank = str(
                    value
                ).strip()
                break

        if not first_nonblank:
            continue

        if not is_axis_header_text(
            first_nonblank
        ):
            continue

        numeric_count = sum(
            1
            for value in row
            if is_numeric(
                value
            )
        )

        if numeric_count < 2:
            continue

        # Must have at least one following signal row with
        # >=2 populated values aligned to the samples.
        signal_rows = 0

        for candidate in rows[
            row_index + 1:
        ]:
            vals = populated(
                candidate
            )

            if len(vals) < 3:
                continue

            first = vals[0]

            # Another axis row marks another block,
            # not a signal.
            if is_axis_header_text(
                first
            ):
                continue

            value_count = sum(
                1
                for value in vals[1:]
                if (
                    is_numeric(value)
                    or is_missing_or_na(
                        value
                    )
                )
            )

            if value_count >= 2:
                signal_rows += 1

        if signal_rows:
            return (
                True,
                row_index,
                classify_axis_label(
                    first_nonblank
                ),
            )

    return (
        False,
        None,
        "",
    )


# ============================================================
# Repeated transposed blocks
# ============================================================

def count_transposed_axis_blocks(
    rows: list[list[str]],
) -> int:
    """
    Example:

        Time | -70 ... 70
        Delta-V | ...

        Time | 80 ... 220
        Delta-V | ...

    Both axis rows belong to the same physical series.
    """

    count = 0

    for row in rows:
        cells = populated(
            row
        )

        if not cells:
            continue

        if not is_axis_header_text(
            cells[0]
        ):
            continue

        numeric_count = sum(
            1
            for value in cells[1:]
            if is_numeric(
                value
            )
        )

        if numeric_count >= 2:
            count += 1

    return count


# ============================================================
# PCM recognition
# ============================================================

def is_pcm_units_row(
    row: list[str],
) -> bool:
    """
    Valid PCM definition row starts approximately with:

        Hex | Seconds | ...
    """

    cells = populated(
        row
    )

    if len(cells) < 2:
        return False

    return (
        cells[0].casefold()
        == "hex"
        and cells[1].casefold()
        == "seconds"
    )


def looks_like_pcm_table(
    heading: str,
    rows: list[list[str]],
) -> bool:
    heading_norm = normalize_text(
        heading
    )

    if (
        "pcm"
        not in heading_norm
    ):
        return False

    for row in rows[:10]:
        if is_pcm_units_row(
            row
        ):
            return True

    # Some validated PCM structures lacked relative time
    # and retained only ordered buffer structure.
    if any(
        "buffer address"
        in normalize_text(
            cell
        )
        for row in rows[:5]
        for cell in row
    ):
        return True

    return False


# ============================================================
# Static snapshot detection
# ============================================================

def looks_like_single_snapshot(
    rows: list[list[str]],
) -> bool:
    """
    A single temporal snapshot is not a sampled time series.
    """

    temporal_rows = 0

    for row in rows:
        cells = populated(
            row
        )

        if not cells:
            continue

        if (
            is_axis_header_text(
                cells[0]
            )
            and sum(
                is_numeric(
                    value
                )
                for value in cells[1:]
            )
            == 1
        ):
            temporal_rows += 1

    return temporal_rows == 1


# ============================================================
# Graphical/garbled PDF evidence
# ============================================================

GRAPHICAL_TEXT_PATTERNS = (
    r"ddeellttaa",
    r"lloonnggiittuuddiinnaall",
    r"ccrraasshh",
    r"ppuullssee",
)


def looks_like_garbled_graphical_evidence(
    rows: list[list[str]],
) -> bool:
    text = " ".join(
        " ".join(
            populated(row)
        )
        for row in rows
    )

    if any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern
        in GRAPHICAL_TEXT_PATTERNS
    ):
        return True

    # Collapsed numeric axis text such as:
    # 0 20 40 60 ... 260 msec
    numbers = re.findall(
        r"[-+]?\d+(?:\.\d+)?",
        text,
    )

    if (
        len(numbers) >= 8
        and re.search(
            r"\b(?:msec|ms|seconds?|sec)\b",
            text,
            re.I,
        )
        and (
            "delta-v"
            in text.casefold()
            or "crash pulse"
            in text.casefold()
        )
    ):
        return True

    return False


# ============================================================
# Full table classifier
# ============================================================

def classify_group4_table(
    *,
    heading: str,
    rows: list[list[str]],
    source_format: str = "",
) -> Group4TableResult:
    """
    Classify an entire structural table/block.

    This is the primary Group 4 classifier.
    """

    source_format = normalize_text(
        source_format
    )

    # --------------------------------------------------------
    # No rows
    # --------------------------------------------------------

    if not rows:
        return Group4TableResult(
            matched=False,
            destination="review",
            family="empty_structure",
            orientation="",
            axis_type="",
            confidence="low",
            reason="No source rows available.",
            requires_review=True,
            review_reason="Empty structural candidate.",
        )

    # --------------------------------------------------------
    # Raw PID/hex block
    # --------------------------------------------------------

    first_cells = [
        cell
        for row in rows[:5]
        for cell in row
    ]

    if any(
        is_pid_or_hex_marker(
            value
        )
        for value in first_cells
    ):
        return Group4TableResult(
            matched=False,
            destination="exclude",
            family="raw_pid_hex",
            orientation="",
            axis_type="",
            confidence="high",
            reason=(
                "Raw PID/hex payload is outside Group 4 "
                "measurement extraction."
            ),
        )

    # --------------------------------------------------------
    # Crash-pulse companion metadata
    # --------------------------------------------------------

    if is_crash_pulse_scalar_companion(
        heading,
        rows,
    ):
        return Group4TableResult(
            matched=False,
            destination="group4_companion",
            family="timeseries_companion_metadata",
            orientation="",
            axis_type="",
            confidence="high",
            reason=(
                "Scalar metadata describes a Group 4 "
                "time-series record but is not sampled data."
            ),
        )

    # --------------------------------------------------------
    # PDF graphical evidence
    # --------------------------------------------------------

    if (
        source_format == "pdf"
        and looks_like_garbled_graphical_evidence(
            rows
        )
    ):
        return Group4TableResult(
            matched=False,
            destination="review",
            family="graphical_timeseries_evidence",
            orientation="",
            axis_type="",
            confidence="high",
            reason=(
                "PDF contains graphical/garbled temporal "
                "evidence that cannot be safely reconstructed."
            ),
            requires_review=True,
            review_reason=(
                "Preserve graph as review evidence; do not "
                "force-parse samples."
            ),
        )

    # --------------------------------------------------------
    # PCM / buffer-order
    # --------------------------------------------------------

    if looks_like_pcm_table(
        heading,
        rows,
    ):
        has_relative_time = any(
            re.search(
                r"\brelative time\b",
                normalize_text(
                    cell
                ),
                re.I,
            )
            for row in rows[:10]
            for cell in row
        )

        return Group4TableResult(
            matched=True,
            destination=GROUP_NAME,
            family="pcm_timeseries",
            orientation=(
                "samples_by_rows"
            ),
            axis_type=(
                "relative_time"
                if has_relative_time
                else "buffer_order"
            ),
            confidence="high",
            reason=(
                "Validated PCM/buffer-order measurement "
                "structure."
            ),
        )

    # --------------------------------------------------------
    # Samples by rows
    # --------------------------------------------------------

    (
        row_match,
        _header_index,
        _axis_col,
        row_axis_type,
    ) = detect_samples_by_rows(
        rows
    )

    if row_match:
        return Group4TableResult(
            matched=True,
            destination=GROUP_NAME,
            family="time_series",
            orientation="samples_by_rows",
            axis_type=row_axis_type,
            confidence="high",
            reason=(
                "Repeated measurements are indexed by an "
                "ordered axis down table rows."
            ),
        )

    # --------------------------------------------------------
    # Samples by columns / transposed
    # --------------------------------------------------------

    (
        col_match,
        _axis_row,
        col_axis_type,
    ) = detect_samples_by_columns(
        rows
    )

    if col_match:
        block_count = (
            count_transposed_axis_blocks(
                rows
            )
        )

        reason = (
            "Repeated measurements are indexed across "
            "table columns."
        )

        if block_count > 1:
            reason += (
                " Multiple repeated axis/signal blocks "
                "occur inside the same physical table."
            )

        return Group4TableResult(
            matched=True,
            destination=GROUP_NAME,
            family="time_series",
            orientation="samples_by_columns",
            axis_type=col_axis_type,
            confidence="high",
            reason=reason,
        )

    # --------------------------------------------------------
    # Single snapshot
    # --------------------------------------------------------

    if looks_like_single_snapshot(
        rows
    ):
        return Group4TableResult(
            matched=False,
            destination="exclude",
            family="single_temporal_snapshot",
            orientation="",
            axis_type="",
            confidence="high",
            reason=(
                "One temporal snapshot does not constitute "
                "a repeated sampled time series."
            ),
        )

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    return Group4TableResult(
        matched=False,
        destination="review",
        family="unresolved_structural_candidate",
        orientation="",
        axis_type="",
        confidence="low",
        reason=(
            "No validated Group 4 structural pattern matched."
        ),
        requires_review=True,
        review_reason=(
            "Preserve source structure for later review."
        ),
    )


# ============================================================
# Observation-level classifier
# ============================================================

def classify_group4(
    observation: Observation,
) -> Group4RuleResult:
    """
    Lightweight routing for one parsed observation.

    IMPORTANT:
    Final Group 4 acceptance should be made with
    classify_group4_table(), because Group 4 is structural.
    """

    # --------------------------------------------------------
    # Empty
    # --------------------------------------------------------

    if observation.is_empty:
        return Group4RuleResult(
            matched=False,
            destination="",
            family="",
            orientation="",
            axis_type="",
            confidence="",
            reason="Empty row.",
        )

    # --------------------------------------------------------
    # Parser already identified repeated structure
    # --------------------------------------------------------

    if observation.is_repeated:
        return Group4RuleResult(
            matched=True,
            destination=GROUP_NAME,
            family="repeated_measurement_candidate",
            orientation="unknown_until_table_review",
            axis_type="ordered_axis",
            confidence="high",
            reason=(
                "Parser identified repeated measurement "
                "structure; final orientation requires "
                "table-level evaluation."
            ),
        )

    # --------------------------------------------------------
    # Header candidate
    # --------------------------------------------------------

    if observation.is_table_header:
        return Group4RuleResult(
            matched=True,
            destination=GROUP_NAME,
            family="timeseries_header_candidate",
            orientation="unknown_until_table_review",
            axis_type=(
                classify_axis_label(
                    observation.label
                )
            ),
            confidence="medium",
            reason=(
                "Observation is a repeated-measurement "
                "table-header candidate."
            ),
        )

    # --------------------------------------------------------
    # A scalar is not Group 4 by itself
    # --------------------------------------------------------

    return Group4RuleResult(
        matched=False,
        destination="",
        family="",
        orientation="",
        axis_type="",
        confidence="",
        reason=(
            "Scalar observation alone does not establish "
            "Group 4 membership."
        ),
    )