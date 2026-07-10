"""Tests for group extraction document text preparation."""

from __future__ import annotations

from apps.intelligence.services.group_extraction_service import _description_text_from_pages


def test_description_anchor_skips_toc_prefers_prose_page():
    """TOC lists section titles; real scope prose is on a later page."""
    page_texts = [
        (
            2,
            "Table of Contents\n"
            "1. Background and Overview of Desired Services\n"
            "2. Minimum Requirements\n"
            "3. Technical Services Specifications\n",
        ),
        (
            17,
            "Background and Overview of Desired Services\n\n"
            "The Suffolk County District Attorney's Office (SCDA) is searching for a contractor "
            "to design, build, and assist in building a cloud intranet portal for staff. "
            "The contractor shall provide Azure hosting and related services.",
        ),
    ]
    text = _description_text_from_pages(page_texts)
    assert "--- Page 17 ---" in text
    assert "SCDA" in text and "searching for a contractor" in text
    assert "--- Page 2 ---" not in text


def test_description_fallback_page_range_when_no_anchor():
    page_texts = [(p, f"Page {p} body text about contractor services and scope.") for p in range(15, 22)]
    text = _description_text_from_pages(page_texts)
    assert "--- Page 15 ---" in text
    assert "--- Page 1 ---" not in text
