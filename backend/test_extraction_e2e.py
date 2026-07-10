"""
E2E extraction test — verifies three field changes:
  1. site_visit_date_time extracted separately from pre_bid_deadline_date_time
  2. set_asides returns MBE/WBE/DBE items
  3. maintenance_and_labor_bond label (not old maintenance_bond)

Runs real LLM extraction on two already-indexed docs.
Usage: python test_extraction_e2e.py
"""
import os, sys, logging
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
sys.path.insert(0, ".")
import django; django.setup()
logging.disable(logging.CRITICAL)

from apps.documents.models import Document
from apps.intelligence.models import DocumentChunk, ExtractedInsight, GeneratedSummary
from apps.intelligence.services.extraction_service import ExtractionService
from apps.intelligence.choices import ExtractionType
from apps.parsing.models import ParsedDocument

SEP = "=" * 70

# Doc with site visit + set asides content in chunks
DOC_SA_SV = "51624e64-3725-4b17-ac77-060845f69930"
# Doc with set asides + maintenance bond content in chunks
DOC_SA_MB = "ae8ad719-e46c-40a4-be1f-217467ecd5c4"


def _get_or_create_summary(doc: Document) -> GeneratedSummary:
    summary = GeneratedSummary.objects.filter(document=doc, is_current=True).first()
    if summary is None:
        summary = GeneratedSummary.objects.create(
            document=doc,
            status="pending",
            is_current=True,
        )
    return summary


def run_single_type(doc_id: str, etype: str) -> list[dict]:
    doc = Document.objects.get(id=doc_id)
    parsed = ParsedDocument.objects.filter(document=doc).first()
    chunks = list(DocumentChunk.objects.filter(document=doc).order_by("chunk_order"))
    summary = _get_or_create_summary(doc)
    total_pages = parsed.total_pages if parsed else 1
    page_texts = []
    if parsed:
        page_texts = list(
            parsed.pages.order_by("page_number").values_list("page_number", "extracted_text")
        )

    from apps.intelligence.services.adaptive_lexicon_service import AdaptiveLexiconService
    from apps.intelligence.services.doc_classifier import classify as classify_document
    from apps.intelligence.services.extraction_retrieval_service import (
        ExtractionRetrievalService, overrides_for_classification,
    )

    cover_text = AdaptiveLexiconService.cover_sample_text(chunks, page_texts)
    lexicon = AdaptiveLexiconService.build(chunks, page_texts)
    classification = classify_document(cover_text)
    doc_type_overrides = overrides_for_classification(classification)
    hybrid_by_type = ExtractionRetrievalService.scores_for_types(
        str(doc.id), [etype], lexicon=lexicon,
        extra_queries_by_type=doc_type_overrides or None,
    )
    selected = ExtractionService.select_chunks(
        chunks, etype, hybrid_scores=hybrid_by_type.get(etype),
        adaptive_terms=lexicon.terms_for(etype),
    )

    insight = ExtractionService._extract_single_type(
        etype, selected, doc, summary, total_pages, page_texts,
        all_chunks=chunks, lexicon=lexicon, cover_text=cover_text,
    )
    return (insight.payload or {}).get("items", [])


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))


def test_site_visit(doc_id: str) -> None:
    print(f"\n{SEP}")
    print("TEST 1: site_visit_date_time separate from pre_bid_deadline_date_time")
    print(f"Doc: {doc_id}")
    print(SEP)

    items = run_single_type(doc_id, ExtractionType.SUBMISSION_DEADLINES)
    labels = [i.get("label") for i in items]
    print(f"\n  All date labels extracted: {labels}")
    for i in items:
        lbl = i.get("label", "?")
        val = i.get("date") or i.get("value") or "?"
        print(f"    {lbl}: {str(val)[:60]}")

    has_site_visit = "site_visit_date_time" in labels
    has_prebid = "pre_bid_deadline_date_time" in labels
    check("site_visit_date_time present", has_site_visit)
    check("pre_bid not absorbing site visit", not (has_prebid and not has_site_visit) or has_site_visit)

    # Also verify alias in grounding: if LLM returned site_visit, check no pre_bid alias conflict
    sv_count = labels.count("site_visit_date_time")
    check("no duplicate site_visit rows", sv_count <= 1, f"count={sv_count}")


def test_set_asides(doc_id: str) -> None:
    print(f"\n{SEP}")
    print("TEST 2: set_asides (MBE/WBE/DBE)")
    print(f"Doc: {doc_id}")
    print(SEP)

    items = run_single_type(doc_id, ExtractionType.SET_ASIDES)
    labels = [i.get("label") for i in items]
    print(f"\n  Set-aside items: {len(items)}")
    for i in items:
        lbl = i.get("label", "?")
        val = i.get("value") or i.get("text") or "?"
        conf = i.get("confidence", "?")
        src = (i.get("source_text") or "")[:50]
        print(f"    {lbl}: {str(val)[:55]}  conf={conf}")
        if src:
            print(f"      src: {src!r}".encode("ascii", "replace").decode())

    check("set_asides items found", len(items) > 0, f"count={len(items)}")
    check("labels are valid set_aside_* keys",
          all(l.startswith("set_aside_") for l in labels if l),
          str(labels))


def test_maintenance_bond(doc_id: str) -> None:
    print(f"\n{SEP}")
    print("TEST 3: maintenance_and_labor_bond label")
    print(f"Doc: {doc_id}")
    print(SEP)

    items = run_single_type(doc_id, ExtractionType.PENALTIES_AND_RISKS)
    labels = [i.get("label") for i in items]
    print(f"\n  Bond items: {len(items)}")
    for i in items:
        lbl = i.get("label", "?")
        val = i.get("value") or i.get("text") or "?"
        print(f"    {lbl}: {str(val)[:60]}")

    old_label_present = "maintenance_bond" in labels
    new_label_present = "maintenance_and_labor_bond" in labels

    check("maintenance_and_labor_bond label present", new_label_present,
          f"labels={labels}")
    check("old maintenance_bond label absent", not old_label_present,
          "alias should have converted it" if old_label_present else "clean")


if __name__ == "__main__":
    doc_id_override = sys.argv[1] if len(sys.argv) > 1 else None

    test_site_visit(doc_id_override or DOC_SA_SV)
    test_set_asides(doc_id_override or DOC_SA_SV)
    test_maintenance_bond(doc_id_override or DOC_SA_MB)

    print(f"\n{SEP}")
    print("DONE")
    print(SEP)
