from django.contrib import admin

from apps.chat.models import DocumentChatMessage, DocumentChatSession, DocumentVectorIndex


@admin.register(DocumentVectorIndex)
class DocumentVectorIndexAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_count", "embedding_model", "indexed_at")


@admin.register(DocumentChatSession)
class DocumentChatSessionAdmin(admin.ModelAdmin):
    list_display = ("document", "title", "created_at", "updated_at")
    search_fields = ("title", "document__original_filename")


class ChatMessageInline(admin.TabularInline):
    model = DocumentChatMessage
    extra = 0
    readonly_fields = ("role", "content", "created_at")


DocumentChatSessionAdmin.inlines = [ChatMessageInline]
