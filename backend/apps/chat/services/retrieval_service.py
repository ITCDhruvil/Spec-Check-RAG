"""Retrieve grounded chunks for a document-scoped query."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.chat.services.vector_store import get_vector_store
from apps.intelligence.models import DocumentChunk
from apps.intelligence.services.openai_service import OpenAIService


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    section_title: str
    score: float
    chunk_order: int
    chunk_type: str = ""


_QUERY_EXPANSIONS: dict[str, list[str]] = {
    "pre-bid": [
        "proposer conference pre-proposal conference timeline schedule",
        "issue date advertisement schedule conference due date time",
    ],
    "prebid": [
        "proposer conference pre-proposal conference timeline schedule",
        "issue date advertisement schedule conference due date time",
    ],
    "pre bid": [
        "proposer conference pre-proposal conference timeline schedule",
        "issue date advertisement schedule conference due date time",
    ],
}

_TIMELINE_QUERY_MARKERS = (
    "pre-bid",
    "prebid",
    "pre bid",
    "deadline",
    "due date",
    "conference",
    "timeline",
    "submission date",
)


def _merge_timeline_chunks(
    by_id: dict[str, "RetrievedChunk"],
    document_id: str,
    query: str,
    *,
    store_name: str,
) -> None:
    """Merge timeline keyword chunks into the result map.

    Chroma (original behaviour): timeline chunks can override vector results and
    rank first — they were designed to rescue missed timeline content when dense
    search fails.

    Azure AI Search: vector search now returns correctly ranked results after the
    score-normalization fix.  Timeline chunks must only *supplement* — they must
    not displace an already-retrieved chunk and must not rank above vector results.
    If a timeline chunk was already retrieved by vector search, keep the vector
    score.  If it was not retrieved, add it with a score below all vector results
    so that it sorts last, acting as a safety net rather than an override.
    """
    timeline = RetrievalService._timeline_keyword_chunks(document_id, query)
    if not timeline:
        return

    if store_name == "azure_search":
        # Additive-only: never override vector scores; rank supplemental chunks last.
        min_vector_score = min((c.score for c in by_id.values()), default=0.0)
        supplement_score = min_vector_score * 0.5 if min_vector_score > 0 else 1e-6
        for chunk in timeline:
            if chunk.chunk_id not in by_id:
                chunk.score = supplement_score
                by_id[chunk.chunk_id] = chunk
        # If the chunk IS already in by_id, keep the vector score unchanged.
    else:
        # Chroma original behaviour: override if timeline score >= existing score.
        for chunk in timeline:
            prev = by_id.get(chunk.chunk_id)
            if prev is None or chunk.score >= prev.score:
                by_id[chunk.chunk_id] = chunk


class RetrievalService:
    @staticmethod
    def _timeline_keyword_chunks(document_id: str, query: str) -> list[RetrievedChunk]:
        """Pin schedule/cover chunks when vector search misses timeline content."""
        lowered = query.lower()
        if not any(marker in lowered for marker in _TIMELINE_QUERY_MARKERS):
            return []

        supplemental: list[RetrievedChunk] = []
        for chunk in DocumentChunk.objects.filter(document_id=document_id).order_by(
            "chunk_order"
        ):
            meta = chunk.metadata or {}
            chunk_type = meta.get("chunk_type", "")
            lower_text = chunk.chunk_text.lower()
            is_schedule = chunk_type == "schedule_table"
            is_cover = chunk_type == "cover_metadata" and chunk.page_start <= 3
            is_legacy_cover = chunk.page_start == 1 and (
                "issue date" in lower_text or "bid period" in lower_text
            )
            if not (is_schedule or is_cover or is_legacy_cover):
                continue
            supplemental.append(
                RetrievedChunk(
                    chunk_id=str(chunk.id),
                    text=chunk.chunk_text,
                    page_start=int(chunk.page_start),
                    page_end=int(chunk.page_end),
                    section_title=str(chunk.section_title or ""),
                    score=0.5,
                    chunk_order=int(chunk.chunk_order),
                    chunk_type=str(chunk_type),
                )
            )
            if is_schedule:
                break
        return supplemental

    @staticmethod
    def _expanded_queries(query: str) -> list[str]:
        q = query.strip()
        if not q:
            return []
        lowered = q.lower()
        extra: list[str] = []
        for key, phrases in _QUERY_EXPANSIONS.items():
            if key in lowered:
                extra.extend(phrases)
                break
        return [q, *extra]

    @staticmethod
    def _parse_hits(
        raw: dict,
        *,
        min_score: float,
    ) -> list[RetrievedChunk]:
        ids = (raw.get("ids") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        scores_raw = (raw.get("scores") or [[]])
        scores_list = scores_raw[0] if scores_raw else []

        results: list[RetrievedChunk] = []
        for i, chunk_id in enumerate(ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            if scores_list and i < len(scores_list):
                score = float(scores_list[i])
            else:
                distance = distances[i] if i < len(distances) else 1.0
                score = max(0.0, 1.0 - float(distance))
            if score < min_score:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=documents[i] if i < len(documents) else "",
                    page_start=int(meta.get("page_start", 1)),
                    page_end=int(meta.get("page_end", 1)),
                    section_title=str(meta.get("section_title", "")),
                    score=round(score, 4),
                    chunk_order=int(meta.get("chunk_order", 0)),
                    chunk_type=str(meta.get("chunk_type", "")),
                )
            )
        return results

    @staticmethod
    def _hyde_passages(query: str, openai: OpenAIService) -> list[str]:
        """C2 — generate a hypothetical answer passage to retrieve by answer-similarity.

        Recovers vocab-mismatch misses where the generic query terms don't appear in
        the target chunk but the *answer* phrasing does. Best-effort: failure returns [].
        """
        from apps.intelligence.prompts.templates import HYDE_SYSTEM_PROMPT, hyde_user_prompt
        from apps.intelligence.services.model_routing import model_for_tier

        try:
            data, _ = openai.chat_json(
                system=HYDE_SYSTEM_PROMPT,
                user=hyde_user_prompt(query),
                model=model_for_tier("fast"),
            )
        except Exception:
            return []
        passage = str((data or {}).get("passage") or "").strip()
        return [passage] if passage else []

    @staticmethod
    def retrieve(document_id: str, query: str) -> list[RetrievedChunk]:
        openai = OpenAIService()
        queries = RetrievalService._expanded_queries(query)

        # C2 — HyDE: append a hypothetical answer passage so vector/semantic search
        # can match chunks by answer-similarity, not just query-term overlap.
        if getattr(settings, "CHAT_HYDE_ENABLED", False):
            queries = queries + RetrievalService._hyde_passages(query, openai)

        query_embeddings, _ = openai.embed_texts(queries)
        if not query_embeddings:
            return []

        store = get_vector_store()
        doc_id = str(document_id)
        # Azure uses a higher top_k because hybrid RRF is server-side and more
        # candidates improve Citation Recall across multi-passage GT groups.
        if store.backend_name() == "azure_search":
            top_k = getattr(settings, "AZURE_SEARCH_TOP_K", settings.CHAT_RETRIEVAL_TOP_K)
            min_score = getattr(settings, "AZURE_SEARCH_MIN_RETRIEVAL_SCORE", 0.0)
        else:
            top_k = settings.CHAT_RETRIEVAL_TOP_K
            min_score = settings.CHAT_MIN_RETRIEVAL_SCORE
        by_id: dict[str, RetrievedChunk] = {}

        for i, embedding in enumerate(query_embeddings):
            search_text = queries[i] if store.backend_name() == "azure_search" else None
            raw = store.query(
                document_id=doc_id,
                query_embedding=embedding,
                top_k=top_k,
                search_text=search_text,
            )
            for chunk in RetrievalService._parse_hits(raw, min_score=min_score):
                prev = by_id.get(chunk.chunk_id)
                if prev is None or chunk.score > prev.score:
                    by_id[chunk.chunk_id] = chunk

        _merge_timeline_chunks(by_id, doc_id, query, store_name=store.backend_name())

        merged = sorted(by_id.values(), key=lambda c: (-c.score, c.chunk_order))
        if merged:
            return merged[:top_k]

        for i, embedding in enumerate(query_embeddings):
            search_text = queries[i] if store.backend_name() == "azure_search" else None
            raw = store.query(
                document_id=doc_id,
                query_embedding=embedding,
                top_k=top_k,
                search_text=search_text,
            )
            for chunk in RetrievalService._parse_hits(raw, min_score=0.0):
                prev = by_id.get(chunk.chunk_id)
                if prev is None or chunk.score > prev.score:
                    by_id[chunk.chunk_id] = chunk

        _merge_timeline_chunks(by_id, doc_id, query, store_name=store.backend_name())

        fallback = sorted(by_id.values(), key=lambda c: (-c.score, c.chunk_order))
        return fallback[: max(1, min(3, top_k))]
