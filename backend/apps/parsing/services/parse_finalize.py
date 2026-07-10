"""
Finalize parse results: hierarchical sections, layout blocks, metadata enrichment.
"""

from __future__ import annotations

from apps.parsing.parsers.base import DocumentParseResult
from apps.parsing.services.layout_blocks import (
    layout_blocks_from_pages,
    layout_blocks_from_tables,
    layout_blocks_to_json,
)
from apps.parsing.services.section_hierarchy import (
    assign_section_hierarchy,
    sections_to_nested_json,
)


def finalize_document_parse(
    result: DocumentParseResult,
    *,
    heading_levels: dict[int, int] | None = None,
) -> DocumentParseResult:
    """Apply hierarchy, layout blocks, and metadata after raw parse."""
    assign_section_hierarchy(result.sections, heading_levels=heading_levels)

    if not result.layout_blocks:
        section_map = {
            (section.page_start, section.title): section.section_order
            for section in result.sections
        }
        page_blocks = layout_blocks_from_pages(
            result.pages,
            section_order_map=section_map,
        )
        table_blocks = layout_blocks_from_tables(result.tables)
        result.layout_blocks = page_blocks + table_blocks

    result.parsing_metadata["layout_blocks"] = layout_blocks_to_json(result.layout_blocks)
    result.parsing_metadata["layout_blocks_count"] = len(result.layout_blocks)
    result.parsing_metadata["section_hierarchy"] = sections_to_nested_json(result.sections)
    return result
