"""
Phase 4 extraction hybrid retrieval test.

Compares keyword-only vs keyword+hybrid chunk selection per extraction type.

Usage (from backend/):
  python eval/run_phase4_extraction_retrieval_test.py --document-id <uuid>
  python eval/run_phase4_extraction_retrieval_test.py --document-id <uuid> --reindex

Requires: document parsed, chunked, and indexed (run Generate Summary once, or --reindex).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from django.conf import settings

from apps.chat.services.index_service import VectorIndexService
from apps.chat.services.vector_store import use_azure_search
from apps.documents.models import Document
from apps.intelligence.choices import FOCUSED_EXTRACTION_TYPES
from apps.intelligence.models import DocumentChunk
from apps.intelligence.services.adaptive_lexicon_service import AdaptiveLexiconService
from apps.intelligence.services.extraction_retrieval_service import ExtractionRetrievalService
from apps.intelligence.services.extraction_service import ExtractionService


def _chunk_summary(chunk) -> dict:
    meta = chunk.metadata or {}
    return {
        "chunk_id": str(chunk.id),
        "chunk_order": chunk.chunk_order,
        "chunk_type": meta.get("chunk_type", ""),
        "pages": f"{chunk.page_start}-{chunk.page_end}",
        "section_title": (chunk.section_title or "")[:80],
        "chars": len(chunk.chunk_text),
    }


def compare_selections(
    chunks: list,
    extraction_type: str,
    hybrid_scores: dict[str, float],
    adaptive_terms: list[str] | None = None,
) -> dict:
    keyword = ExtractionService.select_chunks(
        chunks, extraction_type, keyword_only=True
    )
    static_hybrid = ExtractionService.select_chunks(
        chunks, extraction_type, hybrid_scores=hybrid_scores
    )
    adaptive = ExtractionService.select_chunks(
        chunks,
        extraction_type,
        hybrid_scores=hybrid_scores,
        adaptive_terms=adaptive_terms,
    )
    kw_ids = {str(c.id) for c in keyword}
    st_ids = {str(c.id) for c in static_hybrid}
    ad_ids = {str(c.id) for c in adaptive}
    added_adaptive = ad_ids - kw_ids
    added_hybrid_only = st_ids - kw_ids

    added_details = [_chunk_summary(c) for c in adaptive if str(c.id) in added_adaptive]
    return {
        "extraction_type": extraction_type,
        "keyword_count": len(keyword),
        "static_hybrid_count": len(static_hybrid),
        "adaptive_count": len(adaptive),
        "overlap_keyword_adaptive": len(kw_ids & ad_ids),
        "added_by_static_hybrid": len(added_hybrid_only),
        "added_by_adaptive": len(added_adaptive),
        "adaptive_term_count": len(adaptive_terms or []),
        "hybrid_score_hits": len(hybrid_scores),
        "added_chunks": added_details,
        "adaptive_terms_sample": (adaptive_terms or [])[:6],
        "keyword_chunk_ids": sorted(kw_ids),
        "adaptive_chunk_ids": sorted(ad_ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4 hybrid extraction retrieval test")
    parser.add_argument("--document-id", required=True, help="Document UUID in the database")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Re-embed and upsert chunks before comparison",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output JSON path (default: eval/out/phase4_<doc_id>.json)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 4 Extraction Hybrid Retrieval Test")
    print("=" * 60)
    print(f"HYBRID_ENABLED:     {settings.INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED}")
    print(f"ADAPTIVE_ENABLED:   {settings.INTELLIGENCE_ADAPTIVE_LEXICON_ENABLED}")
    print(f"ADAPTIVE_LLM:       {settings.INTELLIGENCE_ADAPTIVE_LEXICON_LLM}")
    print(f"Vector backend:     {VectorIndexService.backend_name()}")
    print(f"Azure Search:       {use_azure_search()}")
    print(f"Retrieval top-K:    {settings.INTELLIGENCE_EXTRACTION_RETRIEVAL_TOP_K}")
    print(f"Min score:          {settings.INTELLIGENCE_EXTRACTION_MIN_RETRIEVAL_SCORE}")

    document = Document.objects.filter(pk=args.document_id).first()
    if not document:
        print(f"Document not found: {args.document_id}")
        sys.exit(1)

    chunks = list(DocumentChunk.objects.filter(document=document).order_by("chunk_order"))
    if not chunks:
        print("No chunks — run Generate Summary or chunking first.")
        sys.exit(1)

    print(f"\nDocument: {document.original_filename}")
    print(f"Chunks:   {len(chunks)}")

    if args.reindex:
        print("Reindexing...")
        VectorIndexService.index_document(document, force=True)
        print("Reindex: OK")

    indexed = VectorIndexService.is_indexed(document.id)
    print(f"Indexed:  {indexed}")
    if not indexed:
        print("WARNING: document not indexed — hybrid scores will be empty.")
        print("Run with --reindex or generate summary first.")

    doc_id = str(document.id)
    cover_text = AdaptiveLexiconService.cover_sample_text(chunks, list(
        document.parsed_document.pages.order_by("page_number").values_list(
            "page_number", "extracted_text"
        )
    ))
    lexicon = AdaptiveLexiconService.build(chunks, list(
        document.parsed_document.pages.order_by("page_number").values_list(
            "page_number", "extracted_text"
        )
    ))
    focused_types = ExtractionService._focused_types_for_prompt_version()
    hybrid_by_type = ExtractionRetrievalService.scores_for_types(
        doc_id, focused_types, lexicon=lexicon
    )
    AdaptiveLexiconService.enrich_from_hybrid_feedback(lexicon, chunks, hybrid_by_type)

    comparisons = []
    total_added_static = 0
    total_added_adaptive = 0
    print("\nAdaptive lexicon:", lexicon.to_debug_dict())
    print("\nPer-type comparison (KW = keyword only, HY = +hybrid, AD = +adaptive terms):")
    print(f"{'Type':<28} {'KW':>4} {'HY':>4} {'AD':>4} {'+AD':>4} {'terms':>5}")
    print("-" * 58)

    for etype in focused_types:
        scores = hybrid_by_type.get(etype, {})
        row = compare_selections(
            chunks, etype, scores, lexicon.terms_for(etype)
        )
        comparisons.append(row)
        total_added_static += row["added_by_static_hybrid"]
        total_added_adaptive += row["added_by_adaptive"]
        print(
            f"{etype:<28} {row['keyword_count']:>4} {row['static_hybrid_count']:>4} "
            f"{row['adaptive_count']:>4} {row['added_by_adaptive']:>4} "
            f"{row['adaptive_term_count']:>5}"
        )
        for added in row["added_chunks"][:2]:
            print(
                f"  + [{added['chunk_type']}] p{added['pages']} "
                f"{added['section_title']!r}"
            )
        if row["adaptive_terms_sample"]:
            print(f"  terms: {row['adaptive_terms_sample'][:3]}")

    report = {
        "document_id": doc_id,
        "filename": document.original_filename,
        "chunk_count": len(chunks),
        "indexed": indexed,
        "vector_backend": VectorIndexService.backend_name(),
        "hybrid_enabled": settings.INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED,
        "adaptive_lexicon": lexicon.to_debug_dict(),
        "cover_text_chars": len(cover_text),
        "total_added_by_static_hybrid": total_added_static,
        "total_added_by_adaptive": total_added_adaptive,
        "comparisons": comparisons,
    }

    out_path = Path(args.out) if args.out else BACKEND / "eval" / "out" / f"phase4_{doc_id[:8]}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {out_path}")

    if not indexed:
        sys.exit(2)
    if total_added_adaptive == 0 and settings.INTELLIGENCE_HYBRID_RETRIEVAL_ENABLED:
        print("\nNOTE: adaptive layer did not add chunks beyond keyword routing.")
        print("Try a document with unusual terminology or disable LLM to compare heuristic-only.")
    else:
        print(
            f"\nPhase 4 test complete — adaptive added {total_added_adaptive} chunk slots "
            f"(static hybrid: {total_added_static})."
        )


if __name__ == "__main__":
    main()
