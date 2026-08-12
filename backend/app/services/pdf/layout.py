"""Shared house style for generated documents.

Everything here is pure presentation: no database, no object storage. Keeping
the renderers free of I/O means a test can assert on real PDF bytes without
standing up Postgres or MinIO.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

CARRIER_NAME = "InsureCo Insurance Company"
CARRIER_ADDRESS = "1200 Superior Avenue, Cleveland, OH 44114"
CARRIER_CONTACT = "1-800-555-0100 · service@insureco.com"

# Matches the indigo/slate palette the React app uses, so a downloaded PDF looks
# like it came from the same system the user is looking at.
INDIGO = colors.HexColor("#4f46e5")
SLATE_800 = colors.HexColor("#1e293b")
SLATE_500 = colors.HexColor("#64748b")
SLATE_200 = colors.HexColor("#e2e8f0")
SLATE_50 = colors.HexColor("#f8fafc")

_PAGE_MARGIN = 0.75 * inch
_CONTENT_WIDTH = LETTER[0] - 2 * _PAGE_MARGIN

_base = getSampleStyleSheet()

TITLE = ParagraphStyle(
    "DocTitle",
    parent=_base["Title"],
    fontName="Helvetica-Bold",
    fontSize=18,
    leading=22,
    alignment=0,
    textColor=SLATE_800,
    spaceAfter=2,
)

SUBTITLE = ParagraphStyle(
    "DocSubtitle",
    parent=_base["Normal"],
    fontSize=9.5,
    leading=13,
    textColor=SLATE_500,
)

HEADING = ParagraphStyle(
    "DocHeading",
    parent=_base["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=INDIGO,
    spaceBefore=14,
    spaceAfter=6,
)

BODY = ParagraphStyle(
    "DocBody",
    parent=_base["Normal"],
    fontSize=10,
    leading=14,
    textColor=SLATE_800,
    spaceAfter=8,
)

SMALL = ParagraphStyle(
    "DocSmall",
    parent=_base["Normal"],
    fontSize=8,
    leading=11,
    textColor=SLATE_500,
)

RIGHT = ParagraphStyle("DocRight", parent=SUBTITLE, alignment=TA_RIGHT)


def _page_furniture(canvas, doc) -> None:
    """Draw the rule under the letterhead and the footer on every page."""
    canvas.saveState()
    canvas.setStrokeColor(SLATE_200)
    canvas.setLineWidth(0.75)
    y = LETTER[1] - _PAGE_MARGIN + 6
    canvas.line(_PAGE_MARGIN, y, LETTER[0] - _PAGE_MARGIN, y)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE_500)
    canvas.drawString(
        _PAGE_MARGIN,
        _PAGE_MARGIN - 22,
        f"{CARRIER_NAME} · {CARRIER_CONTACT}",
    )
    canvas.drawRightString(
        LETTER[0] - _PAGE_MARGIN,
        _PAGE_MARGIN - 22,
        f"Page {canvas.getPageNumber()}",
    )
    canvas.restoreState()


def letterhead(document_title: str, reference_label: str, reference: str) -> Table:
    """Carrier identity on the left, document reference on the right."""
    left = [
        Paragraph(f"<b>{CARRIER_NAME}</b>", SUBTITLE),
        Paragraph(CARRIER_ADDRESS, SMALL),
    ]
    right = [
        Paragraph(f"<b>{document_title}</b>", RIGHT),
        Paragraph(f"{reference_label}: {reference}", RIGHT),
        Paragraph(f"Issued {date.today().isoformat()}", RIGHT),
    ]
    table = Table([[left, right]], colWidths=[_CONTENT_WIDTH * 0.55, _CONTENT_WIDTH * 0.45])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def key_value_table(rows: Sequence[tuple[str, str]]) -> Table:
    """Two-column label/value block used for summary sections."""
    data = [
        [Paragraph(label, SMALL), Paragraph(value or "—", BODY)] for label, value in rows
    ]
    table = Table(
        data,
        colWidths=[_CONTENT_WIDTH * 0.32, _CONTENT_WIDTH * 0.68],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, SLATE_200),
            ]
        )
    )
    return table


def column_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    align_right: Sequence[int] = (),
) -> Table:
    """Bordered table with a tinted header row, for schedules and coverages."""
    data = [[Paragraph(f"<b>{h}</b>", SMALL) for h in headers]]
    data.extend([[Paragraph(str(cell), BODY) for cell in row] for row in rows])

    width = _CONTENT_WIDTH / len(headers)
    table = Table(data, colWidths=[width] * len(headers), hAlign="LEFT", repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), SLATE_50),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, SLATE_200),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, SLATE_200),
    ]
    for col in align_right:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def build_pdf(story: list[Flowable], *, title: str, author: str = CARRIER_NAME) -> bytes:
    """Render a flowable story to PDF bytes."""
    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=_PAGE_MARGIN,
        rightMargin=_PAGE_MARGIN,
        topMargin=_PAGE_MARGIN,
        bottomMargin=_PAGE_MARGIN,
        title=title,
        author=author,
    )
    doc.build(story, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    return buffer.getvalue()


def spacer(height: float = 10) -> Spacer:
    return Spacer(1, height)
