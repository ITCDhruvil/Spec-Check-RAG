import logging

from celery import shared_task
from django.conf import settings

from apps.processing.choices import PipelineStage, ProcessingErrorType
from apps.processing.errors import StructuredProcessingError
from apps.processing.services.job_service import ProcessingJobService
from apps.processing.services.pipeline_service import DocumentPipelineService

logger = logging.getLogger("apps.celery")


@shared_task(
    bind=True,
    name="processing.process_document",
    autoretry_for=(OSError, ConnectionError),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
)
def process_document_task(self, job_id: str) -> dict:
    """
    Async pipeline: intake validation → document parsing → completed.
    """
    logger.info("task_started job_id=%s celery_task_id=%s", job_id, self.request.id)

    job = ProcessingJobService.get_job(job_id)

    try:
        intake_metadata = DocumentPipelineService.run_intake_validation(job)
        parsing_metadata = DocumentPipelineService.run_document_parsing(job)
        indexing_metadata = DocumentPipelineService.run_chunking_and_indexing(job)

        combined = {
            "pipeline_version": "3.0.0",
            "intake": intake_metadata,
            "parsing": parsing_metadata,
            "chunking_indexing": indexing_metadata,
        }
        ProcessingJobService.mark_pipeline_completed(
            job, metadata_patch={"processing": combined}
        )
        logger.info("task_completed job_id=%s", job_id)
        return {"job_id": job_id, "status": PipelineStage.COMPLETED, "metadata": combined}

    except Exception as exc:
        logger.exception("task_failed job_id=%s attempt=%s", job_id, self.request.retries)

        recoverable = self.request.retries < settings.CELERY_TASK_MAX_RETRIES
        stage = job.current_stage
        if stage in (PipelineStage.EMBEDDING_PROCESSING, PipelineStage.CHUNKING_PROCESSING):
            structured = StructuredProcessingError.from_exception(
                exc,
                stage=stage,
                error_type=(
                    ProcessingErrorType.EMBEDDING_FAILURE
                    if stage == PipelineStage.EMBEDDING_PROCESSING
                    else ProcessingErrorType.CHUNKING_FAILURE
                ),
                recoverable=recoverable,
                retry_count=job.retry_count,
            )
        elif stage == PipelineStage.PARSING_PROCESSING:
            structured = StructuredProcessingError.parsing_failure(
                exc, retry_count=job.retry_count, recoverable=recoverable
            )
        else:
            structured = StructuredProcessingError.intake_failure(
                exc, retry_count=job.retry_count, recoverable=recoverable
            )

        if recoverable:
            ProcessingJobService.increment_retry(job)
            raise self.retry(exc=exc, countdown=settings.CELERY_TASK_DEFAULT_RETRY_DELAY)

        ProcessingJobService.mark_failed(job, structured)
        raise
