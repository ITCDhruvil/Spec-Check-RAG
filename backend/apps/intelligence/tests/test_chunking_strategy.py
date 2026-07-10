"""Phase 2 chunking strategy tests."""

from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.intelligence.services.chunking_strategy import (
    ChunkDraft,
    consolidate_sections,
    dedupe_table_against_sections,
    split_with_overlap,
    _infer_chunk_type,
)


def _section(title, content, page_start=1, page_end=1, order=0):
    return SimpleNamespace(
        title=title,
        content=content,
        page_start=page_start,
        page_end=page_end,
        section_order=order,
        level=1,
        section_path=title,
        parent_section_order=None,
    )


class SplitWithOverlapTests(SimpleTestCase):
    @override_settings(INTELLIGENCE_LEAF_CHUNK_CHARS=200, INTELLIGENCE_CHUNK_OVERLAP_RATIO=0.10)
    def test_splits_long_text_with_overlap(self):
        para_a = "A" * 120
        para_b = "B" * 120
        para_c = "C" * 120
        text = f"{para_a}\n\n{para_b}\n\n{para_c}"
        parts = split_with_overlap(text)
        self.assertGreaterEqual(len(parts), 2)

    def test_preserves_clause_boundary_units(self):
        text = "1.1 Scope\n\nShort intro.\n\n2.1 Bonds\n\nBid bond required."
        parts = split_with_overlap(text, max_chars=500)
        joined = "\n".join(parts)
        self.assertIn("1.1 Scope", joined)
        self.assertIn("2.1 Bonds", joined)


class ConsolidateSectionsTests(SimpleTestCase):
    @override_settings(INTELLIGENCE_COVER_PAGE_MAX=2, INTELLIGENCE_MIN_SECTION_CHARS=40)
    def test_merges_cover_fragments(self):
        sections = [
            _section("CITY OF EXAMPLE", "", 1, 1, 0),
            _section("PROJECT TITLE", "Short title line", 1, 1, 1),
            _section("1 Instructions", "Long body " * 20, 3, 5, 2),
        ]
        logical = consolidate_sections(sections)
        self.assertEqual(len(logical), 2)
        self.assertEqual(logical[0].chunk_type, "cover_metadata")
        self.assertIn("Long body", logical[1].content)


class ChunkTypeTests(SimpleTestCase):
    def test_schedule_table_type(self):
        self.assertEqual(
            _infer_chunk_type("Schedule", "Bid Opening March 11, 2026"),
            "schedule_table",
        )

    def test_bond_type(self):
        self.assertEqual(
            _infer_chunk_type("Security", "Bid bond of 10% required"),
            "bond_clause",
        )


class DedupeTableTests(SimpleTestCase):
    def test_drops_redundant_schedule_table(self):
        table = ChunkDraft(
            "Table",
            "Bid Period | Feb 1 - Mar 1\nBid Opening | Mar 11",
            2,
            2,
            metadata={"chunk_type": "schedule_table"},
        )
        section = ChunkDraft(
            "Bid Schedule",
            "Bid Period | Feb 1 - Mar 1\nBid Opening | Mar 11",
            2,
            2,
            metadata={"chunk_type": "schedule_table"},
        )
        kept = dedupe_table_against_sections([table], [section])
        self.assertEqual(len(kept), 0)
