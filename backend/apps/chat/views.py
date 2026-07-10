from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.models import DocumentChatMessage, DocumentChatSession, DocumentVectorIndex
from apps.chat.serializers import (
    ChatMessageSerializer,
    ChatSessionDetailSerializer,
    ChatSessionSerializer,
    CreateChatSessionSerializer,
    DocumentVectorIndexSerializer,
    SendChatMessageSerializer,
)
from apps.chat.services.chat_service import DocumentChatService
from apps.chat.services.index_service import VectorIndexService
from apps.core.exceptions import ServiceError, ValidationServiceError
from apps.documents.services.document_service import DocumentService


class ChatIndexStatusView(APIView):
    def get(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        record = DocumentVectorIndex.objects.filter(document=document).first()
        if not record:
            return Response(
                {
                    "document_id": str(document.id),
                    "indexed": False,
                    "chunk_count": 0,
                }
            )
        return Response(
            {
                "document_id": str(document.id),
                "indexed": True,
                **DocumentVectorIndexSerializer(record).data,
            }
        )

    def post(self, request, document_id):
        """Build or refresh Chroma index for this document."""
        document = DocumentService.get_document(document_id, request.user)
        try:
            DocumentChatService.ensure_chat_ready(document)
            record = VectorIndexService.index_document(document, force=True)
        except (ValidationServiceError, ServiceError) as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST),
            )
        return Response(
            {
                "message": "Document indexed for chat.",
                "document_id": str(document.id),
                **DocumentVectorIndexSerializer(record).data,
            },
            status=status.HTTP_200_OK,
        )


class ChatSessionListCreateView(APIView):
    def get(self, request, document_id):
        DocumentService.get_document(document_id, request.user)
        sessions = DocumentChatSession.objects.filter(document_id=document_id).order_by(
            "-updated_at"
        )
        return Response(ChatSessionSerializer(sessions, many=True).data)

    def post(self, request, document_id):
        document = DocumentService.get_document(document_id, request.user)
        ser = CreateChatSessionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            session = DocumentChatService.create_session(
                document, title=ser.validated_data.get("title", "")
            )
        except ValidationServiceError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            ChatSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )


class ChatSessionDetailView(APIView):
    def get(self, request, document_id, session_id):
        DocumentService.get_document(document_id, request.user)
        session = DocumentChatSession.objects.prefetch_related("messages").get(
            pk=session_id, document_id=document_id
        )
        return Response(ChatSessionDetailSerializer(session).data)


class ChatMessageCreateView(APIView):
    def post(self, request, document_id, session_id):
        DocumentService.get_document(document_id, request.user)
        session = DocumentChatSession.objects.get(
            pk=session_id, document_id=document_id
        )
        ser = SendChatMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user_msg, assistant_msg = DocumentChatService.send_message(
                session, user_message=ser.validated_data["message"]
            )
        except ValidationServiceError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ServiceError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=exc.status_code,
            )

        follow_ups = (assistant_msg.model_metadata or {}).get("follow_up_questions") or []
        return Response(
            {
                "session_id": str(session.id),
                "user_message": ChatMessageSerializer(user_msg).data,
                "assistant_message": ChatMessageSerializer(assistant_msg).data,
                "follow_up_questions": follow_ups,
            },
            status=status.HTTP_201_CREATED,
        )
