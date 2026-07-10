"""
Agentic field verifier — lightweight Phase 2 of extraction.

After all extraction passes complete, this module inspects the assembled
spec_check_fields for:
  1. Missing required fields (bid_deadline, project_name)
  2. Extraction types that returned zero items

For each affected extraction type it runs a targeted retry with:
  - The strong (escalation) model
  - Wider chunk selection (up to 2× normal cap, plus stratified fill)

New items are merged into the existing ExtractedInsight payloads and
persisted.  The updated insight list is returned for use by the summary
service.  If nothing needs fixing the original list is returned unchanged.
"""

import logging

from django.conf import settings

from apps.intelligence.models import DocumentChunk, ExtractedInsight
from apps.documents.models import Document
from apps.intelligence.services.grounding import aggregate_confidence, merge_insight_items
from apps.intelligence.services.model_routing import extraction_escalation_model
from apps.intelligence.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Retry a date/bond field if its confidence is below this threshold.
LOW_CONF_THRESHOLD: int = getattr(settings, "INTELLIGENCE_AGENTIC_LOW_CONF_THRESHOLD", 50)

# Fields that MUST appear in spec_check_fields; absence triggers a retry.
REQUIRED_FIELD_KEYS: frozenset[str] = frozenset(
    getattr(
        settings,
        "INTELLIGENCE_AGENTIC_REQUIRED_FIELDS",
        ["bid_deadline_date_time", "project_name"],
    )
)

# Maps a spec field_key → the extraction type that owns it.
_FIELD_TYPE_MAP: dict[str, str] = {
    # Dates (submission_deadlines)
    "bid_deadline_date_time": "submission_deadlines",
    "bid_open_date_time": "submission_deadlines",
    "pre_bid_deadline_date_time": "submission_deadlines",
    "site_visit_date_time": "submission_deadlines",
    "question_deadline_date_time": "submission_deadlines",
    "municipal_meeting_date_time": "submission_deadlines",
    "project_start_date_time": "submission_deadlines",
    "project_end_date_time": "submission_deadlines",
    # Identity (eligibility_criteria)
    "project_name": "eligibility_criteria",
    "project_owner": "eligibility_criteria",
    "project_solicitation_number": "eligibility_criteria",
    "project_engineer": "eligibility_criteria",
    "project_architect": "eligibility_criteria",
    # Location / size (technical_requirements)
    "project_location": "technical_requirements",
    "project_square_footage": "technical_requirements",
    # Bonds (penalties_and_risks)
    "bid_bond_information": "penalties_and_risks",
    "payment_and_security_bond": "penalties_and_risks",
    "maintenance_and_labor_bond": "penalties_and_risks",
    "certified_checks": "penalties_and_risks",
    "other_bonds": "penalties_and_risks",
    # Set-asides
    "set_aside_mbe": "set_asides",
    "set_aside_wbe": "set_asides",
    "set_aside_dbe": "set_asides",
    "set_aside_dvbe": "set_asides",
    "set_aside_hub": "set_asides",
    "set_aside_sbe": "set_asides",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _all_field_keys(spec: dict) -> set[str]:
    keys: set[str] = set()
    for bucket in spec.values():
        if not isinstance(bucket, list):
            continue
        for row in bucket:
            fk = row.get("field_key")
            if fk:
                keys.add(fk)
    return keys


def _empty_type_keys(insights: list) -> set[str]:
    """Return extraction_types whose payload has zero items (nothing extracted at all)."""
    return {
        i.extraction_type
        for i in insights
        if not (i.payload or {}).get("items")
    }


def _retry_types(spec: dict, insights: list | None = None) -> dict[str, list[str]]:
    """
    Return {extraction_type: [reason, ...]} for types that need a retry pass.

    Triggers:
      1. Required field absent from spec — extraction missed it entirely.
      2. Extraction type returned zero items — LLM produced nothing (rare).

    NOT triggered by low spec-level confidence.  Low confidence after extraction
    is almost always caused by post-processing penalties (conflicting values,
    citation grounding format mismatch) — a retry with the same chunks returns
    the same correct answer with the same penalty.  Retrying is wasteful.
    """
    present = _all_field_keys(spec)
    missing = REQUIRED_FIELD_KEYS - present

    needs: dict[str, set[str]] = {}
    for fk in missing:
        etype = _FIELD_TYPE_MAP.get(fk)
        if etype:
            needs.setdefault(etype, set()).add(f"missing:{fk}")

    if insights:
        for etype in _empty_type_keys(insights):
            if etype in _FIELD_TYPE_MAP.values():
                needs.setdefault(etype, set()).add("empty_extraction")

    return {k: sorted(v) for k, v in needs.items()}


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    *,
    insights: list[ExtractedInsight],
    chunks: list[DocumentChunk],
    spec: dict,
    document: Document,
    total_pages: int,
    page_texts: list[tuple[int, str]],
) -> list[ExtractedInsight]:
    """
    Verify assembled spec_check_fields and retry weak extraction types.

    Parameters
    ----------
    insights    : completed ExtractedInsight rows from the main extraction pass
    chunks      : all DocumentChunks for the document
    spec        : preliminary spec_check_fields dict (built before finalize)
    document    : source Document
    total_pages : page count from ParsedDocument
    page_texts  : [(page_number, extracted_text), ...]

    Returns the same list (possibly with updated .payload attributes).
    """
    retry_map = _retry_types(spec, insights)
    if not retry_map:
        logger.debug("agentic_verifier nothing to retry document_id=%s", document.id)
        return insights

    logger.info(
        "agentic_verifier triggered document_id=%s types=%s",
        document.id,
        {k: v for k, v in retry_map.items()},
    )

    # Lazy import to avoid circular dependency at module level.
    from apps.intelligence.services.extraction_service import (
        ExtractionService,
        _EXTRACTION_BATCH_SIZE,
    )

    client = OpenAIService()
    insights_by_type = {i.extraction_type: i for i in insights}

    for etype, reasons in retry_map.items():
        insight = insights_by_type.get(etype)
        if not insight:
            logger.debug("agentic_verifier no insight for type=%s, skipping", etype)
            continue

        # Wider chunk selection: keyword-selected + stratified fill up to 2× cap.
        normal_cap = ExtractionService._max_chunks_for_type(etype)
        wider_cap = min(normal_cap * 2, len(chunks))
        keyword_selected = ExtractionService._select_chunks_keyword(chunks, etype)
        seen_ids = {c.id for c in keyword_selected}
        extra = ExtractionService._stratified_fill(
            chunks, seen_ids, wider_cap - len(keyword_selected)
        )
        selected = (keyword_selected + extra)[:wider_cap]

        strong_model = extraction_escalation_model(etype)
        logger.info(
            "agentic_verifier retry type=%s reasons=%s chunks=%s model=%s",
            etype, reasons, len(selected), strong_model,
        )

        new_items, _, usage = ExtractionService._run_extraction_batches(
            etype,
            selected,
            client=client,
            total_pages=total_pages,
            page_texts=page_texts,
            model=strong_model,
            batch_size=_EXTRACTION_BATCH_SIZE,
        )

        if not new_items:
            logger.info("agentic_verifier no new items type=%s", etype)
            continue

        existing = list(insight.payload.get("items") or [])
        merged = merge_insight_items(existing + new_items)

        if len(merged) <= len(existing):
            logger.info(
                "agentic_verifier no improvement type=%s existing=%s merged=%s",
                etype, len(existing), len(merged),
            )
            continue

        insight.payload = {"items": merged}
        insight.confidence_score = aggregate_confidence(merged)
        insight.model_name = f"{insight.model_name}+agentic_retry"
        insight.save(update_fields=["payload", "confidence_score", "model_name"])
        logger.info(
            "agentic_verifier improved type=%s items_before=%s items_after=%s",
            etype, len(existing), len(merged),
        )

    return insights
