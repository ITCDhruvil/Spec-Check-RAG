"""Start or run summary generation (sync dev path vs Celery)."""

from __future__ import annotations

import logging
import threading

from django.conf import settings

from apps.intelligence.services.orchestrator import IntelligenceOrchestrator
from apps.intelligence.tasks import generate_summary_task

logger = logging.getLogger(__name__)


def dispatch_summary_generation(document_id, *, regenerate: bool) -> tuple[dict, int]:
    """
    Returns (response_body, http_status).
    Sync mode runs the full pipeline in a background thread (dev-friendly, no Celery)
    so long-running work does not block other API requests (e.g. PDF preview).
    Async mode marks processing immediately then enqueues Celery.
    """
    if getattr(settings, "INTELLIGENCE_SYNC_GENERATION", False):
        summary = IntelligenceOrchestrator.begin_processing(
            str(document_id), regenerate=regenerate
        )
        doc_id = str(document_id)

        def _run_sync() -> None:
            try:
                IntelligenceOrchestrator.run(doc_id, regenerate=regenerate)
            except Exception:
                logger.exception(
                    "intelligence_sync_failed document_id=%s regenerate=%s",
                    doc_id,
                    regenerate,
                )

        thread = threading.Thread(
            target=_run_sync,
            name=f"intel-sync-{doc_id[:8]}",
            daemon=True,
        )
        thread.start()
        return {
            "message": "Summary generation started.",
            "document_id": doc_id,
            "summary_id": str(summary.id),
            "regenerate": regenerate,
            "sync": True,
        }, 202

    summary = IntelligenceOrchestrator.begin_processing(str(document_id), regenerate=regenerate)
    async_result = generate_summary_task.delay(str(document_id), regenerate=regenerate)
    return {
        "message": "Summary generation started.",
        "document_id": str(document_id),
        "summary_id": str(summary.id),
        "celery_task_id": async_result.id,
        "regenerate": regenerate,
        "sync": False,
    }, 202
