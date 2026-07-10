"""Verify chat citations are grounded in retrieved chunk text and PDF pages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from apps.intelligence.services.citation_service import resolve_page_from_source_text

if TYPE_CHECKING:
    from apps.chat.services.retrieval_service import RetrievedChunk
    from apps.documents.models import Document


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _coerce_page(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page >= 1 else None


def _document_page_texts(document: Document) -> list[tuple[int, str]]:
    try:
        parsed = document.parsed_document
    except Exception:
        return []
    return list(
        parsed.pages.order_by("page_number").values_list(
            "page_number", "extracted_text"
        )
    )


def snap_quote_to_page_text(quote: str, page_text: str) -> tuple[str | None, bool]:
    """
    Return a substring of quote that appears in page_text (for PDF.js highlight).
    Chunk text and PDF text layers often differ slightly; we prefer a PDF-verified snippet.
    """
    quote = (quote or "").strip()
    if not quote or not (page_text or "").strip():
        return None, False

    if _normalize(quote) in _normalize(page_text):
        return quote, True

    words = quote.split()
    best: str | None = None
    best_len = 0

    for length in range(len(words), 2, -1):
        for start in range(0, len(words) - length + 1):
            segment = " ".join(words[start : start + length])
            if len(segment) < 12:
                continue
            if _normalize(segment) in _normalize(page_text):
                if len(segment) > best_len:
                    best = segment
                    best_len = len(segment)
        if best_len >= 24:
            break

    if best:
        return best, True

    if len(words) >= 3:
        anchor = " ".join(words[:3])
        if len(anchor) >= 10 and _normalize(anchor) in _normalize(page_text):
            return anchor, True

    return None, False


def _resolve_page_and_snippet(
    quote: str,
    *,
    page_texts: list[tuple[int, str]],
    page_start: int,
    page_end: int,
    page_hint: int | None,
) -> tuple[int, str, bool]:
    """Pick page in chunk range where quote can be highlighted; snap text to PDF layer."""
    hint = page_hint if page_hint is not None else page_start
    resolved = resolve_page_from_source_text(
        quote,
        page_texts=page_texts,
        page_hint_start=page_start,
        page_hint_end=page_end,
    )
    candidates: list[int] = []
    if resolved is not None:
        candidates.append(resolved)
    if hint not in candidates:
        candidates.append(hint)
    for p in range(page_start, page_end + 1):
        if p not in candidates:
            candidates.append(p)

    for page_num in candidates:
        page_text = next((t for pn, t in page_texts if pn == page_num), "")
        snapped, ok = snap_quote_to_page_text(quote, page_text)
        if ok and snapped:
            return page_num, snapped, True

    fallback_page = candidates[0] if candidates else page_start
    return fallback_page, quote, False


def filter_grounded_citations(
    citations: list[dict],
    retrieved: list[RetrievedChunk],
    *,
    document: Document | None = None,
) -> list[dict]:
    """Drop ungrounded citations; resolve page + PDF-highlightable source_text."""
    if not retrieved:
        return []

    by_id = {c.chunk_id: c for c in retrieved}
    page_texts = _document_page_texts(document) if document else []
    grounded: list[dict] = []

    for item in citations:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id", ""))
        quote = str(item.get("source_text", "")).strip()
        if not chunk_id or not quote:
            continue
        chunk = by_id.get(chunk_id)
        if not chunk:
            continue
        if _normalize(quote) not in _normalize(chunk.text):
            continue

        page_hint = _coerce_page(item.get("page"))
        page_start = int(chunk.page_start)
        page_end = int(chunk.page_end)

        if page_texts:
            page, source_text, highlightable = _resolve_page_and_snippet(
                quote,
                page_texts=page_texts,
                page_start=page_start,
                page_end=page_end,
                page_hint=page_hint,
            )
        else:
            page = page_hint or page_start
            source_text = quote
            highlightable = False

        section = str(item.get("section") or chunk.section_title or "")[:512]

        grounded.append(
            {
                **item,
                "page": page,
                "section": section,
                "source_text": source_text[:2000],
                "highlightable": highlightable,
            }
        )
    return grounded
