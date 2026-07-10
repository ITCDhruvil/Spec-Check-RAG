from rest_framework import serializers

from apps.processing.models import ProcessingJob, ProcessingStageLog


class ProcessingStageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingStageLog
        fields = ("id", "stage", "state", "started_at", "completed_at", "error")


class ProcessingJobDetailSerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(source="document.id")
    document_status = serializers.CharField(source="document.status")
    status = serializers.CharField(source="current_stage", read_only=True)
    pipeline_stage = serializers.CharField(source="current_stage", read_only=True)
    stage_logs = ProcessingStageLogSerializer(many=True, read_only=True)

    class Meta:
        model = ProcessingJob
        fields = (
            "id",
            "document_id",
            "document_status",
            "status",
            "current_stage",
            "pipeline_stage",
            "completed_stages",
            "retry_count",
            "max_retries",
            "error_code",
            "error_message",
            "last_error",
            "celery_task_id",
            "started_at",
            "completed_at",
            "stage_logs",
            "created_at",
            "updated_at",
        )
