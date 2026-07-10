from django.urls import path

from apps.intelligence.views import (
    AppSettingsView,
    CancelSummaryView,
    ExtractedInsightsListView,
    FeedbackDetailView,
    FeedbackListView,
    FeedbackStatsView,
    FieldFeedbackView,
    FineTuneJobListView,
    FineTuneTriggerView,
    GenerateSummaryView,
    GeneratedSummaryDetailView,
    RegenerateSummaryView,
    RepairSpecCheckView,
    SummaryPdfDownloadView,
    SummaryStatusView,
)

urlpatterns = [
    path(
        "documents/<uuid:document_id>/summary/generate/",
        GenerateSummaryView.as_view(),
        name="summary-generate",
    ),
    path(
        "documents/<uuid:document_id>/summary/regenerate/",
        RegenerateSummaryView.as_view(),
        name="summary-regenerate",
    ),
    path(
        "documents/<uuid:document_id>/summary/cancel/",
        CancelSummaryView.as_view(),
        name="summary-cancel",
    ),
    path(
        "documents/<uuid:document_id>/summary/repair-spec-check/",
        RepairSpecCheckView.as_view(),
        name="summary-repair-spec-check",
    ),
    path(
        "documents/<uuid:document_id>/summary/",
        GeneratedSummaryDetailView.as_view(),
        name="summary-detail",
    ),
    path(
        "documents/<uuid:document_id>/summary/download/",
        SummaryPdfDownloadView.as_view(),
        name="summary-pdf-download",
    ),
    path(
        "documents/<uuid:document_id>/summary/status/",
        SummaryStatusView.as_view(),
        name="summary-status",
    ),
    path(
        "documents/<uuid:document_id>/insights/",
        ExtractedInsightsListView.as_view(),
        name="insights-list",
    ),
    path(
        "documents/<uuid:document_id>/field-feedback/",
        FieldFeedbackView.as_view(),
        name="field-feedback",
    ),
    # Feedback insights admin
    path("feedback/stats/", FeedbackStatsView.as_view(), name="feedback-stats"),
    path("feedback/", FeedbackListView.as_view(), name="feedback-list"),
    path("feedback/<uuid:feedback_id>/", FeedbackDetailView.as_view(), name="feedback-detail"),
    path("feedback/settings/", AppSettingsView.as_view(), name="feedback-settings"),
    path("finetune/jobs/", FineTuneJobListView.as_view(), name="finetune-jobs"),
    path("finetune/trigger/", FineTuneTriggerView.as_view(), name="finetune-trigger"),
]
