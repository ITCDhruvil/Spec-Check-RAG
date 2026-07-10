"""
Docling-based parser for PDF and DOCX documents.

Produces the same DocumentParseResult contract as the existing PyMuPDF / Azure DI
parsers so the rest of the pipeline (chunking, indexing, extraction) is unaffected.

Strategy: Docling handles text extraction, table detection, and structure detection.
We map its output to our internal dataclasses and pass through finalize_document_parse
for section hierarchy + layout blocks, same as other parsers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from apps.parsing.choices import ExtractionMethod
from apps.parsing.parsers.base import (
    DocumentParseResult,
    ParsedPageResult,
    ParsedSectionResult,
    ParsedTableResult,
)
from apps.parsing.services.parse_finalize import finalize_document_parse
from apps.parsing.services.quality import aggregate_quality, score_page_text

logger = logging.getLogger(__name__)

def _is_available() -> bool:
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def _sections_from_docling_doc(doc: object) -> list[ParsedSectionResult]:
    """
    Build sections by walking doc.iterate_items() and detecting headings via
    element.label == DocItemLabel.SECTION_HEADER (or 'title').

    This is more reliable than parsing the Markdown export because iterate_items
    provides label metadata; the Markdown ## prefix is only in export_to_markdown().
    """
    try:
        from docling_core.types.doc.labels import DocItemLabel
        _HEADING_LABELS = {DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE}
    except ImportError:
        _HEADING_LABELS = {"section_header", "title"}

    sections: list[ParsedSectionResult] = []
    order = 0
    current_title = "Preamble"
    current_level = 1
    current_parts: list[str] = []
    current_page_start = 1
    current_page_end = 1

    def _page_of(element: object) -> int:
        prov = getattr(element, "prov", None) or []
        return prov[0].page_no if prov else 1

    def flush(page_end: int) -> None:
        nonlocal order, current_title, current_parts, current_page_start, current_page_end
        body = "\n".join(current_parts).strip()
        if body or current_title != "Preamble":
            sections.append(
                ParsedSectionResult(
                    title=current_title,
                    content=body,
                    page_start=current_page_start,
                    page_end=page_end,
                    section_order=order,
                    level=current_level,
                )
            )
            order += 1
        current_parts = []

    for element, _level in doc.iterate_items():
        label = getattr(element, "label", None)
        text = (getattr(element, "text", None) or "").strip()
        pg = _page_of(element)
        current_page_end = pg

        if label in _HEADING_LABELS and text:
            flush(pg)
            current_title = text
            current_level = max(1, int(_level) + 1) if _level else 1
            current_page_start = pg
        else:
            if text:
                current_parts.append(text)

    flush(current_page_end)
    return sections


def parse_with_docling(file_path: Path) -> DocumentParseResult:
    """
    Parse PDF or DOCX using Docling and return DocumentParseResult.

    Raises ImportError if docling is not installed.
    Raises RuntimeError if Docling conversion fails.
    """
    from docling.document_converter import DocumentConverter

    logger.info("docling_parse_start path=%s", file_path)

    converter = DocumentConverter()
    conv_result = converter.convert(str(file_path))
    doc = conv_result.document

    # --- Build per-page text from Docling's page-aware export ---
    # doc.pages is dict[int, PageItem] — keys are 1-based page numbers.
    full_markdown = doc.export_to_markdown()

    page_count = max(doc.pages.keys(), default=1) if doc.pages else 1

    # Collect text per page from iterate_items(); prov is list[ProvenanceItem]
    page_texts: dict[int, list[str]] = {p: [] for p in range(1, page_count + 1)}

    for element, _level in doc.iterate_items():
        prov = getattr(element, "prov", None) or []
        pg = prov[0].page_no if prov else 1
        pg = max(1, min(pg, page_count))
        text = getattr(element, "text", None) or ""
        if text.strip():
            page_texts[pg].append(text)

    # --- ParsedPageResult list ---
    parsed_pages: list[ParsedPageResult] = []
    for pg in range(1, page_count + 1):
        page_md = "\n".join(page_texts.get(pg, []))
        quality = score_page_text(page_md)
        parsed_pages.append(
            ParsedPageResult(
                page_number=pg,
                extracted_text=page_md,
                extraction_method=ExtractionMethod.NATIVE_PDF,
                ocr_used=False,
                quality_score=quality,
                is_empty=not page_md.strip(),
            )
        )

    # --- Tables ---
    all_tables: list[ParsedTableResult] = []
    for table_item in (doc.tables or []):
        prov = getattr(table_item, "prov", None) or []
        pg = prov[0].page_no if prov else 1
        try:
            df = table_item.export_to_dataframe(doc=doc)
            if df is not None and not df.empty:
                headers = [str(c) for c in df.columns.tolist()]
                rows = [[str(v) for v in row] for row in df.values.tolist()]
                all_tables.append(
                    ParsedTableResult(page_number=pg, headers=headers, rows=rows)
                )
        except Exception as exc:
            logger.debug("docling_table_export_skip page=%s error=%s", pg, exc)

    # --- Sections from element labels (heading detection via DocItemLabel) ---
    sections = _sections_from_docling_doc(doc)

    # --- Aggregates ---
    raw_text = "\n\n".join(
        f"--- Page {p.page_number} ---\n{p.extracted_text}"
        for p in parsed_pages
        if p.extracted_text
    )
    structured_text = full_markdown
    page_scores = [p.quality_score for p in parsed_pages if not p.is_empty] or [0.0]
    quality_score = aggregate_quality(page_scores)

    metadata = {
        "file_type": file_path.suffix.lstrip(".").lower(),
        "parser": "docling",
        "total_pages": page_count,
        "empty_pages": sum(1 for p in parsed_pages if p.is_empty),
        "ocr_pages": 0,
        "tables": [
            {"page": t.page_number, "headers": t.headers, "rows": t.rows}
            for t in all_tables
        ],
        "page_quality": [
            {
                "page": p.page_number,
                "quality_score": p.quality_score,
                "extraction_method": p.extraction_method,
                "ocr_used": p.ocr_used,
            }
            for p in parsed_pages
        ],
    }

    result = DocumentParseResult(
        pages=parsed_pages,
        sections=sections,
        tables=all_tables,
        raw_text=raw_text,
        structured_text=structured_text,
        parsing_metadata=metadata,
        parsing_quality_score=quality_score,
        file_type=file_path.suffix.lstrip(".").lower(),
    )

    logger.info(
        "docling_parse_complete path=%s pages=%s sections=%s tables=%s quality=%.2f",
        file_path,
        page_count,
        len(sections),
        len(all_tables),
        quality_score,
    )
    return finalize_document_parse(result)
