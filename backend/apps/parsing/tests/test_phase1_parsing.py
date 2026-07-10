"""Phase 1 parsing tests: section hierarchy, layout blocks, PDF router."""

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.parsing.parsers.base import ParsedPageResult, ParsedSectionResult
from apps.parsing.parsers.pdf_router import parse_pdf
from apps.parsing.services.layout_blocks import layout_blocks_from_pages, polygon_to_bbox
from apps.parsing.services.section_hierarchy import (
    assign_section_hierarchy,
    infer_section_level,
    sections_to_nested_json,
)


class SectionHierarchyTests(SimpleTestCase):
    def test_infer_level_from_numbered_prefix(self):
        self.assertEqual(infer_section_level("1 Introduction"), 1)
        self.assertEqual(infer_section_level("2.1 Technical Requirements"), 2)
        self.assertEqual(infer_section_level("1.5.2 Bond Forms"), 3)

    def test_assign_parent_and_path(self):
        sections = [
            ParsedSectionResult("1 Instructions", "a", 1, 2, 0),
            ParsedSectionResult("1.1 Submission", "b", 2, 3, 1),
            ParsedSectionResult("2 Evaluation", "c", 4, 5, 2),
        ]
        assign_section_hierarchy(sections)
        self.assertEqual(sections[0].level, 1)
        self.assertEqual(sections[0].parent_section_order, None)
        self.assertEqual(sections[1].level, 2)
        self.assertEqual(sections[1].parent_section_order, 0)
        self.assertEqual(sections[1].section_path, "1 Instructions > 1.1 Submission")
        self.assertEqual(sections[2].parent_section_order, None)

    def test_nested_json_tree(self):
        sections = [
            ParsedSectionResult("1 Scope", "x", 1, 1, 0, level=1),
            ParsedSectionResult("1.1 Work", "y", 1, 1, 1, level=2, parent_section_order=0),
        ]
        tree = sections_to_nested_json(sections)
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["title"], "1 Scope")
        self.assertEqual(len(tree[0]["children"]), 1)
        self.assertEqual(tree[0]["children"][0]["title"], "1.1 Work")


class LayoutBlockTests(SimpleTestCase):
    def test_polygon_to_bbox(self):
        bbox = polygon_to_bbox([0, 0, 10, 0, 10, 5, 0, 5])
        self.assertEqual(bbox, [0.0, 0.0, 10.0, 5.0])

    def test_layout_blocks_from_pages_detects_heading(self):
        pages = [
            ParsedPageResult(
                page_number=1,
                extracted_text="SCOPE OF WORK\n\nDeliverables include ...",
                extraction_method="native_pdf",
                ocr_used=False,
                quality_score=0.9,
            )
        ]
        blocks = layout_blocks_from_pages(pages)
        types = [b.block_type for b in blocks]
        self.assertIn("heading", types)
        self.assertIn("paragraph", types)


def _smallest_sample_pdf() -> Path | None:
    sample_dir = Path(__file__).resolve().parents[4] / "sample-docs"
    pdfs = sorted(sample_dir.glob("*.pdf"), key=lambda p: p.stat().st_size)
    return pdfs[0] if pdfs else None


class PdfRouterTests(SimpleTestCase):
    @override_settings(
        PARSING_PDF_PARSER="auto",
        AZURE_DI_ENDPOINT="",
        AZURE_DI_KEY="",
        PARSING_OCR_ENABLED=False,
    )
    def test_auto_falls_back_to_pymupdf_without_azure(self):
        pdf = _smallest_sample_pdf()
        if pdf is None:
            self.skipTest("No sample PDFs available")
        result = parse_pdf(pdf)
        self.assertEqual(result.file_type, "pdf")
        self.assertIn(result.parsing_metadata.get("parser"), ("pymupdf",))
        self.assertGreater(result.parsing_metadata.get("layout_blocks_count", 0), 0)
        self.assertTrue(result.parsing_metadata.get("section_hierarchy"))

    @override_settings(PARSING_PDF_PARSER="pymupdf", PARSING_OCR_ENABLED=False)
    def test_pymupdf_strategy(self):
        pdf = _smallest_sample_pdf()
        if pdf is None:
            self.skipTest("No sample PDFs available")
        result = parse_pdf(pdf)
        self.assertEqual(result.parsing_metadata.get("parser"), "pymupdf")

    @override_settings(
        PARSING_PDF_PARSER="auto",
        AZURE_DI_ENDPOINT="https://example.cognitiveservices.azure.com/",
        AZURE_DI_KEY="test-key",
        PARSING_OCR_ENABLED=False,
    )
    @patch("apps.parsing.parsers.pdf_router.parse_pdf_azure_di")
    @patch("apps.parsing.parsers.pdf_router.is_azure_di_configured", return_value=True)
    def test_auto_uses_azure_when_configured(self, _mock_configured, mock_azure):
        from apps.parsing.parsers.base import DocumentParseResult

        mock_azure.return_value = DocumentParseResult(
            pages=[],
            sections=[],
            tables=[],
            raw_text="",
            structured_text="",
            parsing_metadata={"parser": "azure_document_intelligence"},
            parsing_quality_score=1.0,
            file_type="pdf",
        )
        pdf = _smallest_sample_pdf()
        if pdf is None:
            self.skipTest("No sample PDFs available")
        result = parse_pdf(pdf)
        self.assertEqual(result.parsing_metadata.get("parser"), "azure_document_intelligence")
        mock_azure.assert_called_once()
