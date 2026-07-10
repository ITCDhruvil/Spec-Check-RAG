import logging
from pathlib import Path

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from apps.parsing.choices import ExtractionMethod
from apps.parsing.parsers.base import (
    DocumentParseResult,
    ParsedLayoutBlock,
    ParsedPageResult,
    ParsedSectionResult,
    ParsedTableResult,
)
from apps.parsing.services.parse_finalize import finalize_document_parse
from apps.parsing.services.quality import score_page_text
from apps.parsing.services.section_detection import (
    _extract_heading_title,
    _is_heading_line,
    build_structured_text,
)

logger = logging.getLogger(__name__)


def _iter_block_items(doc: DocxDocument):
    """Yield paragraphs and tables in document reading order."""
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def _heading_level(paragraph) -> int | None:
    style_name = (paragraph.style.name or "").lower() if paragraph.style else ""
    if style_name.startswith("heading"):
        try:
            return int(style_name.replace("heading", "").strip() or "1")
        except ValueError:
            return 1
    return None


def parse_docx(file_path: Path) -> DocumentParseResult:
    doc = DocxDocument(str(file_path))
    paragraphs_text: list[str] = []
    blocks: list[tuple[str, str, int | None]] = []  # kind, text, heading_level
    layout_blocks: list[ParsedLayoutBlock] = []
    tables: list[ParsedTableResult] = []
    table_index = 0

    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = (block.text or "").strip()
            if not text:
                continue
            level = _heading_level(block)
            if level is not None:
                blocks.append(("heading", text, level))
                layout_blocks.append(
                    ParsedLayoutBlock(
                        block_type="heading",
                        page_number=1,
                        text=text,
                        role="sectionHeading",
                    )
                )
            elif _is_heading_line(text):
                title = _extract_heading_title(text)
                blocks.append(("heading", title, None))
                layout_blocks.append(
                    ParsedLayoutBlock(
                        block_type="heading",
                        page_number=1,
                        text=title,
                        role="sectionHeading",
                    )
                )
            else:
                blocks.append(("para", text, None))
                layout_blocks.append(
                    ParsedLayoutBlock(
                        block_type="paragraph",
                        page_number=1,
                        text=text,
                        role="body",
                    )
                )
            paragraphs_text.append(text)
        elif isinstance(block, Table):
            table_index += 1
            rows_raw: list[list[str]] = []
            for row in block.rows:
                rows_raw.append([cell.text.strip() for cell in row.cells])
            if not rows_raw:
                continue
            headers = rows_raw[0]
            data_rows = rows_raw[1:] if len(rows_raw) > 1 else []
            tables.append(
                ParsedTableResult(
                    page_number=1,
                    headers=headers,
                    rows=data_rows,
                    raw=rows_raw,
                )
            )
            table_text = _table_to_text(headers, data_rows)
            blocks.append(("table", table_text, None))
            paragraphs_text.append(table_text)
            layout_blocks.append(
                ParsedLayoutBlock(
                    block_type="table",
                    page_number=1,
                    text=table_text,
                    role="table",
                )
            )

    full_text = "\n".join(paragraphs_text)
    quality = score_page_text(full_text)

    pages = [
        ParsedPageResult(
            page_number=1,
            extracted_text=full_text,
            extraction_method=ExtractionMethod.DOCX_NATIVE,
            ocr_used=False,
            quality_score=quality,
            is_empty=not full_text.strip(),
        )
    ]

    sections, heading_levels = _sections_from_blocks(blocks)
    structured_text = build_structured_text(sections)

    metadata = {
        "file_type": "docx",
        "parser": "python-docx",
        "total_pages": 1,
        "empty_pages": 1 if not full_text.strip() else 0,
        "ocr_pages": 0,
        "tables": [
            {"page": t.page_number, "headers": t.headers, "rows": t.rows} for t in tables
        ],
        "page_quality": [
            {
                "page": 1,
                "quality_score": quality,
                "extraction_method": ExtractionMethod.DOCX_NATIVE,
                "ocr_used": False,
            }
        ],
    }

    result = DocumentParseResult(
        pages=pages,
        sections=sections,
        tables=tables,
        raw_text=full_text,
        structured_text=structured_text,
        parsing_metadata=metadata,
        parsing_quality_score=quality,
        file_type="docx",
        layout_blocks=layout_blocks,
    )
    return finalize_document_parse(result, heading_levels=heading_levels)


def _sections_from_blocks(
    blocks: list[tuple[str, str, int | None]],
) -> tuple[list[ParsedSectionResult], dict[int, int]]:
    sections: list[ParsedSectionResult] = []
    heading_levels: dict[int, int] = {}
    current_title = "Preamble"
    current_lines: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal order, current_title, current_lines
        content = "\n".join(current_lines).strip()
        if content or order == 0:
            sections.append(
                ParsedSectionResult(
                    title=current_title,
                    content=content,
                    page_start=1,
                    page_end=1,
                    section_order=order,
                )
            )
            order += 1
        current_lines = []

    for kind, text, level in blocks:
        if kind == "heading":
            flush()
            current_title = text
            if level is not None:
                heading_levels[order] = level
        else:
            current_lines.append(text)

    flush()

    if not sections:
        return (
            [
                ParsedSectionResult(
                    title="Document",
                    content="",
                    page_start=1,
                    page_end=1,
                    section_order=0,
                )
            ],
            {},
        )
    return sections, heading_levels


def _table_to_text(headers: list[str], rows: list[list[str]]) -> str:
    lines = [" | ".join(headers)]
    for row in rows:
        lines.append(" | ".join(row))
    return "\n".join(lines)
