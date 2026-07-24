from django.test import SimpleTestCase, override_settings

from apps.intelligence.choices import ExtractionType
from apps.intelligence.services.model_routing import (
    EXTRACTION_MODEL_TIER,
    chat_model,
    extraction_escalation_model,
    extraction_model,
    model_for_tier,
    should_escalate_extraction,
)


class ModelRoutingTests(SimpleTestCase):
    @override_settings(
        AI_PROVIDER="azure",
        OPENAI_MODEL="gpt-4o",
        OPENAI_MODEL_FAST="gpt-4o-mini",
        AZURE_OPENAI_CHAT_DEPLOYMENT="",
        AZURE_OPENAI_CHAT_DEPLOYMENT_FAST="",
    )
    def test_tiers_resolve_to_openai_model_names_when_azure_deployments_unset(self):
        self.assertEqual(model_for_tier("fast"), "gpt-4o-mini")
        self.assertEqual(model_for_tier("strong"), "gpt-4o")

    @override_settings(
        AI_PROVIDER="azure",
        OPENAI_MODEL="gpt-4o",
        OPENAI_MODEL_FAST="gpt-4o-mini",
        AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4o",
        AZURE_OPENAI_CHAT_DEPLOYMENT_FAST="gpt-4o-mini",
    )
    def test_tiers_prefer_explicit_azure_deployments(self):
        self.assertEqual(model_for_tier("fast"), "gpt-4o-mini")
        self.assertEqual(model_for_tier("strong"), "gpt-4o")

    @override_settings(
        INTELLIGENCE_MODEL_ROUTING_ENABLED=True,
        FINETUNE_ENABLED=False,
        OPENAI_MODEL="gpt-4o",
        OPENAI_MODEL_FAST="gpt-4o-mini",
        AZURE_OPENAI_CHAT_DEPLOYMENT="",
        AZURE_OPENAI_CHAT_DEPLOYMENT_FAST="",
    )
    def test_extraction_type_tier_mapping(self):
        # SCOPE_OF_WORK is deliberately routed to the strong tier (scattered
        # prose needs the stronger model); TECHNICAL_REQUIREMENTS stays fast.
        self.assertEqual(
            extraction_model(ExtractionType.SCOPE_OF_WORK),
            "gpt-4o",
        )
        self.assertEqual(
            extraction_model(ExtractionType.TECHNICAL_REQUIREMENTS),
            "gpt-4o-mini",
        )
        self.assertEqual(
            extraction_model(ExtractionType.SUBMISSION_DEADLINES),
            "gpt-4o",
        )

    @override_settings(
        INTELLIGENCE_MODEL_ROUTING_ENABLED=False,
        OPENAI_MODEL="gpt-4o",
        OPENAI_MODEL_FAST="gpt-4o-mini",
    )
    def test_routing_disabled_uses_strong_for_all_types(self):
        self.assertEqual(
            extraction_model(ExtractionType.SCOPE_OF_WORK),
            "gpt-4o",
        )

    @override_settings(
        INTELLIGENCE_MODEL_ESCALATION_ENABLED=True,
        INTELLIGENCE_MODEL_ROUTING_ENABLED=True,
        INTELLIGENCE_FAST_MODE=False,  # fast mode short-circuits escalation
        FINETUNE_ENABLED=False,
        OPENAI_MODEL="gpt-4o",
        OPENAI_MODEL_FAST="gpt-4o-mini",
        AZURE_OPENAI_CHAT_DEPLOYMENT="",
        AZURE_OPENAI_CHAT_DEPLOYMENT_FAST="",
    )
    def test_escalation_only_when_fast_tier_returns_empty(self):
        # TECHNICAL_REQUIREMENTS is a fast-tier type (escalation applies);
        # strong-tier types can't escalate (already on the strong model).
        self.assertTrue(
            should_escalate_extraction(
                ExtractionType.TECHNICAL_REQUIREMENTS,
                items=[],
                started_with_fast=True,
            )
        )
        self.assertFalse(
            should_escalate_extraction(
                ExtractionType.TECHNICAL_REQUIREMENTS,
                items=[{"requirement": "x"}],
                started_with_fast=True,
            )
        )
        self.assertFalse(
            should_escalate_extraction(
                ExtractionType.SUBMISSION_DEADLINES,
                items=[],
                started_with_fast=False,
            )
        )

    @override_settings(
        INTELLIGENCE_MODEL_ESCALATION_ENABLED=False,
        INTELLIGENCE_MODEL_ROUTING_ENABLED=True,
    )
    def test_escalation_disabled(self):
        self.assertFalse(
            should_escalate_extraction(
                ExtractionType.SCOPE_OF_WORK,
                items=[],
                started_with_fast=True,
            )
        )

    @override_settings(
        CHAT_OPENAI_MODEL="",
        OPENAI_MODEL="gpt-4o",
    )
    def test_chat_defaults_to_strong_tier(self):
        self.assertEqual(chat_model(), "gpt-4o")

    def test_all_focused_types_have_tier(self):
        from apps.intelligence.choices import FOCUSED_EXTRACTION_TYPES

        for etype in FOCUSED_EXTRACTION_TYPES:
            self.assertIn(etype, EXTRACTION_MODEL_TIER)
