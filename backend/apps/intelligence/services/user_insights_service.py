"""
User insights aggregation for the management dashboard.

Per-user: documents processed, fields extracted, fields corrected, average
processing time. Plus team-wide accuracy trend, failure stats, field-level
problem ranking, and an activity timeline.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.documents.models import Document
from apps.intelligence.models import ExtractedInsight, FieldFeedback
from apps.processing.models import ProcessingJob

User = get_user_model()


def _per_user_rows(since) -> list[dict[str, Any]]:
    """One row per user who has uploaded at least one document."""
    doc_filter = Q(uploaded_documents__created_at__gte=since) if since else Q()

    users = (
        User.objects.filter(uploaded_documents__isnull=False)
        .annotate(
            docs_total=Count("uploaded_documents", filter=doc_filter, distinct=True),
            docs_completed=Count(
                "uploaded_documents",
                filter=doc_filter & Q(uploaded_documents__status="completed"),
                distinct=True,
            ),
            docs_failed=Count(
                "uploaded_documents",
                filter=doc_filter & Q(uploaded_documents__status="failed"),
                distinct=True,
            ),
        )
        .filter(docs_total__gt=0)
        .distinct()
        .order_by("-docs_total")
    )

    rows: list[dict[str, Any]] = []
    for u in users:
        user_docs = Document.objects.filter(uploaded_by=u)
        if since:
            user_docs = user_docs.filter(created_at__gte=since)
        doc_ids = list(user_docs.values_list("id", flat=True))

        # Fields extracted = items across current insights on this user's docs.
        fields_extracted = 0
        for payload in ExtractedInsight.objects.filter(
            document_id__in=doc_ids
        ).values_list("payload", flat=True):
            fields_extracted += len((payload or {}).get("items") or [])

        feedback = FieldFeedback.objects.filter(document_id__in=doc_ids)
        corrections = feedback.filter(rating="down").count()
        confirmations = feedback.filter(rating="up").count()

        # Processing time: completed jobs' started→completed span.
        duration = (
            ProcessingJob.objects.filter(
                document_id__in=doc_ids,
                started_at__isnull=False,
                completed_at__isnull=False,
                current_stage="completed",
            )
            .annotate(
                span=ExpressionWrapper(
                    F("completed_at") - F("started_at"),
                    output_field=DurationField(),
                )
            )
            .aggregate(avg=Avg("span"))["avg"]
        )

        retries = (
            ProcessingJob.objects.filter(document_id__in=doc_ids)
            .aggregate(total=Count("id"))["total"]
            or 0
        ) - len(doc_ids)

        last_doc = user_docs.order_by("-created_at").first()

        rows.append(
            {
                "user_id": str(u.id),
                "username": u.username,
                "email": u.email,
                "docs_total": u.docs_total,
                "docs_completed": u.docs_completed,
                "docs_failed": u.docs_failed,
                "fields_extracted": fields_extracted,
                "fields_corrected": corrections,
                "fields_confirmed": confirmations,
                "correction_rate": (
                    round(corrections / fields_extracted * 100, 1)
                    if fields_extracted
                    else 0.0
                ),
                "avg_processing_seconds": (
                    round(duration.total_seconds(), 1) if duration else None
                ),
                "retry_jobs": max(0, retries),
                "last_activity": (
                    last_doc.created_at.isoformat() if last_doc else None
                ),
            }
        )
    return rows


def _accuracy_trend(since, days: int) -> list[dict[str, Any]]:
    """Daily correction counts: down-votes vs total feedback."""
    start = since or (timezone.now() - timedelta(days=days))
    rows = (
        FieldFeedback.objects.filter(created_at__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            total=Count("id"),
            corrections=Count("id", filter=Q(rating="down")),
        )
        .order_by("day")
    )
    return [
        {
            "date": r["day"].isoformat(),
            "feedback_total": r["total"],
            "corrections": r["corrections"],
            "correction_rate": (
                round(r["corrections"] / r["total"] * 100, 1) if r["total"] else 0.0
            ),
        }
        for r in rows
    ]


def _field_problem_ranking(since) -> list[dict[str, Any]]:
    """Fields most often flagged wrong — where to tune prompts next."""
    qs = FieldFeedback.objects.filter(rating="down")
    if since:
        qs = qs.filter(created_at__gte=since)
    rows = (
        qs.values("field_key")
        .annotate(corrections=Count("id"))
        .order_by("-corrections")[:15]
    )
    return [
        {"field_key": r["field_key"], "corrections": r["corrections"]} for r in rows
    ]


def _failure_stats(since) -> dict[str, Any]:
    docs = Document.objects.all()
    jobs = ProcessingJob.objects.filter(current_stage="failed")
    if since:
        docs = docs.filter(created_at__gte=since)
        jobs = jobs.filter(created_at__gte=since)

    top_errors = list(
        jobs.exclude(error_code="")
        .values("error_code")
        .annotate(count=Count("id"))
        .order_by("-count")[:8]
    )
    return {
        "documents_failed": docs.filter(status="failed").count(),
        "documents_total": docs.count(),
        "top_error_codes": top_errors,
    }


def _activity_timeline(since, days: int) -> list[dict[str, Any]]:
    start = since or (timezone.now() - timedelta(days=days))
    rows = (
        Document.objects.filter(created_at__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            uploads=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
        )
        .order_by("day")
    )
    return [
        {
            "date": r["day"].isoformat(),
            "uploads": r["uploads"],
            "completed": r["completed"],
        }
        for r in rows
    ]


def build_user_detail(user_id: str, days: int = 30) -> dict[str, Any]:
    """Drill-down for one user: document list + field/correction breakdowns."""
    since = timezone.now() - timedelta(days=days) if days else None

    docs = Document.objects.filter(uploaded_by_id=user_id).order_by("-created_at")
    if since:
        docs = docs.filter(created_at__gte=since)
    doc_ids = list(docs.values_list("id", flat=True))

    documents = [
        {
            "id": str(d.id),
            "filename": d.original_filename,
            "status": d.status,
            "size_mb": round(d.size_bytes / 1048576, 1),
            "created_at": d.created_at.isoformat(),
        }
        for d in docs[:200]
    ]

    # Field extraction breakdown: label -> count across this user's docs.
    field_counts: dict[str, int] = {}
    for payload in ExtractedInsight.objects.filter(
        document_id__in=doc_ids
    ).values_list("payload", flat=True):
        for item in (payload or {}).get("items") or []:
            label = str(item.get("label") or "").strip() or "(unlabeled)"
            field_counts[label] = field_counts.get(label, 0) + 1

    # Corrections: totals per field + per-document breakdown (for the
    # per-document filter in the corrected drill-down modal).
    corrected_counts: dict[str, int] = {}
    corrected_by_doc: dict[str, dict[str, int]] = {}
    doc_names = {str(d.id): d.original_filename for d in docs}
    for doc_id, fk in FieldFeedback.objects.filter(
        document_id__in=doc_ids, rating="down"
    ).values_list("document_id", "field_key"):
        key = fk or "(unknown)"
        corrected_counts[key] = corrected_counts.get(key, 0) + 1
        corrected_by_doc.setdefault(str(doc_id), {})
        corrected_by_doc[str(doc_id)][key] = (
            corrected_by_doc[str(doc_id)].get(key, 0) + 1
        )

    return {
        "user_id": str(user_id),
        "period_days": days,
        "documents": documents,
        "fields": sorted(
            ({"field": k, "count": v} for k, v in field_counts.items()),
            key=lambda r: -r["count"],
        ),
        "corrected": sorted(
            ({"field": k, "count": v} for k, v in corrected_counts.items()),
            key=lambda r: -r["count"],
        ),
        "corrected_by_document": [
            {
                "document_id": doc_id,
                "filename": doc_names.get(doc_id, doc_id),
                "fields": sorted(
                    ({"field": k, "count": v} for k, v in fields.items()),
                    key=lambda r: -r["count"],
                ),
            }
            for doc_id, fields in corrected_by_doc.items()
        ],
    }


def build_ai_insights(days: int = 30, *, force_refresh: bool = False) -> dict[str, Any]:
    """LLM-generated analytical insights over the team's extraction data.

    Reads the aggregated stats plus real correction examples and asks the
    model for root-cause / recommendation bullets. Cached per data snapshot
    so page loads don't re-call the LLM until the data changes.
    """
    import hashlib
    import json

    from django.core.cache import cache

    from apps.intelligence.services.model_routing import model_for_tier
    from apps.intelligence.services.openai_service import OpenAIService

    data = build_user_insights(days=days)

    # Real correction examples give the model concrete failure evidence.
    since = timezone.now() - timedelta(days=days) if days else None
    fb = FieldFeedback.objects.filter(rating="down").order_by("-created_at")
    if since:
        fb = fb.filter(created_at__gte=since)
    corrections = list(
        fb.values("field_key", "extracted_value", "correct_value", "issue_type", "comment")[:25]
    )

    payload = {
        "users": data["users"],
        "field_problem_ranking": data["field_problem_ranking"],
        "failure_stats": data["failure_stats"],
        "accuracy_trend": data["accuracy_trend"][-14:],
        "correction_examples": corrections,
    }
    snapshot = json.dumps(payload, sort_keys=True, default=str)
    cache_key = f"ai_insights_{days}_{hashlib.sha256(snapshot.encode()).hexdigest()[:16]}"
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached:
            return cached

    prompt = f"""You are an analytics assistant for a tender-document extraction tool.
Below is the team's usage and accuracy data for the selected period, including
real examples of fields users corrected (extracted value vs correct value + reason).

Analyse it and return the most USEFUL, SPECIFIC insights — not restatements of
the numbers. Focus on:
- the most recurring problem and its likely root cause (look at the correction
  examples: what kind of mistake is the tool making — wrong date picked, wrong
  entity, format issues?),
- which fields need attention and WHY (patterns across corrections),
- concrete, actionable recommendations (what to verify, what to watch),
- any notable user/team pattern worth acting on.

Return valid JSON only:
{{"insights": [{{"title": "<max 8 words>", "detail": "<1-2 sentences, specific>", "kind": "problem" | "recommendation" | "pattern"}}]}}
Return exactly 3 insights, most important first. Base every claim strictly on the data.

Data:
{snapshot[:24000]}"""

    try:
        client = OpenAIService()
        result, _usage = client.chat_json(
            system="You produce precise, data-grounded analytics insights. Never invent numbers.",
            user=prompt,
            model=model_for_tier("strong"),
        )
        insights = [
            i for i in (result.get("insights") or [])
            if isinstance(i, dict) and i.get("title") and i.get("detail")
        ][:3]
    except Exception:
        logger.exception("ai_insights_failed days=%s", days)
        insights = []

    out = {"period_days": days, "insights": insights}
    cache.set(cache_key, out, timeout=6 * 3600)
    return out


def build_user_insights(days: int = 30) -> dict[str, Any]:
    """Full insights payload. days=0 → all time."""
    since = timezone.now() - timedelta(days=days) if days else None
    return {
        "period_days": days,
        "users": _per_user_rows(since),
        "accuracy_trend": _accuracy_trend(since, days or 30),
        "field_problem_ranking": _field_problem_ranking(since),
        "failure_stats": _failure_stats(since),
        "activity_timeline": _activity_timeline(since, days or 30),
    }
