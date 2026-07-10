"""
Canonical citation resolution for extractions and summaries.

Fixes:
- Wrong page numbers (LLM guesses from paragraph numbers like 5.4.4 → page 5)
- Section hierarchy vs internal paragraph numbering (5.4.4 → 4.4.4 under section 4.4)
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

SECTION_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)\s*(.*)$", re.IGNORECASE)
PARAGRAPH_REF_RE = re.compile(r"^\d+(?:\.\d+)+$")


def _normalize_match_text(text: str) -> str:
    """Normalize text for substring citation matching.

    Strips PDF table artifacts (pipe separators, markdown table dashes, repeated
    dashes used as dividers) so source_text extracted from table-parsed chunks
    can be matched against the cleaner page-level text.
    """
    t = (text or "").lower()
    # Remove markdown/PDF table pipe separators and their surrounding spaces
    t = re.sub(r"\s*\|\s*", " ", t)
    # Remove table divider rows (--- | --- patterns)
    t = re.sub(r"[-]{2,}", " ", t)
    # Collapse all whitespace
    return re.sub(r"\s+", " ", t).strip()


def extract_section_prefix(title: str) -> str | None:
    """Leading numbering from a detected section title, e.g. '4.4 Entirety...' → '4.4'."""
    match = SECTION_NUMBER_RE.match((title or "").strip())
    return match.group(1) if match else None


def normalize_paragraph_ref(ref: str, owning_section_title: str) -> str:
    """
    Map internal paragraph refs (5.4.4) to document section refs (4.4.4)
    when they sit under section heading 4.4.
    """
    ref = (ref or "").strip()
    if not ref or not PARAGRAPH_REF_RE.match(ref):
        return ref

    prefix = extract_section_prefix(owning_section_title)
    if not prefix:
        return ref

    ref_parts = ref.split(".")
    prefix_parts = prefix.split(".")
    if not ref_parts or ref_parts[0] == prefix_parts[0]:
        return ref

    if len(ref_parts) >= len(prefix_parts):
        return ".".join(prefix_parts + ref_parts[len(prefix_parts) :])
    return ref


def normalize_section_label(section: str, owning_section_title: str) -> str:
    """Human-readable section label with canonical numbering."""
    section = (section or "").strip()
    if not section:
        return owning_section_title

    if PARAGRAPH_REF_RE.match(section):
        return f"§{normalize_paragraph_ref(section, owning_section_title)}"

    tokens = section.split(None, 1)
    if tokens and PARAGRAPH_REF_RE.match(tokens[0]):
        tokens[0] = normalize_paragraph_ref(tokens[0], owning_section_title)
        return " ".join(tokens)

    prefix = extract_section_prefix(owning_section_title)
    if prefix and section.isdigit() and int(section) <= 30:
        # Likely confused page/paragraph index used as section
        return owning_section_title

    return section or owning_section_title


def resolve_page_from_source_text(
    source_text: str,
    *,
    page_texts: list[tuple[int, str]],
    page_hint_start: int,
    page_hint_end: int,
) -> int | None:
    """Locate verbatim (or near-verbatim) source_text on parsed PDF pages."""
    if not source_text or not page_texts:
        return None

    full_norm = _normalize_match_text(source_text)
    needles: list[str] = []
    if len(full_norm) >= 24:
        needles.append(full_norm)
    short = _normalize_match_text(source_text[:80])
    if len(short) >= 20 and short not in needles:
        needles.append(short)

    def search_in_range(start: int, end: int) -> int | None:
        for page_num, text in page_texts:
            if not (start <= page_num <= end):
                continue
            hay = _normalize_match_text(text)
            for needle in needles:
                if needle in hay:
                    return page_num
        return None

    found = search_in_range(page_hint_start, page_hint_end)
    if found is not None:
        return found

    for page_num, text in page_texts:
        hay = _normalize_match_text(text)
        for needle in needles:
            if needle in hay:
                return page_num

    # Fuzzy fallback on first 50 chars
    fuzzy = _normalize_match_text(source_text[:50])
    if len(fuzzy) >= 25:
        best_page: int | None = None
        best_ratio = 0.0
        for page_num, text in page_texts:
            if page_hint_start <= page_num <= page_hint_end:
                hay = _normalize_match_text(text)
                ratio = SequenceMatcher(None, fuzzy, hay[: max(len(hay), 1)]).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_page = page_num
        if best_ratio >= 0.55 and best_page is not None:
            return best_page

    return None


def canonicalize_extraction_item(
    raw: dict[str, Any],
    *,
    chunk_text: str,
    section_title: str,
    page_start: int,
    page_end: int,
    total_pages: int,
    page_texts: list[tuple[int, str]],
) -> dict[str, Any]:
    """Apply page + section canonicalization; never trust LLM page alone."""
    requirement = str(raw.get("requirement") or "").strip()
    source_text = str(raw.get("source_text") or "").strip()
    section = normalize_section_label(
        str(raw.get("section") or "").strip(),
        section_title,
    )

    resolved = resolve_page_from_source_text(
        source_text,
        page_texts=page_texts,
        page_hint_start=page_start,
        page_hint_end=page_end,
    )

    try:
        llm_page = int(raw.get("page")) if raw.get("page") is not None else None
    except (TypeError, ValueError):
        llm_page = None

    if resolved is not None:
        page_num = resolved
    elif llm_page is not None and page_hint_valid(llm_page, page_start, page_end, total_pages):
        page_num = llm_page
    else:
        page_num = page_start

    if page_num < 1:
        page_num = 1
    if total_pages and page_num > total_pages:
        page_num = min(page_end or total_pages, total_pages)

    confidence = float(raw.get("confidence") or 0.7)
    chunk_norm = _normalize_match_text(chunk_text)
    if source_text:
        if _normalize_match_text(source_text) not in chunk_norm and source_text[:40] not in chunk_text:
            confidence = min(confidence, 0.45)
        if resolved is None and llm_page != page_num:
            confidence = min(confidence, 0.55)
    else:
        confidence = min(confidence, 0.35)

    label = str(raw.get("label") or "").strip()
    date_time = str(raw.get("date_time") or "").strip()
    value = str(raw.get("value") or "").strip()
    if label and (date_time or value) and ":" not in requirement:
        requirement = f"{label}: {date_time or value}"

    out: dict[str, Any] = {
        "requirement": requirement,
        "page": page_num,
        "section": section,
        "section_path": section_title,
        "source_text": source_text[:2000],
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "citation_verified": resolved is not None,
    }
    if label:
        out["label"] = label
    if date_time:
        out["date_time"] = date_time
    if value:
        out["value"] = value
    severity = str(raw.get("severity") or "").strip()
    if severity:
        from apps.intelligence.services.risk_severity import normalize_severity

        out["severity"] = normalize_severity(severity)
    return out


def page_hint_valid(page: int, page_start: int, page_end: int, total_pages: int) -> bool:
    if page < 1 or (total_pages and page > total_pages):
        return False
    return page_start <= page <= page_end


def source_text_in_document(
    source_text: str,
    page_texts: list[tuple[int, str]],
) -> bool:
    """True when normalized source_text appears as a substring on a parsed page."""
    norm = _normalize_match_text(source_text)
    if len(norm) < 12:
        return False
    for _, text in page_texts:
        hay = _normalize_match_text(text)
        if norm in hay:
            return True
    if len(norm) >= 32:
        short = norm[:32]
        for _, text in page_texts:
            if short in _normalize_match_text(text):
                return True
    return False


def build_extraction_citation_lookup(
    insights: list,
    page_texts: list[tuple[int, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Map normalized verbatim source snippets → canonical citation fields."""
    lookup: dict[str, dict[str, Any]] = {}
    for insight in insights:
        for item in insight.payload.get("items", []):
            src = (item.get("source_text") or "").strip()
            if not src:
                continue
            if page_texts and not source_text_in_document(src, page_texts):
                continue
            key = _normalize_match_text(src)[:160]
            if key not in lookup:
                lookup[key] = {
                    "page": item.get("page"),
                    "section": item.get("section"),
                    "section_path": item.get("section_path"),
                    "source_text": src[:2000],
                }
    return lookup


def _collect_extraction_items(insights: list) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for insight in insights:
        for raw in insight.payload.get("items", []):
            if isinstance(raw, dict) and (raw.get("source_text") or "").strip():
                items.append(raw)
    return items


def _find_best_extraction_match(
    quote: str,
    items: list[dict[str, Any]],
    *,
    page_hint: int | None = None,
    label_filter: str | None = None,
) -> tuple[dict[str, Any] | None, float]:
    norm = _normalize_match_text(quote)
    if not norm or not items:
        return None, 0.0

    candidates = items
    if label_filter:
        label_norm = label_filter.strip().lower()
        filtered = [
            it for it in items
            if str(it.get("label") or "").strip().lower() == label_norm
        ]
        if filtered:
            candidates = filtered

    best: dict[str, Any] | None = None
    best_ratio = 0.0
    for item in candidates:
        src = _normalize_match_text(str(item.get("source_text") or ""))
        if not src:
            continue
        ratio = SequenceMatcher(None, norm[:160], src[:160]).ratio()
        try:
            if page_hint is not None and int(item.get("page") or 0) == page_hint:
                ratio += 0.08
        except (TypeError, ValueError):
            pass
        if ratio > best_ratio:
            best_ratio = ratio
            best = item
    return best, best_ratio


def _apply_canon_fields(src: dict[str, Any], canon: dict[str, Any]) -> None:
    src["page"] = canon.get("page", src.get("page"))
    src["section"] = canon.get("section", src.get("section"))
    if canon.get("section_path"):
        src["section_path"] = canon["section_path"]
    if canon.get("source_text"):
        src["source_text"] = canon["source_text"]


def enforce_verbatim_summary_sources(
    data: dict[str, Any],
    *,
    page_texts: list[tuple[int, str]],
    insights: list,
    lookup: dict[str, dict[str, Any]],
) -> None:
    """
    Summary citations must be verbatim PDF text so preview jump/highlight works.
    Paraphrased LLM quotes are replaced from extractions or removed entirely.
    """
    if not page_texts:
        return

    items = [
        it
        for it in _collect_extraction_items(insights)
        if source_text_in_document(str(it.get("source_text") or ""), page_texts)
    ]

    def fix_source(src: dict[str, Any], parent_field_key: str | None = None) -> dict[str, Any] | None:
        if not isinstance(src, dict):
            return None

        source_text = str(src.get("source_text") or "").strip()
        try:
            page_hint = int(src.get("page")) if src.get("page") is not None else None
        except (TypeError, ValueError):
            page_hint = None

        def finalize(candidate: dict[str, Any]) -> dict[str, Any] | None:
            quote = str(candidate.get("source_text") or "").strip()
            if not quote or not source_text_in_document(quote, page_texts):
                return None
            candidate["citation_verified"] = True
            return candidate

        if source_text and source_text_in_document(source_text, page_texts):
            key = _normalize_match_text(source_text)[:160]
            if key and key in lookup:
                _apply_canon_fields(src, lookup[key])
            return finalize(src)

        label_filter = parent_field_key
        if label_filter == "bid_open_date_time":
            label_filter = "bid_deadline_date_time"
        match, ratio = _find_best_extraction_match(
            source_text,
            items,
            page_hint=page_hint,
            label_filter=label_filter,
        )
        if match and ratio >= 0.4:
            src["source_text"] = str(match.get("source_text") or "")[:2000]
            src["page"] = match.get("page", src.get("page"))
            src["section"] = match.get("section", src.get("section"))
            if match.get("section_path"):
                src["section_path"] = match["section_path"]
            return finalize(src)

        return None

    def walk_sources(obj: Any) -> None:
        if isinstance(obj, dict):
            if "sources" in obj and isinstance(obj["sources"], list):
                parent_field_key = str(obj.get("field_key") or "").strip() or None
                kept: list[dict[str, Any]] = []
                for raw in obj["sources"]:
                    if not isinstance(raw, dict):
                        continue
                    fixed = fix_source(raw, parent_field_key=parent_field_key)
                    if fixed is not None:
                        kept.append(fixed)
                obj["sources"] = kept
            for value in obj.values():
                if value is not data.get("_meta"):
                    walk_sources(value)
        elif isinstance(obj, list):
            for item in obj:
                walk_sources(item)

    walk_sources(data)


def canonicalize_summary_sources(
    data: dict[str, Any],
    lookup: dict[str, dict[str, Any]],
) -> None:
    """Rewrite summary citation pages/sections from grounded extractions."""

    def fix_source(src: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(src, dict):
            return src
        key = _normalize_match_text(str(src.get("source_text") or ""))[:160]
        if key and key in lookup:
            canon = lookup[key]
            src["page"] = canon.get("page", src.get("page"))
            src["section"] = canon.get("section", src.get("section"))
            if canon.get("section_path"):
                src["section_path"] = canon["section_path"]
        return src

    def walk_sources(obj: Any) -> None:
        if isinstance(obj, dict):
            if "sources" in obj and isinstance(obj["sources"], list):
                obj["sources"] = [fix_source(s) for s in obj["sources"] if isinstance(s, dict)]
            for value in obj.values():
                if value is not data.get("_meta"):
                    walk_sources(value)
        elif isinstance(obj, list):
            for item in obj:
                walk_sources(item)

    walk_sources(data)
