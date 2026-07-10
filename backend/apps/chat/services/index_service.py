"""Embed document chunks and persist in vector store (Azure Search or Chroma)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from apps.chat.models import DocumentVectorIndex
from apps.chat.services.vector_store import get_vector_store, use_azure_search
from apps.documents.models import Document
from apps.intelligence.models import DocumentChunk
from apps.intelligence.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


class VectorIndexService:
    @staticmethod
    def _store():
        return get_vector_store()

    @staticmethod
    def backend_name() -> str:
        return VectorIndexService._store().backend_name()

    @staticmethod
    def is_indexed(document_id) -> bool:
        record = DocumentVectorIndex.objects.filter(document_id=document_id).first()
        if not record:
            return False
        return VectorIndexService._vectors_exist(str(document_id))

    @staticmethod
    def _vectors_exist(document_id: str) -> bool:
        if use_azure_search():
            from apps.chat.services.azure_search_service import _search_client

            try:
                client = _search_client()
                doc_id = document_id.replace("'", "''")
                results = client.search(
                    search_text="*",
                    filter=f"document_id eq '{doc_id}'",
                    select=["id"],
                    top=1,
                )
                return any(True for _ in results)
            except Exception as exc:
                logger.warning(
                    "azure_search_exists_check_failed document_id=%s error=%s",
                    document_id,
                    exc,
                )
                return False

        from apps.chat.services.chroma_service import get_collection

        try:
            result = get_collection().get(
                where={"document_id": document_id},
                limit=1,
                include=[],
            )
        except Exception as exc:
            logger.warning(
                "chroma_has_vectors_check_failed document_id=%s error=%s",
                document_id,
                exc,
            )
            return False
        return bool(result.get("ids"))

    @staticmethod
    def index_document(document: Document, *, force: bool = False) -> DocumentVectorIndex:
        chunks = list(
            DocumentChunk.objects.filter(document=document).order_by("chunk_order")
        )
        if not chunks:
            from apps.core.exceptions import ValidationServiceError

            raise ValidationServiceError(
                "No chunks found. Run parsing/chunking first.",
                code="chunks_required",
            )

        store = VectorIndexService._store()
        existing = DocumentVectorIndex.objects.filter(document=document).first()

        if (
            not force
            and existing
            and existing.chunk_count == len(chunks)
            and existing.vector_backend == store.backend_name()
            and VectorIndexService._vectors_exist(str(document.id))
        ):
            return existing

        if existing and not VectorIndexService._vectors_exist(str(document.id)):
            logger.warning(
                "stale_vector_index_reindex document_id=%s db_chunks=%s backend=%s",
                document.id,
                len(chunks),
                store.backend_name(),
            )

        old_chunk_ids: list[str] | None = (
            existing.indexed_chunk_ids if existing else None
        )

        openai = OpenAIService()
        # CR-2: embed contextualized_text when Contextual Retrieval is enabled and
        # we're on Azure AI Search. Chroma path stays on plain chunk_text.
        use_contextual = (
            getattr(settings, "CONTEXTUAL_RETRIEVAL_ENABLED", False)
            and store.backend_name() == "azure_search"
        )
        texts = [
            (c.contextualized_text if use_contextual else c.chunk_text) for c in chunks
        ]
        new_chunk_ids = [str(c.id) for c in chunks]
        embeddings, _usage = openai.embed_texts(texts)

        doc_id = str(document.id)
        metadatas = [
            {
                "document_id": doc_id,
                "chunk_id": str(c.id),
                "page_start": int(c.page_start),
                "page_end": int(c.page_end),
                "section_title": (c.section_title or "")[:512],
                "section_path": str((c.metadata or {}).get("section_path", ""))[:512],
                "chunk_type": (c.metadata or {}).get("chunk_type", "general_section"),
                "chunk_order": int(c.chunk_order),
                "tags": (c.metadata or {}).get("tags", []),
            }
            for c in chunks
        ]

        store.upsert_chunks(
            document_id=doc_id,
            chunk_ids=new_chunk_ids,
            old_chunk_ids=old_chunk_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        index_name = (
            settings.AZURE_SEARCH_INDEX_NAME
            if use_azure_search()
            else settings.CHROMA_COLLECTION_NAME
        )

        record, _ = DocumentVectorIndex.objects.update_or_create(
            document=document,
            defaults={
                "chunk_count": len(chunks),
                "embedding_model": settings.OPENAI_EMBEDDING_MODEL,
                "embedding_model_version": settings.OPENAI_EMBEDDING_MODEL,
                "vector_backend": store.backend_name(),
                "collection_name": index_name,
                "indexed_at": timezone.now(),
                "indexed_chunk_ids": new_chunk_ids,
            },
        )
        return record

    @staticmethod
    def ensure_indexed(document: Document) -> DocumentVectorIndex:
        return VectorIndexService.index_document(document, force=False)
