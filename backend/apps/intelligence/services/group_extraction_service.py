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


def _description_text_from_pages(page_texts: list[tuple[int, str]]) -> str:
    """Fallback: scope sections usually start mid-document (pages 15–25)."""
    anchor_page: int | None = None
    best_score = 0
    primary_needle = "Background and Overview of Desired Services"

    for p, t in page_texts:
        text = t or ""
        if primary_needle in text:
            score = _section_quality_score(text, primary_needle)
            if score > best_score:
                best_score = score
                anchor_page = p
        elif anchor_page is None:
            if re.search(
                r"\b(Scope of Work|Project Description|Description of Work)\b", text, re.I
            ):
                for m in re.finditer(
                    r"\b(Scope of Work|Project Description|Description of Work)\b",
                    text,
                    re.I,
                ):
                    score = _section_quality_score(text[m.start() :], m.group(0))
                    if score > best_score:
                        best_score = score
                        anchor_page = p

    # Reject TOC hits (page 2 lists section titles with no prose).
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
        # Bid timelines almost always live on cover pages 1–3.
        cover = "\n\n".join(
            f"--- Page {p} ---\n{t.strip()}"
            for p, t in page_texts[:5]
            if (t or "").strip()
        )
        if cover:
            return cover

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
        critical_gap_ms = int(
            getattr(settings, "INTELLIGENCE_GROUP_EXTRACTION_CRITICAL_GAP_MS", 1500)
        )
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
        critical = [g for g in ordered if g.group_id in CRITICAL_GROUP_IDS]
        non_critical = [g for g in ordered if g.group_id not in CRITICAL_GROUP_IDS]

        # ── Pass 0: critical groups sequentially (never lose dates/description) ─
        for i, group in enumerate(critical):
            if i > 0 and critical_gap_ms > 0:
                time.sleep(critical_gap_ms / 1000.0)
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
                if insight:
                    results[group.extraction_type] = insight
                else:
                    failed_groups.append(group)
            except Exception as exc:
                logger.error(
                    "group_extraction_critical_failed group=%s error=%s",
                    group.group_id,
                    exc,
                    exc_info=True,
                )
                failed_groups.append(group)

        # ── Pass 1: non-critical groups parallel (staggered) ─────────────────
        if non_critical:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map: dict = {}
                for i, group in enumerate(non_critical):
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
                            "group_extraction_failed group=%s error=%s",
                            group.group_id,
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
            if group.group_id not in CRITICAL_GROUP_IDS and group.extraction_type in results:
                continue
            for attempt in range(1, max_retries + 1):
                wait = min(2**attempt, 20)
                logger.info(
                    "group_extraction_retry group=%s attempt=%s wait=%ss",
                    group.group_id,
                    attempt,
                    wait,
                )
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
