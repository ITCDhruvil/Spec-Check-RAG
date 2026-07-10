"""
Quick standalone test for the Docling parser.

Usage (from backend/):
    python test_docling_parse.py <path-to-pdf-or-docx>
    python test_docling_parse.py  # uses first PDF in sample-docs/
"""

import os
import sys
from pathlib import Path

# Bootstrap Django
BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()

from apps.parsing.parsers.docling_parser import _is_available, parse_with_docling


def find_sample_doc() -> Path | None:
    for root in [BACKEND.parent / "sample-docs", BACKEND / "sample-docs"]:
        if root.exists():
            for ext in ("*.pdf", "*.docx"):
                found = list(root.rglob(ext))
                if found:
                    return found[0]
    return None


def main() -> int:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = find_sample_doc()

    if not target:
        print("ERROR: no document supplied and no sample-docs found.", file=sys.stderr)
        return 1

    print(f"Docling available: {_is_available()}")
    if not _is_available():
        print("ERROR: docling not installed — run: pip install docling", file=sys.stderr)
        return 1

    print(f"Parsing: {target}")
    result = parse_with_docling(target)

    print(f"\n--- RESULT ---")
    print(f"Parser:        {result.parsing_metadata.get('parser')}")
    print(f"Pages:         {len(result.pages)}")
    print(f"Sections:      {len(result.sections)}")
    print(f"Tables:        {len(result.tables)}")
    print(f"Quality score: {result.parsing_quality_score:.3f}")
    print(f"Raw text len:  {len(result.raw_text)} chars")

    print(f"\n--- SECTIONS ---")
    for s in result.sections[:10]:
        print(f"  [{s.level}] {s.section_order:02d}  p{s.page_start}-{s.page_end}  {s.title[:60]!r}")

    if result.tables:
        print(f"\n--- FIRST TABLE (page {result.tables[0].page_number}) ---")
        t = result.tables[0]
        print(f"  Headers: {t.headers}")
        for row in t.rows[:3]:
            print(f"  Row: {row}")

    print(f"\n--- FIRST 500 CHARS OF STRUCTURED TEXT ---")
    print(result.structured_text[:500])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
