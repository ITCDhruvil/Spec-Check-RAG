"""
Hierarchical section tree from flat section list.

Uses numbered-clause depth (1 → 1.1 → 1.1.1) and heading levels to assign
parent_section_order and section_path for downstream chunking and citations.
"""

from __future__ import annotations

import re

from apps.parsing.parsers.base import ParsedSectionResult

NUMBERED_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)\s+")


def infer_section_level(title: str, *, heading_level: int | None = None) -> int:
    """Infer hierarchy depth from numbered prefix or explicit heading level."""
    if heading_level is not None and heading_level > 0:
        return heading_level

    match = NUMBERED_PREFIX.match((title or "").strip())
    if match:
        parts = [p for p in match.group(1).split(".") if p]
        if parts and all(len(p) <= 2 for p in parts):
            return len(parts)

    return 1


def assign_section_hierarchy(
    sections: list[ParsedSectionResult],
    *,
    heading_levels: dict[int, int] | None = None,
) -> list[ParsedSectionResult]:
    """
    Assign level, parent_section_order, and section_path on each section in-place.

    heading_levels: optional map section_order → Word-style heading level (DOCX).
    """
    if not sections:
        return sections

    heading_levels = heading_levels or {}
    stack: list[tuple[int, int, str]] = []  # (level, section_order, title)

    for section in sections:
        level = infer_section_level(
            section.title,
            heading_level=heading_levels.get(section.section_order),
        )
        section.level = level

        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            section.parent_section_order = stack[-1][1]
            section.section_path = f"{stack[-1][2]} > {section.title}"
        else:
            section.parent_section_order = None
            section.section_path = section.title

        stack.append((level, section.section_order, section.title))

    return sections


def sections_to_nested_json(sections: list[ParsedSectionResult]) -> list[dict]:
    """Convert flat sections with parent_section_order into nested JSON tree."""
    if not sections:
        return []

    nodes: dict[int, dict] = {}
    roots: list[dict] = []

    for section in sections:
        node = {
            "title": section.title,
            "level": section.level,
            "page_start": section.page_start,
            "page_end": section.page_end,
            "section_order": section.section_order,
            "section_path": section.section_path,
            "children": [],
        }
        nodes[section.section_order] = node

    for section in sections:
        node = nodes[section.section_order]
        parent_order = section.parent_section_order
        if parent_order is not None and parent_order in nodes:
            nodes[parent_order]["children"].append(node)
        else:
            roots.append(node)

    return roots
