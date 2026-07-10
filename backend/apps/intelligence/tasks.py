import logging

from celery import shared_task
from django.conf import settings

from apps.intelligence.services.orchestrator import IntelligenceOrchestrator

logger = logging.getLogger("apps.celery")



@shared_task(
    bind=True,
    name="intelligence.generate_summary",
    max_retries=settings.CELERY_TASK_MAX_RETRIES,
)
def generate_summary_task(self, document_id: str, regenerate: bool = False) -> dict:
    logger.info(
        "generate_summary_started document_id=%s regenerate=%s",
        document_id,
        regenerate,
    )
    try:
        result = IntelligenceOrchestrator.run(document_id, regenerate=regenerate)
        logger.info("generate_summary_completed document_id=%s", document_id)
        return result
    except Exception as exc:
        logger.exception("generate_summary_failed document_id=%s", document_id)
        if self.request.retries < settings.CELERY_TASK_MAX_RETRIES:
            raise self.retry(exc=exc, countdown=settings.CELERY_TASK_DEFAULT_RETRY_DELAY)
        raise


@shared_task(
    bind=True,
    name="intelligence.check_finetune_threshold",
    max_retries=1,
)
def check_finetune_threshold_task(self, extraction_type: str) -> dict:
    """Check if enough feedback to trigger fine-tuning for an extraction type."""
    from apps.intelligence.services.finetune_service import check_and_trigger
    try:
        check_and_trigger(extraction_type)
        return {"extraction_type": extraction_type}
    except Exception as exc:
        logger.exception("check_finetune_threshold_failed extraction_type=%s", extraction_type)
        raise


@shared_task(
    bind=True,
    name="intelligence.poll_finetune_job",
    max_retries=0,  # called on a schedule; don't auto-retry
)
def poll_finetune_job_task(self, job_id: str) -> dict:
    """
    Poll an in-flight Azure fine-tune job.
    Scheduled by Celery beat every 5 minutes while job is running.
    """
    from apps.intelligence.services.finetune_service import poll_job
    try:
        new_status = poll_job(job_id)
        logger.info("poll_finetune_job job_id=%s new_status=%s", job_id, new_status)
        return {"job_id": job_id, "status": new_status}
    except Exception:
        logger.exception("poll_finetune_job_failed job_id=%s", job_id)
        raise
