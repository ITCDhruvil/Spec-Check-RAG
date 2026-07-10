import logging
import threading

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ValidationServiceError
from apps.documents.models import Document
from apps.processing.choices import ACTIVE_STAGES, PipelineStage, StageLogState
from apps.processing.errors import StructuredProcessingError
from apps.processing.models import ProcessingJob, ProcessingStageLog

logger = logging.getLogger(__name__)


class ProcessingJobService:
    @staticmethod
    def create_job(document: Document) -> ProcessingJob:
        job = ProcessingJob.objects.create(
            document=document,
            current_stage=PipelineStage.QUEUED,
            max_retries=settings.CELERY_TASK_MAX_RETRIES,
        )
        document.status = PipelineStage.QUEUED
        document.save(update_fields=["status", "updated_at"])
        ProcessingJobService._log_stage(job, PipelineStage.QUEUED, StageLogState.COMPLETED)
        logger.info("processing_job_created job_id=%s document_id=%s", job.id, document.id)
        return job

    @staticmethod
    def enqueue_job(job: ProcessingJob) -> None:
        from apps.processing.tasks import process_document_task

        job_id = str(job.id)

        if getattr(settings, "PROCESSING_SYNC", False):

            def _run_sync() -> None:
                try:
                    process_document_task.apply(args=[job_id])
                except Exception:
                    logger.exception("processing_sync_failed job_id=%s", job_id)

            thread = threading.Thread(
                target=_run_sync,
                name=f"process-doc-{job_id[:8]}",
                daemon=True,
            )
            thread.start()
            job.celery_task_id = f"sync-{job_id[:12]}"
            job.save(update_fields=["celery_task_id", "updated_at"])
            logger.info("processing_job_started_sync job_id=%s", job.id)
            return

        async_result = process_document_task.apply_async(args=[job_id])
        job.celery_task_id = async_result.id
        job.save(update_fields=["celery_task_id", "updated_at"])
        logger.info(
            "processing_job_enqueued job_id=%s celery_task_id=%s",
            job.id,
            async_result.id,
        )

    @staticmethod
    def get_job(job_id) -> ProcessingJob:
        try:
            return (
                ProcessingJob.objects.select_related("document")
                .prefetch_related("stage_logs")
                .get(pk=job_id)
            )
        except ProcessingJob.DoesNotExist as exc:
            raise ValidationServiceError("Processing job not found.", code="job_not_found") from exc

    @staticmethod
    def get_latest_job_for_document(document_id) -> ProcessingJob | None:
        return (
            ProcessingJob.objects.filter(document_id=document_id)
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    @transaction.atomic
    def transition_to(job: ProcessingJob, stage: str) -> None:
        now = timezone.now()
        if stage in ACTIVE_STAGES and not job.started_at:
            job.started_at = now
        job.current_stage = stage
        job.save(update_fields=["current_stage", "started_at", "updated_at"])

        doc = job.document
        doc.status = stage
        doc.save(update_fields=["status", "updated_at"])

        ProcessingJobService._log_stage(job, stage, StageLogState.STARTED)

    @staticmethod
    @transaction.atomic
    def complete_stage(job: ProcessingJob, stage: str) -> None:
        completed = list(job.completed_stages or [])
        if stage not in completed:
            completed.append(stage)
        job.completed_stages = completed
        job.current_stage = stage
        job.save(update_fields=["completed_stages", "current_stage", "updated_at"])

        doc = job.document
        doc.status = stage
        doc.save(update_fields=["status", "updated_at"])

        ProcessingJobService._close_stage_log(job, stage, StageLogState.COMPLETED)
        logger.info("stage_completed job_id=%s stage=%s", job.id, stage)

    @staticmethod
    @transaction.atomic
    def mark_pipeline_completed(job: ProcessingJob, metadata_patch: dict | None = None) -> None:
        now = timezone.now()
        ProcessingJobService.complete_stage(job, PipelineStage.COMPLETED)
        job.completed_at = now
        job.last_error = {}
        job.error_message = ""
        job.error_code = ""
        job.save(
            update_fields=[
                "completed_at",
                "last_error",
                "error_message",
                "error_code",
                "updated_at",
            ]
        )

        doc = job.document
        doc.status = PipelineStage.COMPLETED
        if metadata_patch:
            doc.metadata = {**doc.metadata, **metadata_patch}
            doc.save(update_fields=["status", "metadata", "updated_at"])
        else:
            doc.save(update_fields=["status", "updated_at"])

        logger.info("processing_job_completed job_id=%s document_id=%s", job.id, doc.id)

    @staticmethod
    @transaction.atomic
    def mark_failed(job: ProcessingJob, error: StructuredProcessingError) -> None:
        now = timezone.now()
        error_dict = error.to_dict()

        job.current_stage = PipelineStage.FAILED
        job.completed_at = now
        job.last_error = error_dict
        job.error_message = error.message[:2000]
        job.error_code = error.error_type
        job.save(
            update_fields=[
                "current_stage",
                "completed_at",
                "last_error",
                "error_message",
                "error_code",
                "updated_at",
            ]
        )

        doc = job.document
        doc.status = PipelineStage.FAILED
        doc.save(update_fields=["status", "updated_at"])

        ProcessingJobService._close_stage_log(
            job,
            error.stage,
            StageLogState.FAILED,
            error=error_dict,
        )

        logger.error(
            "processing_job_failed job_id=%s document_id=%s error=%s",
            job.id,
            doc.id,
            error_dict,
        )

    @staticmethod
    @transaction.atomic
    def increment_retry(job: ProcessingJob, return_stage: str = PipelineStage.QUEUED) -> None:
        job.retry_count += 1
        job.current_stage = return_stage
        job.save(update_fields=["retry_count", "current_stage", "updated_at"])
        doc = job.document
        doc.status = return_stage
        doc.save(update_fields=["status", "updated_at"])

    @staticmethod
    def _log_stage(job: ProcessingJob, stage: str, state: str) -> None:
        ProcessingStageLog.objects.create(job=job, stage=stage, state=state)

    @staticmethod
    def _close_stage_log(
        job: ProcessingJob,
        stage: str,
        state: str,
        error: dict | None = None,
    ) -> None:
        log = (
            ProcessingStageLog.objects.filter(
                job=job,
                stage=stage,
                state=StageLogState.STARTED,
                completed_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )
        if log:
            log.state = state
            log.completed_at = timezone.now()
            if error:
                log.error = error
            log.save(update_fields=["state", "completed_at", "error"])
        else:
            ProcessingStageLog.objects.create(
                job=job,
                stage=stage,
                state=state,
                completed_at=timezone.now(),
                error=error or {},
            )

