"""
Phase 4 learned lexicon A/B test — verify Layer 2 LLM is skipped on repeat/similar docs.

Compares two documents (or the same document twice):
  1. Document A — cold cache: expect LLM lexicon call + terms persisted to DB
  2. Document B — warm cache: expect learned_cache + llm_skipped_cache (no LLM)

Usage (from backend/):
  python eval/run_phase4_learned_lexicon_test.py --reset
  python eval/run_phase4_learned_lexicon_test.py \\
    --doc-a c3f4db27-27c8-4164-bd96-f99ff0b0e2b4 \\
    --doc-b 58df83e0-bd88-42dc-b515-65c543bc75a0

  # Same doc twice (strongest skip signal):
  python eval/run_phase4_learned_lexicon_test.py --reset \\
    --doc-a c3f4db27-27c8-4164-bd96-f99ff0b0e2b4 \\
    --doc-b c3f4db27-27c8-4164-bd96-f99ff0b0e2b4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from django.conf import settings
from django.db.models import Count

from apps.documents.models import Document
from apps.intelligence.choices import LearnedEntryKind, FOCUSED_EXTRACTION_TYPES
from apps.intelligence.models import DocumentChunk, LearnedExtractionTerm
from apps.intelligence.services.adaptive_lexicon_service import AdaptiveLexiconService
from apps.intelligence.services.learned_lexicon_store import LearnedLexiconStore


def _db_stats() -> dict:
    total = LearnedExtractionTerm.objects.filter(is_active=True).count()
    by_type = (
        LearnedExtractionTerm.objects.filter(
            is_active=True, entry_kind=LearnedEntryKind.TERM
        )
        .values("extraction_type")
        .annotate(c=Count("id"))
    )
    by_source = (
        LearnedExtractionTerm.objects.filter(is_active=True)
        .values("source")
        .annotate(c=Count("id"))
    )
    return {
        "total": total,
        "terms_by_type": {row["extraction_type"]: row["c"] for row in by_type},
        "by_source": {row["source"]: row["c"] for row in by_source},
        "cache_sufficient": LearnedLexiconStore.cache_sufficient(list(FOCUSED_EXTRACTION_TYPES)),
    }


def _run_for_document(document_id: str, *, label: str) -> dict:
    document = Document.objects.filter(pk=document_id).first()
    if not document:
        raise SystemExit(f"Document not found: {document_id}")

    chunks = list(DocumentChunk.objects.filter(document=document).order_by("chunk_order"))
    if not chunks:
        raise SystemExit(f"No chunks for {document_id} — run Generate Summary first.")

    page_texts = list(
        document.parsed_document.pages.order_by("page_number").values_list(
            "page_number", "extracted_text"
        )
    )
    cover = AdaptiveLexiconService.cover_sample_text(chunks, page_texts)
    loaded_before_build = LearnedLexiconStore.load_for_types()
    cover_novel_before = LearnedLexiconStore.cover_has_novel_terms(
        cover, loaded_before_build.normalized_terms
    )
    should_skip_before = LearnedLexiconStore.should_skip_llm_lexicon(
        cover, loaded_before_build
    )
    db_before = _db_stats()
    llm_calls = {"count": 0}

    original_chat_json = None

    def _counting_chat_json(self, **kwargs):
        llm_calls["count"] += 1
        return original_chat_json(self, **kwargs)

    from apps.intelligence.services import openai_service

    original_chat_json = openai_service.OpenAIService.chat_json

    with patch.object(openai_service.OpenAIService, "chat_json", _counting_chat_json):
        lexicon = AdaptiveLexiconService.build(chunks, page_texts)

    db_after = _db_stats()

    return {
        "label": label,
        "document_id": str(document.id),
        "filename": document.original_filename,
        "chunk_count": len(chunks),
        "cover_chars": len(cover),
        "cover_has_novel_terms": cover_novel_before,
        "should_skip_llm_before": should_skip_before,
        "llm_chat_json_calls": llm_calls["count"],
        "lexicon_sources": lexicon.sources,
        "llm_skipped": "llm_skipped_cache" in lexicon.sources,
        "llm_used": "llm" in lexicon.sources,
        "learned_cache_loaded": "learned_cache" in lexicon.sources,
        "terms_in_lexicon": sum(len(v) for v in lexicon.terms_by_type.values()),
        "queries_in_lexicon": sum(len(v) for v in lexicon.queries_by_type.values()),
        "lexicon_debug": lexicon.to_debug_dict(),
        "db_before": db_before,
        "db_after": db_after,
        "db_terms_added": db_after["total"] - db_before["total"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Learned lexicon two-document test")
    parser.add_argument("--doc-a", required=True, help="First document UUID (cold cache)")
    parser.add_argument("--doc-b", required=True, help="Second document UUID (warm cache)")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear LearnedExtractionTerm table before test",
    )
    parser.add_argument("--out", default="", help="JSON report path")
    args = parser.parse_args()

    print("=" * 60)
    print("Phase 4 Learned Lexicon — Two Document Test")
    print("=" * 60)
    print(f"LEARNED_LEXICON_ENABLED:  {settings.INTELLIGENCE_LEARNED_LEXICON_ENABLED}")
    print(f"ADAPTIVE_LLM:             {settings.INTELLIGENCE_ADAPTIVE_LEXICON_LLM}")
    print(f"SKIP_IF_CACHE_FULL:       {settings.INTELLIGENCE_ADAPTIVE_LLM_SKIP_IF_CACHE_FULL}")
    print(f"MIN_TERMS_PER_TYPE:       {settings.INTELLIGENCE_LEARNED_LEXICON_MIN_TERMS_PER_TYPE}")
    print()

    if args.reset:
        deleted, _ = LearnedExtractionTerm.objects.all().delete()
        print(f"Reset: deleted {deleted} learned term rows\n")

    print("--- Document A (cold / first pass) ---")
    result_a = _run_for_document(args.doc_a, label="A")
    _print_result(result_a)

    print("\n--- Document B (warm / second pass) ---")
    result_b = _run_for_document(args.doc_b, label="B")
    _print_result(result_b)

    passed = _evaluate(result_a, result_b, same_doc=args.doc_a == args.doc_b)
    report = {
        "settings": {
            "learned_lexicon_enabled": settings.INTELLIGENCE_LEARNED_LEXICON_ENABLED,
            "min_terms_per_type": settings.INTELLIGENCE_LEARNED_LEXICON_MIN_TERMS_PER_TYPE,
            "skip_if_cache_full": settings.INTELLIGENCE_ADAPTIVE_LLM_SKIP_IF_CACHE_FULL,
        },
        "document_a": result_a,
        "document_b": result_b,
        "same_document": args.doc_a == args.doc_b,
        "passed": passed,
    }

    out_path = (
        Path(args.out)
        if args.out
        else BACKEND / "eval" / "out" / "phase4_learned_lexicon_ab.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {out_path}")

    if passed:
        print("\nPASSED — learned lexicon behavior matches expectations.")
        sys.exit(0)
    print("\nFAILED — see checks above.")
    sys.exit(1)


def _print_result(r: dict) -> None:
    print(f"  File:       {r['filename'][:60]}")
    print(f"  Skip LLM?  {r['should_skip_llm_before']} (before build)")
    print(f"  Cover novel:{r['cover_has_novel_terms']} (before build)")
    print(f"  LLM calls:  {r['llm_chat_json_calls']}")
    print(f"  Sources:    {r['lexicon_sources']}")
    print(f"  DB terms:   {r['db_before']['total']} -> {r['db_after']['total']} (+{r['db_terms_added']})")
    print(f"  Cache OK:   {r['db_after']['cache_sufficient']}")
    print(f"  By source:  {r['db_after']['by_source']}")


def _evaluate(a: dict, b: dict, *, same_doc: bool) -> bool:
    checks: list[tuple[str, bool]] = []

    checks.append(("A persisted terms to DB", a["db_terms_added"] > 0 or a["db_after"]["total"] > 0))
    checks.append(
        (
            "A used LLM or heuristic (sources present)",
            bool(a["lexicon_sources"]),
        )
    )

    if same_doc:
        checks.append(("B skipped LLM (same doc repeat)", b["llm_skipped"]))
        checks.append(("B made zero LLM calls", b["llm_chat_json_calls"] == 0))
        checks.append(("B loaded learned_cache", b["learned_cache_loaded"]))
    else:
        # Different doc: warm cache loaded; LLM only if cover introduces new vocabulary
        expect_llm = b["cover_has_novel_terms"]
        if expect_llm:
            checks.append(
                (
                    "B cover has novel terms (LLM call expected)",
                    b["cover_has_novel_terms"],
                )
            )
            checks.append(
                (
                    "B attempted LLM or added new DB terms",
                    b["llm_chat_json_calls"] >= 1 or b["db_terms_added"] > 0,
                )
            )
        else:
            checks.append(("B skipped LLM (no novel cover terms)", b["llm_skipped"]))
            checks.append(("B made zero LLM calls", b["llm_chat_json_calls"] == 0))
        checks.append(("B loaded learned_cache from doc A", b["learned_cache_loaded"]))
        checks.append(
            (
                "B DB terms >= doc A (cache grew or stayed)",
                b["db_after"]["total"] >= a["db_after"]["total"],
            )
        )

    print("\n--- Evaluation ---")
    all_ok = True
    for name, ok in checks:
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name}")
        all_ok = all_ok and ok
    return all_ok


if __name__ == "__main__":
    main()
