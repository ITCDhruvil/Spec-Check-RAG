"""
Azure Document Intelligence layout parser (prebuilt-layout).

Requires AZURE_DI_ENDPOINT and AZURE_DI_KEY. Falls back to PyMuPDF when
credentials are missing or the API call fails.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

from apps.parsing.choices import ExtractionMethod
from apps.parsing.parsers.base import (
    DocumentParseResult,
    ParsedLayoutBlock,
    ParsedPageResult,
    ParsedSectionResult,
    ParsedTableResult,
)
from apps.parsing.services.layout_blocks import polygon_to_bbox
from apps.parsing.services.parse_finalize import finalize_document_parse
from apps.parsing.services.quality import aggregate_quality, score_page_text
from apps.parsing.services.section_detection import (
    _extract_heading_title,
    _is_heading_line,
    build_structured_text,
    detect_sections_from_pages,
)

logger = logging.getLogger(__name__)

HEADING_ROLES = frozenset({"title", "sectionHeading"})


def is_azure_di_configured() -> bool:
    endpoint = getattr(settings, "AZURE_DI_ENDPOINT", "") or ""
    api_key = getattr(settings, "AZURE_DI_KEY", "") or getattr(settings, "AZURE_DI_API_KEY", "") or ""
    return bool(endpoint.strip() and api_key.strip())


def parse_pdf_azure_di(file_path: Path) -> DocumentParseResult:
    """Parse PDF with Azure Document Intelligence prebuilt-layout model."""
    if not is_azure_di_configured():
        raise RuntimeError("Azure Document Intelligence is not configured.")

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = settings.AZURE_DI_ENDPOINT.strip()
    api_key = (getattr(settings, "AZURE_DI_KEY", "") or settings.AZURE_DI_API_KEY).strip()
    model_id = getattr(settings, "AZURE_DI_MODEL", "") or settings.PARSING_AZURE_DI_MODEL

    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    )

    with open(file_path, "rb") as handle:
        poller = client.begin_analyze_document(
            model_id=model_id,
            body=handle,
            content_type="application/pdf",
        )
    analyze_result = poller.result()

    return _convert_di_result(analyze_result, file_path)


def _convert_di_result(analyze_result, _file_path: Path) -> DocumentParseResult:
    """Map Azure DI AnalyzeResult → DocumentParseResult."""
    page_texts: dict[int, list[str]] = {}
    page_roles: dict[int, list[tuple[str, str, list[float]]]] = {}
    layout_blocks: list[ParsedLayoutBlock] = []
    tables: list[ParsedTableResult] = []

    total_pages = len(analyze_result.pages or [])
    if total_pages == 0 and analyze_result.paragraphs:
        for paragraph in analyze_result.paragraphs:
            for region in paragraph.bounding_regions or []:
                total_pages = max(total_pages, region.page_number or 0)
    if total_pages == 0:
        total_pages = 1

    for page_num in range(1, total_pages + 1):
        page_texts[page_num] = []
        page_roles[page_num] = []

    if analyze_result.paragraphs:
        for paragraph in analyze_result.paragraphs:
            content = (paragraph.content or "").strip()
            if not content:
                continue
            role = (paragraph.role or "").strip()
            page_num = 1
            bbox: list[float] = []
            if paragraph.bounding_regions:
                region = paragraph.bounding_regions[0]
                page_num = region.page_number or 1
                bbox = polygon_to_bbox(list(region.polygon or []))

            page_texts.setdefault(page_num, []).append(content)
            page_roles.setdefault(page_num, []).append((role, content, bbox))

            block_type = "heading" if role in HEADING_ROLES else "paragraph"
            layout_blocks.append(
                ParsedLayoutBlock(
                    block_type=block_type,
                    page_number=page_num,
                    text=content,
                    role=role or "body",
                    bbox=bbox,
                )
            )

    if analyze_result.tables:
        for table in analyze_result.tables:
            page_num = 1
            if table.bounding_regions:
                page_num = table.bounding_regions[0].page_number or 1

            cells = table.cells or []
            row_count = table.row_count or 0
            col_count = table.column_count or 0
            grid: list[list[str]] = [
                [""] * col_count for _ in range(max(row_count, 1))
            ]
            for cell in cells:
                r = cell.row_index or 0
                c = cell.column_index or 0
                if r < len(grid) and c < len(grid[r]):
                    grid[r][c] = (cell.content or "").strip()

            headers = grid[0] if grid else []
            rows = grid[1:] if len(grid) > 1 else []
            tables.append(
                ParsedTableResult(
                    page_number=page_num,
                    headers=headers,
                    rows=rows,
                    raw=grid,
                )
            )

            table_lines = []
            if headers:
                table_lines.append(" | ".join(headers))
            for row in rows:
                table_lines.append(" | ".join(row))
            table_text = "\n".join(table_lines).strip()
            if table_text:
                layout_blocks.append(
                    ParsedLayoutBlock(
                        block_type="table",
                        page_number=page_num,
                        text=table_text,
                        role="table",
                    )
                )

    pages: list[ParsedPageResult] = []
    for page_num in range(1, total_pages + 1):
        text = "\n".join(page_texts.get(page_num, [])).strip()
        quality = score_page_text(text)
        pages.append(
            ParsedPageResult(
                page_number=page_num,
                extracted_text=text,
                extraction_method=ExtractionMethod.NATIVE_PDF,
                ocr_used=False,
                quality_score=quality,
                is_empty=not text,
            )
        )

    sections = _sections_from_di_roles(page_roles, pages)
    if len(sections) <= 1:
        sections = detect_sections_from_pages(pages)

    raw_text = "\n\n".join(
        f"--- Page {p.page_number} ---\n{p.extracted_text}"
        for p in pages
        if p.extracted_text
    )
    structured_text = build_structured_text(sections)
    page_scores = [p.quality_score for p in pages if not p.is_empty] or [0.0]
    quality_score = aggregate_quality(page_scores)

    metadata = {
        "file_type": "pdf",
        "parser": "azure_document_intelligence",
        "azure_model": getattr(settings, "AZURE_DI_MODEL", "") or settings.PARSING_AZURE_DI_MODEL,
        "table_parser": "azure_di",
        "total_pages": len(pages),
        "empty_pages": sum(1 for p in pages if p.is_empty),
        "ocr_pages": 0,
        "tables": [
            {"page": t.page_number, "headers": t.headers, "rows": t.rows}
            for t in tables
        ],
        "page_quality": [
            {
                "page": p.page_number,
                "quality_score": p.quality_score,
                "extraction_method": p.extraction_method,
                "ocr_used": p.ocr_used,
            }
            for p in pages
        ],
    }

    result = DocumentParseResult(
        pages=pages,
        sections=sections,
        tables=tables,
        raw_text=raw_text,
        structured_text=structured_text,
        parsing_metadata=metadata,
        parsing_quality_score=quality_score,
        file_type="pdf",
        layout_blocks=layout_blocks,
    )
    return finalize_document_parse(result)


def _sections_from_di_roles(
    page_roles: dict[int, list[tuple[str, str, list[float]]]],
    pages: list[ParsedPageResult],
) -> list[ParsedSectionResult]:
    """Build sections from DI title/sectionHeading roles in reading order."""
    sections: list[ParsedSectionResult] = []
    current_title = "Preamble"
    current_lines: list[str] = []
    current_page_start = 1
    current_page_end = 1
    order = 0

    def flush() -> None:
        nonlocal order, current_title, current_lines, current_page_start, current_page_end
        content = "\n".join(current_lines).strip()
        if content or current_title != "Preamble" or order == 0:
            sections.append(
                ParsedSectionResult(
                    title=current_title,
                    content=content,
                    page_start=current_page_start,
                    page_end=current_page_end,
                    section_order=order,
                )
            )
            order += 1
        current_lines = []

    for page in pages:
        current_page_end = page.page_number
        for role, content, _bbox in page_roles.get(page.page_number, []):
            is_heading = role in HEADING_ROLES or (
                not role and _is_heading_line(content)
            )
            if is_heading:
                flush()
                current_title = _extract_heading_title(content)
                current_page_start = page.page_number
            else:
                if not current_lines and not sections:
                    current_page_start = page.page_number
                current_lines.append(content)

    flush()

    if not sections and pages:
        full_text = "\n\n".join(p.extracted_text for p in pages if p.extracted_text)
        sections.append(
            ParsedSectionResult(
                title="Document",
                content=full_text.strip(),
                page_start=1,
                page_end=pages[-1].page_number,
                section_order=0,
            )
        )

    return sections
