from django.contrib import admin

from apps.documents.models import (
    Document,
    DocumentExtractedContent,
    DocumentVersion,
    SourceReference,
    Tender,
)


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    readonly_fields = ("id", "document", "version_sequence", "created_at")


@admin.register(Tender)
class TenderAdmin(admin.ModelAdmin):
    list_display = ("reference_code", "title", "organization", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reference_code", "title")
    inlines = [DocumentVersionInline]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "status",
        "mime_type",
        "size_bytes",
        "created_at",
    )
    list_filter = ("status", "mime_type")
    search_fields = ("original_filename", "id")
    readonly_fields = ("id", "created_at", "updated_at", "checksum_sha256")


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        "version_label",
        "tender",
        "version_type",
        "version_sequence",
        "is_current",
        "created_at",
    )
    list_filter = ("version_type", "is_current")


@admin.register(DocumentExtractedContent)
class DocumentExtractedContentAdmin(admin.ModelAdmin):
    list_display = ("document", "content_ready", "pipeline_version", "updated_at")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SourceReference)
class SourceReferenceAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "reference_kind",
        "page",
        "section",
        "confidence",
        "created_at",
    )
    list_filter = ("reference_kind",)
