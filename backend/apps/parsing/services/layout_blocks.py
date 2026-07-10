"""
Build layout blocks from page text or parser output for DocumentExtractedContent.
"""

from __future__ import annotations

from apps.parsing.parsers.base import ParsedLayoutBlock, ParsedPageResult, ParsedTableResult
from apps.parsing.services.section_detection import (
    _extract_heading_title,
    _is_heading_line,
)


def polygon_to_bbox(polygon: list[float] | None) -> list[float]:
    """Convert DI polygon [x1,y1,x2,y2,...] to axis-aligned [x0,y0,x1,y1]."""
    if not polygon or len(polygon) < 4:
        return []
    xs = polygon[0::2]
    ys = polygon[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def layout_blocks_from_pages(
    pages: list[ParsedPageResult],
    *,
    section_order_map: dict[tuple[int, str], int] | None = None,
) -> list[ParsedLayoutBlock]:
    """
    Heuristic layout blocks from page text (PyMuPDF / OCR path).

    Splits each page into paragraph and heading blocks using line-level heading detection.
    """
    blocks: list[ParsedLayoutBlock] = []
    section_order_map = section_order_map or {}

    for page in pages:
        if not page.extracted_text.strip():
            continue

        paragraph_lines: list[str] = []
        block_start_y = 0.0

        def flush_paragraph() -> None:
            nonlocal paragraph_lines, block_start_y
            text = "\n".join(paragraph_lines).strip()
            if text:
                blocks.append(
                    ParsedLayoutBlock(
                        block_type="paragraph",
                        page_number=page.page_number,
                        text=text,
                        role="body",
                        bbox=[0, block_start_y, 0, block_start_y],
                    )
                )
            paragraph_lines = []

        for line in page.extracted_text.splitlines():
            if _is_heading_line(line):
                flush_paragraph()
                title = _extract_heading_title(line)
                section_order = section_order_map.get((page.page_number, title))
                blocks.append(
                    ParsedLayoutBlock(
                        block_type="heading",
                        page_number=page.page_number,
                        text=title,
                        role="sectionHeading",
                        bbox=[0, 0, 0, 0],
                        section_order=section_order,
                    )
                )
            else:
                if not paragraph_lines:
                    block_start_y = float(len(blocks))
                paragraph_lines.append(line)

        flush_paragraph()

    return blocks


def layout_blocks_from_tables(tables: list[ParsedTableResult]) -> list[ParsedLayoutBlock]:
    """Emit table-native layout blocks from extracted tables."""
    blocks: list[ParsedLayoutBlock] = []
    for table in tables:
        lines: list[str] = []
        if table.headers:
            lines.append(" | ".join(table.headers))
        for row in table.rows:
            lines.append(" | ".join(row))
        text = "\n".join(lines).strip()
        if not text:
            continue
        blocks.append(
            ParsedLayoutBlock(
                block_type="table",
                page_number=table.page_number,
                text=text,
                role="table",
            )
        )
    return blocks


def layout_blocks_to_json(blocks: list[ParsedLayoutBlock]) -> list[dict]:
    return [
        {
            "type": block.block_type,
            "page": block.page_number,
            "text": block.text[:4000],
            "role": block.role,
            "bbox": block.bbox,
            "section_order": block.section_order,
        }
        for block in blocks
    ]
