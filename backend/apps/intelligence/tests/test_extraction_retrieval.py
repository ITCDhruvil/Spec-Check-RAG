"""Phase 4 hybrid extraction retrieval tests."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from apps.intelligence.choices import ExtractionType
from apps.intelligence.services.chunk_selection_fusion import (
    fuse_chunk_selections,
    reciprocal_rank_fusion,
)
from apps.intelligence.services.extraction_retrieval_service import (
    EXTRACTION_RETRIEVAL_QUERIES,
    ExtractionRetrievalService,
    hybrid_retrieval_enabled,
)


def _chunk(chunk_order: int, *, chunk_type: str = "general_section", text: str = ""):
    cid = uuid4()
    return type(
        "Chunk",
        (),
        {
            "id": cid,
            "chunk_order": chunk_order,
            "page_start": chunk_order,
            "page_end": chunk_order,
            "section_title": f"Section {chunk_order}",
            "chunk_text": text or f"content {chunk_order}",
            "metadata": {"chunk_type": chunk_type},
        },
    )()


class ReciprocalRankFusionTests(SimpleTestCase):
    def test_merged_ids_score_higher_when_in_both_lists(self):
        scores = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d"]])
        self.assertGreater(scores["b"], scores["a"])
        self.assertGreater(scores["b"], scores["d"])
        self.assertIn("c", scores)
        self.assertIn("d", scores)

    def test_weights_scale_hybrid_contribution(self):
        unweighted = reciprocal_rank_fusion([["a"], ["b"]])
        weighted = reciprocal_rank_fusion([["a"], ["b"]], weights=[1.0, 5.0])
        self.assertGreater(weighted["b"], unweighted["b"])


class FuseChunkSelectionTests(SimpleTestCase):
    def test_hybrid_surfaces_chunks_keyword_missed(self):
        chunks = [_chunk(i, text=f"chunk {i}") for i in range(1, 6)]
        keyword_selected = chunks[:2]
        hybrid_scores = {str(chunks[4].id): 0.92, str(chunks[3].id): 0.81}

        fused = fuse_chunk_selections(
            keyword_selected=keyword_selected,
            hybrid_scores=hybrid_scores,
            all_chunks=chunks,
            max_chunks=4,
        )
        fused_ids = {str(c.id) for c in fused}
        self.assertIn(str(chunks[4].id), fused_ids)
        self.assertLessEqual(len(fused), 4)

    def test_empty_hybrid_returns_keyword_selection(self):
        chunks = [_chunk(i) for i in range(3)]
        keyword_selected = chunks[:2]
        fused = fuse_chunk_selections(
            keyword_selected=keyword_selected,
            hybrid_scores={},
            all_chunks=chunks,
            max_chunks=2,
        )
        self.assertEqual([c.id for c in fused], [c.id for c in keyword_selected])


class ExtractionRetrievalServiceTests(SimpleTestCase):
    def test_all_focused_types_have_queries(self):
        from apps.intelligence.choices import FOCUSED_EXTRACTION_TYPES

        for etype in FOCUSED_EXTRACTION_TYPES:
            self.assertTrue(ExtractionRetrievalService.queries_for_type(etype))

    @override_settings(INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED=False)
    def test_scores_for_types_disabled_returns_empty(self):
        result = ExtractionRetrievalService.scores_for_types("doc-1", [ExtractionType.SCOPE_OF_WORK])
        self.assertEqual(result, {})

    @override_settings(INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED=True)
    @patch("apps.intelligence.services.extraction_retrieval_service.VectorIndexService.is_indexed")
    def test_scores_for_types_not_indexed_returns_empty(self, mock_indexed):
        mock_indexed.return_value = False
        result = ExtractionRetrievalService.scores_for_types("doc-1", [ExtractionType.SCOPE_OF_WORK])
        self.assertEqual(result, {})

    @override_settings(
        INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED=True,
        INTELLIGENCE_EXTRACTION_RETRIEVAL_TOP_K=5,
        INTELLIGENCE_EXTRACTION_MIN_RETRIEVAL_SCORE=0.1,
    )
    @patch("apps.intelligence.services.extraction_retrieval_service.get_vector_store")
    @patch("apps.intelligence.services.extraction_retrieval_service.OpenAIService")
    @patch("apps.intelligence.services.extraction_retrieval_service.VectorIndexService.is_indexed")
    def test_scores_for_types_merges_query_hits(self, mock_indexed, mock_openai_cls, mock_store_fn):
        mock_indexed.return_value = True
        chunk_a, chunk_b = str(uuid4()), str(uuid4())

        mock_openai = MagicMock()
        mock_openai.embed_texts.return_value = ([[0.1] * 8, [0.2] * 8], {"total_tokens": 10})
        mock_openai_cls.return_value = mock_openai

        store = MagicMock()
        store.backend_name.return_value = "chroma"
        store.query.side_effect = [
            {
                "ids": [[chunk_a]],
                "documents": [["bid bond 5 percent"]],
                "metadatas": [[{"page_start": 1, "page_end": 1, "section_title": "Bonds", "chunk_order": 3}]],
                "distances": [[0.2]],
                "scores": [[0.8]],
            },
            {
                "ids": [[chunk_b]],
                "documents": [["performance bond 100 percent"]],
                "metadatas": [[{"page_start": 2, "page_end": 2, "section_title": "Bonds", "chunk_order": 4}]],
                "distances": [[0.3]],
                "scores": [[0.7]],
            },
        ]
        mock_store_fn.return_value = store

        etype = ExtractionType.PENALTIES_AND_RISKS
        queries = EXTRACTION_RETRIEVAL_QUERIES[etype]
        result = ExtractionRetrievalService.scores_for_types("doc-1", [etype])

        self.assertEqual(mock_openai.embed_texts.call_count, 1)
        self.assertEqual(len(mock_openai.embed_texts.call_args[0][0]), len(queries))
        self.assertIn(chunk_a, result[etype])
        self.assertIn(chunk_b, result[etype])


class SelectChunksHybridIntegrationTests(SimpleTestCase):
    @override_settings(INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED=True)
    def test_select_chunks_uses_hybrid_scores(self):
        from apps.intelligence.services.extraction_service import ExtractionService

        chunks = [
            _chunk(1, text="general intro"),
            _chunk(2, text="scope overview project description"),
            _chunk(3, text="unrelated appendix forms"),
            _chunk(4, text="zoning variance administrative note only"),
        ]
        keyword = ExtractionService.select_chunks(
            chunks, ExtractionType.SCOPE_OF_WORK, keyword_only=True
        )
        hybrid = ExtractionService.select_chunks(
            chunks,
            ExtractionType.SCOPE_OF_WORK,
            hybrid_scores={str(chunks[3].id): 0.95},
        )
        keyword_ids = {str(c.id) for c in keyword}
        hybrid_ids = {str(c.id) for c in hybrid}
        self.assertIn(str(chunks[3].id), hybrid_ids)
