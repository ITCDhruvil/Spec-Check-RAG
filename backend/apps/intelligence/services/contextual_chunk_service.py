"""
Contextual Retrieval — prepend LLM-generated context snippets to chunks before indexing.

Based on Anthropic's Contextual Retrieval paper (2024): prepend a short (1-2 sentence)
context to each chunk situating it within the full document. Dramatically reduces
retrieval failures for context-sparse chunks (e.g. scope-of-work fragments that lose
solicitation number, project name, and document type when split).

Context is generated ONCE at index time (not query time) using gpt-4o-mini with
automatic OpenAI prompt caching on the stable document prefix. Stored on
DocumentChunk.contextual_prefix; used as the `content` field in Azure AI Search
(both BM25 and semantic ranker see the enriched text). Original chunk_text is still
sent to the LLM for extraction (no synthetic context injected into extraction).
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from apps.intelligence.models import DocumentChunk
    from apps.intelligence.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

# Stable system prompt — same across all documents and all chunks.
# OpenAI auto-caches the stable prefix, so all chunk calls after the first
# for a given document share a warm cache on the full document text.
_SYSTEM_PROMPT = (
    "You are a procurement document expert specializing in US government and "
    "public-sector solicitations (RFQ, IFB, RFP, ITB, IDIQ, BPA). "
    "Given a full procurement document and one chunk from it, write 1-2 sentences "
    "that situate the chunk within the document. "
    "Include as many of these as are present in the document: document type "
    "(RFQ/IFB/RFP), solicitation number, project name, issuing agency/owner, "
    "and what topic the chunk covers. "
    "Answer ONLY with the succinct context — no preamble, no explanation."
)

_USER_TEMPLATE = (
    "<document>\n"
    "{doc_text}"
    "\n</document>\n\n"
    "Here is the chunk to situate within the document above:\n"
    "<chunk>\n"
    "{chunk_text}"
    "\n</chunk>\n\n"
    "Provide a succinct 1-2 sentence context to situate this chunk for retrieval. "
    "Answer only with the context."
)

# Characters of doc_text to include in the prompt.
# 60k chars ≈ 15k tokens — leaves plenty of room for chunk + response in 128k context.
_DEFAULT_MAX_DOC_CHARS = 60_000


def _generate_one(
    chunk: "DocumentChunk",
    doc_text: str,
    openai: "OpenAIService",
    fast_model: str,
    max_doc_chars: int,
) -> tuple[str, str]:
    """Return (chunk_id_str, prefix). Retries on 429; never raises."""
    from openai import RateLimitError

    user_msg = _USER_TEMPLATE.format(
        doc_text=doc_text[:max_doc_chars],
        chunk_text=chunk.chunk_text,
    )
    for attempt in range(4):
        try:
            prefix, _usage = openai.chat_text(
                system=_SYSTEM_PROMPT,
                user=user_msg,
                model=fast_model,
                temperature=0.0,
            )
            logger.debug(
                "contextual_prefix_generated chunk_id=%s chars=%s",
                chunk.id,
                len(prefix),
            )
            return str(chunk.id), prefix.strip()
        except RateLimitError:
            wait = 15 * (2 ** attempt)  # 15s, 30s, 60s, 120s
            logger.warning(
                "contextual_prefix_rate_limit chunk_id=%s attempt=%s wait=%s",
                chunk.id,
                attempt + 1,
                wait,
            )
            time.sleep(wait)
        except Exception as exc:
            logger.warning(
                "contextual_prefix_failed chunk_id=%s error=%s",
                chunk.id,
                exc,
            )
            return str(chunk.id), ""
    logger.warning("contextual_prefix_gave_up chunk_id=%s", chunk.id)
    return str(chunk.id), ""


def generate_contextual_prefixes(
    chunks: list["DocumentChunk"],
    doc_text: str,
) -> dict[str, str]:
    """
    Generate contextual prefixes for all chunks in parallel.

    Returns {chunk_id_str: prefix}. Chunks that fail get empty-string prefix
    (they will index with plain chunk_text, same as today).
    """
    from apps.intelligence.services.model_routing import model_for_tier
    from apps.intelligence.services.openai_service import OpenAIService

    if not chunks:
        return {}

    openai = OpenAIService()
    fast_model = model_for_tier("fast")
    max_doc_chars = getattr(settings, "CONTEXTUAL_RETRIEVAL_MAX_DOC_CHARS", _DEFAULT_MAX_DOC_CHARS)
    max_workers = getattr(settings, "CONTEXTUAL_RETRIEVAL_MAX_WORKERS", 4)

    results: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_generate_one, chunk, doc_text, openai, fast_model, max_doc_chars): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk_id, prefix = future.result()
            results[chunk_id] = prefix

    logger.info(
        "contextual_prefixes_done total=%s non_empty=%s",
        len(chunks),
        sum(1 for v in results.values() if v),
    )
    return results


def generate_and_save(
    chunks: list["DocumentChunk"],
    doc_text: str,
) -> int:
    """
    Generate contextual prefixes and persist them on each DocumentChunk.

    Returns count of chunks that received a non-empty prefix.
    """
    prefixes = generate_contextual_prefixes(chunks, doc_text)
    saved = 0
    to_update = []
    for chunk in chunks:
        prefix = prefixes.get(str(chunk.id), "")
        chunk.contextual_prefix = prefix
        to_update.append(chunk)
        if prefix:
            saved += 1

    # Bulk-update to avoid N individual saves.
    from apps.intelligence.models import DocumentChunk

    DocumentChunk.objects.bulk_update(to_update, ["contextual_prefix"])
    logger.info(
        "contextual_prefixes_saved document_id=%s saved=%s total=%s",
        chunks[0].document_id if chunks else "?",
        saved,
        len(chunks),
    )
    return saved
