from django.urls import path

from apps.documents.views import (
    DocumentDetailView,
    DocumentFileView,
    DocumentListView,
    DocumentPreviewFileView,
    DocumentProcessKickView,
    DocumentStatusView,
    DocumentUploadView,
    TenderDetailView,
    TenderListView,
)

urlpatterns = [
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/<uuid:document_id>/", DocumentDetailView.as_view(), name="document-detail"),
    path(
        "documents/<uuid:document_id>/file/",
        DocumentFileView.as_view(),
        name="document-file",
    ),
    path(
        "documents/<uuid:document_id>/preview-pdf/",
        DocumentPreviewFileView.as_view(),
        name="document-preview-pdf",
    ),
    path(
        "documents/<uuid:document_id>/status/",
        DocumentStatusView.as_view(),
        name="document-status",
    ),
    path(
        "documents/<uuid:document_id>/process/",
        DocumentProcessKickView.as_view(),
        name="document-process-kick",
    ),
    path("tenders/", TenderListView.as_view(), name="tender-list"),
    path("tenders/<uuid:tender_id>/", TenderDetailView.as_view(), name="tender-detail"),
]
