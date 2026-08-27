"""
Convert the case-index data dictionary CSV into a readable PDF.
"""

from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


DATA_ROOT = Path("data")

INPUT_CSV = (
    DATA_ROOT
    / "processed"
    / "linked_tables"
    / "case_index_data_dictionary.csv"
)

OUTPUT_PDF = (
    DATA_ROOT
    / "processed"
    / "linked_tables"
    / "case_index_data_dictionary.pdf"
)


def paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    """Safely place a cell value into a wrapped PDF paragraph."""
    text = "" if pd.isna(value) else str(value)
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return Paragraph(text, style)


def main() -> None:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(
            f"CSV dictionary was not found: {INPUT_CSV}"
        )

    frame = pd.read_csv(INPUT_CSV)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DictionaryTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=16,
        leading=20,
        spaceAfter=12,
    )

    body_style = ParagraphStyle(
        "DictionaryBody",
        parent=styles["BodyText"],
        fontSize=7,
        leading=9,
    )

    header_style = ParagraphStyle(
        "DictionaryHeader",
        parent=body_style,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )

    document = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=landscape(letter),
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch,
    )

    table_data = [
        [
            paragraph(column, header_style)
            for column in frame.columns
        ]
    ]

    for _, row in frame.iterrows():
        table_data.append(
            [
                paragraph(row[column], body_style)
                for column in frame.columns
            ]
        )

    column_widths = [
        1.35 * inch,  # column_name
        2.65 * inch,  # meaning
        2.00 * inch,  # source
        0.75 * inch,  # entity_level
        0.85 * inch,  # data_type
        1.35 * inch,  # role
        0.75 * inch,  # observed_non_null_count
        0.75 * inch,  # observed_missing_count
    ]

    table = LongTable(
        table_data,
        colWidths=column_widths,
        repeatRows=1,
    )

    table.setStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B7C9D6")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#EAF2F8"),
            ]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )

    story = [
        Paragraph("Case Index Data Dictionary", title_style),
        Paragraph(
            (
                "One row describes one feature in the canonical "
                "CISS case-level table."
            ),
            body_style,
        ),
        Spacer(1, 0.15 * inch),
        table,
    ]

    document.build(story)

    print("PDF data dictionary completed.")
    print(f"Output: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()