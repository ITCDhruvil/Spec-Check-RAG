from django.contrib import admin

from apps.intelligence.models import DocumentChunk, ExtractedInsight, GeneratedSummary, LearnedExtractionTerm


class DocumentChunkInline(admin.TabularInline):
    model = DocumentChunk
    extra = 0
    readonly_fields = ("chunk_order", "section_title", "char_count")


class ExtractedInsightInline(admin.TabularInline):
    model = ExtractedInsight
    extra = 0
    readonly_fields = ("extraction_type", "confidence_score")


@admin.register(GeneratedSummary)
class GeneratedSummaryAdmin(admin.ModelAdmin):
    list_display = ("document", "version", "status", "is_current", "total_tokens", "created_at")
    list_filter = ("status", "is_current")
    inlines = [ExtractedInsightInline]


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_order", "section_title", "page_start", "char_count")
    search_fields = ("section_title",)


@admin.register(LearnedExtractionTerm)
class LearnedExtractionTermAdmin(admin.ModelAdmin):
    list_display = (
        "extraction_type",
        "entry_kind",
        "term_display",
        "source",
        "hit_count",
        "is_active",
        "last_seen_at",
    )
    list_filter = ("extraction_type", "entry_kind", "source", "is_active")
    search_fields = ("term_display", "term_normalized")
    readonly_fields = ("term_normalized", "hit_count", "document_count", "created_at", "updated_at")
