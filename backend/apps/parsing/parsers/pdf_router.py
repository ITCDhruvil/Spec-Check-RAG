"""
PDF parsing router: Docling (primary) → Azure Document Intelligence → PyMuPDF.

PARSING_PDF_PARSER values:
  - docling (default): Docling open-source parser; falls back to PyMuPDF if unavailable
  - auto: Azure DI if configured, else PyMuPDF (legacy behaviour)
  - azure: Azure DI only (raises if not configured)
  - pymupdf: local PyMuPDF + pdfplumber only
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

from apps.parsing.parsers.azure_di_parser import is_azure_di_configured, parse_pdf_azure_di
from apps.parsing.parsers.base import DocumentParseResult
from apps.parsing.parsers.pdf_parser import parse_pdf as parse_pdf_pymupdf

logger = logging.getLogger(__name__)


def _try_docling(file_path: Path) -> DocumentParseResult | None:
    """Attempt Docling parse; return None on any failure (acts as soft fallback)."""
    try:
        from apps.parsing.parsers.docling_parser import _is_available, parse_with_docling

        if not _is_available():
            logger.warning("docling_not_installed — falling back to PyMuPDF")
            return None
        return parse_with_docling(file_path)
    except Exception as exc:
        logger.warning("docling_parse_failed path=%s error=%s — falling back to PyMuPDF", file_path, exc)
        return None


def _looks_scanned_or_garbled(result: DocumentParseResult) -> bool:
    """True when local parsing produced unusably poor text (scanned/garbled PDF)."""
    threshold = float(getattr(settings, "PARSING_DI_FALLBACK_QUALITY_THRESHOLD", 0.45))
    if result.parsing_quality_score < threshold:
        return True
    pages = result.pages or []
    if not pages:
        return True
    empty = sum(1 for p in pages if p.is_empty)
    # Mostly-empty documents are scans even when the few text pages score well.
    return empty / len(pages) > 0.5


def _di_fallback_if_poor(
    result: DocumentParseResult, file_path: Path
) -> DocumentParseResult:
    """Re-parse with Azure Document Intelligence when local text quality is poor."""
    if not getattr(settings, "PARSING_DI_FALLBACK_ENABLED", True):
        return result
    if not is_azure_di_configured():
        return result
    if not _looks_scanned_or_garbled(result):
        return result
    try:
        di_result = parse_pdf_azure_di(file_path)
    except Exception as exc:
        logger.warning(
            "azure_di_quality_fallback_failed path=%s error=%s — keeping local parse",
            file_path,
            exc,
        )
        return result
    logger.info(
        "azure_di_quality_fallback path=%s local_quality=%s di_quality=%s",
        file_path,
        result.parsing_quality_score,
        di_result.parsing_quality_score,
    )
    # Keep whichever parse actually read the document better.
    if di_result.parsing_quality_score >= result.parsing_quality_score:
        return di_result
    return result


def parse_pdf(file_path: Path) -> DocumentParseResult:
    strategy = getattr(settings, "PARSING_PDF_PARSER", "docling").lower()

    if strategy == "pymupdf":
        return _di_fallback_if_poor(parse_pdf_pymupdf(file_path), file_path)

    if strategy == "azure":
        if not is_azure_di_configured():
            raise RuntimeError(
                "PARSING_PDF_PARSER=azure but AZURE_DI_ENDPOINT/AZURE_DI_KEY are not set."
            )
        return parse_pdf_azure_di(file_path)

    if strategy == "docling":
        result = _try_docling(file_path)
        if result is not None:
            return _di_fallback_if_poor(result, file_path)
        # Fallback: PyMuPDF
        logger.info("docling_fallback_pymupdf path=%s", file_path)
        return _di_fallback_if_poor(parse_pdf_pymupdf(file_path), file_path)

    # auto (legacy): Azure DI if configured, else PyMuPDF
    if is_azure_di_configured():
        try:
            result = parse_pdf_azure_di(file_path)
            logger.info("pdf_parse_azure_di path=%s pages=%s", file_path, len(result.pages))
            return result
        except Exception as exc:
            logger.warning(
                "azure_di_fallback path=%s error=%s — using PyMuPDF",
                file_path,
                exc,
            )

    return _di_fallback_if_poor(parse_pdf_pymupdf(file_path), file_path)
