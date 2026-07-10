"""Tests for feedback-driven extraction hints."""

from django.test import TestCase

from apps.documents.models import Document
from apps.intelligence.choices import ExtractionType
from apps.intelligence.models import FieldFeedback
from apps.intelligence.services.extraction_feedback_hints import build_group_feedback_hints
from apps.intelligence.services.extraction_groups import GROUP_EXTRACTION_GROUPS


class ExtractionFeedbackHintsTests(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(
            original_filename="test.pdf",
            stored_filename="test.pdf",
            file_path="test/test.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
        )
        self.identity_group = next(
            g for g in GROUP_EXTRACTION_GROUPS if g.group_id == "project_identity"
        )

    def test_empty_when_no_feedback(self):
        self.assertEqual(build_group_feedback_hints(self.identity_group), "")

    def test_includes_wrong_value_correction(self):
        FieldFeedback.objects.create(
            document=self.doc,
            field_key="project_solicitation_number",
            extraction_type=ExtractionType.ELIGIBILITY_CRITERIA,
            rating="down",
            issue_type="wrong_value",
            extracted_value="HOMEWOOD SCHOOLS RENOVATIONS",
            correct_value="ABHM250064",
        )
        hints = build_group_feedback_hints(self.identity_group)
        self.assertIn("Lessons from prior user corrections", hints)
        self.assertIn("ABHM250064", hints)
        self.assertIn("HOMEWOOD SCHOOLS RENOVATIONS", hints)

    def test_includes_missing_field_hint(self):
        FieldFeedback.objects.create(
            document=self.doc,
            field_key="bid_deadline_date_time",
            extraction_type=ExtractionType.SUBMISSION_DEADLINES,
            rating="down",
            issue_type="missing",
        )
        dates_group = next(g for g in GROUP_EXTRACTION_GROUPS if g.group_id == "dates")
        hints = build_group_feedback_hints(dates_group)
        self.assertIn("bid_deadline_date_time", hints)
        self.assertIn("often missed", hints)

    def test_ignores_unrelated_field_feedback(self):
        FieldFeedback.objects.create(
            document=self.doc,
            field_key="bid_bond_information",
            extraction_type=ExtractionType.PENALTIES_AND_RISKS,
            rating="down",
            issue_type="wrong_value",
            extracted_value="wrong",
            correct_value="5% bid bond required",
        )
        self.assertEqual(build_group_feedback_hints(self.identity_group), "")
