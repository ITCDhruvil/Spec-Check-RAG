import logging
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.http import FileResponse
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView, RetrieveDestroyAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
    DocumentUploadResponseSerializer,
    DocumentStatusSerializer,
    ProcessingJobSummarySerializer,
    TenderDetailSerializer,
    TenderSummarySerializer,
)
from apps.documents.services.document_service import DocumentService
from apps.documents.services.tender_service import TenderService
from apps.documents.throttles import UploadRateThrottle
from apps.documents.utils.paths import get_document_absolute_path
from apps.processing.services.job_service import ProcessingJobService

logger = logging.getLogger(__name__)


class DocumentUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UploadRateThrottle]

    def post(self, request):
        uploaded = request.FILES.get("file")
        tender_id = request.data.get("tender_id") or None
        if tender_id:
            tender_id = UUID(str(tender_id))

        supersedes = request.data.get("supersedes_version_id") or None
        if supersedes:
            supersedes = UUID(str(supersedes))

        document = DocumentService.upload(
            uploaded,
            uploaded_by=request.user,
            tender_id=tender_id,
            tender_reference=request.data.get("tender_reference"),
            tender_title=request.data.get("tender_title"),
            organization=request.data.get("organization", ""),
            version_type=request.data.get("version_type"),
            version_label=request.data.get("version_label"),
            supersedes_version_id=supersedes,
            version_notes=request.data.get("version_notes", ""),
        )
        serializer = DocumentUploadResponseSerializer(document)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentListView(ListAPIView):
    serializer_class = DocumentListSerializer

    def get_queryset(self):
        return DocumentService.list_documents(user=self.request.user)


class DocumentDetailView(RetrieveDestroyAPIView):
    serializer_class = DocumentDetailSerializer
    lookup_url_kwarg = "document_id"

    def get_object(self):
        return DocumentService.get_document(self.kwargs["document_id"], self.request.user)

    def perform_destroy(self, instance):
        DocumentService.delete_document(instance.id, user=self.request.user)


class DocumentProcessKickView(APIView):
    """Start or restart the processing pipeline for a document.

    Accepts documents in QUEUED, UPLOADED, or FAILED status.
    For FAILED documents, intelligently resumes from the right stage:
    - If parsing already completed → re-dispatches intelligence (summary) only.
    - Otherwise → resets to QUEUED and re-runs the full pipeline.
    """

    def post(self, request, document_id):
        from apps.processing.choices import PipelineStage

        document = DocumentService.get_document(document_id, request.user)

        # Allow restarting failed documents.
        if document.status == PipelineStage.FAILED:
            return self._restart_failed(document)

        if document.status not in (PipelineStage.QUEUED, PipelineStage.UPLOADED):
            return Response(
                {
                    "message": "Document is already being processed or finished.",
                    "status": document.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        job = ProcessingJobService.get_latest_job_for_document(document.id)
        if not job:
            job = ProcessingJobService.create_job(document)

        ProcessingJobService.enqueue_job(job)
        return Response(
            {
                "message": "Processing started.",
                "document_id": str(document.id),
                "job_id": str(job.id),
                "sync": getattr(settings, "PROCESSING_SYNC", False),
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def _restart_failed(self, document):
        """Resume a failed/cancelled document from the earliest incomplete stage."""
        from apps.processing.choices import PipelineStage

        # If parsing was already complete we can skip straight to intelligence.
        parsing_done = False
        try:
            from apps.parsing.models import ParsingStatus
            parsed = document.parsed_document
            parsing_done = parsed.parsing_status == ParsingStatus.COMPLETED
        except Exception:
            parsing_done = False

        if parsing_done:
            # Re-dispatch summary generation (chunking → extraction → summary).
            from apps.intelligence.models import GeneratedSummary
            from apps.intelligence.services.generation_dispatch import dispatch_summary_generation

            # Retire any stale failed summary so a fresh one is created.
            GeneratedSummary.objects.filter(
                document=document, is_current=True, status="failed"
            ).update(is_current=False)

            try:
                body, http_status = dispatch_summary_generation(
                    document.id, regenerate=False
                )
                return Response(body, status=http_status)
            except Exception as exc:
                return Response(
                    {"error": {"message": str(exc)}},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Parsing was incomplete — reset and restart the full pipeline.
        document.status = PipelineStage.QUEUED
        document.save(update_fields=["status", "updated_at"])

        # Retire any stale summaries so they don't block auto-generation later.
        from apps.intelligence.models import GeneratedSummary
        GeneratedSummary.objects.filter(
            document=document, is_current=True, status="failed"
        ).update(is_current=False)

        job = ProcessingJobService.create_job(document)
        ProcessingJobService.enqueue_job(job)
        return Response(
            {
                "message": "Processing restarted from beginning.",
                "document_id": str(document.id),
                "job_id": str(job.id),
                "sync": getattr(settings, "PROCESSING_SYNC", False),
            },
            status=status.HTTP_202_ACCEPTED,
        )


@method_decorator(xframe_options_exempt, name="dispatch")
class DocumentFileView(APIView):
    """Stream the original uploaded file for in-browser preview."""

    def get(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        file_path = get_document_absolute_path(document)
        if not file_path.is_file():
            return Response(
                {"error": {"message": "Document file not found on storage.", "code": "file_not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )

        response = FileResponse(
            file_path.open("rb"),
            content_type=document.mime_type or "application/octet-stream",
            as_attachment=False,
            filename=document.original_filename,
        )
        response["Content-Disposition"] = (
            f'inline; filename="{document.original_filename}"'
        )
        response["Cache-Control"] = "private, max-age=3600"
        return response


@method_decorator(xframe_options_exempt, name="dispatch")
class DocumentPreviewFileView(APIView):
    """Stream a layout-faithful PDF preview for DOCX (generated at parse time)."""

    def head(self, request, document_id):
        from apps.parsing.services.docx_preview_service import get_preview_pdf_path

        document = DocumentService.get_document(document_id, request.user)
        if not document.original_filename.lower().endswith(".docx"):
            return Response(status=status.HTTP_404_NOT_FOUND)
        if get_preview_pdf_path(document):
            return Response(status=status.HTTP_200_OK)
        return Response(status=status.HTTP_404_NOT_FOUND)

    def get(self, request, document_id):
        from apps.parsing.services.docx_preview_service import (
            attach_docx_preview_metadata,
            get_preview_pdf_path,
        )

        document = DocumentService.get_document(document_id, request.user)
        if not document.original_filename.lower().endswith(".docx"):
            return Response(
                {
                    "error": {
                        "message": "Preview PDF is only available for DOCX documents.",
                        "code": "preview_not_applicable",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        file_path = get_preview_pdf_path(document)
        if not file_path:
            try:
                attach_docx_preview_metadata(document)
            except Exception:
                logger.exception(
                    "docx_preview_generation_failed document_id=%s",
                    document.id,
                )
            document.refresh_from_db()
            file_path = get_preview_pdf_path(document)

        if not file_path:
            return Response(
                {
                    "error": {
                        "message": "DOCX preview PDF is not available. Install LibreOffice or Microsoft Word for conversion.",
                        "code": "preview_not_ready",
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        preview_name = f"{Path(document.original_filename).stem}-preview.pdf"
        response = FileResponse(
            file_path.open("rb"),
            content_type="application/pdf",
            as_attachment=False,
            filename=preview_name,
        )
        response["Content-Disposition"] = f'inline; filename="{preview_name}"'
        response["Cache-Control"] = "private, max-age=3600"
        return response


class DocumentStatusView(APIView):
    def get(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        latest_job = ProcessingJobService.get_latest_job_for_document(document.id)
        payload = {
            "document_id": document.id,
            "status": document.status,
            "completed_stages": latest_job.completed_stages if latest_job else [],
            "latest_job": (
                ProcessingJobSummarySerializer(latest_job).data if latest_job else None
            ),
        }
        serializer = DocumentStatusSerializer(payload)
        return Response(serializer.data)


class TenderListView(ListAPIView):
    serializer_class = TenderSummarySerializer

    def get_queryset(self):
        return TenderService.list_tenders(user=self.request.user)


class TenderDetailView(RetrieveAPIView):
    serializer_class = TenderDetailSerializer
    lookup_url_kwarg = "tender_id"

    def get_object(self):
        return TenderService.get_tender(self.kwargs["tender_id"], user=self.request.user)
