"""
Simple prompt-based extraction: one intelligent-model call per field group, all groups in parallel.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db import close_old_connections, transaction

from apps.documents.models import Document
from apps.intelligence.models import DocumentChunk, ExtractedInsight, GeneratedSummary
from apps.intelligence.prompts.templates import EXTRACTION_SYSTEM_PROMPT
from apps.intelligence.services.extraction_groups import (
    GROUP_EXTRACTION_GROUPS,
    ExtractionGroup,
)
from apps.intelligence.services.extraction_service import (
    ExtractionService,
    _split_bond_items_for_certified_checks,
)
from apps.intelligence.services.grounding import (
    aggregate_confidence,
    merge_insight_items,
    validate_and_score_items,
)
from apps.intelligence.services.extraction_errors import GroupExtractionIncompleteError
from apps.intelligence.services.extraction_feedback_hints import build_group_feedback_hints
from apps.intelligence.services.model_routing import extraction_model, model_for_tier
from apps.intelligence.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

_TRUNCATION_MARKER = "\n\n[... middle of document omitted for length ...]\n\n"

# Groups that must succeed for a usable spec-check briefing.
CRITICAL_GROUP_IDS = frozenset({"dates", "project_description", "project_identity"})
CRITICAL_GROUP_ORDER = ("project_identity", "dates", "project_description")


def _model_for_group(group: ExtractionGroup) -> str:
    """Critical groups always use the strong model for accuracy."""
    if group.group_id in CRITICAL_GROUP_IDS:
        return model_for_tier("strong")
    return extraction_model(group.extraction_type)


def _ordered_groups() -> tuple[ExtractionGroup, ...]:
    by_id = {g.group_id: g for g in GROUP_EXTRACTION_GROUPS}
    critical = tuple(by_id[gid] for gid in CRITICAL_GROUP_ORDER if gid in by_id)
    non_critical = tuple(g for g in GROUP_EXTRACTION_GROUPS if g.group_id not in CRITICAL_GROUP_IDS)
    return critical + non_critical


def prepare_document_text(structured_text: str, raw_text: str) -> str:
    """Prefer structured text; fall back to raw; trim very long documents."""
    text = (structured_text or "").strip() or (raw_text or "").strip()
    if not text:
        return ""

    max_chars = int(getattr(settings, "INTELLIGENCE_GROUP_EXTRACTION_MAX_CHARS", 90_000))
    if len(text) <= max_chars:
        return text

    head = int(max_chars * 0.65)
    tail = max_chars - head - len(_TRUNCATION_MARKER)
    if tail < 2000:
        return text[:max_chars]
    return text[:head] + _TRUNCATION_MARKER + text[-tail:]


def _section_quality_score(chunk: str, needle: str) -> int:
    """Score a candidate section — real prose beats TOC table-of-contents hits."""
    pos = chunk.find(needle)
    after = chunk[pos + len(needle) : pos + len(needle) + 800] if pos >= 0 else chunk[:800]
    after = after.strip()
    if not after:
        return 0
    # TOC pattern: numbered list items with no prose paragraphs.
    toc_like = len(re.findall(r"^\s*\d+\.\s+\w", after[:300], re.MULTILINE)) >= 2
    prose_markers = len(
        re.findall(r"\b(the|shall|contractor|vendor|county|office|design|build)\b", after[:500], re.I)
    )
    sentences = len(re.findall(r"[.!?]", after[:800]))
    score = len(after) + prose_markers * 50 + sentences * 20
    if toc_like and prose_markers < 2:
        score = max(1, score // 10)
    return score


def _best_section_slice(full: str, needles: tuple[str, ...], *, slice_len: int = 18_000) -> str:
    """Pick the document slice most likely to contain real scope prose."""
    best = ""
    best_score = 0
    for needle in needles:
        start = 0
        while True:
            idx = full.find(needle, start)
            if idx < 0:
                break
            chunk = full[idx : idx + slice_len]
            score = _section_quality_score(chunk, needle)
            if score > best_score:
                best_score = score
                best = chunk
            start = idx + max(len(needle), 1)
    return best


_TOC_PAGE_RE = re.compile(r"\btable\s+of\s+contents\b", re.I)
# Heading-like occurrences only: start of a line, optionally prefixed by a
# section designator ("SECTION C:", "3.1", "C."). Mid-sentence mentions of
# "scope of work" in legal boilerplate must not anchor the slice.
_SCOPE_HEADING_RE = re.compile(
    r"^[ \t]*(?:SECTION\s+[A-Z0-9]+\s*[:.\-–]?\s*|[A-Z0-9]+(?:\.\d+)*[:.)]\s+)?"
    r"(Scope of Work|Project Description|Description of Work|Statement of Work|Introduction)\b",
    re.I | re.M,
)


def _description_text_from_pages(page_texts: list[tuple[int, str]]) -> str:
    """Fallback: scope sections usually start mid-document (pages 15–25)."""
    anchor_page: int | None = None
    best_score = 0
    primary_needle = "Background and Overview of Desired Services"

    for p, t in page_texts:
        text = t or ""
        # Never anchor on a table-of-contents page — its section titles match
        # the heading regex but carry no prose (lettered TOCs like "SECTION C:
        # SCOPE OF WORK" defeat the numbered-list heuristic in the scorer).
        if _TOC_PAGE_RE.search(text[:2_000]):
            continue
        if primary_needle in text:
            score = _section_quality_score(text, primary_needle) * 2
            if score > best_score:
                best_score = score
                anchor_page = p
            continue
        # Score EVERY page with a scope-like heading; the best prose wins
        # (an early weak hit must not lock out a later real section).
        for m in _SCOPE_HEADING_RE.finditer(text):
            score = _section_quality_score(text[m.start():], m.group(0))
            if score > best_score:
                best_score = score
                anchor_page = p

    # Reject residual weak hits (heading with no prose after it).
    if anchor_page is not None and best_score < 80:
        anchor_page = None

    if anchor_page is not None:
        page_range = range(max(1, anchor_page - 1), anchor_page + 5)
    else:
        page_range = range(15, 22)

    chunks: list[str] = []
    for p, t in page_texts:
        if p in page_range and (t or "").strip():
            chunks.append(f"--- Page {p} ---\n{t.strip()}")
    return "\n\n".join(chunks)[:12_000]


# Keyword anchors for slice-targeted groups. A page (±1 neighbor) is included
# when any needle matches; misses fall back to the full trimmed document, so
# accuracy is never worse than the old full-blob prompt.
_GROUP_SLICE_NEEDLES: dict[str, tuple[str, ...]] = {
    "project_value": (
        "estimated cost",
        "estimated construction cost",
        "engineer's estimate",
        "engineers estimate",
        "contract value",
        "estimated value",
        "project budget",
        "budget",
        "estimated price",
        "cost range",
        "not to exceed",
    ),
    "bonds": (
        "bid bond",
        "bid security",
        "performance bond",
        "payment bond",
        "labor and material",
        "maintenance bond",
        "certified check",
        "cashier's check",
        "surety",
        "bid guarantee",
        "security deposit",
    ),
    "set_asides": (
        "mbe",
        "wbe",
        "dbe",
        "dvbe",
        "sbe",
        "hub",
        "minority",
        "women-owned",
        "women owned",
        "disadvantaged business",
        "veteran",
        "set-aside",
        "set aside",
        "small business",
        "diversity",
        "participation goal",
    ),
    # Contextual details around date events (opening, submission, questions,
    # award, protest) — feeds the *_note fields of the dates group.
    "dates_notes": (
        "bid opening",
        "publicly opened",
        "public opening",
        "opening of bids",
        "notice of award",
        "intent to award",
        "posting of award",
        "protest",
        "bid validity",
        "bids shall remain",
        "lowest responsible",
        "lowest responsive",
        "questions must",
        "submit questions",
        "pre-bid",
        "site visit",
        "mandatory",
        "conference id",
        "dial",
    ),
    "location_and_size": (
        "project location",
        "site location",
        "location of work",
        "work site",
        "project site",
        "place of work",
        "situated",
        "located in",
        "located at",
        "square feet",
        "square footage",
        "sq. ft",
        "sq ft",
    ),
}


def _keyword_page_slice(
    group_id: str,
    page_texts: list[tuple[int, str]],
    *,
    max_chars: int = 24_000,
) -> str:
    """
    Pages containing group needles, best-scoring first (more distinct needle
    matches = more relevant), assembled in document order up to max_chars.
    """
    needles = _GROUP_SLICE_NEEDLES.get(group_id)
    if not needles or not page_texts:
        return ""

    # Score every page by distinct needle matches; direct hits outrank neighbors.
    scores: dict[int, int] = {}
    for page_num, text in page_texts:
        lowered = (text or "").lower()
        matched = sum(1 for n in needles if n in lowered)
        if matched:
            scores[page_num] = scores.get(page_num, 0) + matched * 10
            for neighbor in (page_num - 1, page_num + 1):
                scores[neighbor] = scores.get(neighbor, 0) + 1

    # Location often appears on cover/notice pages without any needle
    # ("...at 123 Main St, Springfield") — always keep the first pages in play.
    if group_id == "location_and_size":
        for page_num, _ in page_texts[:5]:
            scores[page_num] = scores.get(page_num, 0) + 5

    if not scores:
        return ""

    by_page = {p: (t or "").strip() for p, t in page_texts}
    selected: set[int] = set()
    used = 0
    # Highest score first; ties → earlier page.
    for page_num in sorted(scores, key=lambda p: (-scores[p], p)):
        body = by_page.get(page_num)
        if not body:
            continue
        cost = len(body) + 20
        if used + cost > max_chars:
            continue
        selected.add(page_num)
        used += cost

    if not selected:
        return ""

    return "\n\n".join(
        f"--- Page {p} ---\n{by_page[p]}" for p in sorted(selected)
    )


def prepare_group_document_text(
    group: ExtractionGroup,
    *,
    structured_text: str,
    raw_text: str,
    page_texts: list[tuple[int, str]],
) -> str:
    """
    Tailor document text per group so critical fields are never lost to truncation
    or buried in a 90k-char blob sent to every parallel call.
    """
    full = (structured_text or "").strip() or (raw_text or "").strip()

    if group.group_id == "dates":
        # Bid timelines live on cover pages 1–5; contextual note details
        # (opening/submission/questions/award/protest) are scattered through
        # the administrative section — pull keyword-matched pages too.
        cover_pages = {p for p, _ in page_texts[:5]}
        cover = "\n\n".join(
            f"--- Page {p} ---\n{t.strip()}"
            for p, t in page_texts[:5]
            if (t or "").strip()
        )
        extra = _keyword_page_slice("dates_notes", page_texts, max_chars=24_000)
        if extra:
            # Drop pages already included in the cover block.
            extra_parts = [
                part
                for part in extra.split("\n\n")
                if not any(part.startswith(f"--- Page {p} ---") for p in cover_pages)
            ]
            extra = "\n\n".join(extra_parts)
        if cover or extra:
            return "\n\n".join(s for s in (cover, extra) if s)

    if group.group_id == "project_description":
        # Scope text lives in body pages — cover/TOC misleads section search.
        page_body = _description_text_from_pages(page_texts)
        if page_body:
            return page_body
        needles = (
            "Background and Overview of Desired Services",
            "Technical Services Specifications",
            "Detailed Scope of Services",
            "Scope of Work",
            "Project Description",
            "ADVERTISEMENT FOR PREQUALIFICATION",
            "PREQUALIFICATION PROPOSALS",
            "Description of Work",
            "Work to be Performed",
            "Statement of Work",
        )
        section = _best_section_slice(full, needles)
        if section:
            return section
        body = "\n\n".join(
            f"--- Page {p} ---\n{t.strip()}"
            for p, t in page_texts[1:25]
            if (t or "").strip()
        )
        if body:
            return body[:18_000]

    if group.group_id == "project_identity":
        head = "\n\n".join(
            f"--- Page {p} ---\n{t.strip()}"
            for p, t in page_texts[:8]
            if (t or "").strip()
        )
        if head:
            return head + "\n\n" + full[:20_000]

    # Keyword-anchored groups (value / bonds / set-asides / location): send only
    # the pages that mention the topic instead of the full 90k-char blob.
    sliced = _keyword_page_slice(group.group_id, page_texts)
    if sliced:
        logger.info(
            "group_slice_used group=%s chars=%s (full=%s)",
            group.group_id,
            len(sliced),
            len(full),
        )
        return sliced

    return prepare_document_text(structured_text, raw_text)


def group_extraction_user_prompt(group: ExtractionGroup, document_text: str) -> str:
    labels = ", ".join(group.field_labels)
    feedback_hints = build_group_feedback_hints(group)
    return f"""Field group: {group.title}

Extract ONLY these fields (use EXACT label values): {labels}

Instructions:
{group.instructions}
{feedback_hints}
Rules:
- Every item MUST include verbatim source_text from the document below.
- For dates, set label to the deadline type and date_time to the full date/time string.
- If a field is not in the document, omit it — do NOT guess.
- Respond with valid JSON only.

Full document text:
---
{document_text}
---

Return JSON:
{{
  "items": [
    {{
      "requirement": "<label>: <value>",
      "label": "<exact field label from allowed list>",
      "value": "<extracted text>",
      "date_time": "<for date fields only, else omit>",
      "page": integer or null,
      "section": "section heading or cover page",
      "source_text": "verbatim excerpt",
      "confidence": 0.0 to 1.0
    }}
  ]
}}"""


class GroupExtractionService:
    @staticmethod
    def _group_text(
        group: ExtractionGroup,
        *,
        structured_text: str,
        raw_text: str,
        page_texts: list[tuple[int, str]],
    ) -> str:
        return prepare_group_document_text(
            group,
            structured_text=structured_text,
            raw_text=raw_text,
            page_texts=page_texts,
        )

    @staticmethod
    def _try_extract(
        group: ExtractionGroup,
        document: Document,
        summary: GeneratedSummary,
        *,
        structured_text: str,
        raw_text: str,
        page_texts: list[tuple[int, str]],
        total_pages: int,
    ) -> ExtractedInsight | None:
        group_text = GroupExtractionService._group_text(
            group,
            structured_text=structured_text,
            raw_text=raw_text,
            page_texts=page_texts,
        )
        return GroupExtractionService._extract_group(
            group,
            document,
            summary,
            group_text,
            total_pages,
            page_texts,
            _model_for_group(group),
        )

    @staticmethod
    def run_extractions(
        document: Document,
        summary: GeneratedSummary,
        chunks: list[DocumentChunk],
    ) -> list[ExtractedInsight]:
        parsed = document.parsed_document
        total_pages = parsed.total_pages or 1
        page_texts = list(
            parsed.pages.order_by("page_number").values_list("page_number", "extracted_text")
        )
        document_text = prepare_document_text(parsed.structured_text, parsed.raw_text)
        if not document_text:
            logger.warning("group_extraction_no_text document_id=%s", document.id)
            return []

        workers = min(
            len(GROUP_EXTRACTION_GROUPS),
            int(getattr(settings, "INTELLIGENCE_GROUP_EXTRACTION_WORKERS", 3)),
        )
        stagger_ms = int(getattr(settings, "INTELLIGENCE_GROUP_EXTRACTION_STAGGER_MS", 400))
        max_retries = int(getattr(settings, "INTELLIGENCE_GROUP_EXTRACTION_RETRIES", 3))

        logger.info(
            "group_extraction_start document_id=%s groups=%s workers=%s routing=per_group",
            document.id,
            len(GROUP_EXTRACTION_GROUPS),
            workers,
        )

        results: dict[str, ExtractedInsight] = {}
        failed_groups: list[ExtractionGroup] = []
        structured_text = parsed.structured_text or ""
        raw_text = parsed.raw_text or ""

        ordered = _ordered_groups()

        # ── Pass 1: all groups in one parallel wave (criticals submitted first;
        # any critical failure is recovered by the sequential retry pass below).
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map: dict = {}
            for i, group in enumerate(ordered):
                if stagger_ms > 0 and i > 0:
                    time.sleep(stagger_ms / 1000.0)
                fut = pool.submit(
                    GroupExtractionService._try_extract,
                    group,
                    document,
                    summary,
                    structured_text=structured_text,
                    raw_text=raw_text,
                    page_texts=page_texts,
                    total_pages=total_pages,
                )
                future_map[fut] = group

            for fut in as_completed(future_map):
                group = future_map[fut]
                try:
                    insight = fut.result()
                    if insight:
                        results[group.extraction_type] = insight
                    else:
                        failed_groups.append(group)
                except Exception as exc:
                    logger.error(
                        "group_extraction_failed group=%s critical=%s error=%s",
                        group.group_id,
                        group.group_id in CRITICAL_GROUP_IDS,
                        exc,
                        exc_info=True,
                    )
                    failed_groups.append(group)

        # ── Pass 2: retry failed groups sequentially (rate-limit recovery) ───
        # Deduplicate failed_groups while preserving order
        seen_failed: set[str] = set()
        unique_failed: list[ExtractionGroup] = []
        for g in failed_groups:
            if g.group_id not in seen_failed:
                seen_failed.add(g.group_id)
                unique_failed.append(g)
        failed_groups = unique_failed

        # Only retry critical failed groups — optional groups (bonds, value) are best-effort.
        retry_queue = [g for g in failed_groups if g.group_id in CRITICAL_GROUP_IDS]
        retry_queue += [g for g in failed_groups if g.group_id not in CRITICAL_GROUP_IDS]

        for group in retry_queue:
            # Cooperative cancel: stop retry waits promptly when the user cancels.
            from apps.processing.services.job_service import ProcessingJobService

            job = ProcessingJobService.get_latest_job_for_document(document.id)
            if job:
                ProcessingJobService.raise_if_cancelled(job)
            if group.group_id not in CRITICAL_GROUP_IDS and group.extraction_type in results:
                continue
            for attempt in range(1, max_retries + 1):
                # First retry immediately (failures are mostly transient);
                # back off exponentially only on repeated failures.
                wait = 0 if attempt == 1 else min(2**attempt, 20)
                logger.info(
                    "group_extraction_retry group=%s attempt=%s wait=%ss",
                    group.group_id,
                    attempt,
                    wait,
                )
                if wait:
                    time.sleep(wait)
                try:
                    insight = GroupExtractionService._try_extract(
                        group,
                        document,
                        summary,
                        structured_text=structured_text,
                        raw_text=raw_text,
                        page_texts=page_texts,
                        total_pages=total_pages,
                    )
                except Exception as exc:
                    logger.warning(
                        "group_extraction_retry_failed group=%s attempt=%s error=%s",
                        group.group_id,
                        attempt,
                        exc,
                    )
                    insight = None
                if insight:
                    results[group.extraction_type] = insight
                    break

        missing_critical = [
            g.group_id
            for g in GROUP_EXTRACTION_GROUPS
            if g.group_id in CRITICAL_GROUP_IDS
            and g.extraction_type not in results
        ]
        if missing_critical:
            logger.error(
                "group_extraction_incomplete document_id=%s missing_critical=%s",
                document.id,
                missing_critical,
            )
            raise GroupExtractionIncompleteError(missing_critical)

        # ── Verify pass: must-have fields get one focused strong-model re-ask ─
        GroupExtractionService._verify_must_have_fields(
            document, summary, results, page_texts
        )

        # ── Dedicated notes call: contextual details around each date event ──
        # A single focused call is far more reliable than bundling the six
        # note fields into the (already large) dates prompt.
        try:
            GroupExtractionService._extract_date_notes(
                document, summary, results, page_texts
            )
        except Exception as exc:
            logger.warning("date_notes_extraction_failed error=%s", exc)

        ordered_insights = [
            results[g.extraction_type]
            for g in GROUP_EXTRACTION_GROUPS
            if g.extraction_type in results
        ]
        logger.info(
            "group_extraction_complete document_id=%s insights=%s",
            document.id,
            len(ordered_insights),
        )
        return ordered_insights

    @staticmethod
    def _extract_date_notes(
        document: Document,
        summary: GeneratedSummary,
        results: dict[str, ExtractedInsight],
        page_texts: list[tuple[int, str]],
    ) -> None:
        """One focused call for the six *_note fields; merged into the
        submission_deadlines insight so postprocess attaches them to rows."""
        insight = results.get("submission_deadlines")
        if insight is None:
            return
        date_items = (insight.payload.get("items") or [])
        if not date_items:
            return

        anchors = "\n".join(
            f"- {i.get('label')}: {i.get('date_time') or i.get('value') or ''}"
            for i in date_items
            if i.get("label")
        )

        cover = "\n\n".join(
            f"--- Page {p} ---\n{(t or '').strip()}"
            for p, t in page_texts[:5]
            if (t or "").strip()
        )
        extra = _keyword_page_slice("dates_notes", page_texts, max_chars=26_000)
        context = "\n\n".join(s for s in (cover, extra) if s)[:60_000]
        if not context:
            return

        prompt = f"""These dates were already extracted from the tender document:
{anchors}

Now extract ONLY the contextual NOTE for each date event. Use EXACTLY these labels:
bid_deadline_note, bid_open_note, pre_bid_note, site_visit_note, question_deadline_note, award_note.

What each note captures (each detail as its own short sentence; omit a note entirely when the document states nothing for that event; NEVER put one event's details into another event's note):
- bid_deadline_note: where/how bids are submitted (portal, mailing address, copies, envelope marking), named contact person with email/phone, prohibited methods (no oral/email/fax), any instruction tied to the due date.
- bid_open_note: public or private opening, in person or virtual, opening location (room, address) or meeting/dial-in details (platform, link, phone, conference ID), who conducts it, whether bidders may attend, how results are announced.
- pre_bid_note: MANDATORY or NON-MANDATORY (start the note with 'Mandatory.' or 'Non-mandatory.' when stated), location or virtual details, who should attend, sign-in rules, site walk-through, RSVP deadline and contact.
- site_visit_note: MANDATORY or NON-MANDATORY (same prefix rule), meeting point/address, escort/check-in, scheduling (fixed vs by appointment + contact), safety/PPE or badging, per-site times.
- question_deadline_note: where to submit questions (email address, portal), required format (in writing, subject rules, bid number), who answers and how answers are distributed (addendum, posting), whether verbal questions are prohibited.
- award_note: where/how the award is decided (board/council meeting, location, time), stated award criteria (e.g. lowest responsible bidder), bid validity period, how award is announced/posted, protest window and procedure.

Rules:
- Every item MUST include verbatim source_text from the pages below.
- Do NOT guess; omit notes with no stated details.
- Respond with valid JSON only: {{"items": [{{"requirement": "<label>: <value>", "label": "<label>", "value": "<note text>", "page": integer or null, "section": "...", "source_text": "verbatim excerpt", "confidence": 0.0 to 1.0}}]}}

Document pages:
---
{context}
---"""

        client = OpenAIService()
        try:
            data, _usage = client.chat_json(
                system=EXTRACTION_SYSTEM_PROMPT,
                user=prompt,
                model=model_for_tier("strong"),
            )
        except Exception as exc:
            logger.warning("date_notes_llm_failed error=%s", exc)
            return

        note_labels = {
            "bid_deadline_note", "bid_open_note", "pre_bid_note",
            "site_visit_note", "question_deadline_note", "award_note",
        }
        found = [
            i for i in (data.get("items") or [])
            if str(i.get("label") or "").strip() in note_labels
            and str(i.get("value") or "").strip()
        ]
        if not found:
            logger.info("date_notes_empty document_id=%s", document.id)
            return

        total_pages = max((p for p, _ in page_texts), default=1)
        validated = validate_and_score_items(
            found,
            chunk_text=context,
            section_title="Date notes",
            page_start=1,
            page_end=total_pages,
            total_pages=total_pages,
            page_texts=page_texts,
        )
        merged = merge_insight_items((insight.payload.get("items") or []) + validated)
        insight.payload = {"items": merged}
        insight.save(update_fields=["payload", "updated_at"])
        ExtractionService._sync_source_references(document, insight)
        logger.info(
            "date_notes_saved document_id=%s notes=%s",
            document.id,
            [i.get("label") for i in validated],
        )

    # Must-have fields: absence after a successful group pass triggers one
    # focused strong-model re-ask against the cover pages.
    _MUST_HAVE_FIELDS: tuple[tuple[str, str, str], ...] = (
        # (field label, owning extraction_type, one-line ask)
        (
            "project_name",
            "eligibility_criteria",
            "project_name = the tender/project title from the cover page or notice.",
        ),
        (
            "bid_deadline_date_time",
            "submission_deadlines",
            "bid_deadline_date_time = the date and time proposals/bids are due.",
        ),
    )

    @staticmethod
    def _verify_must_have_fields(
        document: Document,
        summary: GeneratedSummary,
        results: dict[str, ExtractedInsight],
        page_texts: list[tuple[int, str]],
    ) -> None:
        """One focused re-ask for any must-have field the group pass missed."""
        if not bool(
            getattr(settings, "INTELLIGENCE_MUST_HAVE_VERIFY_ENABLED", True)
        ):
            return

        missing: list[tuple[str, str, str]] = []
        for label, etype, ask in GroupExtractionService._MUST_HAVE_FIELDS:
            insight = results.get(etype)
            items = (insight.payload.get("items") if insight else None) or []
            if not any(str(i.get("label") or "").strip() == label for i in items):
                missing.append((label, etype, ask))
        if not missing:
            return

        cover = "\n\n".join(
            f"--- Page {p} ---\n{(t or '').strip()}"
            for p, t in page_texts[:6]
            if (t or "").strip()
        )[:30_000]
        if not cover:
            return

        asks = "\n".join(f"- {ask}" for _, _, ask in missing)
        labels = ", ".join(label for label, _, _ in missing)
        prompt = f"""These required fields were not found on the first pass. Look again carefully.

Extract ONLY these fields (use EXACT label values): {labels}

{asks}

Rules:
- Every item MUST include verbatim source_text from the pages below.
- If a field is truly absent, omit it — do NOT guess.
- Respond with valid JSON only: {{"items": [{{"requirement": "<label>: <value>", "label": "<label>", "value": "<text>", "date_time": "<for dates>", "page": integer or null, "section": "...", "source_text": "verbatim excerpt", "confidence": 0.0 to 1.0}}]}}

Cover pages:
---
{cover}
---"""

        client = OpenAIService()
        try:
            data, _usage = client.chat_json(
                system=EXTRACTION_SYSTEM_PROMPT,
                user=prompt,
                model=model_for_tier("strong"),
            )
        except Exception as exc:
            logger.warning("must_have_verify_llm_failed error=%s", exc)
            return

        found = data.get("items") or []
        if not found:
            logger.info(
                "must_have_verify_empty document_id=%s missing=%s",
                document.id,
                [m[0] for m in missing],
            )
            return

        total_pages = max((p for p, _ in page_texts), default=1)
        validated = validate_and_score_items(
            found,
            chunk_text=cover,
            section_title="Must-have verification",
            page_start=1,
            page_end=total_pages,
            total_pages=total_pages,
            page_texts=page_texts,
        )
        by_type: dict[str, list[dict]] = {}
        wanted = {label: etype for label, etype, _ in missing}
        for item in validated:
            label = str(item.get("label") or "").strip()
            etype = wanted.get(label)
            if etype:
                by_type.setdefault(etype, []).append(item)

        for etype, new_items in by_type.items():
            insight = results.get(etype)
            if insight is None:
                continue
            merged = merge_insight_items(
                (insight.payload.get("items") or []) + new_items
            )
            insight.payload = {"items": merged}
            insight.confidence_score = aggregate_confidence(merged)
            insight.save(update_fields=["payload", "confidence_score", "updated_at"])
            ExtractionService._sync_source_references(document, insight)
            logger.info(
                "must_have_verify_recovered document_id=%s type=%s fields=%s",
                document.id,
                etype,
                [i.get("label") for i in new_items],
            )

    @staticmethod
    def _extract_group(
        group: ExtractionGroup,
        document: Document,
        summary: GeneratedSummary,
        document_text: str,
        total_pages: int,
        page_texts: list[tuple[int, str]],
        model: str,
    ) -> ExtractedInsight | None:
        close_old_connections()
        client = OpenAIService()
        user_prompt = group_extraction_user_prompt(group, document_text)

        try:
            data, usage = client.chat_json(
                system=EXTRACTION_SYSTEM_PROMPT,
                user=user_prompt,
                model=model,
            )
        except Exception as exc:
            logger.warning(
                "group_extraction_llm_failed group=%s error=%s",
                group.group_id,
                exc,
            )
            return None

        items = data.get("items") or []
        validated = validate_and_score_items(
            items,
            chunk_text=document_text,
            section_title=group.title,
            page_start=1,
            page_end=total_pages,
            total_pages=total_pages,
            page_texts=page_texts,
        )
        merged = merge_insight_items(validated)

        if group.extraction_type == "penalties_and_risks":
            merged = _split_bond_items_for_certified_checks(merged)

        if not merged:
            logger.info("group_extraction_empty group=%s", group.group_id)
            return None

        return GroupExtractionService._persist_insight(
            document=document,
            summary=summary,
            extraction_type=group.extraction_type,
            items=merged,
            model=model,
            usage=usage,
        )

    @staticmethod
    @transaction.atomic
    def _persist_insight(
        *,
        document: Document,
        summary: GeneratedSummary,
        extraction_type: str,
        items: list[dict],
        model: str,
        usage: dict,
    ) -> ExtractedInsight:
        confidence = aggregate_confidence(items)
        insight = ExtractedInsight.objects.create(
            document=document,
            generated_summary=summary,
            extraction_type=extraction_type,
            payload={"items": items},
            confidence_score=confidence,
            model_name=model,
            prompt_version=settings.INTELLIGENCE_PROMPT_VERSION,
            token_usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "model": model,
                "mode": "group_extraction",
            },
            chunk_ids=[],
        )
        ExtractionService._sync_source_references(document, insight)
        logger.info(
            "group_extraction_saved group_type=%s items=%s confidence=%s",
            extraction_type,
            len(items),
            confidence,
        )
        return insight
