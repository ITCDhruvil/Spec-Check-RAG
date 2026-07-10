"""Document-scoped RAG chat with grounded citations."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.chat.choices import ChatMessageRole
from apps.chat.models import DocumentChatMessage, DocumentChatSession
from apps.chat.prompts import CHAT_SYSTEM_PROMPT, NOT_FOUND_IN_DOCUMENT
from apps.chat.services.citation_validation import filter_grounded_citations
from apps.chat.services.index_service import VectorIndexService
from apps.chat.services.retrieval_service import RetrievedChunk, RetrievalService
from apps.core.exceptions import ValidationServiceError
from apps.documents.choices import SourceReferenceKind
from apps.documents.models import Document, SourceReference
from apps.intelligence.models import DocumentChunk
from apps.intelligence.services.model_routing import chat_model
from apps.intelligence.services.openai_service import OpenAIService
from apps.parsing.choices import ParsingStatus
from apps.parsing.models import ParsedDocument

logger = logging.getLogger(__name__)

def _parse_follow_up_questions(payload: dict, *, user_message: str) -> list[str]:
    raw = payload.get("follow_up_questions") or []
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    user_norm = user_message.strip().lower()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        q = item.strip()
        if not q or len(q) > 200:
            continue
        key = q.lower()
        if key == user_norm or key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= 4:
            break
    return out


class DocumentChatService:
    @staticmethod
    def ensure_chat_ready(document: Document) -> None:
        try:
            parsed = document.parsed_document
        except ParsedDocument.DoesNotExist as exc:
            raise ValidationServiceError(
                "Document must be parsed before chat.",
                code="parsing_required",
            ) from exc
        if parsed.parsing_status != ParsingStatus.COMPLETED:
            raise ValidationServiceError(
                "Parsing is not complete.",
                code="parsing_incomplete",
            )
        if not DocumentChunk.objects.filter(document=document).exists():
            raise ValidationServiceError(
                "Document has no chunks. Run Generate summary first (creates chunks), "
                "then chat.",
                code="chunks_required",
            )

    @staticmethod
    def create_session(document: Document, *, title: str = "") -> DocumentChatSession:
        DocumentChatService.ensure_chat_ready(document)
        return DocumentChatSession.objects.create(
            document=document,
            title=title[:256],
        )

    @staticmethod
    def _format_context(chunks: list[RetrievedChunk]) -> str:
        blocks = []
        for c in chunks:
            page = c.page_start if c.page_start == c.page_end else f"{c.page_start}-{c.page_end}"
            blocks.append(
                f"[CHUNK_ID={c.chunk_id} | {c.section_title} | p.{page} | score={c.score}]\n"
                f"{c.text}"
            )
        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _history_messages(session: DocumentChatSession) -> list[dict]:
        qs = session.messages.order_by("created_at")
        max_messages = settings.CHAT_MAX_HISTORY_TURNS * 2
        recent = list(qs)[-max_messages:] if max_messages else list(qs)
        out = []
        for msg in recent:
            if msg.role in (ChatMessageRole.USER, ChatMessageRole.ASSISTANT):
                out.append({"role": msg.role, "content": msg.content})
        return out

    @staticmethod
    @transaction.atomic
    def send_message(
        session: DocumentChatSession,
        *,
        user_message: str,
    ) -> tuple[DocumentChatMessage, DocumentChatMessage]:
        user_message = (user_message or "").strip()
        if not user_message:
            raise ValidationServiceError("Message cannot be empty.", code="empty_message")
        if len(user_message) > 8000:
            raise ValidationServiceError(
                "Message too long (max 8000 characters).",
                code="message_too_long",
            )

        document = session.document
        DocumentChatService.ensure_chat_ready(document)
        VectorIndexService.ensure_indexed(document)

        retrieved = RetrievalService.retrieve(str(document.id), user_message)

        user_record = DocumentChatMessage.objects.create(
            session=session,
            role=ChatMessageRole.USER,
            content=user_message,
            retrieval_chunks=[
                {
                    "chunk_id": c.chunk_id,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "section_title": c.section_title,
                    "score": c.score,
                }
                for c in retrieved
            ],
        )

        if not session.title:
            session.title = user_message[:80] + ("…" if len(user_message) > 80 else "")
            session.save(update_fields=["title", "updated_at"])

        if not retrieved:
            assistant_record = DocumentChatMessage.objects.create(
                session=session,
                role=ChatMessageRole.ASSISTANT,
                content=NOT_FOUND_IN_DOCUMENT,
                citations=[],
                token_usage={},
                model_metadata={
                    "prompt_version": settings.CHAT_PROMPT_VERSION,
                    "retrieval_count": 0,
                    "refused": True,
                    "reason": "no_retrieved_chunks",
                },
            )
            session.save(update_fields=["updated_at"])
            logger.warning(
                "chat_no_retrieval document_id=%s session_id=%s",
                document.id,
                session.id,
            )
            return user_record, assistant_record

        context = DocumentChatService._format_context(retrieved)

        history = DocumentChatService._history_messages(session)
        prior = history[:-1] if history else []
        history_block = ""
        if prior:
            lines = [f"{m['role'].upper()}: {m['content']}" for m in prior]
            history_block = "PRIOR CONVERSATION:\n" + "\n".join(lines) + "\n\n"

        prompt_user = (
            f"{history_block}"
            f"CONTEXT (document excerpts only):\n{context}\n\n"
            f"USER QUESTION:\n{user_message}"
        )

        openai = OpenAIService()
        payload, usage = openai.chat_json(
            system=CHAT_SYSTEM_PROMPT,
            user=prompt_user,
            temperature=settings.OPENAI_TEMPERATURE,
            model=chat_model(),
        )

        refused = bool(payload.get("refused"))
        if refused:
            answer = NOT_FOUND_IN_DOCUMENT
        else:
            answer = str(payload.get("answer") or "").strip()
            if not answer:
                refused = True
                answer = NOT_FOUND_IN_DOCUMENT

        citations_raw = payload.get("citations") or []
        citations = []
        for item in citations_raw:
            if not isinstance(item, dict):
                continue
            citations.append(
                {
                    "chunk_id": str(item.get("chunk_id", "")),
                    "page": item.get("page"),
                    "section": str(item.get("section", ""))[:512],
                    "source_text": str(item.get("source_text", ""))[:2000],
                    "relevance": float(item.get("relevance", 0) or 0),
                }
            )

        citations = filter_grounded_citations(
            citations, retrieved, document=document
        )
        if not refused and not citations:
            refused = True
            answer = NOT_FOUND_IN_DOCUMENT

        follow_up_questions = (
            [] if refused else _parse_follow_up_questions(payload, user_message=user_message)
        )

        assistant_record = DocumentChatMessage.objects.create(
            session=session,
            role=ChatMessageRole.ASSISTANT,
            content=str(answer),
            citations=citations,
            token_usage=usage,
            model_metadata={
                "prompt_version": settings.CHAT_PROMPT_VERSION,
                "retrieval_count": len(retrieved),
                "refused": refused,
                "follow_up_questions": follow_up_questions,
            },
        )

        DocumentChatService._sync_citations(document, assistant_record, citations)
        session.save(update_fields=["updated_at"])

        logger.info(
            "chat_message document_id=%s session_id=%s tokens=%s",
            document.id,
            session.id,
            usage.get("total_tokens", 0),
        )
        return user_record, assistant_record

    @staticmethod
    def _sync_citations(
        document: Document,
        message: DocumentChatMessage,
        citations: list[dict],
    ) -> None:
        version = getattr(document, "version", None)
        for item in citations:
            conf = item.get("relevance")
            SourceReference.objects.create(
                document=document,
                document_version=version,
                reference_kind=SourceReferenceKind.CITATION,
                source_document_label=document.original_filename,
                page=item.get("page"),
                section=item.get("section", "")[:512],
                excerpt=item.get("source_text", "")[:2000],
                confidence=Decimal(str(conf)) if conf is not None else None,
                chunk_id=item.get("chunk_id", ""),
                metadata={
                    "chat_message_id": str(message.id),
                    "prompt_version": settings.CHAT_PROMPT_VERSION,
                },
            )
