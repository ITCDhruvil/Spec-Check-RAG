"""
One-off Phase 1 parse test — run from backend/:
  python eval/run_phase1_parse_test.py "path/to/file.pdf"
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Django bootstrap
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from django.conf import settings

from apps.parsing.parsers.azure_di_parser import is_azure_di_configured
from apps.parsing.parsers.pdf_router import parse_pdf


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python eval/run_phase1_parse_test.py <pdf-path>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1]).resolve()
    if not pdf_path.is_file():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    print("=" * 60)
    print("Phase 1 Parse Test")
    print("=" * 60)
    print(f"File:       {pdf_path.name}")
    print(f"Size:       {pdf_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"Parser:     PARSING_PDF_PARSER={settings.PARSING_PDF_PARSER}")
    print(f"Azure DI:   configured={is_azure_di_configured()} model={settings.AZURE_DI_MODEL}")
    print("-" * 60)

    started = time.perf_counter()
    result = parse_pdf(pdf_path)
    elapsed = time.perf_counter() - started

    meta = result.parsing_metadata
    print(f"Elapsed:    {elapsed:.1f}s")
    print(f"Engine:     {meta.get('parser')}")
    print(f"Pages:      {meta.get('total_pages')}")
    print(f"Empty pgs:  {meta.get('empty_pages', 0)}")
    print(f"OCR pages:  {meta.get('ocr_pages', 0)}")
    print(f"Quality:    {result.parsing_quality_score:.3f}")
    print(f"Tables:     {len(meta.get('tables', []))}")
    print(f"Sections:   {len(result.sections)}")
    print(f"Layout blk: {meta.get('layout_blocks_count', len(result.layout_blocks))}")
    print(f"Raw chars:  {len(result.raw_text):,}")
    print("-" * 60)

    print("\nTop-level sections (first 15):")
    for s in result.sections[:15]:
        parent = f" parent={s.parent_section_order}" if s.parent_section_order is not None else ""
        print(
            f"  [{s.section_order}] L{s.level} p{s.page_start}-{s.page_end}{parent} "
            f"{s.title[:70]!r} ({len(s.content)} chars)"
        )
    if len(result.sections) > 15:
        print(f"  ... +{len(result.sections) - 15} more sections")

    print("\nSample layout blocks (first 8):")
    blocks = meta.get("layout_blocks") or []
    for block in blocks[:8]:
        text_preview = (block.get("text") or "")[:80].replace("\n", " ")
        print(
            f"  p{block.get('page')} {block.get('type'):10} role={block.get('role',''):15} "
            f"{text_preview!r}..."
        )

    print("\nSample tables (first 3):")
    for table in meta.get("tables", [])[:3]:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        print(f"  page {table.get('page')}: headers={headers[:5]} rows={len(rows)}")

    out_dir = BACKEND / "eval" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"phase1_parse_{pdf_path.stem[:40]}.json"
    report = {
        "file": str(pdf_path),
        "elapsed_seconds": round(elapsed, 2),
        "parsing_metadata": {
            k: meta[k]
            for k in (
                "parser",
                "azure_model",
                "total_pages",
                "empty_pages",
                "ocr_pages",
                "tables",
                "layout_blocks_count",
            )
            if k in meta
        },
        "parsing_quality_score": result.parsing_quality_score,
        "section_count": len(result.sections),
        "sections_sample": [
            {
                "order": s.section_order,
                "level": s.level,
                "title": s.title,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "parent_section_order": s.parent_section_order,
                "section_path": s.section_path,
                "content_chars": len(s.content),
            }
            for s in result.sections[:30]
        ],
        "layout_blocks_sample": (meta.get("layout_blocks") or [])[:20],
    }
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out_file}")


if __name__ == "__main__":
    main()
