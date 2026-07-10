import logging

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdminUser
from apps.core.exceptions import ServiceError, ValidationServiceError
from apps.documents.services.document_service import DocumentService
from apps.intelligence.choices import SummaryStatus
from apps.intelligence.models import ExtractedInsight, GeneratedSummary
from apps.intelligence.services.briefing_pdf_service import BriefingPdfService
from apps.intelligence.serializers import (
    ExtractedInsightSerializer,
    GeneratedSummarySerializer,
    SummaryStatusSerializer,
)
from apps.intelligence.services.generation_dispatch import dispatch_summary_generation
from apps.processing.choices import PipelineStage
from apps.processing.services.job_service import ProcessingJobService

logger = logging.getLogger(__name__)


class GenerateSummaryView(APIView):
    def post(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        regenerate = request.data.get("regenerate", False) in (True, "true", "1")

        if not regenerate:
            current = GeneratedSummary.objects.filter(
                document=document, is_current=True, status="completed"
            ).first()
            if current:
                return Response(
                    {
                        "message": "Summary exists. Set regenerate=true to replace.",
                        "summary_id": str(current.id),
                    },
                    status=status.HTTP_200_OK,
                )

        try:
            body, http_status = dispatch_summary_generation(
                document.id, regenerate=regenerate
            )
        except ServiceError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        except ValidationServiceError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(body, status=http_status)


class RegenerateSummaryView(APIView):
    def post(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        try:
            body, http_status = dispatch_summary_generation(
                document.id, regenerate=True
            )
        except ServiceError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )
        except ValidationServiceError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(body, status=http_status)


class GeneratedSummaryDetailView(APIView):
    def get(self, request, document_id):
        DocumentService.get_document(document_id, request.user)
        summary = GeneratedSummary.objects.filter(
            document_id=document_id, is_current=True
        ).first()
        if not summary:
            raise ValidationServiceError(
                "No summary found for this document.",
                code="summary_not_found",
            )
        return Response(GeneratedSummarySerializer(summary).data)


class SummaryPdfDownloadView(APIView):
    """Download the current briefing as a structured PDF report."""

    def get(self, request, document_id):
        variant = (request.query_params.get("variant") or "full").strip().lower()
        if variant not in ("full", "executive"):
            raise ValidationServiceError(
                "variant must be 'full' or 'executive'.",
                code="invalid_variant",
            )

        document = DocumentService.get_document(document_id, request.user)
        summary = GeneratedSummary.objects.filter(
            document_id=document_id,
            is_current=True,
            status=SummaryStatus.COMPLETED,
        ).first()
        if not summary or not summary.summary_json:
            raise ValidationServiceError(
                "No completed briefing available to export.",
                code="summary_not_ready",
            )

        pdf_bytes = BriefingPdfService.render(
            summary, document, variant=variant
        )
        filename = BriefingPdfService.suggested_filename_for_variant(
            document, summary, variant=variant
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = len(pdf_bytes)
        return response


class ExtractedInsightsListView(APIView):
    def get(self, request, document_id):
        DocumentService.get_document(document_id, request.user)
        summary_id = request.query_params.get("summary_id")
        qs = ExtractedInsight.objects.filter(document_id=document_id).order_by(
            "extraction_type"
        )
        if summary_id:
            qs = qs.filter(generated_summary_id=summary_id)
        else:
            current = GeneratedSummary.objects.filter(
                document_id=document_id, is_current=True
            ).first()
            if current:
                qs = qs.filter(generated_summary=current)
        return Response(ExtractedInsightSerializer(qs, many=True).data)


class CancelSummaryView(APIView):
    def post(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        summary = GeneratedSummary.objects.filter(
            document=document, is_current=True
        ).first()

        # If already in a terminal state, nothing to do.
        if summary and summary.status in ("completed", "failed"):
            return Response(
                {"message": "Nothing to cancel.", "status": summary.status},
                status=status.HTTP_200_OK,
            )

        # Revoke the Celery task (best-effort — may not exist yet if parsing hasn't
        # handed off to intelligence, or may already be done).
        job = ProcessingJobService.get_latest_job_for_document(document.id)
        if job and job.celery_task_id:
            try:
                from celery import current_app as celery_app
                celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
            except Exception as exc:
                logger.warning(
                    "cancel_revoke_failed document_id=%s task_id=%s error=%s",
                    document_id,
                    job.celery_task_id,
                    exc,
                )

        # Mark the summary failed — create a placeholder row if none exists yet
        # (e.g. cancelled during early parsing before the intelligence worker ran).
        if summary:
            summary.status = "failed"
            summary.error_message = "Cancelled by user."
            summary.completed_at = timezone.now()
            summary.save(update_fields=["status", "error_message", "completed_at"])
        else:
            summary = GeneratedSummary.objects.create(
                document=document,
                status="failed",
                error_message="Cancelled by user.",
                is_current=True,
                completed_at=timezone.now(),
            )

        # Always mark the document itself as failed — this is what the dashboard
        # badge reads. Without this the document stays in "parsing_processing" /
        # "queued" indefinitely after the user cancels.
        document.status = PipelineStage.FAILED
        document.save(update_fields=["status", "updated_at"])

        if job:
            try:
                from apps.processing.errors import StructuredProcessingError
                from apps.processing.choices import ProcessingErrorType
                structured = StructuredProcessingError(
                    error_type=ProcessingErrorType.EXTRACTION_FAILURE,
                    stage=job.current_stage,
                    recoverable=True,
                    retry_count=job.retry_count,
                    message="Cancelled by user.",
                )
                ProcessingJobService.mark_failed(job, structured)
            except Exception as exc:
                logger.warning("cancel_job_mark_failed error=%s", exc)

        logger.info(
            "processing_cancelled document_id=%s summary_id=%s",
            document_id,
            summary.id,
        )
        return Response({"message": "Processing cancelled.", "summary_id": str(summary.id)})


class RepairSpecCheckView(APIView):
    """
    Rebuild spec_check_fields from the stored ExtractedInsight rows.

    This is a lightweight, no-LLM repair that can fix existing summaries whose
    spec_check_fields were empty due to an old prompt version or LLM non-compliance.
    POST /api/v1/documents/{id}/summary/repair-spec-check/
    """

    def post(self, request, document_id):
        DocumentService.get_document(document_id, request.user)
        from apps.documents.models import Document
        from apps.intelligence.services.summary_postprocess import (
            build_spec_check_fields_from_insights,
            postprocess_summary,
        )

        summary = GeneratedSummary.objects.filter(
            document_id=document_id,
            is_current=True,
            status="completed",
        ).first()
        if not summary:
            raise ValidationServiceError(
                "No completed summary found for this document.",
                code="summary_not_found",
            )

        insights = list(
            ExtractedInsight.objects.filter(
                document_id=document_id,
                generated_summary=summary,
            )
        )
        if not insights:
            # Fallback: take the most recent insights for the document.
            insights = list(
                ExtractedInsight.objects.filter(document_id=document_id).order_by(
                    "-created_at"
                )[:20]
            )

        if not insights:
            raise ValidationServiceError(
                "No extraction insights found for this document.",
                code="no_insights",
            )

        document = Document.objects.filter(id=document_id).first()
        data = {"spec_check_fields": build_spec_check_fields_from_insights(insights)}
        data = postprocess_summary(data, insights, document=document)

        stored = dict(summary.summary_json or {})
        stored["spec_check_fields"] = data.get("spec_check_fields")
        meta = dict(stored.get("_meta") or {})
        meta["spec_check_repaired_at"] = timezone.now().isoformat()
        if data.get("_meta", {}).get("field_warnings"):
            meta["field_warnings"] = data["_meta"]["field_warnings"]
        stored["_meta"] = meta
        data = stored
        spec_fields = data.get("spec_check_fields") or {}

        summary.summary_json = data
        summary.save(update_fields=["summary_json", "updated_at"])

        logger.info(
            "spec_check_repaired document_id=%s summary_id=%s",
            document_id,
            summary.id,
        )
        return Response(
            {
                "message": "spec_check_fields rebuilt from extraction insights.",
                "summary_id": str(summary.id),
                "fields_populated": {
                    k: len(v) for k, v in spec_fields.items() if isinstance(v, list)
                },
            }
        )


class SummaryStatusView(APIView):
    def get(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        summary = GeneratedSummary.objects.filter(
            document_id=document_id, is_current=True
        ).first()

        # Intelligence stages — pass through as-is for the UI progress bar.
        _INTEL_STAGES = frozenset(
            {
                PipelineStage.CHUNKING_PROCESSING,
                PipelineStage.CHUNKING_COMPLETED,
                PipelineStage.EMBEDDING_PROCESSING,
                PipelineStage.EMBEDDING_COMPLETED,
                PipelineStage.EXTRACTION_PROCESSING,
                PipelineStage.EXTRACTION_COMPLETED,
                PipelineStage.SUMMARY_PROCESSING,
            }
        )
        if document.status in _INTEL_STAGES:
            progress_stage = document.status
        elif (
            document.status == PipelineStage.COMPLETED
            and summary
            and summary.status == "completed"
        ):
            # Full pipeline done — briefing is actually ready.
            progress_stage = PipelineStage.COMPLETED
        elif document.status == PipelineStage.COMPLETED:
            # Parse finished but intelligence not done — never send "completed"
            # to the UI or it flashes 100% before extraction starts.
            progress_stage = PipelineStage.PARSING_COMPLETED
        else:
            progress_stage = document.status

        payload = {
            "document_id": document.id,
            "document_status": document.status,
            "summary_status": summary.status if summary else None,
            "summary_id": summary.id if summary else None,
            "version": summary.version if summary else None,
            "progress_stage": progress_stage,
            "total_tokens": summary.total_tokens if summary else None,
            "error_message": summary.error_message if summary else None,
        }
        return Response(SummaryStatusSerializer(payload).data)


class FieldFeedbackView(APIView):
    """
    POST /api/v1/documents/{id}/field-feedback/

    Body:
      field_key         str   required  e.g. "bid_deadline_date_time"
      extraction_type   str   required  e.g. "submission_deadlines"
      rating            str   required  "up" | "down"
      issue_type        str   optional  "wrong_value"|"wrong_source"|"missing"|"other"
      extracted_value   str   optional  what the system extracted
      correct_value     str   optional  what is correct (required for fine-tuning)
      comment           str   optional  free text
      source_text_context str optional  verbatim citation text
      doc_type          str   optional  classified doc type
    """

    def post(self, request, document_id):
        DocumentService.get_document(document_id, request.user)
        data = request.data
        field_key = str(data.get("field_key") or "").strip()
        extraction_type = str(data.get("extraction_type") or "").strip()
        rating = str(data.get("rating") or "").strip().lower()

        if not field_key or not extraction_type:
            return Response(
                {"error": "field_key and extraction_type are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if rating not in ("up", "down"):
            return Response(
                {"error": "rating must be 'up' or 'down'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from apps.intelligence.services.feedback_service import process_feedback
            feedback = process_feedback(
                document_id=str(document_id),
                field_key=field_key,
                extraction_type=extraction_type,
                rating=rating,
                issue_type=str(data.get("issue_type") or ""),
                extracted_value=str(data.get("extracted_value") or ""),
                correct_value=str(data.get("correct_value") or ""),
                comment=str(data.get("comment") or ""),
                source_text_context=str(data.get("source_text_context") or ""),
                doc_type=str(data.get("doc_type") or ""),
            )
        except Exception as exc:
            logger.exception("field_feedback_failed document_id=%s field=%s", document_id, field_key)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            "field_feedback_saved document_id=%s field=%s rating=%s",
            document_id, field_key, rating,
        )
        return Response(
            {"id": str(feedback.id), "rating": rating, "field_key": field_key},
            status=status.HTTP_201_CREATED,
        )


class MaintenanceStatusView(APIView):
    """
    GET /api/health/
    Returns {"status": "ok"|"maintenance", "maintenance": bool, ...}
    Used by frontend to show the maintenance banner during fine-tuning.
    """

    def get(self, request):
        from apps.intelligence.services.maintenance_service import maintenance_status
        ms = maintenance_status()
        return Response({
            "status": "maintenance" if ms["maintenance"] else "ok",
            **ms,
        })


# ---------------------------------------------------------------------------
# Feedback Insights admin views
# ---------------------------------------------------------------------------

class FeedbackStatsView(APIView):
    """
    GET /api/v1/feedback/stats/
    Returns aggregate counts + per-type breakdown + active fine-tune jobs.
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.db.models import Count, Q
        from apps.intelligence.models import FieldFeedback, FineTuneJob, AppSetting
        from apps.intelligence.services.finetune_service import _threshold, _max_cost_usd, _enabled

        total = FieldFeedback.objects.count()
        up = FieldFeedback.objects.filter(rating="up").count()
        down = FieldFeedback.objects.filter(rating="down").count()
        with_correction = FieldFeedback.objects.filter(rating="down", correct_value__gt="").count()
        used = FieldFeedback.objects.filter(used_in_finetune=True).count()

        # Per-extraction-type breakdown
        by_type = list(
            FieldFeedback.objects.values("extraction_type")
            .annotate(
                total=Count("id"),
                up=Count("id", filter=Q(rating="up")),
                down=Count("id", filter=Q(rating="down")),
                with_correction=Count("id", filter=Q(rating="down", correct_value__gt="")),
                used_in_finetune=Count("id", filter=Q(used_in_finetune=True)),
            )
            .order_by("extraction_type")
        )

        # Active jobs
        active_jobs = list(
            FineTuneJob.objects.exclude(status__in=["succeeded", "failed", "cancelled"])
            .values("id", "extraction_type", "status", "feedback_count", "estimated_cost_usd", "created_at")
            .order_by("-created_at")[:5]
        )

        # Active fine-tuned models
        ft_models = {}
        for row in by_type:
            etype = row["extraction_type"]
            model_id = AppSetting.get(f"finetune_model_{etype}", "")
            if model_id:
                ft_models[etype] = model_id

        return Response({
            "total": total,
            "up": up,
            "down": down,
            "with_correction": with_correction,
            "used_in_finetune": used,
            "by_type": by_type,
            "active_jobs": active_jobs,
            "fine_tuned_models": ft_models,
            "settings": {
                "finetune_enabled": _enabled(),
                "threshold": _threshold(),
                "max_cost_usd": _max_cost_usd(),
            },
        })


class FeedbackListView(APIView):
    """
    GET /api/v1/feedback/?extraction_type=X&rating=down&page=1&page_size=50
    DELETE /api/v1/feedback/:id/  (via FeedbackDetailView)
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        from apps.intelligence.models import FieldFeedback

        qs = FieldFeedback.objects.select_related("document").order_by("-created_at")

        etype = request.query_params.get("extraction_type")
        rating = request.query_params.get("rating")
        used = request.query_params.get("used_in_finetune")

        if etype:
            qs = qs.filter(extraction_type=etype)
        if rating in ("up", "down"):
            qs = qs.filter(rating=rating)
        if used == "true":
            qs = qs.filter(used_in_finetune=True)
        elif used == "false":
            qs = qs.filter(used_in_finetune=False)

        page_size = min(int(request.query_params.get("page_size", 50)), 200)
        page = max(int(request.query_params.get("page", 1)), 1)
        offset = (page - 1) * page_size
        total = qs.count()

        items = list(
            qs[offset: offset + page_size].values(
                "id", "field_key", "extraction_type", "doc_type", "rating",
                "issue_type", "extracted_value", "correct_value", "comment",
                "source_text_context", "used_in_finetune", "created_at",
                "document_id",
            )
        )
        # Add document filename
        from apps.documents.models import Document
        doc_ids = {str(i["document_id"]) for i in items}
        doc_names = {
            str(d.id): d.original_filename
            for d in Document.objects.filter(id__in=doc_ids).only("id", "original_filename")
        }
        for item in items:
            item["document_filename"] = doc_names.get(str(item["document_id"]), "")
            item["id"] = str(item["id"])
            item["document_id"] = str(item["document_id"])
            # Truncate long fields for list view
            item["source_text_context"] = (item["source_text_context"] or "")[:200]

        return Response({
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": items,
        })


class FeedbackDetailView(APIView):
    """DELETE /api/v1/feedback/:id/ — remove a feedback entry."""

    permission_classes = [IsAdminUser]

    def delete(self, request, feedback_id):
        from apps.intelligence.models import FieldFeedback
        deleted, _ = FieldFeedback.objects.filter(id=feedback_id).delete()
        if not deleted:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FineTuneJobListView(APIView):
    """GET /api/v1/finetune/jobs/"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        from apps.intelligence.models import FineTuneJob
        jobs = list(
            FineTuneJob.objects.order_by("-created_at")[:50].values(
                "id", "extraction_type", "status", "azure_job_id",
                "base_model", "fine_tuned_model_id", "feedback_count",
                "estimated_cost_usd", "error_message", "created_at", "updated_at",
            )
        )
        for j in jobs:
            j["id"] = str(j["id"])
        return Response({"results": jobs})


class FineTuneTriggerView(APIView):
    """POST /api/v1/finetune/trigger/  body: {extraction_type}"""

    permission_classes = [IsAdminUser]

    def post(self, request):
        from apps.intelligence.services.finetune_service import trigger
        etype = str(request.data.get("extraction_type") or "").strip()
        if not etype:
            return Response({"error": "extraction_type required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            job = trigger(etype)
            return Response({
                "job_id": str(job.id),
                "status": job.status,
                "feedback_count": job.feedback_count,
                "estimated_cost_usd": job.estimated_cost_usd,
            }, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class AppSettingsView(APIView):
    """
    GET  /api/v1/feedback/settings/   — read all writable settings
    PATCH /api/v1/feedback/settings/  — update one or many
    """

    permission_classes = [IsAdminUser]

    # Allowed keys + their types. Only these are exposed.
    _SCHEMA: dict[str, type] = {
        "FINETUNE_ENABLED": bool,
        "FINETUNE_FEEDBACK_THRESHOLD": int,
        "FINETUNE_MAX_COST_USD": float,
        "FINETUNE_BASE_MODEL": str,
    }

    def _read(self) -> dict:
        from django.conf import settings as django_settings
        from apps.intelligence.models import AppSetting
        result = {}
        for key, typ in self._SCHEMA.items():
            # AppSetting override > Django settings default
            override = AppSetting.get(f"setting_{key}", "")
            if override:
                if typ is bool:
                    result[key] = override.lower() in ("1", "true", "yes")
                elif typ is int:
                    result[key] = int(override)
                elif typ is float:
                    result[key] = float(override)
                else:
                    result[key] = override
            else:
                result[key] = getattr(django_settings, key, None)
        return result

    def get(self, request):
        return Response(self._read())

    def patch(self, request):
        from apps.intelligence.models import AppSetting
        updated = {}
        errors = {}
        for key, value in (request.data or {}).items():
            if key not in self._SCHEMA:
                errors[key] = "Unknown setting"
                continue
            typ = self._SCHEMA[key]
            try:
                if typ is bool:
                    coerced = str(value).lower() in ("1", "true", "yes", "True")
                    AppSetting.set(f"setting_{key}", "1" if coerced else "0", f"Override for {key}")
                    # Also update Django settings in-process so current request sees it
                    from django.conf import settings as ds
                    setattr(ds, key, coerced)
                elif typ is int:
                    coerced = int(value)
                    AppSetting.set(f"setting_{key}", str(coerced), f"Override for {key}")
                    from django.conf import settings as ds
                    setattr(ds, key, coerced)
                elif typ is float:
                    coerced = float(value)
                    AppSetting.set(f"setting_{key}", str(coerced), f"Override for {key}")
                    from django.conf import settings as ds
                    setattr(ds, key, coerced)
                else:
                    AppSetting.set(f"setting_{key}", str(value), f"Override for {key}")
                    from django.conf import settings as ds
                    setattr(ds, key, str(value))
                updated[key] = value
            except (ValueError, TypeError) as exc:
                errors[key] = str(exc)

        resp = {"updated": updated}
        if errors:
            resp["errors"] = errors
        return Response(resp)
