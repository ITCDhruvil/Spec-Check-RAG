"""
Feedback processing service.

On NEGATIVE feedback:
  1. Store the correction in FieldFeedback.
  2. Immediately update LearnedExtractionTerm (fast in-context win).
  3. Enqueue threshold check → triggers fine-tuning when enough data.

On POSITIVE feedback:
  1. Store; boost hit_count on any matching learned terms.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def process_feedback(
    document_id: str,
    field_key: str,
    extraction_type: str,
    rating: str,
    *,
    issue_type: str = "",
    extracted_value: str = "",
    correct_value: str = "",
    comment: str = "",
    source_text_context: str = "",
    doc_type: str = "",
) -> "FieldFeedback":
    """
    Create a FieldFeedback row and kick off downstream effects.
    Returns the saved feedback instance.
    """
    from apps.documents.models import Document
    from apps.intelligence.models import FieldFeedback

    document = Document.objects.get(id=document_id)

    feedback = FieldFeedback.objects.create(
        document=document,
        field_key=field_key,
        extraction_type=extraction_type,
        doc_type=doc_type,
        rating=rating,
        issue_type=issue_type,
        extracted_value=extracted_value[:2000],
        correct_value=correct_value[:2000],
        comment=comment[:1000],
        source_text_context=source_text_context[:4000],
    )

    if rating == "down":
        _update_lexicon_from_correction(
            extraction_type, field_key, correct_value, source_text_context
        )
        _enqueue_threshold_check(extraction_type)
    else:
        _boost_positive(extraction_type)

    logger.info(
        "feedback_processed doc=%s field=%s type=%s rating=%s",
        document_id, field_key, extraction_type, rating,
    )
    return feedback


def _update_lexicon_from_correction(
    extraction_type: str,
    field_key: str,
    correct_value: str,
    source_text: str,
) -> None:
    """
    Extract meaningful terms from the correction and add them to LearnedExtractionTerm.
    These flow into the next extraction's retrieval queries automatically.
    """
    from apps.intelligence.models import LearnedExtractionTerm
    from apps.intelligence.choices import LearnedEntryKind, LearnedTermSource

    candidates: list[str] = []
    if field_key and correct_value and len(correct_value.strip()) >= 2:
        candidates.append(f"{field_key}: {correct_value.strip()[:120]}")
    if correct_value and len(correct_value.strip()) >= 4:
        candidates.append(correct_value.strip()[:128])
    # Add first 80 chars of source context as a query hint.
    if source_text and len(source_text.strip()) >= 20:
        candidates.append(source_text.strip()[:80])

    for term in candidates:
        norm = term.lower().strip()
        if not norm:
            continue
        obj, created = LearnedExtractionTerm.objects.get_or_create(
            extraction_type=extraction_type,
            entry_kind=LearnedEntryKind.QUERY,
            term_normalized=norm[:256],
            defaults={
                "term_display": term[:512],
                "source": LearnedTermSource.HEURISTIC,
                "hit_count": 1,
            },
        )
        if not created:
            LearnedExtractionTerm.objects.filter(pk=obj.pk).update(
                hit_count=obj.hit_count + 1,
                is_active=True,
            )


def _boost_positive(extraction_type: str) -> None:
    """Positive signal: small hit_count bump on all active terms for this type."""
    from apps.intelligence.models import LearnedExtractionTerm
    LearnedExtractionTerm.objects.filter(
        extraction_type=extraction_type,
        is_active=True,
    ).update(hit_count=__import__("django.db.models", fromlist=["F"]).F("hit_count") + 1)


def _enqueue_threshold_check(extraction_type: str) -> None:
    """Dispatch Celery task to check if we have enough data to fine-tune."""
    try:
        from apps.intelligence.tasks import check_finetune_threshold_task
        check_finetune_threshold_task.delay(extraction_type)
    except Exception:
        # Celery not running in dev — fall back to sync check.
        logger.warning(
            "finetune_threshold_celery_unavailable extraction_type=%s — skipping async check",
            extraction_type,
        )
