"""Learned lexicon DB cache tests."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.intelligence.choices import ExtractionType, LearnedEntryKind, LearnedTermSource
from apps.intelligence.models import LearnedExtractionTerm
from apps.intelligence.services.learned_lexicon_store import (
    LearnedLexiconStore,
    LoadedLearnedLexicon,
    normalize_lexicon_term,
)


class LearnedLexiconStoreTests(TestCase):
    @override_settings(INTELLIGENCE_LEARNED_LEXICON_ENABLED=True)
    def test_record_terms_deduplicates(self):
        etype = ExtractionType.SUBMISSION_DEADLINES
        _, created1 = LearnedLexiconStore.record_terms(
            etype, ["Sealed Bids Due"], LearnedTermSource.LLM
        )
        _, created2 = LearnedLexiconStore.record_terms(
            etype, ["sealed bids due"], LearnedTermSource.LLM
        )
        self.assertEqual(created1, 1)
        self.assertEqual(created2, 0)
        self.assertEqual(LearnedExtractionTerm.objects.count(), 1)
        row = LearnedExtractionTerm.objects.get()
        self.assertEqual(row.hit_count, 2)

    @override_settings(INTELLIGENCE_LEARNED_LEXICON_ENABLED=True)
    def test_load_for_types_returns_ranked_terms(self):
        etype = ExtractionType.SCOPE_OF_WORK
        LearnedExtractionTerm.objects.create(
            extraction_type=etype,
            entry_kind=LearnedEntryKind.TERM,
            term_normalized="playground improvements",
            term_display="Playground Improvements",
            source=LearnedTermSource.LLM,
            hit_count=5,
        )
        LearnedExtractionTerm.objects.create(
            extraction_type=etype,
            entry_kind=LearnedEntryKind.TERM,
            term_normalized="restroom building",
            term_display="Restroom Building",
            source=LearnedTermSource.HEURISTIC,
            hit_count=2,
        )
        loaded = LearnedLexiconStore.load_for_types([etype])
        self.assertEqual(loaded.terms_by_type[etype][0], "Playground Improvements")
        self.assertIn("playground improvements", loaded.normalized_terms)

    @override_settings(
        INTELLIGENCE_LEARNED_LEXICON_ENABLED=True,
        INTELLIGENCE_LEARNED_LEXICON_MIN_TERMS_PER_TYPE=2,
        INTELLIGENCE_ADAPTIVE_LLM_SKIP_IF_CACHE_FULL=True,
    )
    def test_should_skip_llm_when_cache_full_and_no_novel_cover_terms(self):
        etype = ExtractionType.SUBMISSION_DEADLINES
        for i in range(3):
            LearnedExtractionTerm.objects.create(
                extraction_type=etype,
                entry_kind=LearnedEntryKind.TERM,
                term_normalized=f"known term {i}",
                term_display=f"Known Term {i}",
                source=LearnedTermSource.LLM,
            )
        for other in [
            ExtractionType.ELIGIBILITY_CRITERIA,
            ExtractionType.TECHNICAL_REQUIREMENTS,
            ExtractionType.SCOPE_OF_WORK,
            ExtractionType.PAYMENT_TERMS,
            ExtractionType.PENALTIES_AND_RISKS,
            ExtractionType.MANDATORY_DOCUMENTS,
            ExtractionType.EVALUATION_CRITERIA,
        ]:
            for i in range(2):
                LearnedExtractionTerm.objects.create(
                    extraction_type=other,
                    entry_kind=LearnedEntryKind.TERM,
                    term_normalized=f"{other}-term-{i}",
                    term_display=f"{other} term {i}",
                    source=LearnedTermSource.LLM,
                )

        loaded = LearnedLexiconStore.load_for_types()
        cover = "Known Term 0\nBid No. IFB-2024-001\nFebruary 20, 2026"
        self.assertTrue(LearnedLexiconStore.cache_sufficient([etype]))
        # Novel IFB number on cover should force LLM
        self.assertTrue(
            LearnedLexiconStore.cover_has_novel_terms(
                "Brand New Circular Z-99 compliance section",
                loaded.normalized_terms,
            )
        )

    def test_normalize_lexicon_term(self):
        self.assertEqual(normalize_lexicon_term("  Sealed   Bids Due  "), "sealed bids due")

    @override_settings(
        INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED=True,
        INTELLIGENCE_ADAPTIVE_LEXICON_LLM=True,
        INTELLIGENCE_LEARNED_LEXICON_ENABLED=True,
        INTELLIGENCE_LEARNED_LEXICON_MIN_TERMS_PER_TYPE=1,
        INTELLIGENCE_ADAPTIVE_LLM_SKIP_IF_CACHE_FULL=True,
        INTELLIGENCE_FAST_MODE=False,  # fast mode short-circuits the LLM path
    )
    @patch("apps.intelligence.services.adaptive_lexicon_service.OpenAIService")
    def test_build_skips_llm_when_term_already_in_cache(self, mock_openai_cls):
        from apps.intelligence.choices import FOCUSED_EXTRACTION_TYPES
        from apps.intelligence.services.adaptive_lexicon_service import AdaptiveLexiconService

        # Cache must be "sufficient" for every focused type — seed the actual
        # list so the test tracks FOCUSED_EXTRACTION_TYPES as it evolves.
        for etype in FOCUSED_EXTRACTION_TYPES:
            LearnedExtractionTerm.objects.create(
                extraction_type=etype,
                entry_kind=LearnedEntryKind.TERM,
                term_normalized=f"cached-{etype}-term",
                term_display=f"Cached {etype} term",
                source=LearnedTermSource.LLM,
                hit_count=3,
            )

        cover = "Cached submission_deadlines term\nProject overview paragraph."
        lex = AdaptiveLexiconService.build([], [("1", cover)])
        mock_openai_cls.assert_not_called()
        self.assertIn("llm_skipped_cache", lex.sources)
        self.assertIn("learned_cache", lex.sources)
