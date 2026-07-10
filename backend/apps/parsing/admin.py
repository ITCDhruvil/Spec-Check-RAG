from django.contrib import admin

from apps.parsing.models import DocumentPage, DocumentSection, ParsedDocument


class DocumentPageInline(admin.TabularInline):
    model = DocumentPage
    extra = 0
    readonly_fields = ("page_number", "quality_score", "ocr_used", "extraction_method")


class DocumentSectionInline(admin.TabularInline):
    model = DocumentSection
    extra = 0
    readonly_fields = ("section_order", "title", "page_start", "page_end")


@admin.register(ParsedDocument)
class ParsedDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document",
        "parsing_status",
        "total_pages",
        "parsing_quality_score",
        "created_at",
    )
    list_filter = ("parsing_status",)
    inlines = [DocumentPageInline, DocumentSectionInline]
