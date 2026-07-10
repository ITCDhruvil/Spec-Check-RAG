from copy import deepcopy

from rest_framework import serializers

from apps.intelligence.choices import SummaryStatus
from apps.intelligence.models import DocumentChunk, ExtractedInsight, GeneratedSummary
from apps.intelligence.services.summary_postprocess import reapply_summary_citations

class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = (
            "id",
            "section_title",
            "page_start",
            "page_end",
            "chunk_order",
            "char_count",
            "metadata",
            "created_at",
        )


class ExtractedInsightSerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = ExtractedInsight
        fields = (
            "id",
            "extraction_type",
            "payload",
            "confidence_score",
            "model_name",
            "prompt_version",
            "token_usage",
            "item_count",
            "created_at",
        )

    def get_item_count(self, obj: ExtractedInsight) -> int:
        return len(obj.payload.get("items", []))


class GeneratedSummarySerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(source="document.id", read_only=True)

    def to_representation(self, instance: GeneratedSummary) -> dict:
        data = super().to_representation(instance)
        if (
            instance.status == SummaryStatus.COMPLETED
            and instance.summary_json
            and instance.document_id
        ):
            payload = deepcopy(instance.summary_json)
            insights = list(
                ExtractedInsight.objects.filter(generated_summary=instance)
            )
            if not insights:
                insights = list(
                    ExtractedInsight.objects.filter(document_id=instance.document_id)
                )
            reapply_summary_citations(payload, insights, instance.document)
            data["summary_json"] = payload
        return data

    class Meta:
        model = GeneratedSummary
        fields = (
            "id",
            "document_id",
            "status",
            "version",
            "is_current",
            "summary_json",
            "model_metadata",
            "total_tokens",
            "error_message",
            "last_error",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        )


class SummaryStatusSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    document_status = serializers.CharField()
    summary_status = serializers.CharField(allow_null=True)
    summary_id = serializers.UUIDField(allow_null=True)
    version = serializers.IntegerField(allow_null=True)
    progress_stage = serializers.CharField(allow_null=True)
    total_tokens = serializers.IntegerField(allow_null=True)
    error_message = serializers.CharField(allow_null=True, required=False)
