"""
Phase 3 Azure Search index smoke test.

  python eval/run_phase3_index_test.py

Upserts one test vector, queries it, then deletes it.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from django.conf import settings

from apps.chat.services.azure_search_service import AzureSearchVectorStore, ensure_search_index
from apps.chat.services.vector_store import embedding_dimensions, use_azure_search
from apps.intelligence.services.openai_service import OpenAIService


def main() -> None:
    print("=" * 60)
    print("Phase 3 Azure Search Index Test")
    print("=" * 60)
    print(f"AZURE_SEARCH_RAG_ENABLED: {settings.AZURE_SEARCH_RAG_ENABLED}")
    print(f"use_azure_search():       {use_azure_search()}")
    print(f"Index:                    {settings.AZURE_SEARCH_INDEX_NAME}")
    print(f"Embedding model:          {settings.OPENAI_EMBEDDING_MODEL}")
    print(f"Vector dimensions:        {embedding_dimensions()}")

    if not use_azure_search():
        print("Azure Search not enabled/configured — skipping live test.")
        sys.exit(0)

    test_doc_id = f"test-{uuid.uuid4()}"
    test_chunk_id = str(uuid.uuid4())
    text = "Bid deadline March 11, 2026 at 11:00 AM. Pre-bid meeting March 4, 2026."

    openai = OpenAIService()
    embeddings, usage = openai.embed_texts([text])
    print(f"Embedding tokens: {usage.get('total_tokens', 0)}")

    ensure_search_index(vector_dimensions=len(embeddings[0]))
    AzureSearchVectorStore.upsert_chunks(
        document_id=test_doc_id,
        chunk_ids=[test_chunk_id],
        old_chunk_ids=None,
        embeddings=embeddings,
        documents=[text],
        metadatas=[
            {
                "document_id": test_doc_id,
                "chunk_id": test_chunk_id,
                "section_title": "Bid Schedule",
                "section_path": "Cover > Bid Schedule",
                "chunk_type": "schedule_table",
                "page_start": 2,
                "page_end": 2,
                "chunk_order": 1,
                "tags": ["deadline"],
            }
        ],
    )
    print("Upsert: OK")

    raw = AzureSearchVectorStore.query(
        document_id=test_doc_id,
        query_embedding=embeddings[0],
        top_k=3,
        search_text="bid deadline March",
    )
    hits = (raw.get("ids") or [[]])[0]
    print(f"Hybrid query hits: {len(hits)}")
    if hits:
        docs = (raw.get("documents") or [[]])[0]
        print(f"Top hit preview: {docs[0][:80]!r}...")

    AzureSearchVectorStore.delete_document_vectors(test_doc_id)
    print("Cleanup: OK")
    print("Phase 3 Azure Search smoke test PASSED")


if __name__ == "__main__":
    main()
