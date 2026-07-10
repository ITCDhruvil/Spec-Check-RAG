from django.db import models

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.documents.models import Document
from apps.parsing.choices import ExtractionMethod, ParsingStatus


class ParsedDocument(UUIDPrimaryKeyModel, TimeStampedModel):
    """Structured parse output for an uploaded document."""

    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="parsed_document",
    )
    parsing_status = models.CharField(
        max_length=32,
        choices=ParsingStatus.choices,
        default=ParsingStatus.PENDING,
        db_index=True,
    )
    total_pages = models.PositiveIntegerField(default=0)
    raw_text = models.TextField(blank=True)
    structured_text = models.TextField(
        blank=True,
        help_text="Normalized reading-order text with section markers.",
    )
    parsing_metadata = models.JSONField(default=dict, blank=True)
    parsing_quality_score = models.FloatField(
        default=0.0,
        help_text="Aggregate quality 0.0–1.0 across pages.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Parsed {self.document_id} ({self.parsing_status})"


class DocumentPage(UUIDPrimaryKeyModel, TimeStampedModel):
    """Page-level extracted text and quality metrics."""

    parsed_document = models.ForeignKey(
        ParsedDocument,
        on_delete=models.CASCADE,
        related_name="pages",
    )
    page_number = models.PositiveIntegerField()
    extracted_text = models.TextField(blank=True)
    extraction_method = models.CharField(
        max_length=32,
        choices=ExtractionMethod.choices,
        default=ExtractionMethod.NATIVE_PDF,
    )
    ocr_used = models.BooleanField(default=False)
    quality_score = models.FloatField(default=0.0)

    class Meta:
        ordering = ["page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["parsed_document", "page_number"],
                name="unique_parsed_page_number",
            ),
        ]

    def __str__(self) -> str:
        return f"Page {self.page_number} ({self.parsed_document_id})"


class DocumentSection(UUIDPrimaryKeyModel, TimeStampedModel):
    """Heuristic section split for downstream summarization."""

    parsed_document = models.ForeignKey(
        ParsedDocument,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    title = models.CharField(max_length=512)
    content = models.TextField(blank=True)
    page_start = models.PositiveIntegerField(default=1)
    page_end = models.PositiveIntegerField(default=1)
    section_order = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(
        default=1,
        help_text="Hierarchy depth (1=top, 2=1.1, etc.).",
    )
    parent_section_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="section_order of parent section, if nested.",
    )
    section_path = models.CharField(
        max_length=1024,
        blank=True,
        help_text='Full path, e.g. "Instructions > 1.1 Submission".',
    )

    class Meta:
        ordering = ["section_order"]

    def __str__(self) -> str:
        return f"{self.section_order}. {self.title}"
