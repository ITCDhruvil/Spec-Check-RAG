from rest_framework import serializers

from apps.documents.models import Document, DocumentExtractedContent, DocumentVersion, Tender
from apps.documents.services.content_service import DocumentContentService
from apps.processing.models import ProcessingJob


class ProcessingJobSummarySerializer(serializers.ModelSerializer):
    status = serializers.CharField(source="current_stage", read_only=True)
    pipeline_stage = serializers.CharField(source="current_stage", read_only=True)

    class Meta:
        model = ProcessingJob
        fields = (
            "id",
            "status",
            "current_stage",
            "pipeline_stage",
            "completed_stages",
            "retry_count",
            "error_code",
            "error_message",
            "last_error",
            "celery_task_id",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )


class DocumentVersionSummarySerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(source="document.id")
    is_current = serializers.BooleanField()

    class Meta:
        model = DocumentVersion
        fields = (
            "id",
            "document_id",
            "version_type",
            "version_label",
            "version_sequence",
            "is_current",
            "supersedes_id",
            "published_at",
            "created_at",
        )


class TenderSummarySerializer(serializers.ModelSerializer):
    version_count = serializers.SerializerMethodField()
    current_version = serializers.SerializerMethodField()

    class Meta:
        model = Tender
        fields = (
            "id",
            "reference_code",
            "title",
            "organization",
            "status",
            "version_count",
            "current_version",
            "created_at",
            "updated_at",
        )

    def get_version_count(self, obj: Tender) -> int:
        return obj.document_versions.count()

    def get_current_version(self, obj: Tender) -> dict | None:
        current = obj.document_versions.filter(is_current=True).first()
        if not current:
            return None
        return DocumentVersionSummarySerializer(current).data


class TenderDetailSerializer(TenderSummarySerializer):
    versions = DocumentVersionSummarySerializer(
        source="document_versions",
        many=True,
        read_only=True,
    )

    class Meta(TenderSummarySerializer.Meta):
        fields = TenderSummarySerializer.Meta.fields + ("versions", "metadata")


class ExtractedContentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentExtractedContent
        fields = (
            "content_ready",
            "raw_text_length",
            "page_count",
            "section_count",
            "pipeline_version",
        )

    raw_text_length = serializers.SerializerMethodField()
    page_count = serializers.SerializerMethodField()
    section_count = serializers.SerializerMethodField()

    def get_raw_text_length(self, obj: DocumentExtractedContent) -> int:
        return len(obj.raw_text or "")

    def get_page_count(self, obj: DocumentExtractedContent) -> int:
        return len(obj.page_map or [])

    def get_section_count(self, obj: DocumentExtractedContent) -> int:
        return DocumentContentService._count_sections(obj.section_hierarchy or [])


class DocumentListSerializer(serializers.ModelSerializer):
    tender_reference = serializers.SerializerMethodField()
    tender_title = serializers.SerializerMethodField()
    version_label = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id",
            "original_filename",
            "mime_type",
            "size_bytes",
            "status",
            "marked_done",
            "tender_reference",
            "tender_title",
            "version_label",
            "created_at",
            "updated_at",
        )

    def get_tender_reference(self, obj: Document) -> str | None:
        if hasattr(obj, "version") and obj.version:
            return obj.version.tender.reference_code
        return obj.metadata.get("tender_reference")

    def get_tender_title(self, obj: Document) -> str | None:
        if hasattr(obj, "version") and obj.version:
            title = obj.version.tender.title
            # Auto-generated titles mirror the reference code — not a real title.
            if title and title != obj.version.tender.reference_code:
                return title
        return None

    def get_version_label(self, obj: Document) -> str | None:
        if hasattr(obj, "version") and obj.version:
            return obj.version.version_label
        return obj.metadata.get("version_label")


class DocumentDetailSerializer(serializers.ModelSerializer):
    latest_job = serializers.SerializerMethodField()
    tender = serializers.SerializerMethodField()
    version = serializers.SerializerMethodField()
    extracted_content = serializers.SerializerMethodField()
    source_trace_schema = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id",
            "original_filename",
            "stored_filename",
            "mime_type",
            "size_bytes",
            "status",
            "metadata",
            "checksum_sha256",
            "tender",
            "version",
            "extracted_content",
            "source_trace_schema",
            "created_at",
            "updated_at",
            "latest_job",
        )

    def get_latest_job(self, obj: Document) -> dict | None:
        job = obj.processing_jobs.order_by("-created_at").first()
        if not job:
            return None
        return ProcessingJobSummarySerializer(job).data

    def get_tender(self, obj: Document) -> dict | None:
        if not hasattr(obj, "version") or not obj.version:
            return None
        t = obj.version.tender
        return {
            "id": str(t.id),
            "reference_code": t.reference_code,
            "title": t.title,
            "organization": t.organization,
            "status": t.status,
        }

    def get_version(self, obj: Document) -> dict | None:
        if not hasattr(obj, "version") or not obj.version:
            return None
        v = obj.version
        return DocumentVersionSummarySerializer(v).data

    def get_extracted_content(self, obj: Document) -> dict:
        summary = DocumentContentService.content_summary(obj)
        return summary

    def get_source_trace_schema(self, obj: Document) -> dict:
        """Document canonical citation shape for Phase 2+ extractions."""
        version = getattr(obj, "version", None)
        return {
            "source_document": obj.original_filename,
            "document_id": str(obj.id),
            "tender_reference": version.tender.reference_code if version else None,
            "version_label": version.version_label if version else None,
            "page": None,
            "section": None,
            "section_path": None,
            "chunk_id": None,
            "confidence": None,
        }


class DocumentUploadResponseSerializer(serializers.ModelSerializer):
    job_id = serializers.SerializerMethodField()
    tender_reference = serializers.SerializerMethodField()
    version_label = serializers.SerializerMethodField()
    version_id = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id",
            "original_filename",
            "mime_type",
            "size_bytes",
            "status",
            "job_id",
            "tender_reference",
            "version_label",
            "version_id",
            "created_at",
        )

    def get_job_id(self, obj: Document):
        job = obj.processing_jobs.order_by("-created_at").first()
        return str(job.id) if job else None

    def get_tender_reference(self, obj: Document) -> str | None:
        return obj.metadata.get("tender_reference")

    def get_version_label(self, obj: Document) -> str | None:
        return obj.metadata.get("version_label")

    def get_version_id(self, obj: Document) -> str | None:
        return obj.metadata.get("version_id")


class DocumentStatusSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    status = serializers.CharField()
    completed_stages = serializers.ListField(child=serializers.CharField(), required=False)
    latest_job = serializers.DictField(allow_null=True)
