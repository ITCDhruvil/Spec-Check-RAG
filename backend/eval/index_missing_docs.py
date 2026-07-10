"""Index the 4 documents that have chunks in DB but are not yet vector-indexed."""
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

from apps.chat.services.index_service import VectorIndexService
from apps.documents.models import Document
from apps.intelligence.models import DocumentChunk

UNINDEXED = [
    "744bea43-d936-4175-beb2-8803d29b1a7d",
    "58df83e0-bd88-42dc-b515-65c543bc75a0",
    "2aef38d9-b6a1-42a6-8f7c-73ad03173840",
    "6fde1046-0c54-43b3-990c-0e5b8dde1478",
]


def main() -> None:
    for doc_id in UNINDEXED:
        doc = Document.objects.filter(id=doc_id).first()
        if not doc:
            print(f"SKIP {doc_id[:8]} — not in DB")
            continue

        chunk_count = DocumentChunk.objects.filter(document_id=doc_id).count()
        if chunk_count == 0:
            print(f"SKIP {doc_id[:8]} — no chunks")
            continue

        already = VectorIndexService.is_indexed(doc_id)
        if already:
            print(f"SKIP {doc_id[:8]} — already indexed")
            continue

        print(f"Indexing {doc_id[:8]} ({chunk_count} chunks)...", end=" ", flush=True)
        t0 = time.time()
        try:
            record = VectorIndexService.index_document(doc, force=False)
            elapsed = round(time.time() - t0, 1)
            print(f"OK  {elapsed}s  backend={record.vector_backend}")
        except Exception as exc:
            elapsed = round(time.time() - t0, 1)
            print(f"FAILED  {elapsed}s  error={exc}")

    print("\nVerifying...")
    for doc_id in UNINDEXED:
        status = VectorIndexService.is_indexed(doc_id)
        print(f"  {doc_id[:8]}  indexed={status}")


if __name__ == "__main__":
    main()
