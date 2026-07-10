from django.db import models

from apps.chat.choices import ChatMessageRole
from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.documents.models import Document


class DocumentVectorIndex(UUIDPrimaryKeyModel, TimeStampedModel):
    """Tracks vector indexing state for a document's chunks."""

    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="vector_index",
    )
    chunk_count = models.PositiveIntegerField(default=0)
    embedding_model = models.CharField(max_length=128)
    embedding_model_version = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Embedding model version/id used at index time.",
    )
    vector_backend = models.CharField(
        max_length=32,
        default="chroma",
        help_text="chroma | azure_search",
    )
    collection_name = models.CharField(max_length=128)
    indexed_at = models.DateTimeField()
    indexed_chunk_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Chunk IDs currently indexed for this document.",
    )

    class Meta:
        verbose_name_plural = "document vector indexes"

    def __str__(self) -> str:
        return f"Vector index for {self.document_id} ({self.chunk_count} chunks)"


class DocumentChatSession(UUIDPrimaryKeyModel, TimeStampedModel):
    """Conversation scoped to a single document."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    title = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Chat {self.id}"


class DocumentChatMessage(UUIDPrimaryKeyModel, TimeStampedModel):
    session = models.ForeignKey(
        DocumentChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=ChatMessageRole.choices)
    content = models.TextField()
    citations = models.JSONField(
        default=list,
        blank=True,
        help_text="Grounded citations: chunk_id, page, section, source_text, score",
    )
    retrieval_chunks = models.JSONField(
        default=list,
        blank=True,
        help_text="Chunks sent to the LLM for this turn",
    )
    token_usage = models.JSONField(default=dict, blank=True)
    model_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:48]}"
