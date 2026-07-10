"""
Dynamic LLM model routing for extraction and chat.

Tiers map to Azure deployment names (gpt-4o-mini vs gpt-4o).
"""

from __future__ import annotations

from django.conf import settings

from apps.intelligence.choices import ExtractionType

ModelTier = str  # "fast" | "strong"


def _resolve_deployment(explicit: str, fallback: str) -> str:
    value = (explicit or "").strip()
    if value and value not in {"your-gpt-deployment-name", "your-embedding-deployment-name"}:
        return value
    return fallback


def model_for_tier(tier: ModelTier) -> str:
    """Resolve Azure/OpenAI deployment name for a tier."""
    if tier == "fast":
        return _resolve_deployment(
            getattr(settings, "AZURE_OPENAI_CHAT_DEPLOYMENT_FAST", ""),
            getattr(settings, "OPENAI_MODEL_FAST", "gpt-4o-mini"),
        )
    return _resolve_deployment(
        getattr(settings, "AZURE_OPENAI_CHAT_DEPLOYMENT", ""),
        settings.OPENAI_MODEL,
    )


def chat_model() -> str:
    """Model for document Q&A chat."""
    explicit = getattr(settings, "CHAT_OPENAI_MODEL", "") or ""
    if explicit.strip():
        return _resolve_deployment(explicit, settings.OPENAI_MODEL)
    return model_for_tier("strong")


# Spec-check extraction type → model tier.
# fast  = cover-page style, mostly explicit text (gpt-4o-mini)
# strong = scattered / legal / date logic / bonds (gpt-4o)
EXTRACTION_MODEL_TIER: dict[str, ModelTier] = {
    ExtractionType.SCOPE_OF_WORK: "fast",
    ExtractionType.TECHNICAL_REQUIREMENTS: "fast",
    ExtractionType.ELIGIBILITY_CRITERIA: "strong",
    ExtractionType.SUBMISSION_DEADLINES: "strong",
    ExtractionType.PAYMENT_TERMS: "strong",
    ExtractionType.PENALTIES_AND_RISKS: "strong",
    ExtractionType.MANDATORY_DOCUMENTS: "strong",
    ExtractionType.SET_ASIDES: "fast",
    ExtractionType.EVALUATION_CRITERIA: "fast",
    ExtractionType.EXECUTIVE_OVERVIEW: "strong",
}


def finetuned_model_for_type(extraction_type: str) -> str | None:
    """
    Return the fine-tuned model ID for this extraction type if one exists.
    Reads from AppSetting (set by finetune_service.poll_job on success).
    Returns None when no fine-tuned model is available.
    """
    try:
        from apps.intelligence.models import AppSetting
        val = AppSetting.get(f"finetune_model_{extraction_type}", "")
        return val.strip() or None
    except Exception:
        return None


def extraction_model(extraction_type: str) -> str:
    """
    Deployment name for an extraction pass.
    Prefers fine-tuned model when available (set after successful fine-tune job).
    """
    if not getattr(settings, "INTELLIGENCE_MODEL_ROUTING_ENABLED", True):
        return model_for_tier("strong")

    # Check for a fine-tuned model first (most accurate).
    if getattr(settings, "FINETUNE_ENABLED", True):
        ft = finetuned_model_for_type(extraction_type)
        if ft:
            return ft

    tier = EXTRACTION_MODEL_TIER.get(extraction_type, "strong")
    return model_for_tier(tier)


def extraction_escalation_model(extraction_type: str) -> str:
    """Strong model used when fast tier returns empty / low-confidence."""
    return model_for_tier("strong")


def should_escalate_extraction(
    extraction_type: str,
    *,
    items: list[dict],
    started_with_fast: bool,
) -> bool:
    """True when we should retry with the strong model."""
    if not getattr(settings, "INTELLIGENCE_MODEL_ESCALATION_ENABLED", True):
        return False
    if not started_with_fast:
        return False
    if extraction_model(extraction_type) == extraction_escalation_model(extraction_type):
        return False
    if items:
        return False
    return True
