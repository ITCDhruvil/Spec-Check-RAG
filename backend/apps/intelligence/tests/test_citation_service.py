from apps.intelligence.services.citation_service import (
    normalize_paragraph_ref,
    normalize_section_label,
    resolve_page_from_source_text,
)


def test_normalize_paragraph_ref_maps_internal_numbering():
    assert (
        normalize_paragraph_ref("5.4.4", "4.4 Entirety of Required Works")
        == "4.4.4"
    )
    assert (
        normalize_paragraph_ref("5.3.6", "4.3.6 Payment Schedule")
        == "4.3.6"
    )


def test_normalize_section_label_prefixes_paragraph_ref():
    assert normalize_section_label("5.4.4", "4.4 Entirety") == "§4.4.4"


def test_resolve_page_from_source_text():
    pages = [
        (3, "Intro text on page three."),
        (13, "Clause 3.5.3 payment terms appear here."),
        (21, "Section 4.16.1 evaluation criteria detailed requirements."),
    ]
    assert (
        resolve_page_from_source_text(
            "Clause 3.5.3 payment terms appear here.",
            page_texts=pages,
            page_hint_start=1,
            page_hint_end=30,
        )
        == 13
    )
    assert (
        resolve_page_from_source_text(
            "Section 4.16.1 evaluation criteria",
            page_texts=pages,
            page_hint_start=1,
            page_hint_end=5,
        )
        == 21
    )
