"""
Fast extraction mode — keyword-only field extraction without RAG/indexing.

Enable with INTELLIGENCE_FAST_MODE=True in backend/.env for spec-check workflows
that only need structured fields from the document (no chat / vector search).
"""

from __future__ import annotations

from django.conf import settings


def fast_extraction_enabled() -> bool:
    return bool(getattr(settings, "INTELLIGENCE_FAST_MODE", False))


def group_extraction_enabled() -> bool:
    """One LLM call per field group — simple parallel prompt extraction."""
    if bool(getattr(settings, "INTELLIGENCE_GROUP_EXTRACTION", False)):
        return True
    return fast_extraction_enabled()


def skip_chunking_in_intelligence() -> bool:
    return group_extraction_enabled()


def skip_indexing_on_parse() -> bool:
    return fast_extraction_enabled() or bool(
        getattr(settings, "INTELLIGENCE_SKIP_INDEXING_ON_PARSE", False)
    )


def skip_embedding_in_intelligence() -> bool:
    return fast_extraction_enabled() or bool(
        getattr(settings, "INTELLIGENCE_SKIP_EMBEDDING", False)
    )


def keyword_only_extraction() -> bool:
    if fast_extraction_enabled():
        return True
    return not bool(getattr(settings, "INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED", True))


def defer_docx_preview() -> bool:
    return fast_extraction_enabled() or bool(
        getattr(settings, "DOCX_PREVIEW_DEFER", False)
    )


def default_extraction_chunks() -> int:
    if fast_extraction_enabled():
        return int(getattr(settings, "INTELLIGENCE_FAST_DEFAULT_CHUNKS", 6))
    return int(getattr(settings, "INTELLIGENCE_DEFAULT_EXTRACTION_CHUNKS", 10))


def broad_extraction_chunks() -> int:
    if fast_extraction_enabled():
        return int(getattr(settings, "INTELLIGENCE_FAST_BROAD_CHUNKS", 8))
    return int(getattr(settings, "INTELLIGENCE_BROAD_EXTRACTION_CHUNKS", 14))


def extraction_batch_size() -> int:
    if fast_extraction_enabled():
        return int(getattr(settings, "INTELLIGENCE_FAST_BATCH_SIZE", 5))
    return int(getattr(settings, "INTELLIGENCE_EXTRACTION_BATCH_SIZE", 3))
