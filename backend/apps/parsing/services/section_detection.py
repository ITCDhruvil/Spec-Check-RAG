import re

from apps.parsing.parsers.base import ParsedPageResult, ParsedSectionResult

# Numbered headings: 1. Introduction, 2.1 Technical Requirements
NUMBERED_HEADING = re.compile(
    r"^(\d+(?:\.\d+)*)\s+(.+)$",
    re.MULTILINE,
)

# Annexure A, Appendix B
ANNEX_HEADING = re.compile(
    r"^((?:Annexure|Annex|Appendix)\s+[A-Z0-9]+(?:\s*[-–:]\s*.+)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# ALL CAPS short lines (sometimes headings, sometimes noise)
ALL_CAPS_HEADING = re.compile(r"^[A-Z][A-Z0-9\s\-/&]{3,80}$")

KNOWN_SECTION_TITLES = {
    "introduction",
    "scope of work",
    "technical requirements",
    "eligibility criteria",
    "submission instructions",
    "evaluation criteria",
    "payment terms",
    "general terms and conditions",
    "commercial terms",
    "bill of quantities",
    "instructions to bidders",
    "statement of work",
}


def _is_numbered_heading_line(line: str) -> bool:
    """
    True for real clause headings (e.g. '2.1 Technical Requirements'),
    not prose that starts with a number (e.g. '86 miles in length.').
    """
    stripped = line.strip()
    match = NUMBERED_HEADING.match(stripped)
    if not match:
        return False

    # Reject phone numbers / addresses / years that look like "386.336.4189 (fax)"
    # or "2700 Judge Fran Jamieson Way" being misread as a clause number heading.
    number = (match.group(1) or "").strip()
    parts = [p for p in number.split(".") if p]
    # Typical clause numbering: 1, 1.1, 1.5.2 (short segments). If any segment
    # is long, it is likely a phone number, year, or address.
    if not parts or any(len(p) > 2 for p in parts):
        return False

    title = (match.group(2) or "").strip()
    if not title:
        return False
    # Clause titles should contain letters; reject numeric blobs like "53.0".
    if sum(1 for ch in title if ch.isalpha()) < 2:
        return False
    # Headings don't start with a parenthesis (common in phone "(fax)").
    if title.startswith("("):
        return False
    if re.search(r"\b(fax|tel|phone)\b", title, re.IGNORECASE):
        return False
    # Geography / stats sentences misread as section "86" + "miles in length."
    if title[0].islower():
        return False
    if re.search(r"\bmiles\b", title, re.IGNORECASE) and re.search(
        r"\blength\b", title, re.IGNORECASE
    ):
        return False
    # Long sentence ending in a period is body text, not a heading.
    if title.endswith(".") and len(title.split()) >= 4:
        return False
    return True


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 200:
        return False

    if _is_numbered_heading_line(stripped):
        return True
    if ANNEX_HEADING.match(stripped):
        return True
    if stripped.lower() in KNOWN_SECTION_TITLES:
        return True
    if ALL_CAPS_HEADING.match(stripped) and len(stripped.split()) <= 12:
        # Avoid treating isolated single-word ALL CAPS tokens as section headings.
        # In many PDFs these are split fragments from logos/company names (e.g. "CARR", "RIGGS").
        words = stripped.split()
        if len(words) == 1:
            return False
        # Also avoid very short 2-word fragments (common in headers) unless they match known titles.
        if len(words) == 2 and len(stripped) <= 10 and stripped.lower() not in KNOWN_SECTION_TITLES:
            return False
        return True

    # Title case short line without trailing period
    if (
        len(stripped) < 80
        and stripped[0].isupper()
        and not stripped.endswith(".")
        and stripped.lower() in KNOWN_SECTION_TITLES
    ):
        return True

    words = stripped.split()
    if len(words) <= 8 and stripped == stripped.title() and not stripped.endswith("."):
        lower = stripped.lower()
        if any(k in lower for k in KNOWN_SECTION_TITLES):
            return True

    return False


def _extract_heading_title(line: str) -> str:
    stripped = line.strip()
    match = NUMBERED_HEADING.match(stripped)
    if match:
        return f"{match.group(1)} {match.group(2)}".strip()
    return stripped


def detect_sections_from_pages(pages: list[ParsedPageResult]) -> list[ParsedSectionResult]:
    """Lightweight section detection from page-ordered text."""
    sections: list[ParsedSectionResult] = []
    current_title = "Preamble"
    current_lines: list[str] = []
    current_page_start = 1
    current_page_end = 1
    order = 0

    def flush() -> None:
        nonlocal order, current_title, current_lines, current_page_start, current_page_end
        content = "\n".join(current_lines).strip()
        if content or current_title != "Preamble":
            sections.append(
                ParsedSectionResult(
                    title=current_title,
                    content=content,
                    page_start=current_page_start,
                    page_end=current_page_end,
                    section_order=order,
                )
            )
            order += 1
        current_lines = []

    for page in pages:
        if page.is_empty and not page.extracted_text.strip():
            current_page_end = page.page_number
            continue

        current_page_end = page.page_number
        for line in page.extracted_text.splitlines():
            if _is_heading_line(line):
                flush()
                current_title = _extract_heading_title(line)
                current_page_start = page.page_number
                current_lines = []
            else:
                if not current_lines and not sections:
                    current_page_start = page.page_number
                current_lines.append(line)

    flush()

    if not sections:
        full_text = "\n\n".join(p.extracted_text for p in pages if p.extracted_text)
        sections.append(
            ParsedSectionResult(
                title="Document",
                content=full_text.strip(),
                page_start=1,
                page_end=pages[-1].page_number if pages else 1,
                section_order=0,
            )
        )

    return sections


def build_structured_text(sections: list[ParsedSectionResult]) -> str:
    parts = []
    for section in sections:
        parts.append(f"## {section.title}\n\n{section.content.strip()}\n")
    return "\n".join(parts).strip()
