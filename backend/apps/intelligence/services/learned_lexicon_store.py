"""Persistent cross-document learned vocabulary (Layer 1 cache for adaptive extraction)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import Count, F
from django.utils import timezone

from apps.intelligence.choices import FOCUSED_EXTRACTION_TYPES, LearnedEntryKind, LearnedTermSource
from apps.intelligence.models import LearnedExtractionTerm

logger = logging.getLogger(__name__)


def learned_lexicon_enabled() -> bool:
    return bool(getattr(settings, "INTELLIGENCE_LEARNED_LEXICON_ENABLED", True))


def normalize_lexicon_term(term: str) -> str:
    return re.sub(r"\s+", " ", (term or "").strip().lower())


@dataclass
class LoadedLearnedLexicon:
    terms_by_type: dict[str, list[str]] = field(default_factory=dict)
    queries_by_type: dict[str, list[str]] = field(default_factory=dict)
    normalized_terms: set[str] = field(default_factory=set)
    normalized_queries: set[str] = field(default_factory=set)
    total_terms: int = 0
    total_queries: int = 0


class LearnedLexiconStore:
    @staticmethod
    def load_for_types(
        extraction_types: list[str] | None = None,
        *,
        max_per_type: int | None = None,
    ) -> LoadedLearnedLexicon:
        """Load active learned terms/queries from DB, ranked by hit_count."""
        if not learned_lexicon_enabled():
            return LoadedLearnedLexicon()

        types = extraction_types or list(FOCUSED_EXTRACTION_TYPES)
        limit = max_per_type or getattr(settings, "INTELLIGENCE_LEARNED_LEXICON_MAX_PER_TYPE", 60)
        loaded = LoadedLearnedLexicon()

        rows = (
            LearnedExtractionTerm.objects.filter(
                extraction_type__in=types,
                is_active=True,
            )
            .order_by("extraction_type", "entry_kind", "-hit_count", "term_display")
        )

        counts: dict[tuple[str, str], int] = {}
        for row in rows:
            key = (row.extraction_type, row.entry_kind)
            if counts.get(key, 0) >= limit:
                continue
            counts[key] = counts.get(key, 0) + 1

            if row.entry_kind == LearnedEntryKind.QUERY:
                bucket = loaded.queries_by_type.setdefault(row.extraction_type, [])
                bucket.append(row.term_display)
                loaded.normalized_queries.add(row.term_normalized)
                loaded.total_queries += 1
            else:
                bucket = loaded.terms_by_type.setdefault(row.extraction_type, [])
                bucket.append(row.term_display)
                loaded.normalized_terms.add(row.term_normalized)
                loaded.total_terms += 1

        return loaded

    @staticmethod
    def cache_sufficient(
        extraction_types: list[str],
        min_per_type: int | None = None,
    ) -> bool:
        """True when every type has at least min_per_type learned search terms."""
        if not learned_lexicon_enabled():
            return False

        minimum = min_per_type or getattr(
            settings, "INTELLIGENCE_LEARNED_LEXICON_MIN_TERMS_PER_TYPE", 8
        )
        counts = (
            LearnedExtractionTerm.objects.filter(
                extraction_type__in=extraction_types,
                entry_kind=LearnedEntryKind.TERM,
                is_active=True,
            )
            .values("extraction_type")
            .annotate(c=Count("id"))
        )
        by_type = {row["extraction_type"]: row["c"] for row in counts}
        return all(by_type.get(etype, 0) >= minimum for etype in extraction_types)

    @staticmethod
    def cover_has_novel_terms(cover_text: str, known_normalized: set[str]) -> bool:
        """True when cover text contains terms not yet in the learned cache."""
        from apps.intelligence.services.adaptive_lexicon_service import AdaptiveLexiconService

        if not cover_text.strip():
            return False
        mined = AdaptiveLexiconService.mine_terms_from_text(cover_text, limit=30)
        for term in mined:
            if normalize_lexicon_term(term) not in known_normalized:
                return True
        return False

    @staticmethod
    def should_skip_llm_lexicon(cover_text: str, loaded: LoadedLearnedLexicon) -> bool:
        """
        Skip Layer 2 LLM when cache is mature AND cover introduces no new vocabulary.
        """
        if not getattr(settings, "INTELLIGENCE_ADAPTIVE_LLM_SKIP_IF_CACHE_FULL", True):
            return False
        if not learned_lexicon_enabled():
            return False
        if not LearnedLexiconStore.cache_sufficient(list(FOCUSED_EXTRACTION_TYPES)):
            return False
        if LearnedLexiconStore.cover_has_novel_terms(cover_text, loaded.normalized_terms):
            return False
        return True

    @staticmethod
    def record_terms(
        extraction_type: str,
        terms: list[str],
        source: str,
        *,
        known_normalized: set[str] | None = None,
    ) -> tuple[list[str], int]:
        """
        Upsert terms; return (new_terms_for_caller, newly_created_count).
        Skips terms already in known_normalized without DB write.
        """
        if not learned_lexicon_enabled() or not terms:
            return [], 0

        known = known_normalized or set()
        new_for_caller: list[str] = []
        created_count = 0
        now = timezone.now()

        for raw in terms:
            display = (raw or "").strip()
            if len(display) < 3:
                continue
            norm = normalize_lexicon_term(display)
            if not norm or norm in known:
                continue

            obj, created = LearnedExtractionTerm.objects.get_or_create(
                extraction_type=extraction_type,
                entry_kind=LearnedEntryKind.TERM,
                term_normalized=norm,
                defaults={
                    "term_display": display[:512],
                    "source": source,
                    "hit_count": 1,
                    "document_count": 1,
                    "last_seen_at": now,
                },
            )
            if created:
                created_count += 1
                new_for_caller.append(display)
                known.add(norm)
            else:
                LearnedExtractionTerm.objects.filter(pk=obj.pk).update(
                    hit_count=F("hit_count") + 1,
                    last_seen_at=now,
                    term_display=display[:512],
                )
                known.add(norm)

        return new_for_caller, created_count

    @staticmethod
    def record_queries(
        extraction_type: str,
        queries: list[str],
        source: str,
        *,
        known_normalized: set[str] | None = None,
    ) -> tuple[list[str], int]:
        if not learned_lexicon_enabled() or not queries:
            return [], 0

        known = known_normalized or set()
        new_for_caller: list[str] = []
        created_count = 0
        now = timezone.now()

        for raw in queries:
            display = (raw or "").strip()
            if len(display) < 8:
                continue
            norm = normalize_lexicon_term(display)
            if not norm or norm in known:
                continue

            obj, created = LearnedExtractionTerm.objects.get_or_create(
                extraction_type=extraction_type,
                entry_kind=LearnedEntryKind.QUERY,
                term_normalized=norm,
                defaults={
                    "term_display": display[:512],
                    "source": source,
                    "hit_count": 1,
                    "document_count": 1,
                    "last_seen_at": now,
                },
            )
            if created:
                created_count += 1
                new_for_caller.append(display)
                known.add(norm)
            else:
                LearnedExtractionTerm.objects.filter(pk=obj.pk).update(
                    hit_count=F("hit_count") + 1,
                    last_seen_at=now,
                    term_display=display[:512],
                )
                known.add(norm)

        return new_for_caller, created_count

    @staticmethod
    def persist_lexicon_snapshot(lexicon) -> dict[str, int]:
        """Write any terms/queries from a document lexicon not yet in DB."""
        if not learned_lexicon_enabled():
            return {"terms_created": 0, "queries_created": 0}

        loaded = LearnedLexiconStore.load_for_types()
        terms_created = 0
        queries_created = 0

        for etype in FOCUSED_EXTRACTION_TYPES:
            for term in lexicon.terms_by_type.get(etype, []):
                _, created = LearnedLexiconStore.record_terms(
                    etype,
                    [term],
                    LearnedTermSource.HEURISTIC,
                    known_normalized=set(loaded.normalized_terms),
                )
                terms_created += created

            for query in lexicon.queries_by_type.get(etype, []):
                _, created = LearnedLexiconStore.record_queries(
                    etype,
                    [query],
                    LearnedTermSource.LLM,
                    known_normalized=set(loaded.normalized_queries),
                )
                queries_created += created

        if terms_created or queries_created:
            logger.info(
                "learned_lexicon_persisted terms_created=%s queries_created=%s",
                terms_created,
                queries_created,
            )
        return {"terms_created": terms_created, "queries_created": queries_created}
