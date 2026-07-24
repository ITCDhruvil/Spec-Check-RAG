"""
Learning-loop regression tracking.

After a document is re-extracted, every prior correction for it is re-checked
against the new result:
  resolved  — the new value matches the user's correction (mistake fixed)
  recurred  — the new value repeats the original mistake (or still misses it)

This is the record that proves whether the feedback → prompt-hint /
fine-tune pipeline actually stopped a mistake from happening again.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.utils import timezone

from apps.intelligence.models import FieldFeedback, GeneratedSummary

logger = logging.getLogger(__name__)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _values_match(new_value: str, correct_value: str) -> bool:
    """Loose match: exact after normalization, or one contains the other
    (users often correct with a longer/shorter phrasing of the same fact)."""
    a, b = _normalize(new_value), _normalize(correct_value)
    if not a or not b:
        return False
    if a == b:
        return True
    return a in b or b in a


def _extract_current_values(summary_json: dict) -> dict[str, str]:
    """field_key -> current displayed value from spec_check_fields."""
    values: dict[str, str] = {}
    spec = (summary_json or {}).get("spec_check_fields") or {}
    for bucket in spec.values():
        if not isinstance(bucket, list):
            continue
        for row in bucket:
            if not isinstance(row, dict):
                continue
            fk = str(row.get("field_key") or "").strip()
            if not fk or row.get("_not_found"):
                continue
            value = str(row.get("date") or "").strip()
            if not value:
                text = str(row.get("text") or "").strip()
                value = text.split(": ", 1)[1] if ": " in text else text
            # Events notes are checkable too (feedback key = <fk>_events).
            note = str(row.get("_note") or "").strip()
            if note:
                values[f"{fk}_events"] = note
            if value:
                # Keep the longest value seen per key (multi-row fields).
                if len(value) > len(values.get(fk, "")):
                    values[fk] = value
    return values


def recheck_corrections(document_id, summary: GeneratedSummary) -> dict[str, int]:
    """Re-check every down-feedback for this document against the new summary.
    Returns counts {resolved, recurred, unchecked}."""
    feedbacks = list(
        FieldFeedback.objects.filter(document_id=document_id, rating="down")
    )
    if not feedbacks:
        return {"resolved": 0, "recurred": 0, "unchecked": 0}

    current = _extract_current_values(summary.summary_json or {})
    now = timezone.now()
    resolved = recurred = unchecked = 0

    for fb in feedbacks:
        new_value = current.get(fb.field_key, "")
        correct = (fb.correct_value or "").strip()

        if correct:
            if _values_match(new_value, correct):
                fb.resolution_status = FieldFeedback.ResolutionStatus.RESOLVED
                resolved += 1
            else:
                fb.resolution_status = FieldFeedback.ResolutionStatus.RECURRED
                recurred += 1
        elif fb.issue_type == "missing":
            # User said the value was missing — resolved when it now exists.
            if new_value:
                fb.resolution_status = FieldFeedback.ResolutionStatus.RESOLVED
                resolved += 1
            else:
                fb.resolution_status = FieldFeedback.ResolutionStatus.RECURRED
                recurred += 1
        else:
            # Flagged wrong without a stated correction: resolved when the
            # value CHANGED from the flagged one.
            old_wrong = (fb.extracted_value or "").strip()
            if old_wrong and new_value and not _values_match(new_value, old_wrong):
                fb.resolution_status = FieldFeedback.ResolutionStatus.RESOLVED
                resolved += 1
            elif old_wrong and new_value:
                fb.resolution_status = FieldFeedback.ResolutionStatus.RECURRED
                recurred += 1
            else:
                unchecked += 1
                continue

        fb.last_checked_at = now
        fb.recheck_count += 1
        fb.save(
            update_fields=[
                "resolution_status",
                "last_checked_at",
                "recheck_count",
                "updated_at",
            ]
        )

    logger.info(
        "learning_loop_recheck document_id=%s resolved=%s recurred=%s unchecked=%s",
        document_id,
        resolved,
        recurred,
        unchecked,
    )
    return {"resolved": resolved, "recurred": recurred, "unchecked": unchecked}


def learning_effectiveness() -> dict[str, Any]:
    """Aggregate learning-loop stats for the Feedback page."""
    from django.db.models import Count, Q

    per_field = list(
        FieldFeedback.objects.filter(rating="down")
        .values("field_key")
        .annotate(
            corrections=Count("id"),
            resolved=Count("id", filter=Q(resolution_status="resolved")),
            recurred=Count("id", filter=Q(resolution_status="recurred")),
            pending=Count("id", filter=Q(resolution_status="pending")),
        )
        .order_by("-corrections")[:20]
    )
    totals = {
        "corrections": sum(r["corrections"] for r in per_field),
        "resolved": sum(r["resolved"] for r in per_field),
        "recurred": sum(r["recurred"] for r in per_field),
        "pending": sum(r["pending"] for r in per_field),
    }
    return {"totals": totals, "per_field": per_field}
