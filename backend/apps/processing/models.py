from django.db import models

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.documents.models import Document
from apps.processing.choices import PipelineStage, StageLogState


class ProcessingJob(UUIDPrimaryKeyModel, TimeStampedModel):
    """Async processing job with granular stages and structured failure records."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="processing_jobs",
    )
    current_stage = models.CharField(
        max_length=64,
        choices=PipelineStage.choices,
        default=PipelineStage.QUEUED,
        db_index=True,
    )
    completed_stages = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered list of stage values successfully completed.",
    )
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    last_error = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured error: error_type, stage, recoverable, retry_count, details.",
    )
    # Legacy plain-text fields kept for quick filtering; canonical source is last_error
    error_message = models.TextField(blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["current_stage", "-created_at"]),
            models.Index(fields=["document", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Job {self.id} [{self.current_stage}] for {self.document_id}"

    @property
    def status(self) -> str:
        """API alias for current_stage."""
        return self.current_stage

    @property
    def pipeline_stage(self) -> str:
        """Backward-compatible alias."""
        return self.current_stage


class ProcessingStageLog(UUIDPrimaryKeyModel):
    """Per-stage audit trail for partial recovery and debugging."""

    job = models.ForeignKey(
        ProcessingJob,
        on_delete=models.CASCADE,
        related_name="stage_logs",
    )
    stage = models.CharField(max_length=64, choices=PipelineStage.choices, db_index=True)
    state = models.CharField(max_length=16, choices=StageLogState.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["started_at"]
        indexes = [
            models.Index(fields=["job", "stage"]),
        ]

    def __str__(self) -> str:
        return f"{self.job_id} {self.stage} {self.state}"
