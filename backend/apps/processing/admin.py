from django.contrib import admin

from apps.processing.models import ProcessingJob, ProcessingStageLog


class ProcessingStageLogInline(admin.TabularInline):
    model = ProcessingStageLog
    extra = 0
    readonly_fields = ("stage", "state", "started_at", "completed_at", "error")


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "document",
        "current_stage",
        "retry_count",
        "created_at",
    )
    list_filter = ("current_stage",)
    search_fields = ("id", "document__original_filename", "celery_task_id")
    readonly_fields = ("id", "created_at", "updated_at", "last_error", "completed_stages")
    inlines = [ProcessingStageLogInline]
