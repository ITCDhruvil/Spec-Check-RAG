"""Adaptive lexicon tests."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from apps.intelligence.choices import ExtractionType
from apps.intelligence.services.adaptive_lexicon_service import (
    AdaptiveLexiconService,
    DocumentAdaptiveLexicon,
    adaptive_lexicon_enabled,
)


class HeuristicMiningTests(SimpleTestCase):
    def test_mines_bid_numbers_and_labels(self):
        text = """
        INVITATION TO BID
        Project No. 2024-001
        Bid No. IFB-65738
        Owner: City of Riverside
        Proposer's Conference: March 4, 2026 at 10:00 AM
        """
        terms = AdaptiveLexiconService.mine_terms_from_text(text)
        joined = " ".join(terms).lower()
        self.assertIn("65738", joined)
        self.assertTrue(any("ifb" in t.lower() or "2024" in t for t in terms))

    def test_assigns_terms_to_deadline_type(self):
        terms = ["Proposer's Conference", "Bid No. IFB-99"]
        routed = AdaptiveLexiconService._assign_heuristic_terms_to_types(terms)
        self.assertIn("Proposer's Conference", routed[ExtractionType.SUBMISSION_DEADLINES])


class DocumentAdaptiveLexiconTests(SimpleTestCase):
    def test_deduplicates_terms(self):
        lex = DocumentAdaptiveLexicon()
        lex.add_terms(ExtractionType.SCOPE_OF_WORK, ["Playground Improvements", "playground improvements"], source="test")
        self.assertEqual(len(lex.terms_for(ExtractionType.SCOPE_OF_WORK)), 1)

    def test_queries_for_merges_unique(self):
        lex = DocumentAdaptiveLexicon()
        lex.add_queries(ExtractionType.SCOPE_OF_WORK, ["scope query", "scope query"], source="test")
        self.assertEqual(len(lex.queries_for(ExtractionType.SCOPE_OF_WORK)), 1)


class AdaptiveLexiconBuildTests(SimpleTestCase):
    @override_settings(INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED=False)
    def test_build_disabled_returns_empty(self):
        lex = AdaptiveLexiconService.build([], [("1", "Bid No. 123")])
        self.assertEqual(lex.sources, [])

    @override_settings(
        INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED=True,
        INTELLIGENCE_ADAPTIVE_LEXICON_LLM=False,
        INTELLIGENCE_LEARNED_LEXICON_ENABLED=False,
    )
    def test_build_heuristic_only(self):
        lex = AdaptiveLexiconService.build(
            [],
            [("1", "Project: FORD PARK PLAYGROUND\nBid No. 2026-001\nOwner: City of Beaumont")],
        )
        self.assertIn("heuristic_global", lex.sources)
        self.assertTrue(lex.terms_for(ExtractionType.ELIGIBILITY_CRITERIA))

    @override_settings(
        INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED=True,
        INTELLIGENCE_ADAPTIVE_LEXICON_LLM=True,
        INTELLIGENCE_LEARNED_LEXICON_ENABLED=False,
    )
    @patch("apps.intelligence.services.adaptive_lexicon_service.OpenAIService")
    def test_build_merges_llm_terms(self, mock_openai_cls):
        mock_openai = MagicMock()
        mock_openai.chat_json.return_value = (
            {
                "types": {
                    ExtractionType.SUBMISSION_DEADLINES: {
                        "terms": ["Sealed Bids Due"],
                        "search_queries": ["When are sealed bids due for Ford Park?"],
                    }
                }
            },
            {"total_tokens": 50},
        )
        mock_openai_cls.return_value = mock_openai

        lex = AdaptiveLexiconService.build([], [("1", "Ford Park Playground bid notice")])
        self.assertIn("llm", lex.sources)
        self.assertIn("Sealed Bids Due", lex.terms_for(ExtractionType.SUBMISSION_DEADLINES))
        self.assertTrue(lex.queries_for(ExtractionType.SUBMISSION_DEADLINES))


class AdaptiveKeywordScoringTests(SimpleTestCase):
    @override_settings(INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED=True)
    def test_adaptive_terms_boost_keyword_selection(self):
        from apps.intelligence.services.extraction_service import ExtractionService

        def _make(order: int, text: str):
            return type(
                "Chunk",
                (),
                {
                    "id": uuid4(),
                    "chunk_order": order,
                    "page_start": order,
                    "page_end": order,
                    "section_title": f"Section {order}",
                    "chunk_text": text,
                    "metadata": {},
                },
            )()

        chunks = [_make(i, f"Generic boilerplate paragraph number {i}.") for i in range(12)]
        chunks[7] = _make(
            7,
            "Packages must comply with Circular Z-99 receipt window requirements.",
        )

        without = ExtractionService.select_chunks(
            chunks, ExtractionType.SUBMISSION_DEADLINES, keyword_only=True
        )
        with_adaptive = ExtractionService.select_chunks(
            chunks,
            ExtractionType.SUBMISSION_DEADLINES,
            adaptive_terms=["Circular Z-99"],
            keyword_only=True,
        )
        without_ids = {str(c.id) for c in without}
        adaptive_ids = {str(c.id) for c in with_adaptive}
        target_id = str(chunks[7].id)
        self.assertNotIn(target_id, without_ids)
        self.assertIn(target_id, adaptive_ids)


class ExtractionRetrievalAdaptiveQueryTests(SimpleTestCase):
    def test_queries_merge_static_and_lexicon(self):
        from apps.intelligence.services.extraction_retrieval_service import ExtractionRetrievalService

        lex = DocumentAdaptiveLexicon()
        lex.add_queries(
            ExtractionType.SUBMISSION_DEADLINES,
            ["Sealed bids due Ford Park playground"],
            source="test",
        )
        lex.add_terms(ExtractionType.SUBMISSION_DEADLINES, ["Sealed Bids Due"], source="test")

        queries = ExtractionRetrievalService.queries_for_type(
            ExtractionType.SUBMISSION_DEADLINES, lex
        )
        self.assertGreater(len(queries), 3)
        self.assertTrue(any("sealed bids due ford park" in q.lower() for q in queries))
