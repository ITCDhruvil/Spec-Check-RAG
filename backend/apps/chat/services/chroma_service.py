"""Chroma persistent vector store — one collection, filter by document_id."""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from django.conf import settings

logger = logging.getLogger(__name__)

# Silence the noisy posthog telemetry version-mismatch errors.
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

_client: chromadb.ClientAPI | None = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        persist_dir = str(settings.CHROMA_PERSIST_DIR)
        settings.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


class ChromaVectorStore:
    @staticmethod
    def delete_vectors_by_ids(chunk_ids: list[str]) -> None:
        """Delete specific vectors by their Chroma IDs — O(k) not O(N)."""
        if not chunk_ids:
            return
        collection = get_collection()
        try:
            collection.delete(ids=chunk_ids)
        except Exception as exc:
            logger.warning("chroma_delete_by_ids_failed count=%s error=%s", len(chunk_ids), exc)

    @staticmethod
    def delete_document_vectors(document_id: str) -> None:
        """Fallback: delete by metadata filter. Slower than delete_vectors_by_ids."""
        collection = get_collection()
        try:
            collection.delete(where={"document_id": document_id})
        except Exception as exc:
            logger.warning("chroma_delete_failed document_id=%s error=%s", document_id, exc)

    @staticmethod
    def upsert_chunks(
        *,
        document_id: str,
        chunk_ids: list[str],
        old_chunk_ids: list[str] | None = None,
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """
        Upsert new chunks, then remove stale vectors.

        When `old_chunk_ids` is provided we delete only those specific IDs
        (O(k) vs O(N) metadata scan). Falls back to filter-based deletion when
        old IDs are unavailable (e.g. first-time indexing with no prior record).
        """
        if not chunk_ids:
            return
        collection = get_collection()

        # 1. Upsert new vectors first so there's no gap in availability.
        collection.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        # 2. Remove stale vectors that are no longer in the current chunk set.
        new_id_set = set(chunk_ids)
        if old_chunk_ids is not None:
            stale = [cid for cid in old_chunk_ids if cid not in new_id_set]
            if stale:
                ChromaVectorStore.delete_vectors_by_ids(stale)
        else:
            # No prior IDs — fall back to filter scan to clear any previous data.
            ChromaVectorStore.delete_document_vectors(document_id)

        logger.info(
            "chroma_indexed document_id=%s chunks=%s",
            document_id,
            len(chunk_ids),
        )

    @staticmethod
    def query(
        *,
        document_id: str,
        query_embedding: list[float],
        top_k: int,
        search_text: str | None = None,
    ) -> dict[str, Any]:
        collection = get_collection()
        return collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"document_id": document_id},
            include=["documents", "metadatas", "distances"],
        )

    @staticmethod
    def backend_name() -> str:
        return "chroma"
