from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import landscape, legal
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)


def paragraph(value, style):
    """Safely place long text inside PDF table cells."""
    if pd.isna(value):
        value = ""
    return Paragraph(str(value), style)


def add_page_number(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        legal[1] - 0.35 * inch,
        0.25 * inch,
        f"Page {document.page}",
    )
    canvas.restoreState()


def main() -> None:
    modeling_directory = Path("data/processed/modeling")

    input_csv = (
        modeling_directory
        / "model1_feature_registry.csv"
    )

    output_pdf = (
        modeling_directory
        / "model1_feature_registry.pdf"
    )

    if not input_csv.exists():
        raise FileNotFoundError(
            f"Feature registry CSV was not found: {input_csv}\n"
            "Run build_model1_feature_registry.py first."
        )

    registry = pd.read_csv(input_csv)

    registry = registry.sort_values(
        [
            "feature_group",
            "model1_decision",
            "column_name",
        ]
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "RegistryTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "RegistrySubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#444444"),
        spaceAfter=14,
    )

    header_style = ParagraphStyle(
        "Header",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        alignment=TA_CENTER,
        textColor=colors.white,
    )

    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.2,
        alignment=TA_LEFT,
    )

    document = SimpleDocTemplate(
        str(output_pdf),
        pagesize=landscape(legal),
        rightMargin=0.28 * inch,
        leftMargin=0.28 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.42 * inch,
        title="Model 1 Feature Registry",
        author="ABL CISS Pipeline",
    )

    story = [
        Paragraph(
            "Model 1 Delta-V and PDOF Feature Registry",
            title_style,
        ),
        Paragraph(
            "Decision record for the candidate flat table. "
            "This document does not delete data; it records how each "
            "column should be handled for the initial prediction models.",
            subtitle_style,
        ),
    ]

    table_data = [
        [
            paragraph("Column", header_style),
            paragraph("Evidence group", header_style),
            paragraph("Model 1 decision", header_style),
            paragraph("Reason code", header_style),
            paragraph("Coverage", header_style),
            paragraph("Decision explanation", header_style),
        ]
    ]

    for _, row in registry.iterrows():
        coverage = (
            f"{row['coverage_percent']:.2f}%"
            if pd.notna(row["coverage_percent"])
            else "N/A"
        )

        table_data.append(
            [
                paragraph(row["column_name"], cell_style),
                paragraph(row["feature_group"], cell_style),
                paragraph(row["model1_decision"], cell_style),
                paragraph(row["reason_code"], cell_style),
                paragraph(coverage, cell_style),
                paragraph(row["decision_explanation"], cell_style),
            ]
        )

    table = LongTable(
        table_data,
        repeatRows=1,
        colWidths=[
            2.05 * inch,
            1.55 * inch,
            1.55 * inch,
            1.65 * inch,
            0.55 * inch,
            3.1 * inch,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#1F4E78"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.25,
                    colors.HexColor("#B7C9D6"),
                ),
                (
                    "BACKGROUND",
                    (0, 1),
                    (-1, -1),
                    colors.HexColor("#F7FAFC"),
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.HexColor("#F7FAFC"),
                        colors.HexColor("#EAF1F5"),
                    ],
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
            ]
        )
    )

    story.append(Spacer(1, 0.05 * inch))
    story.append(table)

    document.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )

    print(f"Created PDF: {output_pdf}")


if __name__ == "__main__":
    main()