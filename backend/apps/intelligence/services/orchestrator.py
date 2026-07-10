import logging

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError, ValidationServiceError
from apps.documents.choices import SourceReferenceKind
from apps.documents.models import Document, SourceReference
from apps.intelligence.choices import SummaryStatus
from apps.intelligence.models import DocumentChunk, ExtractedInsight, GeneratedSummary
from apps.intelligence.services.chunking_service import ChunkingService
from apps.intelligence.services.extraction_service import ExtractionService
from apps.intelligence.services.summary_service import SummaryService
from apps.parsing.choices import ParsingStatus
from apps.parsing.models import ParsedDocument
from apps.processing.choices import PipelineStage
from apps.processing.choices import ProcessingErrorType
from apps.processing.errors import StructuredProcessingError
from apps.processing.models import ProcessingJob
from apps.processing.services.job_service import ProcessingJobService

logger = logging.getLogger(__name__)


class IntelligenceOrchestrator:
    @staticmethod
    def ensure_parsed(document: Document) -> ParsedDocument:
        try:
            parsed = document.parsed_document
        except ParsedDocument.DoesNotExist as exc:
            raise ValidationServiceError(
                "Document must be parsed before generating summary.",
                code="parsing_required",
            ) from exc
        if parsed.parsing_status != ParsingStatus.COMPLETED:
            raise ValidationServiceError(
                "Parsing is not complete.",
                code="parsing_incomplete",
            )
        return parsed

    @staticmethod
    @transaction.atomic
    def prepare_summary_record(document: Document, *, regenerate: bool) -> GeneratedSummary:
        if regenerate:
            GeneratedSummary.objects.filter(document=document, is_current=True).update(
                is_current=False
            )
            last_version = (
                GeneratedSummary.objects.filter(document=document)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            )
            version = last_version + 1
        else:
            existing = GeneratedSummary.objects.filter(
                document=document, is_current=True
            ).first()
            if existing and existing.status == SummaryStatus.COMPLETED:
                raise ValidationServiceError(
                    "Summary already exists. Use regenerate.",
                    code="summary_exists",
                )
            if existing and existing.status == SummaryStatus.PROCESSING:
                raise ValidationServiceError(
                    "Summary generation already in progress.",
                    code="summary_in_progress",
                )
            version = 1
            if existing:
                version = existing.version
                existing.delete()

        return GeneratedSummary.objects.create(
            document=document,
            status=SummaryStatus.PROCESSING,
            version=version,
            is_current=True,
            started_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def begin_processing(document_id, *, regenerate: bool) -> GeneratedSummary:
        """Mark document + summary as processing before Celery picks up the task."""
        document = Document.objects.select_related("parsed_document", "version").get(
            pk=document_id
        )
        IntelligenceOrchestrator.ensure_parsed(document)
        summary = IntelligenceOrchestrator.prepare_summary_record(document, regenerate=regenerate)

        if regenerate:
            SourceReference.objects.filter(
                document=document,
                reference_kind=SourceReferenceKind.EXTRACTION,
            ).delete()
            ExtractedInsight.objects.filter(document=document).delete()

        job = ProcessingJobService.get_latest_job_for_document(document.id)
        if not job:
            job = ProcessingJobService.create_job(document)

        ProcessingJobService.transition_to(job, PipelineStage.CHUNKING_PROCESSING)
        logger.info(
            "intelligence_begin_processing document_id=%s summary_id=%s regenerate=%s",
            document_id,
            summary.id,
            regenerate,
        )
        return summary

    @staticmethod
    def run(document_id, *, regenerate: bool = False) -> dict:
        document = Document.objects.select_related("parsed_document", "version").get(
            pk=document_id
        )
        IntelligenceOrchestrator.ensure_parsed(document)

        summary = GeneratedSummary.objects.filter(
            document=document, is_current=True, status=SummaryStatus.PROCESSING
        ).first()

        if summary:
            job = ProcessingJobService.get_latest_job_for_document(document.id)
            if not job:
                job = ProcessingJobService.create_job(document)
        else:
            summary = IntelligenceOrchestrator.prepare_summary_record(
                document, regenerate=regenerate
            )
            if regenerate:
                SourceReference.objects.filter(
                    document=document,
                    reference_kind=SourceReferenceKind.EXTRACTION,
                ).delete()
            job = ProcessingJobService.get_latest_job_for_document(document.id)
            if not job:
                job = ProcessingJobService.create_job(document)
            ProcessingJobService.transition_to(job, PipelineStage.CHUNKING_PROCESSING)

        total_tokens = 0

        try:
            if document.status != PipelineStage.CHUNKING_PROCESSING:
                ProcessingJobService.transition_to(job, PipelineStage.CHUNKING_PROCESSING)

            from apps.intelligence.services.fast_mode import (
                skip_chunking_in_intelligence,
                skip_embedding_in_intelligence,
            )

            existing_chunks = list(
                DocumentChunk.objects.filter(document=document).order_by("chunk_order")
            )
            if skip_chunking_in_intelligence():
                if regenerate and existing_chunks:
                    DocumentChunk.objects.filter(document=document).delete()
                chunks = []
                logger.info(
                    "chunking_skipped document_id=%s reason=group_extraction",
                    document_id,
                )
            elif regenerate or not existing_chunks:
                chunks = ChunkingService.build_chunks(document)
            else:
                chunks = existing_chunks
            ProcessingJobService.complete_stage(job, PipelineStage.CHUNKING_COMPLETED)

            if skip_embedding_in_intelligence():
                logger.info(
                    "embedding_skipped document_id=%s reason=fast_mode",
                    document_id,
                )
                ProcessingJobService.complete_stage(job, PipelineStage.EMBEDDING_COMPLETED)
            else:
                ProcessingJobService.transition_to(job, PipelineStage.EMBEDDING_PROCESSING)
                from apps.chat.services.index_service import VectorIndexService

                VectorIndexService.index_document(document, force=regenerate)
                ProcessingJobService.complete_stage(job, PipelineStage.EMBEDDING_COMPLETED)

            ProcessingJobService.transition_to(job, PipelineStage.EXTRACTION_PROCESSING)
            ExtractedInsight.objects.filter(
                document=document, generated_summary=summary
            ).delete()
            insights = ExtractionService.run_extractions(document, summary, chunks)
            ProcessingJobService.complete_stage(job, PipelineStage.EXTRACTION_COMPLETED)

            ProcessingJobService.transition_to(job, PipelineStage.SUMMARY_PROCESSING)
            summary = SummaryService.generate_final_summary(document, summary, insights)
            ProcessingJobService.complete_stage(job, PipelineStage.SUMMARY_PROCESSING)
            ProcessingJobService.mark_pipeline_completed(
                job,
                metadata_patch={
                    "intelligence": {
                        "summary_id": str(summary.id),
                        "version": summary.version,
                        "total_tokens": summary.total_tokens,
                    }
                },
            )

            total_tokens = summary.total_tokens
            return {
                "summary_id": str(summary.id),
                "version": summary.version,
                "status": summary.status,
                "chunk_count": len(chunks),
                "insight_count": len(insights),
                "total_tokens": total_tokens,
            }

        except Exception as exc:
            logger.exception("intelligence_failed document_id=%s", document_id)
            summary.status = SummaryStatus.FAILED
            summary.error_message = str(exc)[:2000]
            summary.completed_at = timezone.now()
            error_type = (
                ProcessingErrorType.EXTRACTION_FAILURE
                if job.current_stage == PipelineStage.EXTRACTION_PROCESSING
                else ProcessingErrorType.SUMMARY_FAILURE
            )
            structured = StructuredProcessingError.from_exception(
                exc,
                stage=job.current_stage,
                error_type=error_type,
                recoverable=False,
                retry_count=0,
            )
            summary.last_error = structured.to_dict()
            summary.save()

            ProcessingJobService.mark_failed(job, structured)
            raise
