"""
Rebuild Azure Search index with updated HNSW config (m=16).
Steps:
  1. Delete existing index
  2. Re-create via ensure_search_index (picks up new m=16 config)
  3. Re-index all documents that have chunks in DB

WARNING: Deletes all vectors. All documents will be re-embedded and re-uploaded.
Estimated time: ~2-5 min for all 8 documents (embed + upload).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

sys.stdout.reconfigure(encoding="utf-8")

from django.conf import settings

from apps.chat.services.azure_search_service import (
    _index_client,
    ensure_search_index,
)
from apps.chat.services.index_service import VectorIndexService
from apps.documents.models import Document
from apps.intelligence.models import DocumentChunk
from apps.intelligence.services.chunking_service import ChunkingService

# ---- Step 1: delete existing index ----
index_name = settings.AZURE_SEARCH_INDEX_NAME
print(f"Deleting index '{index_name}'...", end=" ", flush=True)
try:
    client = _index_client()
    client.delete_index(index_name)
    print("deleted.")
except Exception as exc:
    print(f"WARNING: {exc}")

# Reset the module-level ready flag so ensure_search_index will recreate
import apps.chat.services.azure_search_service as _svc
_svc._index_ready = False

# ---- Step 2: recreate index ----
print("Recreating index with m=16...", end=" ", flush=True)
ensure_search_index()
print("done.")

# ---- Step 3: re-chunk, generate prefixes, re-embed ----
docs_with_chunks = (
    Document.objects.filter(
        id__in=DocumentChunk.objects.values_list("document_id", flat=True).distinct()
    )
)
print(f"\nRe-chunking and re-indexing {docs_with_chunks.count()} documents...")

success = 0
failed = 0
for doc in docs_with_chunks:
    print(f"  {str(doc.id)[:8]}...", end=" ", flush=True)
    t0 = time.time()
    try:
        chunks = ChunkingService.build_chunks(doc)
        print(f"chunks={len(chunks)}", end=" ", flush=True)
        record = VectorIndexService.index_document(doc, force=True)
        elapsed = round(time.time() - t0, 1)
        print(f"OK  {elapsed}s")
        success += 1
    except Exception as exc:
        elapsed = round(time.time() - t0, 1)
        print(f"FAILED  {elapsed}s  {exc}")
        failed += 1

print(f"\nDone. Success={success}  Failed={failed}")

# ---- Verify ----
print("\nVerifying all documents indexed...")
for doc in docs_with_chunks:
    ok = VectorIndexService.is_indexed(str(doc.id))
    print(f"  {str(doc.id)[:8]}  indexed={ok}")
