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


def parse_pdf(file_path: Path) -> DocumentParseResult:
    strategy = getattr(settings, "PARSING_PDF_PARSER", "docling").lower()

    if strategy == "pymupdf":
        return parse_pdf_pymupdf(file_path)

    if strategy == "azure":
        if not is_azure_di_configured():
            raise RuntimeError(
                "PARSING_PDF_PARSER=azure but AZURE_DI_ENDPOINT/AZURE_DI_KEY are not set."
            )
        return parse_pdf_azure_di(file_path)

    if strategy == "docling":
        result = _try_docling(file_path)
        if result is not None:
            return result
        # Fallback: PyMuPDF
        logger.info("docling_fallback_pymupdf path=%s", file_path)
        return parse_pdf_pymupdf(file_path)

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

    return parse_pdf_pymupdf(file_path)
