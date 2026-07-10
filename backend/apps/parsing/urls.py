from django.urls import path

from apps.parsing.views import (
    ParsedDocumentDetailView,
    ParsedDocumentPageDetailView,
    ParsedDocumentPagesView,
    ParsedDocumentSectionsView,
    ParsingStatusView,
)

urlpatterns = [
    path(
        "documents/<uuid:document_id>/parsed/",
        ParsedDocumentDetailView.as_view(),
        name="parsed-document-detail",
    ),
    path(
        "documents/<uuid:document_id>/parsed/status/",
        ParsingStatusView.as_view(),
        name="parsed-status",
    ),
    path(
        "documents/<uuid:document_id>/parsed/pages/",
        ParsedDocumentPagesView.as_view(),
        name="parsed-pages",
    ),
    path(
        "documents/<uuid:document_id>/parsed/pages/<int:page_number>/",
        ParsedDocumentPageDetailView.as_view(),
        name="parsed-page-detail",
    ),
    path(
        "documents/<uuid:document_id>/parsed/sections/",
        ParsedDocumentSectionsView.as_view(),
        name="parsed-sections",
    ),
]
