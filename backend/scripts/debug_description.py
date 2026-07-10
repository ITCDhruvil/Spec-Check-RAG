"""Debug project_description extraction for RFP doc."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from apps.documents.models import Document
from apps.intelligence.prompts.templates import EXTRACTION_SYSTEM_PROMPT
from apps.intelligence.services.extraction_feedback_hints import build_group_feedback_hints
from apps.intelligence.services.extraction_groups import GROUP_EXTRACTION_GROUPS
from apps.intelligence.services.group_extraction_service import (
    _description_text_from_pages,
    group_extraction_user_prompt,
    prepare_group_document_text,
)
from apps.intelligence.services.grounding import validate_and_score_items
from apps.intelligence.services.openai_service import OpenAIService

DOC_ID = "47adb3c7-f410-455d-9063-ce0576be4e62"


def main() -> None:
    doc = Document.objects.select_related("parsed_document").get(pk=DOC_ID)
    page_texts = list(
        doc.parsed_document.pages.order_by("page_number").values_list(
            "page_number", "extracted_text"
        )
    )
    group = next(g for g in GROUP_EXTRACTION_GROUPS if g.group_id == "project_description")
    client = OpenAIService()

    def llm_count(text: str) -> tuple[int, int]:
        data, _ = client.chat_json(
            system=EXTRACTION_SYSTEM_PROMPT,
            user=group_extraction_user_prompt(group, text),
            model="gpt-4o",
        )
        raw = data.get("items") or []
        validated = validate_and_score_items(
            raw,
            chunk_text=text,
            section_title=group.title,
            page_start=1,
            page_end=49,
            total_pages=49,
            page_texts=page_texts,
        )
        return len(raw), len(validated)

    print("=== Page range sweep ===")
    for lo, hi in [(17, 20), (16, 20), (16, 22), (17, 22), (16, 21)]:
        chunks = [
            f"--- Page {p} ---\n{t.strip()}"
            for p, t in page_texts
            if lo <= p <= hi and (t or "").strip()
        ]
        text = "\n\n".join(chunks)
        raw, val = llm_count(text)
        print(f"pages {lo}-{hi} len={len(text)} raw={raw} validated={val}")

    print("\n=== Cap sweep (pages 16-22) ===")
    base = [
        f"--- Page {p} ---\n{t.strip()}"
        for p, t in page_texts
        if 16 <= p <= 22 and (t or "").strip()
    ]
    full_16_22 = "\n\n".join(base)
    for cap in [4000, 6000, 7500, 8500, 9000, len(full_16_22)]:
        text = full_16_22[:cap]
        raw, val = llm_count(text)
        print(f"cap {cap} len={len(text)} raw={raw} validated={val}")

    prep = prepare_group_document_text(
        group,
        structured_text=doc.parsed_document.structured_text or "",
        raw_text=doc.parsed_document.raw_text or "",
        page_texts=page_texts,
    )
    desc_pages = _description_text_from_pages(page_texts)
    print(f"\n=== Pipeline text ===")
    print(f"prepare_group len={len(prep)}")
    print(f"_description_text_from_pages len={len(desc_pages)}")
    print(f"first 300 chars:\n{prep[:300]!r}")
    raw, val = llm_count(prep)
    print(f"prepare_group raw={raw} validated={val}")

    hints = build_group_feedback_hints(group)
    print(f"\nhints ({len(hints)} chars):\n{hints or 'NONE'}")


if __name__ == "__main__":
    main()
