import json
import logging

from django.conf import settings
from django.utils import timezone

from apps.documents.models import Document
from apps.intelligence.choices import SummaryStatus
from apps.intelligence.models import ExtractedInsight, GeneratedSummary
from apps.intelligence.services.grounding import detect_missing_extractions
from apps.intelligence.services.summary_postprocess import (
    build_spec_check_fields_from_insights,
    finalize_spec_check_fields,
    postprocess_summary,
)

logger = logging.getLogger(__name__)


class SummaryService:
    @staticmethod
    def build_extractions_context(insights: list[ExtractedInsight]) -> str:
        payload = {}
        for insight in insights:
            payload[insight.extraction_type] = {
                "confidence_score": insight.confidence_score,
                "items": insight.payload.get("items", []),
            }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @staticmethod
    def generate_final_summary(
        document: Document,
        summary: GeneratedSummary,
        insights: list[ExtractedInsight],
    ) -> GeneratedSummary:
        # Deterministic spec-check field builder (no summary LLM pass).
        data = {"spec_check_fields": build_spec_check_fields_from_insights(insights)}
        data = postprocess_summary(data, insights, document=document)
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "model": "none"}
        model_name = "none"

        # Ensure spec_check_fields is populated. If the LLM returned an empty
        # or missing spec_check_fields (e.g. old-format response), build it
        # deterministically from the already-extracted insights.
        spec = data.get("spec_check_fields")
        if not isinstance(spec, dict) or not any(
            bool(spec.get(k))
            for k in (
                "project_metadata_items",
                "project_people_items",
                "project_size_location_items",
                "project_dates",
                "bond_items",
                "set_aside_items",
            )
        ):
            spec = build_spec_check_fields_from_insights(insights)
            warnings = finalize_spec_check_fields(spec)
            data["spec_check_fields"] = spec
            if warnings:
                data.setdefault("_meta", {})["field_warnings"] = warnings
            logger.info(
                "spec_check_fields_fallback document_id=%s fields=%s",
                document.id,
                {k: len(v) for k, v in spec.items() if isinstance(v, list)},
            )

        present_types = {i.extraction_type for i in insights if i.payload.get("items")}
        missing = detect_missing_extractions(present_types)

        prior_meta = dict(data.get("_meta") or {})
        data["_meta"] = {
            "model": model_name,
            "prompt_version": settings.INTELLIGENCE_PROMPT_VERSION,
            "generated_at": timezone.now().isoformat(),
            "missing_extraction_types": missing,
            "insight_count": len(insights),
            "token_usage": usage,
        }
        if prior_meta.get("field_warnings"):
            data["_meta"]["field_warnings"] = prior_meta["field_warnings"]

        summary.summary_json = data
        summary.model_metadata = {
            "model": model_name,
            "prompt_version": settings.INTELLIGENCE_PROMPT_VERSION,
            "missing_sections": missing,
        }
        summary.total_tokens = usage.get("total_tokens", 0)
        summary.status = SummaryStatus.COMPLETED
        summary.completed_at = timezone.now()
        summary.save()

        document.metadata = {
            **document.metadata,
            "intelligence": {
                "summary_id": str(summary.id),
                "version": summary.version,
                "total_tokens": summary.total_tokens,
            },
        }
        document.save(update_fields=["metadata", "updated_at"])

        logger.info("summary_generated document_id=%s version=%s", document.id, summary.version)
        return summary
