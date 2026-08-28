from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, legal
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


INPUT_PATH = Path(
    "data/processed/linked_tables/"
    "vehicle_event_index_data_dictionary.csv"
)

OUTPUT_PATH = Path(
    "data/processed/linked_tables/"
    "vehicle_event_index_data_dictionary.pdf"
)


def cell(value, style):
    return Paragraph("" if pd.isna(value) else str(value), style)


def main() -> None:
    df = pd.read_csv(INPUT_PATH)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=16,
        spaceAfter=10,
    )

    text_style = ParagraphStyle(
        "DictionaryCell",
        parent=styles["BodyText"],
        fontSize=6.5,
        leading=7.5,
    )

    document = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=landscape(legal),
        leftMargin=0.25 * inch,
        rightMargin=0.25 * inch,
        topMargin=0.3 * inch,
        bottomMargin=0.3 * inch,
    )

    story = [
        Paragraph("Vehicle-Event Index Data Dictionary", title_style),
        Paragraph(
            "One row represents one audited CISS vehicle involved in one "
            "crash event. Target and leakage-risk fields are explicitly "
            "identified for safe machine-learning use.",
            styles["BodyText"],
        ),
        Spacer(1, 0.12 * inch),
    ]

    table_data = [
        [
            cell("Column", text_style),
            cell("Meaning", text_style),
            cell("Source", text_style),
            cell("Level / Join", text_style),
            cell("Role", text_style),
            cell("ML use", text_style),
            cell("Coverage", text_style),
        ]
    ]

    for _, row in df.iterrows():
        table_data.append(
            [
                cell(row["column_name"], text_style),
                cell(row["meaning"], text_style),
                cell(row["source_file"], text_style),
                cell(
                    f'{row["entity_level"]}<br/>{row["join_key"]}',
                    text_style,
                ),
                cell(row["role"], text_style),
                cell(row["ML_use"], text_style),
                cell(f'{row["coverage_percent"]}%', text_style),
            ]
        )

    table = Table(
        table_data,
        colWidths=[
            1.55 * inch,
            3.3 * inch,
            1.65 * inch,
            1.35 * inch,
            1.45 * inch,
            1.55 * inch,
            0.6 * inch,
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
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#EAF2F8")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    story.append(table)
    document.build(story)

    print(f"Created: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
    