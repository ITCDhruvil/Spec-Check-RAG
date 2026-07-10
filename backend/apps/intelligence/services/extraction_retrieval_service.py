"""
Hybrid (BM25 + vector) chunk retrieval for field extraction passes.

Complements keyword routing in ExtractionService.select_chunks with semantic search
over the document's indexed chunks (Azure AI Search or Chroma).
"""

from __future__ import annotations

import logging

from django.conf import settings

from apps.chat.services.index_service import VectorIndexService
from apps.chat.services.retrieval_service import RetrievalService
from apps.chat.services.vector_store import get_vector_store
from apps.intelligence.choices import ExtractionType
from apps.intelligence.services.adaptive_lexicon_service import DocumentAdaptiveLexicon
from apps.intelligence.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

# Natural-language queries per extraction type — tuned for spec-check bidding docs.
EXTRACTION_RETRIEVAL_QUERIES: dict[str, list[str]] = {
    ExtractionType.ELIGIBILITY_CRITERIA: [
        "project name owner solicitation number tender reference invitation to bid",
        "project engineer architect consultant design professional firm name",
        "bidder eligibility qualification experience prequalification requirements",
    ],
    ExtractionType.SUBMISSION_DEADLINES: [
        "bid closing date submission deadline proposal due date time",
        "pre-bid conference proposer conference mandatory meeting",
        "site visit walkthrough mandatory site inspection date",
        "questions deadline clarification due bid opening municipal meeting council award",
    ],
    ExtractionType.TECHNICAL_REQUIREMENTS: [
        "project location site address facility campus municipality county",
        "technical specifications equipment installation requirements materials quantity",
        "contractor furnish labor materials equipment supplies required work",
        "sealed proposals prequalified contractors received owner location address",
    ],
    ExtractionType.SCOPE_OF_WORK: [
        "project description scope of work overview summary",
        "work to be performed deliverables services specifications",
        "statement of work demolition removal utility services contractor required",
        # NOTE: IT/network-specific scope vocabulary lives in DOC_TYPE_QUERY_OVERRIDES
        # (domain=it_network) so it only fires for network documents instead of
        # polluting construction/general scope retrieval.
    ],
    ExtractionType.PAYMENT_TERMS: [
        "estimated project value budget contract amount cost range dollar",
        "payment terms invoice milestone retention commercial pricing",
        "project value threshold notice newspaper publication general circulation requirement",
    ],
    ExtractionType.PENALTIES_AND_RISKS: [
        "bid bond performance bond payment bond surety guarantee SF-24",
        "certified check cashier check bid security bond amount percentage",
        "liquidated damages penalty termination default forfeit",
    ],
    ExtractionType.MANDATORY_DOCUMENTS: [
        "mandatory forms annexures appendices required documents submission",
        "how to obtain bid documents download acquire solicitation package",
        "proposal submission instructions bid submission requirements",
    ],
    ExtractionType.SET_ASIDES: [
        "MBE WBE DBE DVBE HUB SBE minority women disadvantaged small business goal percentage",
        "set-aside subcontracting goal diversity participation requirement",
    ],
    ExtractionType.EVALUATION_CRITERIA: [],
}


# C1 — doc-type query routing. Augment base queries with class-specific vocabulary,
# keyed by classification axis ("domain" / "solicitation_type") and value. Systematizes
# the manual per-doc-type query fixes from phases 2/3.
DOC_TYPE_QUERY_OVERRIDES: dict[str, dict[str, dict[str, list[str]]]] = {
    "domain": {
        "it_network": {
            ExtractionType.SCOPE_OF_WORK: [
                "network cabling switches wireless wifi equipment installation "
                "configuration system design",
            ],
            ExtractionType.TECHNICAL_REQUIREMENTS: [
                "structured cabling category 6 fiber patch panel access point "
                "switch port specifications",
            ],
        },
    },
    "solicitation_type": {
        "federal_rfq": {
            ExtractionType.PENALTIES_AND_RISKS: [
                "bid guarantee bid bond SF-24 performance payment bond SF-25 surety",
            ],
            ExtractionType.MANDATORY_DOCUMENTS: [
                "standard form SF-1449 representations certifications offeror fill-in",
            ],
        },
        "state_ifb": {
            ExtractionType.PENALTIES_AND_RISKS: [
                "bid security certified check cashier check percentage of bid bond",
            ],
        },
    },
}


def doc_type_routing_enabled() -> bool:
    return bool(getattr(settings, "INTELLIGENCE_DOC_TYPE_ROUTING_ENABLED", True))


def overrides_for_classification(classification) -> dict[str, list[str]]:
    """
    Build {extraction_type: [extra queries]} from a DocClassification.

    Routing ON  → inject only overrides matching the document's classified axes.
    Routing OFF → inject every override (superset = pre-C1 behavior, used as rollback).
    """
    routing = doc_type_routing_enabled()
    merged: dict[str, list[str]] = {}

    def _add(type_map: dict[str, list[str]]) -> None:
        for etype, queries in type_map.items():
            bucket = merged.setdefault(etype, [])
            for q in queries:
                if q not in bucket:
                    bucket.append(q)

    for axis, by_value in DOC_TYPE_QUERY_OVERRIDES.items():
        if routing:
            value = getattr(classification, axis, None) if classification else None
            if value and value in by_value:
                _add(by_value[value])
        else:
            for type_map in by_value.values():
                _add(type_map)
    return merged


def hybrid_retrieval_enabled() -> bool:
    from apps.intelligence.services.fast_mode import keyword_only_extraction

    if keyword_only_extraction():
        return False
    return bool(getattr(settings, "INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED", True))


class ExtractionRetrievalService:
    @staticmethod
    def queries_for_type(
        extraction_type: str,
        lexicon: DocumentAdaptiveLexicon | None = None,
    ) -> list[str]:
        static = list(EXTRACTION_RETRIEVAL_QUERIES.get(extraction_type, []))
        if not lexicon:
            return static
        adaptive = lexicon.queries_for(extraction_type)
        terms = lexicon.terms_for(extraction_type)
        # Turn distinctive short terms into BM25-friendly query strings for Azure hybrid search.
        term_query = " ".join(terms[:6]) if terms else ""
        merged: list[str] = []
        seen: set[str] = set()
        for q in static + adaptive + ([term_query] if term_query else []):
            key = q.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(q.strip())
        return merged

    @staticmethod
    def scores_for_types(
        document_id: str,
        extraction_types: list[str],
        *,
        lexicon: DocumentAdaptiveLexicon | None = None,
        extra_queries_by_type: dict[str, list[str]] | None = None,
    ) -> dict[str, dict[str, float]]:
        """
        Batch hybrid search for multiple extraction types.

        Returns {extraction_type: {chunk_id: max_similarity_score}}.
        """
        if not hybrid_retrieval_enabled():
            return {}

        if not VectorIndexService.is_indexed(document_id):
            logger.warning(
                "extraction_hybrid_skipped document_id=%s reason=not_indexed",
                document_id,
            )
            return {}

        query_specs: list[tuple[str, str]] = []
        for etype in extraction_types:
            queries = ExtractionRetrievalService.queries_for_type(etype, lexicon)
            if extra_queries_by_type:
                queries = queries + list(extra_queries_by_type.get(etype, []))
            for query in queries:
                if query.strip():
                    query_specs.append((etype, query.strip()))
        if not query_specs:
            return {}

        openai = OpenAIService()
        query_texts = [q for _, q in query_specs]
        embeddings, usage = openai.embed_texts(query_texts)
        if not embeddings:
            return {}

        store = get_vector_store()
        top_k = getattr(settings, "INTELLIGENCE_EXTRACTION_RETRIEVAL_TOP_K", 12)
        min_score = getattr(settings, "INTELLIGENCE_EXTRACTION_MIN_RETRIEVAL_SCORE", 0.18)

        scores_by_type: dict[str, dict[str, float]] = {t: {} for t in extraction_types}
        total_hits = 0

        for (etype, query_text), embedding in zip(query_specs, embeddings):
            search_text = query_text if store.backend_name() == "azure_search" else None
            raw = store.query(
                document_id=document_id,
                query_embedding=embedding,
                top_k=top_k,
                search_text=search_text,
            )
            hits = RetrievalService._parse_hits(raw, min_score=min_score)
            if not hits and min_score > 0:
                hits = RetrievalService._parse_hits(raw, min_score=0.0)

            for hit in hits:
                bucket = scores_by_type.setdefault(etype, {})
                prev = bucket.get(hit.chunk_id, 0.0)
                bucket[hit.chunk_id] = max(prev, hit.score)
                total_hits += 1

        logger.info(
            "extraction_hybrid_retrieval document_id=%s types=%s queries=%s hits=%s embed_tokens=%s",
            document_id,
            len(extraction_types),
            len(query_specs),
            total_hits,
            usage.get("total_tokens", 0),
        )
        return scores_by_type
