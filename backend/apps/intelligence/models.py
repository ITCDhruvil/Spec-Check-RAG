from django.db import models

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.documents.models import Document
from apps.intelligence.choices import (
    ExtractionType,
    LearnedEntryKind,
    LearnedTermSource,
    SummaryStatus,
)
from apps.parsing.models import ParsedDocument


class GeneratedSummary(UUIDPrimaryKeyModel, TimeStampedModel):
    """Grounded procurement summary for a document."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="generated_summaries",
    )
    status = models.CharField(
        max_length=32,
        choices=SummaryStatus.choices,
        default=SummaryStatus.PENDING,
        db_index=True,
    )
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True, db_index=True)
    summary_json = models.JSONField(default=dict, blank=True)
    model_metadata = models.JSONField(default=dict, blank=True)
    total_tokens = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    last_error = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["document", "is_current"]),
        ]

    def __str__(self) -> str:
        return f"Summary v{self.version} for {self.document_id} [{self.status}]"


class DocumentChunk(UUIDPrimaryKeyModel, TimeStampedModel):
    """Section-aware semantic chunk for extraction."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    parsed_document = models.ForeignKey(
        ParsedDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
        null=True,
        blank=True,
    )
    section_title = models.CharField(max_length=512)
    page_start = models.PositiveIntegerField(default=1)
    page_end = models.PositiveIntegerField(default=1)
    chunk_order = models.PositiveIntegerField(default=0)
    chunk_text = models.TextField()
    contextual_prefix = models.TextField(
        blank=True,
        default="",
        help_text="LLM-generated context snippet prepended for retrieval (Contextual Retrieval).",
    )
    char_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["chunk_order"]
        indexes = [
            models.Index(fields=["document", "chunk_order"]),
        ]

    @property
    def contextualized_text(self) -> str:
        """chunk_text prefixed with contextual_prefix when available (retrieval-only)."""
        if self.contextual_prefix:
            return f"{self.contextual_prefix}\n\n{self.chunk_text}"
        return self.chunk_text

    def __str__(self) -> str:
        return f"Chunk {self.chunk_order} ({self.section_title})"


class ExtractedInsight(UUIDPrimaryKeyModel, TimeStampedModel):
    """Structured procurement extraction with source grounding."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="extracted_insights",
    )
    generated_summary = models.ForeignKey(
        GeneratedSummary,
        on_delete=models.CASCADE,
        related_name="insights",
        null=True,
        blank=True,
    )
    extraction_type = models.CharField(
        max_length=64,
        choices=ExtractionType.choices,
        db_index=True,
    )
    payload = models.JSONField(
        default=dict,
        help_text='{"items": [{"requirement", "page", "section", "source_text", "confidence"}]}',
    )
    confidence_score = models.FloatField(default=0.0)
    model_name = models.CharField(max_length=128, blank=True)
    prompt_version = models.CharField(max_length=32, blank=True)
    token_usage = models.JSONField(default=dict, blank=True)
    chunk_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["extraction_type"]
        indexes = [
            models.Index(fields=["document", "extraction_type"]),
            models.Index(fields=["generated_summary", "extraction_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.extraction_type} ({self.document_id})"


class LearnedExtractionTerm(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Cross-document learned vocabulary for adaptive extraction (Layer 1 cache).

    Layer 2 (LLM) writes new terms here; Layer 1 loads this table before each document
    to reduce repeated LLM lexicon calls. Duplicates are merged on term_normalized.
    """

    extraction_type = models.CharField(
        max_length=64,
        choices=ExtractionType.choices,
        db_index=True,
    )
    entry_kind = models.CharField(
        max_length=16,
        choices=LearnedEntryKind.choices,
        default=LearnedEntryKind.TERM,
        db_index=True,
    )
    term_normalized = models.CharField(
        max_length=256,
        db_index=True,
        help_text="Lowercase dedupe key",
    )
    term_display = models.CharField(
        max_length=512,
        help_text="Preferred display text (latest seen casing)",
    )
    source = models.CharField(
        max_length=32,
        choices=LearnedTermSource.choices,
        default=LearnedTermSource.HEURISTIC,
    )
    hit_count = models.PositiveIntegerField(default=1)
    document_count = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-hit_count", "term_display"]
        constraints = [
            models.UniqueConstraint(
                fields=["extraction_type", "entry_kind", "term_normalized"],
                name="uniq_learned_term_per_type_kind",
            ),
        ]
        indexes = [
            models.Index(fields=["extraction_type", "entry_kind", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.extraction_type}/{self.entry_kind}: {self.term_display}"


# ---------------------------------------------------------------------------
# Feedback + fine-tuning pipeline (C5)
# ---------------------------------------------------------------------------

class FeedbackRating(models.TextChoices):
    UP = "up", "Thumbs up"
    DOWN = "down", "Thumbs down"


class FeedbackIssueType(models.TextChoices):
    WRONG_VALUE = "wrong_value", "Extracted wrong value"
    WRONG_SOURCE = "wrong_source", "Wrong source / citation"
    MISSING = "missing", "Value is missing"
    OTHER = "other", "Other"


class FieldFeedback(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    User feedback on a single extracted spec-check field.

    Negative feedback drives fine-tuning dataset construction; positive
    feedback reinforces the current extraction path.
    """

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="field_feedbacks",
    )
    field_key = models.CharField(max_length=128, db_index=True)
    extraction_type = models.CharField(
        max_length=64,
        choices=ExtractionType.choices,
        db_index=True,
    )
    doc_type = models.CharField(
        max_length=64,
        blank=True,
        help_text="Classified solicitation type (federal_rfq / state_ifb / rfp / …)",
    )
    rating = models.CharField(
        max_length=8,
        choices=FeedbackRating.choices,
        db_index=True,
    )
    issue_type = models.CharField(
        max_length=32,
        choices=FeedbackIssueType.choices,
        blank=True,
    )
    # What the system extracted (stored for dataset construction).
    extracted_value = models.TextField(blank=True)
    # What the user says is correct (blank = user only flagged, no correction given).
    correct_value = models.TextField(blank=True)
    comment = models.TextField(blank=True)
    # Verbatim source text from the citation — used as LLM context for fine-tune dataset.
    source_text_context = models.TextField(blank=True)
    # Prevent double-use in fine-tuning runs.
    used_in_finetune = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["extraction_type", "rating", "used_in_finetune"]),
            models.Index(fields=["document", "field_key"]),
        ]

    def __str__(self) -> str:
        return f"{self.rating} on {self.field_key} ({self.document_id})"


class FineTuneJobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    UPLOADING = "uploading", "Uploading dataset"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class FineTuneJob(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Tracks a single Azure OpenAI fine-tuning job triggered from feedback.

    On success: fine_tuned_model_id is stored and model_routing picks it up.
    On failure: error_message explains what went wrong; base model stays active.
    """

    extraction_type = models.CharField(
        max_length=64,
        choices=ExtractionType.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=FineTuneJobStatus.choices,
        default=FineTuneJobStatus.PENDING,
        db_index=True,
    )
    azure_job_id = models.CharField(max_length=256, blank=True, db_index=True)
    azure_file_id = models.CharField(max_length=256, blank=True)
    base_model = models.CharField(max_length=128, blank=True)
    fine_tuned_model_id = models.CharField(max_length=256, blank=True)
    feedback_count = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"FineTuneJob {self.extraction_type} [{self.status}]"


class AppSetting(TimeStampedModel):
    """
    Single-row application settings table (one row per key).
    Used for maintenance mode flag and active fine-tuned model IDs.
    """

    key = models.CharField(max_length=128, primary_key=True)
    value = models.TextField(blank=True)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key}={self.value[:40]}"

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key: str, value: str, description: str = "") -> None:
        cls.objects.update_or_create(
            key=key,
            defaults={"value": value, "description": description},
        )
