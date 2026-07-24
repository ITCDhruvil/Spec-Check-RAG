import logging
from pathlib import Path

import fitz
import pdfplumber
from django.conf import settings
from PIL import Image

from apps.parsing.choices import ExtractionMethod
from apps.parsing.parsers.base import DocumentParseResult, ParsedPageResult, ParsedTableResult
from apps.parsing.services.quality import aggregate_quality, is_poor_extraction, score_page_text
from apps.parsing.services.parse_finalize import finalize_document_parse
from apps.parsing.services.section_detection import (
    build_structured_text,
    detect_sections_from_pages,
)

logger = logging.getLogger(__name__)


def _ocr_page_image(pix: fitz.Pixmap) -> str:
    import pytesseract

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img)


def _extract_page_native(page: fitz.Page) -> str:
    """
    Extract page text in a stable reading order.

    PyMuPDF's default "text" output can scramble columns and break line ordering.
    `sort=True` substantially improves multi-column layouts for many tender PDFs.
    """
    try:
        text = page.get_text("text", sort=True) or ""
    except TypeError:
        # Older PyMuPDF versions may not support sort kwarg.
        text = page.get_text("text") or ""
    return text


def _strip_repeating_headers_footers(page_texts: list[str]) -> list[str]:
    """
    Remove lines that repeat on many pages (running headers/footers).

    We only consider the top/bottom few lines of each page as candidates and remove
    those appearing on >= 30% of pages. This reduces noisy "section" detection
    (e.g. repeated agency names / page headers).
    """
    if not page_texts:
        return page_texts

    def norm(line: str) -> str:
        return " ".join(line.strip().split())

    # Collect candidate header/footer lines.
    counts: dict[str, int] = {}
    per_page_candidates: list[set[str]] = []
    for txt in page_texts:
        lines = [norm(l) for l in (txt or "").splitlines() if norm(l)]
        top = lines[:3]
        bottom = lines[-3:] if len(lines) > 3 else []
        cand = {
            l
            for l in (top + bottom)
            if 3 <= len(l) <= 80 and any(ch.isalpha() for ch in l)
        }
        per_page_candidates.append(cand)
        for l in cand:
            counts[l] = counts.get(l, 0) + 1

    threshold = max(2, int(0.30 * len(page_texts)))
    to_remove = {l for l, c in counts.items() if c >= threshold}
    if not to_remove:
        return page_texts

    cleaned: list[str] = []
    for txt, cand in zip(page_texts, per_page_candidates):
        remove = to_remove.intersection(cand)
        if not remove:
            cleaned.append(txt)
            continue
        out_lines: list[str] = []
        for raw in (txt or "").splitlines():
            n = norm(raw)
            if n and n in remove:
                continue
            out_lines.append(raw)
        cleaned.append("\n".join(out_lines))
    return cleaned


def _extract_tables_pymupdf(doc: fitz.Document) -> list[ParsedTableResult]:
    """Table extraction via PyMuPDF's native detector (reuses the open handle;
    ~3x faster than the previous pdfplumber pass which re-parsed the whole file)."""
    tables: list[ParsedTableResult] = []
    for index in range(len(doc)):
        page_num = index + 1
        try:
            found = doc.load_page(index).find_tables()
        except Exception as exc:
            logger.warning(
                "pymupdf_tables_failed page=%s error=%s", page_num, exc
            )
            continue
        for tab in found.tables:
            try:
                data = tab.extract()
            except Exception:
                continue
            if not data:
                continue
            headers = [str(c or "").strip() for c in data[0]]
            rows = [
                [str(c or "").strip() for c in row]
                for row in data[1:]
                if any(str(c or "").strip() for c in row)
            ]
            tables.append(
                ParsedTableResult(
                    page_number=page_num,
                    headers=headers,
                    rows=rows,
                    raw=data,
                )
            )
    return tables


def _extract_tables_pdfplumber(file_path: Path) -> list[ParsedTableResult]:
    tables: list[ParsedTableResult] = []
    try:
        with pdfplumber.open(str(file_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables() or []:
                    if not table:
                        continue
                    headers = [str(c or "").strip() for c in table[0]]
                    rows = [
                        [str(c or "").strip() for c in row]
                        for row in table[1:]
                        if any(str(c or "").strip() for c in row)
                    ]
                    tables.append(
                        ParsedTableResult(
                            page_number=page_num,
                            headers=headers,
                            rows=rows,
                            raw=table,
                        )
                    )
    except Exception as exc:
        logger.warning("pdfplumber_tables_failed path=%s error=%s", file_path, exc)
    return tables


def parse_pdf(file_path: Path) -> DocumentParseResult:
    pages: list[ParsedPageResult] = []
    ocr_pages_count = 0
    empty_pages = 0

    doc = fitz.open(str(file_path))
    tables: list[ParsedTableResult] = []
    try:
        raw_page_texts: list[str] = []
        for index in range(len(doc)):
            page_number = index + 1
            page = doc.load_page(index)
            text = _extract_page_native(page)
            method = ExtractionMethod.NATIVE_PDF
            ocr_used = False
            quality = score_page_text(text)

            if settings.PARSING_OCR_ENABLED and is_poor_extraction(quality):
                try:
                    pix = page.get_pixmap(dpi=200)
                    ocr_text = _ocr_page_image(pix)
                    ocr_quality = score_page_text(ocr_text)
                    if ocr_quality > quality:
                        text = ocr_text
                        method = ExtractionMethod.OCR
                        ocr_used = True
                        quality = ocr_quality
                        ocr_pages_count += 1
                except Exception as exc:
                    logger.warning(
                        "ocr_fallback_failed page=%s error=%s", page_number, exc
                    )

            is_empty = not text.strip()
            if is_empty:
                empty_pages += 1

            raw_page_texts.append(text)
            pages.append(
                ParsedPageResult(
                    page_number=page_number,
                    extracted_text=text,
                    extraction_method=method,
                    ocr_used=ocr_used,
                    quality_score=quality,
                    is_empty=is_empty,
                )
            )
        # Tables while the handle is open (native detector, no second file parse).
        if getattr(settings, "PARSING_TABLE_PARSER", "pymupdf").lower() != "pdfplumber":
            tables = _extract_tables_pymupdf(doc)
    finally:
        doc.close()

    # Strip repeating headers/footers to improve downstream section detection.
    cleaned_texts = _strip_repeating_headers_footers(raw_page_texts)
    if cleaned_texts and len(cleaned_texts) == len(pages):
        for p, new_text in zip(pages, cleaned_texts):
            p.extracted_text = new_text

    if getattr(settings, "PARSING_TABLE_PARSER", "pymupdf").lower() == "pdfplumber":
        tables = _extract_tables_pdfplumber(file_path)
    sections = detect_sections_from_pages(pages)
    raw_text = "\n\n".join(
        f"--- Page {p.page_number} ---\n{p.extracted_text}" for p in pages if p.extracted_text
    )
    structured_text = build_structured_text(sections)
    page_scores = [p.quality_score for p in pages if not p.is_empty] or [0.0]
    quality_score = aggregate_quality(page_scores)

    metadata = {
        "file_type": "pdf",
        "parser": "pymupdf",
        "table_parser": getattr(settings, "PARSING_TABLE_PARSER", "pymupdf").lower(),
        "total_pages": len(pages),
        "empty_pages": empty_pages,
        "ocr_pages": ocr_pages_count,
        "tables": [
            {
                "page": t.page_number,
                "headers": t.headers,
                "rows": t.rows,
            }
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
    )
    return finalize_document_parse(result)
