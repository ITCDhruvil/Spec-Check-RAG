"""
Vector store abstraction — Azure AI Search (hybrid) or Chroma (dense-only).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from django.conf import settings

logger = logging.getLogger(__name__)


class VectorStoreProtocol(Protocol):
    @staticmethod
    def upsert_chunks(
        *,
        document_id: str,
        chunk_ids: list[str],
        old_chunk_ids: list[str] | None,
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None: ...

    @staticmethod
    def query(
        *,
        document_id: str,
        query_embedding: list[float],
        top_k: int,
        search_text: str | None = None,
    ) -> dict[str, Any]: ...

    @staticmethod
    def delete_vectors_by_ids(chunk_ids: list[str]) -> None: ...

    @staticmethod
    def delete_document_vectors(document_id: str) -> None: ...

    @staticmethod
    def backend_name() -> str: ...


def is_azure_search_configured() -> bool:
    endpoint = getattr(settings, "AZURE_SEARCH_ENDPOINT", "") or ""
    key = getattr(settings, "AZURE_SEARCH_KEY", "") or ""
    index = getattr(settings, "AZURE_SEARCH_INDEX_NAME", "") or ""
    return bool(endpoint.strip() and key.strip() and index.strip())


def use_azure_search() -> bool:
    return bool(
        getattr(settings, "AZURE_SEARCH_RAG_ENABLED", False)
        and is_azure_search_configured()
    )


def embedding_dimensions(model: str | None = None) -> int:
    explicit = getattr(settings, "AZURE_SEARCH_VECTOR_DIMENSIONS", 0)
    if explicit:
        return int(explicit)

    azure_embed = getattr(settings, "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "") or ""
    if "large" in azure_embed.lower():
        return 3072

    name = (model or settings.OPENAI_EMBEDDING_MODEL or "").lower()
    if "large" in name or "3072" in name:
        return 3072
    return 1536


def _resolve_azure_deployment(explicit: str, fallback: str) -> str:
    """Use explicit Azure deployment when set; otherwise fall back to OPENAI_* model name."""
    value = (explicit or "").strip()
    if value and value not in {"your-gpt-deployment-name", "your-embedding-deployment-name"}:
        return value
    return fallback


def get_vector_store() -> type[VectorStoreProtocol]:
    if use_azure_search():
        from apps.chat.services.azure_search_service import AzureSearchVectorStore

        logger.debug("vector_store backend=azure_search")
        return AzureSearchVectorStore

    from apps.chat.services.chroma_service import ChromaVectorStore

    logger.debug("vector_store backend=chroma")
    return ChromaVectorStore


def normalize_query_response(
    *,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
    scores: list[float],
) -> dict[str, Any]:
    """Standard shape for RetrievalService (scores as similarity 0–1)."""
    distances = [max(0.0, 1.0 - s) for s in scores]
    return {
        "ids": [ids],
        "documents": [documents],
        "metadatas": [metadatas],
        "distances": [distances],
        "scores": [scores],
    }
