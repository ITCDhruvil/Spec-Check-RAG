"""
Reciprocal rank fusion (RRF) for merging keyword-routed and hybrid-retrieved chunks.
"""

from __future__ import annotations

from apps.intelligence.models import DocumentChunk


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    *,
    weights: list[float] | None = None,
    k: int = 60,
) -> dict[str, float]:
    """Merge ranked chunk-id lists into a single RRF score map."""
    scores: dict[str, float] = {}
    if not ranked_lists:
        return scores

    w = weights or [1.0] * len(ranked_lists)
    for weight, ids in zip(w, ranked_lists):
        for rank, chunk_id in enumerate(ids):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight * (1.0 / (k + rank + 1))
    return scores


def fuse_chunk_selections(
    *,
    keyword_selected: list[DocumentChunk],
    hybrid_scores: dict[str, float],
    all_chunks: list[DocumentChunk],
    max_chunks: int,
    keyword_weight: float = 1.0,
    hybrid_weight: float = 1.0,
) -> list[DocumentChunk]:
    """
    Merge keyword routing with hybrid retrieval scores via RRF, then return top chunks
    in document order for stable LLM context.
    """
    if not hybrid_scores:
        return keyword_selected[:max_chunks]

    chunks_by_id = {str(c.id): c for c in all_chunks}

    hybrid_ranked = sorted(
        (cid for cid in hybrid_scores if cid in chunks_by_id),
        key=lambda cid: (-hybrid_scores[cid], chunks_by_id[cid].chunk_order),
    )
    keyword_ranked = [str(c.id) for c in keyword_selected]

    fused = reciprocal_rank_fusion(
        [keyword_ranked, hybrid_ranked],
        weights=[keyword_weight, hybrid_weight],
    )

    ranked = sorted(
        fused.keys(),
        key=lambda cid: (-fused[cid], chunks_by_id[cid].chunk_order if cid in chunks_by_id else 0),
    )

    selected: list[DocumentChunk] = []
    seen: set[str] = set()
    for cid in ranked:
        chunk = chunks_by_id.get(cid)
        if chunk is None or cid in seen:
            continue
        selected.append(chunk)
        seen.add(cid)
        if len(selected) >= max_chunks:
            break

    if len(selected) < max_chunks:
        for chunk in keyword_selected:
            cid = str(chunk.id)
            if cid in seen:
                continue
            selected.append(chunk)
            seen.add(cid)
            if len(selected) >= max_chunks:
                break

    selected.sort(key=lambda c: c.chunk_order)
    return selected[:max_chunks]
