"""
Phase 2 chunking test — parse + chunk a PDF and print stats.

  python eval/run_phase2_chunk_test.py "path/to/file.pdf"
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from apps.intelligence.services.chunking_strategy import (
    build_section_chunks,
    build_table_chunks,
    consolidate_sections,
    dedupe_table_against_sections,
)
from apps.intelligence.services.chunking_service import _infer_tags
from apps.intelligence.services.citation_service import extract_section_prefix
from apps.parsing.parsers.pdf_router import parse_pdf


def _sections_from_parse(result):
    return [
        type("S", (), {
            "title": s.title,
            "content": s.content,
            "page_start": s.page_start,
            "page_end": s.page_end,
            "section_order": s.section_order,
            "level": s.level,
            "section_path": s.section_path,
            "parent_section_order": s.parent_section_order,
        })()
        for s in result.sections
    ]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python eval/run_phase2_chunk_test.py <pdf-path>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1]).resolve()
    print(f"Parsing {pdf_path.name}...")
    t0 = time.perf_counter()
    result = parse_pdf(pdf_path)
    parse_sec = time.perf_counter() - t0
    print(f"Parse: {parse_sec:.1f}s — {len(result.sections)} raw sections")

    class FakeParsed:
        parsing_metadata = result.parsing_metadata

    sections = _sections_from_parse(result)
    t1 = time.perf_counter()
    logical = consolidate_sections(sections)
    table_drafts = build_table_chunks(FakeParsed())  # type: ignore[arg-type]
    section_drafts = build_section_chunks(
        logical,
        section_tags_fn=_infer_tags,
        section_prefix_fn=extract_section_prefix,
    )
    table_drafts = dedupe_table_against_sections(table_drafts, section_drafts)
    all_drafts = table_drafts + section_drafts
    chunk_sec = time.perf_counter() - t1

    types = Counter(d.metadata.get("chunk_type", "?") for d in all_drafts)
    char_counts = [len(d.chunk_text) for d in all_drafts]

    print(f"Chunk: {chunk_sec:.2f}s")
    print(f"Logical sections: {len(logical)} (from {len(sections)} raw)")
    print(f"Total chunks: {len(all_drafts)}")
    print(f"Chunk types: {dict(types)}")
    if char_counts:
        print(f"Chars/chunk: min={min(char_counts)} avg={sum(char_counts)//len(char_counts)} max={max(char_counts)}")

    print("\nFirst 12 chunks:")
    for i, d in enumerate(all_drafts[:12]):
        preview = d.chunk_text[:60].replace("\n", " ")
        print(
            f"  [{i+1}] {d.metadata.get('chunk_type'):16} p{d.page_start}-{d.page_end} "
            f"{len(d.chunk_text):5}ch  {d.section_title[:40]!r}  {preview!r}..."
        )

    out = BACKEND / "eval" / "out" / f"phase2_chunks_{pdf_path.stem[:30]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "file": str(pdf_path),
                "parse_seconds": round(parse_sec, 2),
                "chunk_seconds": round(chunk_sec, 2),
                "raw_sections": len(sections),
                "logical_sections": len(logical),
                "chunk_count": len(all_drafts),
                "chunk_types": dict(types),
                "chunks_sample": [
                    {
                        "chunk_type": d.metadata.get("chunk_type"),
                        "section_title": d.section_title,
                        "page_start": d.page_start,
                        "char_count": len(d.chunk_text),
                        "leaf_count": d.metadata.get("leaf_count"),
                    }
                    for d in all_drafts[:40]
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nReport: {out}")


if __name__ == "__main__":
    main()
