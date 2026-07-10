"""Generate a structured procurement briefing PDF from summary JSON."""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.documents.models import Document
from apps.intelligence.models import GeneratedSummary

NOT_FOUND = "Not found in document."


def _xml_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _has_text(value: Any) -> bool:
    return bool(_clean_text(value))


class BriefingPdfService:
    @staticmethod
    def suggested_filename_for_variant(
        document: Document, summary: GeneratedSummary, *, variant: str
    ) -> str:
        stem = re.sub(r"[^\w\-]+", "_", document.original_filename.rsplit(".", 1)[0])
        stem = stem.strip("_")[:80] or "document"
        label = "executive_summary" if variant == "executive" else "briefing"
        return f"{stem}_procurement_{label}_v{summary.version}.pdf"

    @staticmethod
    def render(
        summary: GeneratedSummary,
        document: Document,
        *,
        variant: str = "full",
    ) -> bytes:
        data = summary.summary_json or {}
        meta = data.get("_meta") or {}
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=0.85 * inch,
            rightMargin=0.85 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            title=f"Procurement Briefing — {document.original_filename}",
        )

        styles = BriefingPdfService._build_styles(getSampleStyleSheet())
        story: list = []

        story.extend(
            BriefingPdfService._cover_block(
                document, summary, meta, styles
            )
        )

        BriefingPdfService._add_executive_summary(story, data, styles)

        story.append(Spacer(1, 0.25 * inch))
        story.append(
            Paragraph(
                "<font size='8' color='#64748b'>"
                "AI-generated procurement intelligence. Verify figures and dates "
                "against the source tender before bid decisions."
                "</font>",
                styles["body"],
            )
        )

        doc.build(story)
        return buffer.getvalue()

    @staticmethod
    def _build_styles(base) -> dict[str, ParagraphStyle]:
        return {
            "title": ParagraphStyle(
                "BriefTitle",
                parent=base["Heading1"],
                fontSize=20,
                leading=24,
                spaceAfter=6,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#0f172a"),
            ),
            "subtitle": ParagraphStyle(
                "BriefSubtitle",
                parent=base["Normal"],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor("#475569"),
                spaceAfter=4,
                alignment=TA_LEFT,
            ),
            "section": ParagraphStyle(
                "SectionHeading",
                parent=base["Heading2"],
                fontSize=13,
                leading=16,
                spaceBefore=16,
                spaceAfter=10,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#1e40af"),
            ),
            "body": ParagraphStyle(
                "Body",
                parent=base["Normal"],
                fontSize=10,
                leading=15,
                alignment=TA_JUSTIFY,
                textColor=colors.HexColor("#0f172a"),
            ),
            "body_left": ParagraphStyle(
                "BodyLeft",
                parent=base["Normal"],
                fontSize=10,
                leading=14,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#0f172a"),
            ),
            "empty": ParagraphStyle(
                "Empty",
                parent=base["Normal"],
                fontSize=10,
                leading=14,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#64748b"),
                fontName="Helvetica-Oblique",
            ),
            "check_group": ParagraphStyle(
                "CheckGroup",
                parent=base["Normal"],
                fontSize=10,
                leading=13,
                spaceBefore=8,
                spaceAfter=4,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#1e293b"),
                fontName="Helvetica-Bold",
            ),
        }

    @staticmethod
    def _cover_block(
        document: Document,
        summary: GeneratedSummary,
        meta: dict,
        styles: dict[str, ParagraphStyle],
    ) -> list:
        generated_at = meta.get("generated_at") or summary.completed_at
        if generated_at and hasattr(generated_at, "strftime"):
            gen_label = generated_at.strftime("%d %b %Y %H:%M UTC")
        elif generated_at:
            try:
                gen_label = datetime.fromisoformat(
                    str(generated_at).replace("Z", "+00:00")
                ).strftime("%d %b %Y %H:%M")
            except ValueError:
                gen_label = str(generated_at)[:19]
        else:
            gen_label = "—"

        block = [
            Paragraph("Procurement Intelligence Briefing", styles["title"]),
            Paragraph(_xml_escape(document.original_filename), styles["subtitle"]),
            Paragraph(
                f"Report version {summary.version} · Generated {gen_label}",
                styles["subtitle"],
            ),
        ]
        if meta.get("prompt_version"):
            block.append(
                Paragraph(
                    f"Analysis prompt v{_xml_escape(str(meta['prompt_version']))}",
                    styles["subtitle"],
                )
            )
        block.append(Spacer(1, 0.22 * inch))
        return block

    @staticmethod
    def _section_heading(story: list, title: str, styles: dict) -> None:
        story.append(Paragraph(title, styles["section"]))

    @staticmethod
    def _add_paragraphs_justified(
        story: list, text: str, styles: dict[str, ParagraphStyle]
    ) -> None:
        for para in re.split(r"\n\s*\n", text):
            chunk = _clean_text(para)
            if chunk:
                story.append(Paragraph(_xml_escape(chunk), styles["body"]))
                story.append(Spacer(1, 0.07 * inch))

    @staticmethod
    def _add_executive_summary(story: list, data: dict, styles: dict) -> None:
        BriefingPdfService._section_heading(story, "Executive Summary", styles)
        text = _clean_text((data.get("executive_summary") or {}).get("text"))
        if text:
            BriefingPdfService._add_paragraphs_justified(story, text, styles)
        else:
            story.append(Paragraph(NOT_FOUND, styles["empty"]))


    @staticmethod
    def _standard_table_style() -> TableStyle:
        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eff6ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
