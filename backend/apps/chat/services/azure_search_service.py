"""
Azure AI Search vector store — hybrid BM25 + vector with document_id filter.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from apps.chat.services.vector_store import embedding_dimensions, normalize_query_response

logger = logging.getLogger(__name__)

_index_ready = False


def _credential():
    from azure.core.credentials import AzureKeyCredential

    return AzureKeyCredential(settings.AZURE_SEARCH_KEY)


def _index_client():
    from azure.search.documents.indexes import SearchIndexClient

    return SearchIndexClient(
        endpoint=settings.AZURE_SEARCH_ENDPOINT,
        credential=_credential(),
    )


def _search_client():
    from azure.search.documents import SearchClient

    return SearchClient(
        endpoint=settings.AZURE_SEARCH_ENDPOINT,
        index_name=settings.AZURE_SEARCH_INDEX_NAME,
        credential=_credential(),
    )


def ensure_search_index(*, vector_dimensions: int | None = None) -> None:
    """Create or update the Azure Search index schema (idempotent)."""
    global _index_ready
    if _index_ready:
        return

    from azure.search.documents.indexes.models import (
        HnswAlgorithmConfiguration,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SearchableField,
        SemanticConfiguration,
        SemanticField,
        SemanticPrioritizedFields,
        SemanticSearch,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )

    dims = vector_dimensions or embedding_dimensions()
    index_name = settings.AZURE_SEARCH_INDEX_NAME
    semantic_config_name = getattr(
        settings, "AZURE_SEARCH_SEMANTIC_CONFIG", "speccheck-semantic"
    )

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(
            name="document_id",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dims,
            vector_search_profile_name="vector-profile",
        ),
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="section_title", type=SearchFieldDataType.String),
        SimpleField(name="section_path", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="chunk_type", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page_start", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="page_end", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="chunk_order", type=SearchFieldDataType.Int32, filterable=True),
        SearchableField(name="tags", type=SearchFieldDataType.String),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-config",
                parameters={
                    "m": 16,
                    "efConstruction": 400,
                    "efSearch": 500,
                    "metric": "cosine",
                },
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw-config",
            )
        ],
    )

    # Semantic ranker config (B1): L2 cross-encoder rerank over title+content.
    # section_title carries the section heading; content is the chunk body.
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=semantic_config_name,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="section_title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="tags")],
                ),
            )
        ]
    )

    index = SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )
    client = _index_client()
    try:
        existing = client.get_index(index_name)
        existing_vector = next(
            (f for f in existing.fields if f.name == "content_vector"),
            None,
        )
        existing_dims = getattr(existing_vector, "vector_search_dimensions", None)
        if existing_dims and existing_dims != dims:
            raise RuntimeError(
                f"Azure Search index '{index_name}' uses {existing_dims} dimensions but "
                f"embedding model '{settings.OPENAI_EMBEDDING_MODEL}' needs {dims}. "
                f"Create a new index (e.g. AZURE_SEARCH_INDEX_NAME=speccheck-chunks-3072) "
                f"or delete the existing index in Azure Portal."
            )
        # Index exists with matching dims. Fall through to create_or_update_index so
        # schema-compatible updates (e.g. semantic config) are applied idempotently
        # without deleting/reindexing vectors.
    except RuntimeError:
        raise
    except Exception:
        pass  # index does not exist — create below

    client.create_or_update_index(index)
    _index_ready = True
    logger.info(
        "azure_search_index_ready index=%s dimensions=%s",
        index_name,
        dims,
    )


def _doc_from_upsert(
    chunk_id: str,
    embedding: list[float],
    text: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    tags = metadata.get("tags", [])
    if isinstance(tags, list):
        tags_str = ",".join(str(t) for t in tags)
    else:
        tags_str = str(tags or "")

    return {
        "id": chunk_id,
        "chunk_id": chunk_id,
        "document_id": str(metadata.get("document_id", "")),
        "content": text,
        "content_vector": embedding,
        "section_title": str(metadata.get("section_title", ""))[:512],
        "section_path": str(metadata.get("section_path", ""))[:512],
        "chunk_type": str(metadata.get("chunk_type", "general_section")),
        "page_start": int(metadata.get("page_start", 1)),
        "page_end": int(metadata.get("page_end", 1)),
        "chunk_order": int(metadata.get("chunk_order", 0)),
        "tags": tags_str,
    }


class AzureSearchVectorStore:
    @staticmethod
    def backend_name() -> str:
        return "azure_search"

    @staticmethod
    def delete_vectors_by_ids(chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        client = _search_client()
        try:
            client.delete_documents(documents=[{"id": cid} for cid in chunk_ids])
        except Exception as exc:
            logger.warning(
                "azure_search_delete_ids_failed count=%s error=%s",
                len(chunk_ids),
                exc,
            )

    @staticmethod
    def delete_document_vectors(document_id: str) -> None:
        client = _search_client()
        doc_id = str(document_id).replace("'", "''")
        try:
            results = client.search(
                search_text="*",
                filter=f"document_id eq '{doc_id}'",
                select=["id"],
                top=1000,
            )
            ids = [{"id": r["id"]} for r in results if r.get("id")]
            if ids:
                client.delete_documents(documents=ids)
        except Exception as exc:
            logger.warning(
                "azure_search_delete_doc_failed document_id=%s error=%s",
                document_id,
                exc,
            )

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
        if not chunk_ids:
            return

        ensure_search_index(vector_dimensions=len(embeddings[0]) if embeddings else None)

        client = _search_client()
        batch_docs = [
            _doc_from_upsert(cid, emb, text, meta)
            for cid, emb, text, meta in zip(chunk_ids, embeddings, documents, metadatas)
        ]

        for start in range(0, len(batch_docs), 500):
            batch = batch_docs[start : start + 500]
            client.merge_or_upload_documents(documents=batch)

        new_id_set = set(chunk_ids)
        if old_chunk_ids is not None:
            stale = [cid for cid in old_chunk_ids if cid not in new_id_set]
            if stale:
                AzureSearchVectorStore.delete_vectors_by_ids(stale)
        else:
            AzureSearchVectorStore.delete_document_vectors(document_id)

        logger.info(
            "azure_search_indexed document_id=%s chunks=%s",
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
        from azure.search.documents.models import VectorizedQuery

        ensure_search_index(vector_dimensions=len(query_embedding))
        client = _search_client()
        doc_id = str(document_id).replace("'", "''")

        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )

        search_kwargs: dict[str, Any] = {
            "search_text": search_text or "*",
            "vector_queries": [vector_query],
            "filter": f"document_id eq '{doc_id}'",
            "select": [
                "id",
                "content",
                "section_title",
                "section_path",
                "chunk_type",
                "page_start",
                "page_end",
                "chunk_order",
                "tags",
            ],
            "top": top_k,
        }

        # B1 — semantic ranker: L2 cross-encoder rerank. Needs real query text
        # (not the "*" match-all), so only engage when search_text is provided.
        semantic_on = (
            getattr(settings, "AZURE_SEARCH_SEMANTIC_ENABLED", False)
            and bool(search_text)
        )
        if semantic_on:
            search_kwargs["query_type"] = "semantic"
            search_kwargs["semantic_configuration_name"] = getattr(
                settings, "AZURE_SEARCH_SEMANTIC_CONFIG", "speccheck-semantic"
            )

        try:
            results = client.search(**search_kwargs)
            results = list(results)
        except Exception as exc:
            # Semantic unsupported / quota exceeded → fall back to hybrid RRF.
            if semantic_on:
                logger.warning("azure_semantic_fallback error=%s", exc)
                search_kwargs.pop("query_type", None)
                search_kwargs.pop("semantic_configuration_name", None)
                semantic_on = False
                results = list(client.search(**search_kwargs))
            else:
                raise

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        scores: list[float] = []

        for item in results:
            ids.append(str(item.get("id", "")))
            documents.append(str(item.get("content") or ""))
            metadatas.append(
                {
                    "chunk_id": item.get("id"),
                    "section_title": item.get("section_title", ""),
                    "section_path": item.get("section_path", ""),
                    "chunk_type": item.get("chunk_type", ""),
                    "page_start": item.get("page_start", 1),
                    "page_end": item.get("page_end", 1),
                    "chunk_order": item.get("chunk_order", 0),
                    "tags": item.get("tags", ""),
                }
            )
            # B1 — prefer semantic reranker score (0–4 scale) when present; it is
            # the L2 cross-encoder relevance and a far better ranking signal than RRF.
            # Fall back to raw RRF score (~0.01–0.05, query-relative) when semantic
            # is off. No fixed-constant normalization (the old ÷40 collapsed scores).
            reranker_score = item.get("@search.reranker_score")
            if reranker_score is None:
                reranker_score = item.get("@search.rerankerScore")
            if semantic_on and reranker_score is not None:
                scores.append(float(reranker_score))
            else:
                scores.append(float(item.get("@search.score", 0.0)))

        return normalize_query_response(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            scores=scores,
        )
