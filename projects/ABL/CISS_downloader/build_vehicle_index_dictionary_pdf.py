from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


INPUT_PATH = Path(
    "data/processed/linked_tables/vehicle_index_data_dictionary.csv"
)

OUTPUT_PATH = Path(
    "data/processed/linked_tables/vehicle_index_data_dictionary.pdf"
)


def paragraph(value, style):
    if pd.isna(value):
        value = ""
    return Paragraph(str(value), style)


def main() -> None:
    df = pd.read_csv(INPUT_PATH)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DictionaryTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=16,
        spaceAfter=12,
    )

    text_style = ParagraphStyle(
        "DictionaryText",
        parent=styles["BodyText"],
        fontSize=7,
        leading=8,
    )

    document = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=letter,
        rightMargin=0.3 * inch,
        leftMargin=0.3 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )

    story = [
        Paragraph("Vehicle Index Data Dictionary", title_style),
        Paragraph(
            "One row in vehicle_index represents one audited vehicle within "
            "one CISS crash case. Raw source values are preserved.",
            styles["BodyText"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    table_data = [
        [
            paragraph("Column", text_style),
            paragraph("Meaning", text_style),
            paragraph("Source", text_style),
            paragraph("Role", text_style),
            paragraph("Type", text_style),
            paragraph("Coverage", text_style),
        ]
    ]

    for _, row in df.iterrows():
        table_data.append(
            [
                paragraph(row["column_name"], text_style),
                paragraph(row["meaning"], text_style),
                paragraph(row["source"], text_style),
                paragraph(row["role"], text_style),
                paragraph(row["data_type"], text_style),
                paragraph(
                    f'{row["coverage_percent"]}%',
                    text_style,
                ),
            ]
        )

    table = Table(
        table_data,
        colWidths=[
            1.55 * inch,
            2.15 * inch,
            1.45 * inch,
            0.9 * inch,
            0.6 * inch,
            0.55 * inch,
        ],
        repeatRows=1,
    )

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#EAF2F8")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story.append(table)
    document.build(story)

    print(f"Created: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()