"""
Phase 2 chunking strategy: section-bound splits, overlap, chunk types, table-native chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.conf import settings

from apps.parsing.models import DocumentSection, ParsedDocument

# Hard boundary: numbered clause headings (1. / 2.1 / 2.1.3 Title)
CLAUSE_HEADING = re.compile(r"^\d+(?:\.\d+)+\s+[A-Za-z]")

SCHEDULE_TABLE_MARKERS = (
    "bid period",
    "bid opening",
    "bid schedule",
    "pre-bid",
    "prebid",
    "due date",
    "closing date",
    "submission deadline",
    "request for information",
    "issue date",
)

BOND_MARKERS = (
    "bid bond",
    "performance bond",
    "payment bond",
    "maintenance bond",
    "surety",
    "certified check",
    "bid security",
    "bid guarantee",
)

ANNEX_MARKERS = ("annexure", "annex ", "appendix", "form ", "attachment ")


@dataclass
class ChunkDraft:
    """In-memory chunk before DocumentChunk persistence."""

    section_title: str
    chunk_text: str
    page_start: int
    page_end: int
    metadata: dict = field(default_factory=dict)


@dataclass
class _LogicalSection:
    title: str
    content: str
    page_start: int
    page_end: int
    section_order: int
    level: int = 1
    section_path: str = ""
    parent_section_order: int | None = None
    chunk_type: str = "general_section"


def _leaf_max_chars() -> int:
    return getattr(settings, "INTELLIGENCE_LEAF_CHUNK_CHARS", 4800)


def _parent_max_chars() -> int:
    return getattr(settings, "INTELLIGENCE_MAX_CHUNK_CHARS", 6000)


def _overlap_chars() -> int:
    ratio = getattr(settings, "INTELLIGENCE_CHUNK_OVERLAP_RATIO", 0.10)
    return max(100, int(_leaf_max_chars() * ratio))


def _cover_page_max() -> int:
    return getattr(settings, "INTELLIGENCE_COVER_PAGE_MAX", 2)


def _min_section_chars() -> int:
    return getattr(settings, "INTELLIGENCE_MIN_SECTION_CHARS", 40)


def _infer_chunk_type(title: str, content: str) -> str:
    combined = f"{title}\n{content}".lower()
    if any(m in combined for m in SCHEDULE_TABLE_MARKERS):
        return "schedule_table"
    if any(m in combined for m in BOND_MARKERS):
        return "bond_clause"
    if any(combined.startswith(m) or f"\n{m}" in combined for m in ANNEX_MARKERS):
        return "form_annex"
    if "instruction" in combined and "bidder" in combined:
        return "general_section"
    return "general_section"


def _is_cover_fragment(section: DocumentSection) -> bool:
    """True when a tiny section on early pages is likely cover/header noise."""
    if section.page_start > _cover_page_max():
        return False
    content_len = len((section.content or "").strip())
    if content_len == 0:
        return True
    if content_len < _min_section_chars():
        title = (section.title or "").strip()
        if title.upper() == title and len(title.split()) <= 8:
            return True
    return False


def consolidate_sections(sections: list[DocumentSection]) -> list[_LogicalSection]:
    """
    Merge fragmented cover-page sections and drop empty duplicates.

    Produces fewer, richer logical sections before leaf splitting.
    """
    if not sections:
        return []

    logical: list[_LogicalSection] = []
    cover_buffer: list[DocumentSection] = []

    def flush_cover() -> None:
        nonlocal cover_buffer
        if not cover_buffer:
            return
        titles: list[str] = []
        parts: list[str] = []
        page_start = min(s.page_start for s in cover_buffer)
        page_end = max(s.page_end for s in cover_buffer)
        for s in cover_buffer:
            t = (s.title or "").strip()
            c = (s.content or "").strip()
            if t and t.lower() != "preamble":
                titles.append(t)
            if c:
                parts.append(c if not t else f"{t}\n{c}")
        merged_title = titles[0] if len(titles) == 1 else "Cover / Front Matter"
        merged_content = "\n\n".join(parts).strip()
        if merged_content or cover_buffer:
            logical.append(
                _LogicalSection(
                    title=merged_title,
                    content=merged_content,
                    page_start=page_start,
                    page_end=page_end,
                    section_order=cover_buffer[0].section_order,
                    level=1,
                    section_path=merged_title,
                    chunk_type="cover_metadata",
                )
            )
        cover_buffer = []

    for section in sections:
        content = (section.content or "").strip()
        if _is_cover_fragment(section):
            cover_buffer.append(section)
            continue

        flush_cover()

        if not content:
            continue

        logical.append(
            _LogicalSection(
                title=section.title,
                content=content,
                page_start=section.page_start,
                page_end=section.page_end,
                section_order=section.section_order,
                level=getattr(section, "level", 1) or 1,
                section_path=getattr(section, "section_path", "") or section.title,
                parent_section_order=getattr(section, "parent_section_order", None),
                chunk_type=_infer_chunk_type(section.title, content),
            )
        )

    flush_cover()
    return logical


def _text_units(text: str) -> list[str]:
    """
    Split text into indivisible units: paragraphs, preserving clause headings as units.
    """
    units: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if len(lines) == 1:
            units.append(lines[0])
            continue
        current: list[str] = []
        for line in lines:
            stripped = line.strip()
            if CLAUSE_HEADING.match(stripped) and current:
                units.append("\n".join(current))
                current = [stripped]
            else:
                current.append(stripped)
        if current:
            units.append("\n".join(current))
    return units


def split_with_overlap(text: str, *, max_chars: int | None = None) -> list[str]:
    """Split text at paragraph/clause boundaries with trailing overlap between parts."""
    max_chars = max_chars or _leaf_max_chars()
    overlap = _overlap_chars()
    units = _text_units(text)
    if not units:
        return [text] if text.strip() else []

    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if not current:
            return
        parts.append("\n\n".join(current))
        if overlap > 0 and len(parts) > 0:
            joined = parts[-1]
            tail = joined[-overlap:] if len(joined) > overlap else joined
            current = [tail] if tail.strip() else []
            current_len = len(tail)
        else:
            current = []
            current_len = 0

    for unit in units:
        unit_len = len(unit)
        if unit_len > max_chars:
            if current:
                flush()
            # Long single unit: hard-split on sentences/lines without overlap mid-unit
            for line in unit.splitlines():
                if current_len + len(line) + 1 > max_chars and current:
                    parts.append("\n\n".join(current))
                    current = [line]
                    current_len = len(line)
                else:
                    current.append(line)
                    current_len += len(line) + 1
            continue

        if current_len + unit_len + 2 > max_chars and current:
            flush()

        current.append(unit)
        current_len += unit_len + 2

    if current:
        parts.append("\n\n".join(current))

    # Remove duplicate overlap-only leading fragments
    cleaned: list[str] = []
    for part in parts:
        p = part.strip()
        if not p:
            continue
        if cleaned and len(p) < overlap and p in cleaned[-1]:
            continue
        cleaned.append(p)
    return cleaned or ([text.strip()] if text.strip() else [])


def _table_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    lines: list[str] = []
    if headers:
        lines.append(" | ".join(str(h) for h in headers))
        lines.append(" | ".join("---" for _ in headers))
    for row in rows:
        lines.append(" | ".join(str(c) for c in row))
    return "\n".join(lines)


def _infer_table_chunk_type(headers: list[str], rows: list[list[str]]) -> str:
    blob = " ".join(headers + [c for row in rows for c in row]).lower()
    if any(m in blob for m in SCHEDULE_TABLE_MARKERS):
        return "schedule_table"
    if any(m in blob for m in BOND_MARKERS):
        return "bond_clause"
    return "table"


def build_table_chunks(parsed: ParsedDocument) -> list[ChunkDraft]:
    """Dedicated table-native chunks from parsing metadata."""
    drafts: list[ChunkDraft] = []
    seen_pages: set[int] = set()
    for table in parsed.parsing_metadata.get("tables", []):
        page = int(table.get("page") or 1)
        headers = table.get("headers") or []
        rows = table.get("rows") or []
        if not headers and not rows:
            continue
        text = _table_to_markdown(headers, rows)
        if not text.strip():
            continue
        chunk_type = _infer_table_chunk_type(headers, rows)
        # One schedule_table chunk per page (prefer first / richest table on page)
        if chunk_type == "schedule_table" and page in seen_pages:
            continue
        seen_pages.add(page)
        drafts.append(
            ChunkDraft(
                section_title=f"Table (page {page})",
                chunk_text=text,
                page_start=page,
                page_end=page,
                metadata={
                    "chunk_type": chunk_type,
                    "table_native": True,
                    "tags": ["deadline"] if chunk_type == "schedule_table" else [],
                },
            )
        )
    return drafts


def build_section_chunks(
    logical_sections: list[_LogicalSection],
    *,
    section_tags_fn,
    section_prefix_fn,
) -> list[ChunkDraft]:
    """Split logical sections into leaf chunks with parent context metadata."""
    drafts: list[ChunkDraft] = []
    parent_cap = _parent_max_chars()

    for section in logical_sections:
        chunk_type = section.chunk_type
        if chunk_type == "general_section":
            chunk_type = _infer_chunk_type(section.title, section.content)

        parent_text = section.content[:parent_cap]
        parts = split_with_overlap(section.content)
        if not parts:
            continue

        tags = section_tags_fn(section.title)
        if chunk_type == "cover_metadata":
            tags = list(set(tags + ["eligibility", "deadline"]))
        if chunk_type == "schedule_table":
            tags = list(set(tags + ["deadline"]))
        if chunk_type == "bond_clause":
            tags = list(set(tags + ["payment", "risk"]))

        for leaf_index, part_text in enumerate(parts):
            drafts.append(
                ChunkDraft(
                    section_title=section.title,
                    chunk_text=part_text,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    metadata={
                        "chunk_type": chunk_type,
                        "section_order": section.section_order,
                        "section_level": section.level,
                        "section_path": section.section_path,
                        "parent_section_order": section.parent_section_order,
                        "part_index": leaf_index,
                        "leaf_index": leaf_index,
                        "leaf_count": len(parts),
                        "parent_text": parent_text,
                        "parent_char_count": len(section.content),
                        "tags": tags,
                        "section_prefix": section_prefix_fn(section.title),
                        "overlap_chars": _overlap_chars() if leaf_index > 0 else 0,
                    },
                )
            )

    return drafts


def dedupe_table_against_sections(
    table_drafts: list[ChunkDraft],
    section_drafts: list[ChunkDraft],
) -> list[ChunkDraft]:
    """
    Drop table chunks whose text is already embedded in a schedule_table section chunk.
    Keeps standalone table chunks when they add coverage.
    """
    schedule_sections = {
        d.chunk_text[:200]
        for d in section_drafts
        if d.metadata.get("chunk_type") == "schedule_table"
    }
    kept: list[ChunkDraft] = []
    for draft in table_drafts:
        if draft.metadata.get("chunk_type") != "schedule_table":
            kept.append(draft)
            continue
        head = draft.chunk_text[:200]
        if any(head in s or s in head for s in schedule_sections):
            continue
        kept.append(draft)
    return kept
