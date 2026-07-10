"""
Adaptive document lexicon for unpredictable bidding documents.

Instead of relying only on fixed keyword lists, each document gets:
1. Heuristic term mining from cover/TOC text (no LLM)
2. Optional LLM vocabulary pass (gpt-4o-mini) — document-specific terms + search queries
3. Feedback mining from hybrid retrieval hits — terms from chunks keyword routing missed
4. Empty-extraction retry — LLM generates ad-hoc search queries for that type
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from django.conf import settings

from apps.intelligence.choices import ExtractionType, FOCUSED_EXTRACTION_TYPES, LearnedTermSource
from apps.intelligence.models import DocumentChunk
from apps.intelligence.services.learned_lexicon_store import (
    LearnedLexiconStore,
    LoadedLearnedLexicon,
    learned_lexicon_enabled,
    normalize_lexicon_term,
)
from apps.intelligence.prompts.templates import (
    ADAPTIVE_LEXICON_SYSTEM_PROMPT,
    ADAPTIVE_RETRY_QUERIES_SYSTEM_PROMPT,
    adaptive_lexicon_user_prompt,
    adaptive_retry_queries_user_prompt,
)
from apps.intelligence.services.model_routing import model_for_tier
from apps.intelligence.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    """
    a an the and or but if in on at to for of is are was were be been being
    by with from as this that these those it its they them their we you your
    shall will may must not all any each per via into out up down over under
    section page table contents herein thereof hereof hereby hereunder
    """.split()
)

_LABEL_PATTERN = re.compile(
    r"(?:^|\n)\s*([A-Za-z][A-Za-z0-9\s\/\-\(\)]{2,48}?)\s*:\s",
    re.MULTILINE,
)
_ID_PATTERN = re.compile(
    r"\b(?:IFB|RFP|RFQ|ITB|Bid|Project|Contract|Solicitation|Spec|Tender|Job|File)"
    r"\s*(?:No\.?|Number|#|:)\s*[\w\-\/\.]+",
    re.IGNORECASE,
)
_PROPER_PHRASE = re.compile(
    r"\b[A-Z][A-Za-z0-9\-]*(?:\s+(?:[A-Z][A-Za-z0-9\-]*|of|and|&|No\.)){0,5}\b"
)
_DATE_LIKE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)


def adaptive_lexicon_enabled() -> bool:
    return bool(getattr(settings, "INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED", True))


def adaptive_llm_enabled() -> bool:
    from apps.intelligence.services.fast_mode import fast_extraction_enabled

    if fast_extraction_enabled():
        return False
    return adaptive_lexicon_enabled() and bool(
        getattr(settings, "INTELLIGENCE_ADAPTIVE_LEXICON_LLM", True)
    )


def adaptive_retry_enabled() -> bool:
    from apps.intelligence.services.fast_mode import fast_extraction_enabled

    if fast_extraction_enabled():
        return False
    return adaptive_lexicon_enabled() and bool(
        getattr(settings, "INTELLIGENCE_ADAPTIVE_RETRY_ON_EMPTY", True)
    )


@dataclass
class DocumentAdaptiveLexicon:
    """Per-document vocabulary merged into keyword routing and hybrid queries."""

    terms_by_type: dict[str, list[str]] = field(default_factory=dict)
    queries_by_type: dict[str, list[str]] = field(default_factory=dict)
    global_terms: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def terms_for(self, extraction_type: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for term in self.global_terms + self.terms_by_type.get(extraction_type, []):
            key = term.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(term.strip())
        return out

    def queries_for(self, extraction_type: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for q in self.queries_by_type.get(extraction_type, []):
            key = q.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(q.strip())
        return out

    def add_terms(self, extraction_type: str, terms: list[str], *, source: str) -> None:
        if not terms:
            return
        bucket = self.terms_by_type.setdefault(extraction_type, [])
        existing = {t.lower() for t in bucket}
        for term in terms:
            cleaned = (term or "").strip()
            if len(cleaned) < 3 or cleaned.lower() in existing:
                continue
            bucket.append(cleaned)
            existing.add(cleaned.lower())
        if source not in self.sources:
            self.sources.append(source)

    def add_queries(self, extraction_type: str, queries: list[str], *, source: str) -> None:
        if not queries:
            return
        bucket = self.queries_by_type.setdefault(extraction_type, [])
        existing = {q.lower() for q in bucket}
        for query in queries:
            cleaned = (query or "").strip()
            if len(cleaned) < 8 or cleaned.lower() in existing:
                continue
            bucket.append(cleaned)
            existing.add(cleaned.lower())
        if source not in self.sources:
            self.sources.append(source)

    def add_global_terms(self, terms: list[str], *, source: str) -> None:
        existing = {t.lower() for t in self.global_terms}
        for term in terms:
            cleaned = (term or "").strip()
            if len(cleaned) < 3 or cleaned.lower() in existing:
                continue
            self.global_terms.append(cleaned)
            existing.add(cleaned.lower())
        if source not in self.sources:
            self.sources.append(source)

    def to_debug_dict(self) -> dict:
        return {
            "sources": self.sources,
            "global_term_count": len(self.global_terms),
            "terms_by_type": {k: v[:8] for k, v in self.terms_by_type.items()},
            "queries_by_type": {k: v[:4] for k, v in self.queries_by_type.items()},
        }


class AdaptiveLexiconService:
    @staticmethod
    def cover_sample_text(
        chunks: list[DocumentChunk],
        page_texts: list[tuple[int, str]],
        *,
        max_pages: int | None = None,
        max_chars: int = 12000,
    ) -> str:
        max_p = max_pages or getattr(settings, "INTELLIGENCE_COVER_PAGE_MAX_PAGES", 3)
        parts: list[str] = []
        if page_texts:
            for page_num, text in page_texts[:max_p]:
                if (text or "").strip():
                    parts.append(f"--- Page {page_num} ---\n{text.strip()}")
        if not parts and chunks:
            first = sorted(chunks, key=lambda c: c.chunk_order)[:5]
            for c in first:
                parts.append(
                    f"--- Pages {c.page_start}-{c.page_end} | {c.section_title} ---\n"
                    f"{c.chunk_text.strip()}"
                )
        combined = "\n\n".join(parts).strip()
        return combined[:max_chars]

    @staticmethod
    def mine_terms_from_text(text: str, *, limit: int = 40) -> list[str]:
        """Extract document-specific phrases without an LLM."""
        if not text:
            return []

        found: list[str] = []
        seen: set[str] = set()

        def _add(raw: str) -> None:
            cleaned = re.sub(r"\s+", " ", (raw or "").strip())
            if len(cleaned) < 3 or len(cleaned) > 80:
                return
            key = cleaned.lower()
            if key in seen or key in _STOPWORDS:
                return
            if sum(1 for w in key.split() if w in _STOPWORDS) >= len(key.split()) - 1:
                return
            seen.add(key)
            found.append(cleaned)

        for match in _ID_PATTERN.finditer(text):
            _add(match.group())

        for match in _DATE_LIKE.finditer(text):
            _add(match.group())

        for match in _LABEL_PATTERN.finditer(text):
            _add(match.group(1))

        for match in _PROPER_PHRASE.finditer(text):
            phrase = match.group().strip()
            if len(phrase.split()) >= 2:
                _add(phrase)

        return found[:limit]

    @staticmethod
    def _assign_heuristic_terms_to_types(terms: list[str]) -> dict[str, list[str]]:
        """Route mined terms to extraction types using loose semantic hooks."""
        hooks: dict[str, tuple[str, ...]] = {
            ExtractionType.ELIGIBILITY_CRITERIA: (
                "owner", "engineer", "architect", "solicitation", "bid no", "project no",
                "ifb", "rfp", "contractor", "bidder", "qualif",
            ),
            ExtractionType.SUBMISSION_DEADLINES: (
                "deadline", "due", "closing", "conference", "meeting", "opening", "date",
                "pre-bid", "prebid", "walkthrough", "municipal", "council",
            ),
            ExtractionType.TECHNICAL_REQUIREMENTS: (
                "square", "sq ft", "location", "address", "site", "completion", "duration",
                "start", "area", "campus",
            ),
            ExtractionType.SCOPE_OF_WORK: (
                "scope", "description", "work", "project", "improvement", "construction",
                "services", "overview",
            ),
            ExtractionType.PAYMENT_TERMS: (
                "value", "budget", "cost", "amount", "price", "payment", "$", "estimate",
            ),
            ExtractionType.PENALTIES_AND_RISKS: (
                "bond", "surety", "penalty", "security", "guarantee", "check", "forfeit",
            ),
            ExtractionType.MANDATORY_DOCUMENTS: (
                "form", "obtain", "download", "submit", "proposal", "document", "annex",
                "appendix", "instructions",
            ),
            ExtractionType.SET_ASIDES: (
                "mbe", "wbe", "dbe", "dvbe", "hub", "sbe", "minority", "women", "disadvantaged",
                "small business", "set-aside", "set aside", "diversity", "participation goal",
            ),
        }
        active_types = set(FOCUSED_EXTRACTION_TYPES)
        routed: dict[str, list[str]] = {t: [] for t in FOCUSED_EXTRACTION_TYPES}
        for term in terms:
            lower = term.lower()
            matched = False
            for etype, keys in hooks.items():
                if etype not in active_types:
                    continue
                if any(k in lower for k in keys):
                    routed[etype].append(term)
                    matched = True
            if not matched:
                for etype in FOCUSED_EXTRACTION_TYPES:
                    routed[etype].append(term)
        return routed

    @staticmethod
    def build(
        chunks: list[DocumentChunk],
        page_texts: list[tuple[int, str]],
    ) -> DocumentAdaptiveLexicon:
        lexicon = DocumentAdaptiveLexicon()
        if not adaptive_lexicon_enabled():
            return lexicon

        cover = AdaptiveLexiconService.cover_sample_text(chunks, page_texts)
        if not cover:
            return lexicon

        loaded = LearnedLexiconStore.load_for_types(list(FOCUSED_EXTRACTION_TYPES))
        for etype, terms in loaded.terms_by_type.items():
            lexicon.add_terms(etype, terms, source="learned_cache")
        for etype, queries in loaded.queries_by_type.items():
            lexicon.add_queries(etype, queries, source="learned_cache")
        if loaded.total_terms or loaded.total_queries:
            lexicon.sources.insert(0, "learned_cache")

        heuristic = AdaptiveLexiconService.mine_terms_from_text(cover)
        lexicon.add_global_terms(heuristic, source="heuristic_global")
        routed = AdaptiveLexiconService._assign_heuristic_terms_to_types(heuristic)
        for etype, terms in routed.items():
            lexicon.add_terms(etype, terms, source="heuristic_routed")
            LearnedLexiconStore.record_terms(
                etype,
                terms,
                LearnedTermSource.HEURISTIC,
                known_normalized=set(loaded.normalized_terms),
            )

        if adaptive_llm_enabled():
            if LearnedLexiconStore.should_skip_llm_lexicon(cover, loaded):
                logger.info("adaptive_lexicon_llm_skipped reason=learned_cache_sufficient")
                lexicon.sources.append("llm_skipped_cache")
            else:
                AdaptiveLexiconService._merge_llm_lexicon(lexicon, cover, loaded)

        logger.info(
            "adaptive_lexicon_built global_terms=%s typed_types=%s sources=%s learned_terms=%s",
            len(lexicon.global_terms),
            sum(1 for v in lexicon.terms_by_type.values() if v),
            lexicon.sources,
            loaded.total_terms,
        )
        return lexicon

    @staticmethod
    def _merge_llm_lexicon(
        lexicon: DocumentAdaptiveLexicon,
        cover_text: str,
        loaded: LoadedLearnedLexicon,
    ) -> None:
        try:
            client = OpenAIService()
            data, usage = client.chat_json(
                system=ADAPTIVE_LEXICON_SYSTEM_PROMPT,
                user=adaptive_lexicon_user_prompt(cover_text),
                model=model_for_tier("fast"),
            )
        except Exception as exc:
            logger.warning("adaptive_lexicon_llm_failed error=%s", exc)
            return

        types_payload = data.get("types") or {}
        if not isinstance(types_payload, dict):
            return

        known_terms = set(loaded.normalized_terms)
        known_queries = set(loaded.normalized_queries)
        new_term_count = 0
        skipped_term_count = 0

        for etype, payload in types_payload.items():
            if etype not in FOCUSED_EXTRACTION_TYPES or not isinstance(payload, dict):
                continue
            raw_terms = payload.get("terms") or []
            raw_queries = payload.get("search_queries") or payload.get("queries") or []

            novel_terms: list[str] = []
            if isinstance(raw_terms, list):
                for t in raw_terms:
                    display = str(t).strip()
                    if len(display) < 3:
                        continue
                    if normalize_lexicon_term(display) in known_terms:
                        skipped_term_count += 1
                        continue
                    novel_terms.append(display)

            novel_queries: list[str] = []
            if isinstance(raw_queries, list):
                for q in raw_queries:
                    display = str(q).strip()
                    if len(display) < 8:
                        continue
                    if normalize_lexicon_term(display) in known_queries:
                        continue
                    novel_queries.append(display)

            if novel_terms:
                lexicon.add_terms(etype, novel_terms, source="llm")
                _, created = LearnedLexiconStore.record_terms(
                    etype,
                    novel_terms,
                    LearnedTermSource.LLM,
                    known_normalized=known_terms,
                )
                new_term_count += created
            if novel_queries:
                lexicon.add_queries(etype, novel_queries, source="llm")
                LearnedLexiconStore.record_queries(
                    etype,
                    novel_queries,
                    LearnedTermSource.LLM,
                    known_normalized=known_queries,
                )

        logger.info(
            "adaptive_lexicon_llm merged types=%s tokens=%s new_terms=%s skipped_known=%s",
            len(types_payload),
            usage.get("total_tokens", 0),
            new_term_count,
            skipped_term_count,
        )

    @staticmethod
    def enrich_from_hybrid_feedback(
        lexicon: DocumentAdaptiveLexicon,
        chunks: list[DocumentChunk],
        hybrid_scores: dict[str, dict[str, float]],
        *,
        score_threshold: float | None = None,
    ) -> None:
        """
        Mine terms from high-scoring hybrid hits — captures novel document wording
        that static keywords missed.
        """
        if not adaptive_lexicon_enabled():
            return

        threshold = score_threshold
        if threshold is None:
            threshold = getattr(settings, "INTELLIGENCE_ADAPTIVE_FEEDBACK_MIN_SCORE", 0.22)

        chunks_by_id = {str(c.id): c for c in chunks}
        for etype, scores in hybrid_scores.items():
            top_ids = sorted(scores.keys(), key=lambda cid: -scores[cid])[:6]
            for cid in top_ids:
                if scores[cid] < threshold:
                    continue
                chunk = chunks_by_id.get(cid)
                if not chunk:
                    continue
                mined = AdaptiveLexiconService.mine_terms_from_text(
                    f"{chunk.section_title}\n{chunk.chunk_text}",
                    limit=12,
                )
                lexicon.add_terms(etype, mined, source="hybrid_feedback")
                if learned_lexicon_enabled():
                    LearnedLexiconStore.record_terms(
                        etype,
                        mined,
                        LearnedTermSource.HYBRID_FEEDBACK,
                    )

    @staticmethod
    def expand_for_empty_type(
        lexicon: DocumentAdaptiveLexicon,
        extraction_type: str,
        cover_text: str,
    ) -> list[str]:
        """Generate ad-hoc hybrid search queries when an extraction pass returned nothing."""
        if not adaptive_retry_enabled() or not cover_text:
            return []

        try:
            client = OpenAIService()
            data, _usage = client.chat_json(
                system=ADAPTIVE_RETRY_QUERIES_SYSTEM_PROMPT,
                user=adaptive_retry_queries_user_prompt(extraction_type, cover_text),
                model=model_for_tier("fast"),
            )
        except Exception as exc:
            logger.warning(
                "adaptive_retry_queries_failed type=%s error=%s",
                extraction_type,
                exc,
            )
            return []

        queries = data.get("search_queries") or data.get("queries") or []
        if not isinstance(queries, list):
            return []

        cleaned = [str(q).strip() for q in queries if str(q).strip()]
        lexicon.add_queries(extraction_type, cleaned, source="empty_retry")
        if learned_lexicon_enabled():
            LearnedLexiconStore.record_queries(
                extraction_type,
                cleaned,
                LearnedTermSource.EMPTY_RETRY,
            )
        return cleaned
