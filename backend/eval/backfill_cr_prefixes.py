"""
Backfill empty contextual_prefix on DocumentChunk rows for benchmark docs,
then re-index those docs to Azure Search with consistent contextualized text.

Run this when a prior prefix-generation run was interrupted (e.g. 429 rate limit),
leaving a mix of prefixed and plain chunks in the same document — which degrades
ranking consistency.

Usage:
    # Backfill + re-index only the 8 benchmark docs (default)
    python eval/backfill_cr_prefixes.py

    # Specific doc-id prefixes
    python eval/backfill_cr_prefixes.py --doc-ids 744bea43 6fde1046

    # All docs in DB with any empty prefix
    python eval/backfill_cr_prefixes.py --all
"""
from __future__ import annotations

import argparse
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
from apps.intelligence.services.contextual_chunk_service import generate_and_save

# Default: all 8 benchmark doc-id prefixes
BENCHMARK_DOC_PREFIXES = [
    "c3f4db27",  # NPS RFQ
    "46d515c0",  # HRSD IFB
    "3bca0c61",  # E-rate
    "873de021",  # Allegan
    "2aef38d9",
    "58df83e0",
    "6fde1046",
    "744bea43",
]


def _doc_text(doc: Document) -> str:
    """Full document text for contextual prefix prompts (matches chunking_service)."""
    from apps.parsing.choices import ParsingStatus
    from apps.parsing.models import ParsedDocument

    try:
        parsed = ParsedDocument.objects.get(
            document=doc,
            parsing_status=ParsingStatus.COMPLETED,
        )
        if parsed.structured_text:
            return parsed.structured_text
    except ParsedDocument.DoesNotExist:
        pass

    from apps.documents.models import DocumentPage

    pages = DocumentPage.objects.filter(document=doc).order_by("page_number")
    return "\n\n".join(p.text for p in pages if p.text)


def backfill_doc(doc: Document, force: bool = False) -> dict:
    chunks = list(
        DocumentChunk.objects.filter(document=doc).order_by("chunk_order")
    )
    empty = [c for c in chunks if not c.contextual_prefix]
    to_generate = chunks if force else empty

    result = {
        "doc_id": str(doc.id)[:8],
        "total_chunks": len(chunks),
        "empty_before": len(empty),
        "prefixes_saved": 0,
        "reindexed": False,
        "error": None,
    }

    if not to_generate and not force:
        print(f"  [{result['doc_id']}] all {len(chunks)} chunks have prefixes -- skip generation")
    else:
        if to_generate:
            label = "all" if force else "empty"
            print(
                f"  [{result['doc_id']}] generating prefixes for {len(to_generate)}/{len(chunks)} {label} chunks..."
            )
            try:
                doc_text = _doc_text(doc)
                if not doc_text:
                    print(f"  [{result['doc_id']}] WARNING: no page text found -- skipping")
                    result["error"] = "no page text"
                    return result
                saved = generate_and_save(to_generate, doc_text)
                result["prefixes_saved"] = saved
                print(f"  [{result['doc_id']}] prefixes saved: {saved}/{len(to_generate)}")
            except Exception as exc:
                result["error"] = str(exc)
                print(f"  [{result['doc_id']}] FAILED prefix generation: {exc}")
                return result

    # Re-index to Azure Search using contextualized_text (CR-2 path)
    print(f"  [{result['doc_id']}] re-indexing to Azure Search...")
    try:
        t0 = time.time()
        VectorIndexService.index_document(doc, force=True)
        elapsed = round(time.time() - t0, 1)
        result["reindexed"] = True
        print(f"  [{result['doc_id']}] re-indexed OK ({elapsed}s)")
    except Exception as exc:
        result["error"] = str(exc)
        print(f"  [{result['doc_id']}] FAILED re-index: {exc}")

    return result


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--doc-ids",
        nargs="+",
        default=None,
        help="Doc ID prefixes to backfill (8 chars)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Backfill all docs in DB that have any empty prefix",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-index even if all prefixes already filled",
    )
    args = parser.parse_args()

    if args.all:
        doc_ids_with_empty = (
            DocumentChunk.objects.filter(contextual_prefix="")
            .values_list("document_id", flat=True)
            .distinct()
        )
        docs = Document.objects.filter(id__in=doc_ids_with_empty)
        print(f"Found {docs.count()} docs with empty prefixes")
    elif args.doc_ids:
        docs = []
        for prefix in args.doc_ids:
            qs = Document.objects.filter(id__startswith=prefix)
            if not qs.exists():
                print(f"  [SKIP] no doc matching {prefix}")
            else:
                docs.append(qs.first())
    else:
        # Default: benchmark docs
        docs = []
        for prefix in BENCHMARK_DOC_PREFIXES:
            qs = Document.objects.filter(id__startswith=prefix)
            if qs.exists():
                docs.append(qs.first())
        print(f"Benchmark docs found: {len(docs)}/{len(BENCHMARK_DOC_PREFIXES)}")

    print(f"\nBackfilling {len(docs)} documents...\n")
    results = []
    for doc in docs:
        r = backfill_doc(doc, force=args.force)
        results.append(r)
        print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    ok = [r for r in results if r["reindexed"]]
    fail = [r for r in results if r["error"]]
    skipped = [r for r in results if not r["reindexed"] and not r["error"]]
    print(f"  Re-indexed : {len(ok)}")
    print(f"  Skipped    : {len(skipped)}")
    print(f"  Failed     : {len(fail)}")
    if fail:
        print("\nFailed docs:")
        for r in fail:
            print(f"  {r['doc_id']}  error={r['error']}")

    total_empty_before = sum(r["empty_before"] for r in results)
    total_saved = sum(r["prefixes_saved"] for r in results)
    print(f"\n  Empty prefixes before : {total_empty_before}")
    print(f"  Prefixes generated    : {total_saved}")
    remaining = total_empty_before - total_saved
    if remaining:
        print(f"  Still empty           : {remaining}  (hit 429? re-run script)")
    else:
        print("  All prefixes filled -- embedding space now consistent")
    print("\nNext: python eval/run_retrieval_benchmark.py  ->  benchmark_phase6b.json")


if __name__ == "__main__":
    main()
