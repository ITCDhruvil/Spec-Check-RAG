from django.urls import path

from apps.chat.views import (
    ChatIndexStatusView,
    ChatMessageCreateView,
    ChatSessionDetailView,
    ChatSessionListCreateView,
)

urlpatterns = [
    path(
        "documents/<uuid:document_id>/chat/index/",
        ChatIndexStatusView.as_view(),
        name="chat-index",
    ),
    path(
        "documents/<uuid:document_id>/chat/sessions/",
        ChatSessionListCreateView.as_view(),
        name="chat-sessions",
    ),
    path(
        "documents/<uuid:document_id>/chat/sessions/<uuid:session_id>/",
        ChatSessionDetailView.as_view(),
        name="chat-session-detail",
    ),
    path(
        "documents/<uuid:document_id>/chat/sessions/<uuid:session_id>/messages/",
        ChatMessageCreateView.as_view(),
        name="chat-messages",
    ),
]
