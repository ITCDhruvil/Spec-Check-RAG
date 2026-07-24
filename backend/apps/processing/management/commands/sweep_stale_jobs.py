"""
Stale-job watchdog: no document may show "processing" forever.

Finds documents stuck in a non-terminal status with no progress for longer
than the threshold and resolves them:
  • QUEUED / UPLOADED  → re-enqueue once (worker likely died before pickup);
                          if already retried, mark FAILED.
  • mid-pipeline stage → mark FAILED with an honest error (the processing
                          thread/worker died; work will not resume by itself).

Run automatically at server startup (serve.py) and safe to run any time:
    python manage.py sweep_stale_jobs [--max-age-minutes 30] [--dry-run]
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.documents.models import Document
from apps.processing.choices import PipelineStage
from apps.processing.models import ProcessingJob
from apps.processing.services.job_service import ProcessingJobService

logger = logging.getLogger(__name__)

TERMINAL_STATES = {PipelineStage.COMPLETED, PipelineStage.FAILED}
REQUEUEABLE_STATES = {PipelineStage.QUEUED, PipelineStage.UPLOADED}

STALE_RETRY_MARKER = "stale_sweep_requeued"


class Command(BaseCommand):
    help = "Fail or re-enqueue documents stuck in a non-terminal state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-minutes",
            type=int,
            default=30,
            help="Consider a document stale after this many minutes without progress.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report stale documents without changing anything.",
        )

    def handle(self, *args, **options):
        max_age = options["max_age_minutes"]
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timezone.timedelta(minutes=max_age)

        stale_docs = Document.objects.exclude(status__in=TERMINAL_STATES).filter(
            updated_at__lt=cutoff
        )

        requeued = failed = 0
        for doc in stale_docs:
            job = ProcessingJobService.get_latest_job_for_document(doc.id)
            already_requeued = bool(
                job and (job.last_error or {}).get(STALE_RETRY_MARKER)
            )

            if doc.status in REQUEUEABLE_STATES and not already_requeued:
                self.stdout.write(
                    f"requeue  {doc.id} status={doc.status} "
                    f"stale_since={doc.updated_at:%Y-%m-%d %H:%M}"
                )
                if not dry_run:
                    if not job:
                        job = ProcessingJobService.create_job(doc)
                    job.last_error = {
                        **(job.last_error or {}),
                        STALE_RETRY_MARKER: timezone.now().isoformat(),
                    }
                    job.save(update_fields=["last_error", "updated_at"])
                    ProcessingJobService.enqueue_job(job)
                requeued += 1
                continue

            reason = (
                "queued job never picked up (re-enqueue already attempted)"
                if doc.status in REQUEUEABLE_STATES
                else f"processing died mid-stage ({doc.status})"
            )
            self.stdout.write(
                f"fail     {doc.id} status={doc.status} "
                f"stale_since={doc.updated_at:%Y-%m-%d %H:%M} reason={reason}"
            )
            if not dry_run:
                doc.status = PipelineStage.FAILED
                doc.save(update_fields=["status", "updated_at"])
                if job:
                    job.current_stage = PipelineStage.FAILED
                    job.error_code = "stale_job"
                    job.error_message = (
                        f"Marked failed by stale-job sweep: {reason}. "
                        "Use retry to reprocess."
                    )
                    job.completed_at = timezone.now()
                    job.save(
                        update_fields=[
                            "current_stage",
                            "error_code",
                            "error_message",
                            "completed_at",
                            "updated_at",
                        ]
                    )
                # A processing summary from the dead run must not block retries.
                from apps.intelligence.models import GeneratedSummary

                GeneratedSummary.objects.filter(
                    document=doc, is_current=True, status="processing"
                ).update(status="failed", error_message="Stale-job sweep: processing died.")
            failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"sweep complete: requeued={requeued} failed={failed} "
                f"(threshold {max_age}m{', dry-run' if dry_run else ''})"
            )
        )
