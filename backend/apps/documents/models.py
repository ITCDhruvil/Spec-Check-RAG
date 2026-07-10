from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.documents.choices import DocumentVersionType, SourceReferenceKind, TenderStatus
from apps.processing.choices import PipelineStage


class Tender(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Procurement package grouping all document versions (RFP, corrigendums, clarifications).
    """

    reference_code = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Business reference, e.g. RFP-2026-0142",
    )
    title = models.CharField(max_length=512)
    organization = models.CharField(max_length=256, blank=True)
    status = models.CharField(
        max_length=32,
        choices=TenderStatus.choices,
        default=TenderStatus.ACTIVE,
        db_index=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.reference_code} — {self.title}"


class Document(UUIDPrimaryKeyModel, TimeStampedModel):
    """Binary upload record (file storage). Linked to tender via DocumentVersion."""

    original_filename = models.CharField(max_length=512)
    stored_filename = models.CharField(max_length=512)
    file_path = models.CharField(max_length=1024)
    mime_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.BigIntegerField()
    status = models.CharField(
        max_length=64,
        choices=PipelineStage.choices,
        default=PipelineStage.UPLOADED,
        db_index=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.id})"


class DocumentVersion(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Versioned document within a tender lineage (Version 1, Corrigendum A, etc.).
    """

    tender = models.ForeignKey(
        Tender,
        on_delete=models.CASCADE,
        related_name="document_versions",
    )
    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="version",
    )
    version_type = models.CharField(
        max_length=32,
        choices=DocumentVersionType.choices,
        default=DocumentVersionType.ORIGINAL,
        db_index=True,
    )
    version_label = models.CharField(
        max_length=128,
        help_text="Display label, e.g. 'Version 2', 'Corrigendum A'",
    )
    version_sequence = models.PositiveIntegerField(
        default=1,
        help_text="Monotonic sequence within tender for ordering.",
    )
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    is_current = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Active version for retrieval and summarization.",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["tender", "version_sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["tender", "version_sequence"],
                name="unique_tender_version_sequence",
            ),
        ]
        indexes = [
            models.Index(fields=["tender", "is_current"]),
            models.Index(fields=["tender", "version_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.tender.reference_code} / {self.version_label}"


class DocumentExtractedContent(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Phase 2+ storage for raw text and layout — required before chunking for
    citation traceability and retrieval debugging.
    Phase 1: scaffold with empty placeholders.
    """

    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="extracted_content",
    )
    raw_text = models.TextField(blank=True)
    page_map = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"page": 1, "start_offset": 0, "end_offset": 1200, ...}]',
    )
    layout_structure = models.JSONField(
        default=dict,
        blank=True,
        help_text="Blocks, tables, headers detected during OCR/layout parse.",
    )
    section_hierarchy = models.JSONField(
        default=list,
        blank=True,
        help_text='Nested sections, e.g. [{"title": "Eligibility", "level": 1, "children": []}]',
    )
    content_ready = models.BooleanField(
        default=False,
        help_text="True when raw_text and page_map are populated (post-OCR).",
    )
    pipeline_version = models.CharField(max_length=32, default="1.0.0")

    class Meta:
        verbose_name_plural = "document extracted contents"

    def __str__(self) -> str:
        return f"Content for {self.document_id}"


class SourceReference(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    Legal-grade traceability: every future extraction/summary must cite source coordinates.
    Populated in Phase 2+ when extractions and RAG answers are generated.
    """

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="source_references",
    )
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="source_references",
    )
    reference_kind = models.CharField(
        max_length=32,
        choices=SourceReferenceKind.choices,
        default=SourceReferenceKind.CITATION,
        db_index=True,
    )
    source_document_label = models.CharField(
        max_length=512,
        blank=True,
        help_text="Human-readable source, e.g. filename or version label.",
    )
    page = models.PositiveIntegerField(null=True, blank=True)
    section = models.CharField(max_length=512, blank=True)
    section_path = models.CharField(
        max_length=1024,
        blank=True,
        help_text="Hierarchical path, e.g. 'Volume II > Eligibility Criteria'",
    )
    chunk_id = models.CharField(max_length=128, blank=True, db_index=True)
    char_offset_start = models.PositiveIntegerField(null=True, blank=True)
    char_offset_end = models.PositiveIntegerField(null=True, blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="0.0000–1.0000",
    )
    excerpt = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["document", "reference_kind"]),
            models.Index(fields=["document_version", "page"]),
        ]

    def to_trace_dict(self) -> dict:
        """Canonical trace payload for API responses and audit exports."""
        return {
            "source_document": self.source_document_label or str(self.document_id),
            "page": self.page,
            "section": self.section,
            "section_path": self.section_path,
            "chunk_id": self.chunk_id or None,
            "confidence": float(self.confidence) if self.confidence is not None else None,
            "char_offset_start": self.char_offset_start,
            "char_offset_end": self.char_offset_end,
            "reference_kind": self.reference_kind,
        }
