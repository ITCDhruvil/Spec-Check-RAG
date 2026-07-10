from rest_framework import serializers

from apps.chat.models import DocumentChatMessage, DocumentChatSession, DocumentVectorIndex


class DocumentVectorIndexSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVectorIndex
        fields = (
            "chunk_count",
            "embedding_model",
            "collection_name",
            "indexed_at",
            "updated_at",
        )


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChatMessage
        fields = (
            "id",
            "role",
            "content",
            "citations",
            "retrieval_chunks",
            "token_usage",
            "model_metadata",
            "created_at",
        )


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = DocumentChatSession
        fields = (
            "id",
            "document_id",
            "title",
            "message_count",
            "created_at",
            "updated_at",
        )

    def get_message_count(self, obj: DocumentChatSession) -> int:
        return obj.messages.count()


class ChatSessionDetailSerializer(ChatSessionSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta(ChatSessionSerializer.Meta):
        fields = ChatSessionSerializer.Meta.fields + ("messages",)


class SendChatMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=8000)


class CreateChatSessionSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=256, required=False, allow_blank=True)
