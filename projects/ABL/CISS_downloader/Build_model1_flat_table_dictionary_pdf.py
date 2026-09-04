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
    "data/processed/modeling/"
    "model1_delta_v_pdof_candidate_flat_data_dictionary.csv"
)

OUTPUT_PATH = Path(
    "data/processed/modeling/"
    "model1_delta_v_pdof_candidate_flat_data_dictionary.pdf"
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
        Paragraph(
            "Model 1 Delta-V and PDOF Candidate Feature Dictionary",
            title_style,
        ),
        Paragraph(
            "This is a feature-specification workspace, not the final "
            "training matrix. Fields marked as targets, leakage, or "
            "provenance must not be used as Model 1 inputs.",
            styles["BodyText"],
        ),
        Spacer(1, 0.12 * inch),
    ]

    table_data = [
        [
            cell("Column", text_style),
            cell("Feature group", text_style),
            cell("Source table", text_style),
            cell("Model 1 status", text_style),
            cell("Data type", text_style),
            cell("Coverage", text_style),
            cell("Review notes", text_style),
        ]
    ]

    for _, row in df.iterrows():
        table_data.append(
            [
                cell(row["column_name"], text_style),
                cell(row["feature_group"], text_style),
                cell(row["source_table"], text_style),
                cell(row["model1_feature_status"], text_style),
                cell(row["data_type"], text_style),
                cell(f'{row["coverage_percent"]}%', text_style),
                cell(row["review_notes"], text_style),
            ]
        )

    table = Table(
        table_data,
        colWidths=[
            1.8 * inch,
            1.8 * inch,
            1.45 * inch,
            1.8 * inch,
            0.75 * inch,
            0.6 * inch,
            2.0 * inch,
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