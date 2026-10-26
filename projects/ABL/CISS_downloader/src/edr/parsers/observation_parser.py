from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any


# ============================================================
# Observation model
# ============================================================

@dataclass
class Observation:
    row_index: int
    row_number: int

    raw_row: list[str]

    observation_type: str

    label: str
    values: list[str]
    value_count: int

    packed_sequence: bool
    packed_sequence_count: int

    section_context: str

    is_empty: bool
    is_section_heading: bool
    is_scalar: bool
    is_repeated: bool
    is_table_header: bool

    parser_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================
# Generic text helpers
# ============================================================

def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()

    text = text.replace("\u2013", "-")
    text = text.replace("\u2014", "-")
    text = text.replace("\u2212", "-")
    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def nonempty_cells(row: list[str]) -> list[str]:
    return [
        clean_text(cell)
        for cell in row
        if clean_text(cell)
    ]


# ============================================================
# Empty / section detection
# ============================================================

def is_empty_row(row: list[str]) -> bool:
    return len(nonempty_cells(row)) == 0


def looks_like_section_heading(
    row: list[str],
) -> bool:
    """
    Conservative detection of one-cell section headings.

    Examples:
        CDR FILE INFORMATION
        SYSTEM STATUS AT EVENT
        LONGITUDINAL CRASH PULSE (...)
    """

    cells = nonempty_cells(row)

    if len(cells) != 1:
        return False

    text = cells[0]

    if len(text) > 220:
        return False

    if not re.search(r"[A-Za-z]", text):
        return False

    return True


# ============================================================
# Packed sequence detection
# ============================================================

def split_packed_sequence(
    value: str,
) -> list[str]:
    """
    Detect repeated values stored in a single CSV cell.

    Example:
        "Off, Off, Off, Off, Off"

    becomes:
        ["Off", "Off", "Off", "Off", "Off"]

    A threshold of 5 tokens is intentionally conservative so
    ordinary text such as "Side Crash, Left" is not interpreted
    as a repeated measurement.
    """

    text = clean_text(value)

    if not text:
        return []

    if "," not in text:
        return []

    tokens = [
        token.strip()
        for token in text.split(",")
        if token.strip()
    ]

    if len(tokens) < 5:
        return []

    return tokens


# ============================================================
# Table-header detection
# ============================================================

def looks_like_table_header(
    row: list[str],
) -> bool:
    """
    Identify likely repeated-measurement table headers.

    Examples:
        Time (msec) | Delta-V Longitudinal | Delta-V Lateral
        Time (ms) | Acceleration
        Sample | Vehicle Speed | Engine Speed

    Important:
    A scalar field such as

        Time From Time Zero to Deployment (Rollover) (ms) | 45

    must NOT be interpreted as a table header.
    """

    cells = nonempty_cells(row)

    if len(cells) < 2:
        return False

    normalized = [
        normalize_text(cell)
        for cell in cells
    ]

    first = normalized[0]

    # ========================================================
    # Detect whether remaining cells look like scalar values
    # ========================================================

    def looks_like_scalar_value(
        value: str,
    ) -> bool:
        text = normalize_text(value)

        if not text:
            return True

        # Numeric value, optionally signed/decimal
        if re.fullmatch(
            r"[-+]?"
            r"(?:\d+(?:\.\d*)?|\.\d+)"
            r"(?:[eE][-+]?\d+)?"
            r"(?:\s*[a-zA-Z/%^0-9]+)?",
            text,
        ):
            return True

        common_states = {
            "yes",
            "no",
            "on",
            "off",
            "true",
            "false",
            "active",
            "inactive",
            "deployed",
            "not deployed",
            "buckled",
            "unbuckled",
            "complete",
            "incomplete",
            "sna",
            "n/a",
            "na",
            "unknown",
        }

        if text in common_states:
            return True

        return False

    remaining = normalized[1:]

    # --------------------------------------------------------
    # Two-column rows
    #
    # A two-column row is treated as scalar unless the first
    # cell is a clear ordered axis and the second cell looks
    # like a measurement/signal name. This prevents labels
    # such as "Time to Deployment Command" from becoming
    # false table headers while preserving true headers such
    # as "Time (ms) | Acceleration".
    # --------------------------------------------------------

    if len(cells) == 2:
        second = normalized[1]

        axis_patterns = (
            r"^time(?:\s*\([^)]*\))?$",
            r"^times(?:\s*\([^)]*\))?$",
            r"^relative time(?:\s*\([^)]*\))?$",
            r"^sample(?:\s*(?:number|#))?$",
            r"^sample index$",
            r"^index$",
            r"^buffer(?:\s*(?:address|index|order))?$",
            r"^sequence(?:\s*(?:number|#))?$",
        )

        first_is_axis = any(
            re.fullmatch(
                pattern,
                first,
                re.IGNORECASE,
            )
            is not None
            for pattern in axis_patterns
        )

        measurement_terms_two_col = (
            "delta-v",
            "delta v",
            "acceleration",
            "velocity",
            "speed",
            "angular rate",
            "pressure",
            "throttle",
            "brake",
            "steering",
            "rpm",
            "yaw rate",
            "roll rate",
            "lateral acceleration",
            "longitudinal acceleration",
        )

        second_is_signal = any(
            term in second
            for term in measurement_terms_two_col
        )

        return bool(
            first_is_axis
            and second_is_signal
        )

    # ========================================================
    # Strong axis/header first-column signal
    # ========================================================

    strong_first_column_patterns = (
        "time",
        "sample",
        "index",
        "buffer",
        "sequence",
    )

    if first.startswith(
        strong_first_column_patterns
    ):
        return True

    # ========================================================
    # Multi-signal header detection
    # ========================================================

    measurement_terms = (
        "delta-v",
        "delta v",
        "acceleration",
        "velocity",
        "speed",
        "angular rate",
        "pressure",
        "status",
        "position",
        "throttle",
        "brake",
        "steering",
        "rpm",
    )

    hits = 0

    for cell in normalized:
        if any(
            term in cell
            for term in measurement_terms
        ):
            hits += 1

    return hits >= 2
# ============================================================
# Label/value handling
# ============================================================

def extract_label_and_values(
    row: list[str],
) -> tuple[str, list[str]]:
    """
    The first column is treated as the candidate label.

    Remaining non-empty cells are candidate values.
    """

    if not row:
        return "", []

    label = clean_text(row[0])

    values = [
        clean_text(cell)
        for cell in row[1:]
        if clean_text(cell)
    ]

    return label, values


def detect_repeated_values(
    values: list[str],
) -> tuple[
    bool,
    bool,
    list[str],
]:
    """
    Returns:

        is_repeated
        packed_sequence
        normalized_values

    Supported forms:

        Label | v1 | v2 | v3 | ...

    and:

        Label | "v1, v2, v3, ..."
    """

    # --------------------------------------------------------
    # Standard repeated values across multiple CSV columns
    # --------------------------------------------------------

    if len(values) >= 3:
        return (
            True,
            False,
            values,
        )

    # --------------------------------------------------------
    # Packed repeated sequence inside one CSV cell
    # --------------------------------------------------------

    if len(values) == 1:
        packed = split_packed_sequence(
            values[0]
        )

        if packed:
            return (
                True,
                True,
                packed,
            )

    return (
        False,
        False,
        values,
    )


# ============================================================
# Main row parser
# ============================================================

def parse_observation(
    row: list[str],
    row_index: int,
    section_context: str = "",
) -> Observation:
    """
    Convert one raw CDR CSV row into a structural observation.

    IMPORTANT:
    This function does NOT assign Groups 1-6.

    It answers only:

        What kind of row is this?
    """

    cleaned_row = [
        clean_text(cell)
        for cell in row
    ]

    row_number = row_index + 1

    # ========================================================
    # Empty row
    # ========================================================

    if is_empty_row(cleaned_row):
        return Observation(
            row_index=row_index,
            row_number=row_number,
            raw_row=cleaned_row,
            observation_type="empty",
            label="",
            values=[],
            value_count=0,
            packed_sequence=False,
            packed_sequence_count=0,
            section_context=section_context,
            is_empty=True,
            is_section_heading=False,
            is_scalar=False,
            is_repeated=False,
            is_table_header=False,
            parser_status="parsed",
        )

    # ========================================================
    # Section heading
    # ========================================================

    if looks_like_section_heading(
        cleaned_row
    ):
        heading = nonempty_cells(
            cleaned_row
        )[0]

        return Observation(
            row_index=row_index,
            row_number=row_number,
            raw_row=cleaned_row,
            observation_type="section_heading",
            label=heading,
            values=[],
            value_count=0,
            packed_sequence=False,
            packed_sequence_count=0,
            section_context=heading,
            is_empty=False,
            is_section_heading=True,
            is_scalar=False,
            is_repeated=False,
            is_table_header=False,
            parser_status="parsed",
        )

    # ========================================================
    # Table header
    # ========================================================

    if looks_like_table_header(
        cleaned_row
    ):
        cells = nonempty_cells(
            cleaned_row
        )

        return Observation(
            row_index=row_index,
            row_number=row_number,
            raw_row=cleaned_row,
            observation_type="table_header",
            label=(
                cells[0]
                if cells
                else ""
            ),
            values=cells[1:],
            value_count=max(
                len(cells) - 1,
                0,
            ),
            packed_sequence=False,
            packed_sequence_count=0,
            section_context=section_context,
            is_empty=False,
            is_section_heading=False,
            is_scalar=False,
            is_repeated=False,
            is_table_header=True,
            parser_status="parsed",
        )

    # ========================================================
    # Label/value rows
    # ========================================================

    label, values = (
        extract_label_and_values(
            cleaned_row
        )
    )

    if label:
        # ----------------------------------------------------
        # Protected semantic lists
        #
        # These labels may contain multiple pipe-/column-
        # separated values, but they are categorical/report
        # lists rather than time-series measurements. Preserve
        # them as scalar semantic observations so the routing
        # layer can send them to Group 3 or Group 1.
        # ----------------------------------------------------

        normalized_label = normalize_text(
            label
        )

        protected_non_timeseries_list = (
            normalized_label.startswith(
                "occupant size classification"
            )
            or normalized_label in {
                "event(s) recovered",
                "events recovered",
                "events_recovered_text",
            }
        )

        if (
            protected_non_timeseries_list
            and len(values) >= 1
        ):
            return Observation(
                row_index=row_index,
                row_number=row_number,
                raw_row=cleaned_row,
                observation_type="scalar",
                label=label,
                values=values,
                value_count=len(values),
                packed_sequence=False,
                packed_sequence_count=0,
                section_context=section_context,
                is_empty=False,
                is_section_heading=False,
                is_scalar=True,
                is_repeated=False,
                is_table_header=False,
                parser_status="parsed",
            )

        (
            is_repeated,
            packed_sequence,
            parsed_values,
        ) = detect_repeated_values(
            values
        )

        # ----------------------------------------------------
        # Repeated measurement
        # ----------------------------------------------------

        if is_repeated:
            return Observation(
                row_index=row_index,
                row_number=row_number,
                raw_row=cleaned_row,
                observation_type=(
                    "repeated_measurement"
                ),
                label=label,
                values=parsed_values,
                value_count=len(
                    parsed_values
                ),
                packed_sequence=(
                    packed_sequence
                ),
                packed_sequence_count=(
                    len(parsed_values)
                    if packed_sequence
                    else 0
                ),
                section_context=(
                    section_context
                ),
                is_empty=False,
                is_section_heading=False,
                is_scalar=False,
                is_repeated=True,
                is_table_header=False,
                parser_status="parsed",
            )

        # ----------------------------------------------------
        # Scalar
        # ----------------------------------------------------

        if len(values) == 1:
            return Observation(
                row_index=row_index,
                row_number=row_number,
                raw_row=cleaned_row,
                observation_type="scalar",
                label=label,
                values=values,
                value_count=1,
                packed_sequence=False,
                packed_sequence_count=0,
                section_context=(
                    section_context
                ),
                is_empty=False,
                is_section_heading=False,
                is_scalar=True,
                is_repeated=False,
                is_table_header=False,
                parser_status="parsed",
            )

        # ----------------------------------------------------
        # Label only
        # ----------------------------------------------------

        if len(values) == 0:
            return Observation(
                row_index=row_index,
                row_number=row_number,
                raw_row=cleaned_row,
                observation_type="label_only",
                label=label,
                values=[],
                value_count=0,
                packed_sequence=False,
                packed_sequence_count=0,
                section_context=(
                    section_context
                ),
                is_empty=False,
                is_section_heading=False,
                is_scalar=False,
                is_repeated=False,
                is_table_header=False,
                parser_status="parsed",
            )

        # ----------------------------------------------------
        # Two-value row
        # ----------------------------------------------------

        return Observation(
            row_index=row_index,
            row_number=row_number,
            raw_row=cleaned_row,
            observation_type="multi_value",
            label=label,
            values=values,
            value_count=len(values),
            packed_sequence=False,
            packed_sequence_count=0,
            section_context=(
                section_context
            ),
            is_empty=False,
            is_section_heading=False,
            is_scalar=False,
            is_repeated=False,
            is_table_header=False,
            parser_status="parsed",
        )

    # ========================================================
    # Fallback
    # ========================================================

    cells = nonempty_cells(
        cleaned_row
    )

    return Observation(
        row_index=row_index,
        row_number=row_number,
        raw_row=cleaned_row,
        observation_type="unclassified",
        label="",
        values=cells,
        value_count=len(cells),
        packed_sequence=False,
        packed_sequence_count=0,
        section_context=section_context,
        is_empty=False,
        is_section_heading=False,
        is_scalar=False,
        is_repeated=False,
        is_table_header=False,
        parser_status="unclassified",
    )


# ============================================================
# Whole-file parser
# ============================================================

def parse_rows(
    rows: list[list[str]],
) -> list[Observation]:
    """
    Parse an entire CSV while maintaining section context.
    """

    observations: list[Observation] = []

    current_section = ""

    for row_index, row in enumerate(
        rows
    ):
        observation = (
            parse_observation(
                row=row,
                row_index=row_index,
                section_context=(
                    current_section
                ),
            )
        )

        if observation.is_section_heading:
            current_section = (
                observation.label
            )

        else:
            observation.section_context = (
                current_section
            )

        observations.append(
            observation
        )

    return observations


# ============================================================
# Serialization
# ============================================================

def observations_to_json(
    observations: list[Observation],
) -> str:
    return json.dumps(
        [
            obs.to_dict()
            for obs in observations
        ],
        indent=2,
        ensure_ascii=False,
    )