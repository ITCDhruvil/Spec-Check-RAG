import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db import close_old_connections, transaction

from apps.documents.choices import SourceReferenceKind
from apps.documents.models import Document, SourceReference
from apps.intelligence.choices import ExtractionType, FOCUSED_EXTRACTION_TYPES
from apps.intelligence.models import DocumentChunk, ExtractedInsight, GeneratedSummary
from apps.intelligence.prompts.templates import (
    COVER_PAGE_IDENTITY_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    cover_page_identity_user_prompt,
    extraction_user_prompt,
)
from apps.intelligence.services.grounding import (
    aggregate_confidence,
    merge_insight_items,
    validate_and_score_items,
)
from apps.intelligence.services.adaptive_lexicon_service import (
    AdaptiveLexiconService,
    DocumentAdaptiveLexicon,
    adaptive_retry_enabled,
)
from apps.intelligence.services.chunk_selection_fusion import fuse_chunk_selections
from apps.intelligence.services.doc_classifier import classify as classify_document
from apps.intelligence.services.extraction_retrieval_service import (
    ExtractionRetrievalService,
    hybrid_retrieval_enabled,
    overrides_for_classification,
)
from apps.intelligence.services.model_routing import (
    EXTRACTION_MODEL_TIER,
    extraction_escalation_model,
    extraction_model,
    model_for_tier,
    should_escalate_extraction,
)
from apps.intelligence.services.fast_mode import (
    broad_extraction_chunks,
    default_extraction_chunks,
    extraction_batch_size,
    fast_extraction_enabled,
    group_extraction_enabled,
    keyword_only_extraction,
)
from apps.intelligence.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

# Maximum parallel threads — one per extraction type.
# Bounded at 8 (= len(FOCUSED_EXTRACTION_TYPES)) so we never over-subscribe.
_EXTRACTION_WORKERS = getattr(settings, "INTELLIGENCE_EXTRACTION_WORKERS", 8)

# Max chars to send per chunk to the LLM after paragraph-level pre-filtering (#5).
# Chunks are up to INTELLIGENCE_MAX_CHUNK_CHARS (6 000) — filtering trims them to this.
_CHUNK_TRIM_CHARS = getattr(settings, "INTELLIGENCE_CHUNK_TRIM_CHARS", 3500)

# How many chunks to group into a single LLM call (#6).
# Default 3 → a 14-chunk type makes 5 calls instead of 14 (~65% fewer calls per type).
# Set to 1 to disable batching and send one chunk per call (original behaviour).
_EXTRACTION_BATCH_SIZE = extraction_batch_size()

# Keyword hints for chunk routing (broad — indirect procurement language included)
EXTRACTION_CHUNK_KEYWORDS: dict[str, list[str]] = {
    ExtractionType.ELIGIBILITY_CRITERIA: [
        "eligibility", "qualification", "experience", "bidder", "contractor",
        "disqualif", "minimum", "marks", "pre-qualif",
        # Spec-check metadata (project identity + named parties + acquisition instructions)
        "project name", "project description", "project owner", "owner",
        "project engineer", "engineer", "architect", "project architect",
        "consultant", "solicitation", "tender", "invitation", "bid no",
        "tender no", "project no", "reference", "case no",
        "obtain", "download", "acquire", "instructions to bidders",
    ],
    ExtractionType.SUBMISSION_DEADLINES: [
        "deadline", "submission", "closing", "due", "validity", "etender",
        "e-tender", "portal", "query", "clarification", "proposal", "late",
        # Pre-bid / conference (US RFPs rarely say "pre-bid" — use Proposer's Conference)
        "conference", "proposer", "bidder", "pre-bid", "prebid", "pre bid",
        "pre-registration", "pre registration", "mandatory", "non-mandatory",
        "timeline", "advertised", "issue date", "anticipated", "opening",
        "walkthrough", "site visit", "questions due", "february", "january",
        # Spec-check calendar events
        "bid closing", "proposal due", "due date", "closing date",
        "municipal meeting", "council", "board meeting", "public hearing",
        "questions deadline", "clarification due", "bid opening",
    ],
    ExtractionType.TECHNICAL_REQUIREMENTS: [
        "technical", "specification", "sla", "performance", "sso", "sharepoint",
        "portal", "mobile", "workflow", "dashboard", "integration", "vapt",
        "hosting", "maintenance", "training", "source code", "24x7", "uptime",
        # Physical / managed security services
        "security", "guard", "guarding", "escort", "patrol", "manpower",
        "personnel", "deployment", "shift", "roster", "cctv", "access control",
        "transport", "emergency", "incident", "audit", "uniform", "weapon",
        "background check", "statutory", "labor", "labour", "standby",
        "women", "safety protocol",
        # Spec-check project size & site facts
        "square feet", "sq ft", "sqft", "square footage", "area", "floor area",
        "location", "address", "site", "parcel", "site location", "campus",
        "start date", "begin date", "completion date", "substantial completion",
        "project duration", "time of performance",
        # Engineering/architectural wording
        "architect", "engineering", "design",
    ],
    ExtractionType.SCOPE_OF_WORK: [
        "scope", "work", "deliverable", "milestone", "sow", "implementation",
        "vendor", "responsib", "subcontract",
        "security service", "transport", "escort", "guarding", "bangalore",
        "chennai", "location", "site", "headcount", "manpower", "personnel",
        "deployment", "standby", "24x7", "shift", "operational",
        # Spec-check description and acquisition instructions
        "project description", "overview", "scope summary",
        "documents may be obtained", "documents are available", "how to obtain",
        "obtain the bid", "download", "acquire", "request for proposals",
        "request for quotation", "invitation to bid", "instruction to bidders",
    ],
    ExtractionType.PAYMENT_TERMS: [
        "payment", "commercial", "price", "invoice", "retention", "fixed",
        "guarantee", "bond", "validity", "tax", "milestone", "advance",
        "performance", "bank", "quoted",
        # Spec-check value/budget language
        "value", "estimated value", "estimated", "budget", "cost", "amount",
        "contract value", "total project cost", "range", "$",
    ],
    ExtractionType.PENALTIES_AND_RISKS: [
        "penalty", "liquidated", "termination", "liability", "risk",
        "reject", "non-conform", "noncomform", "breach", "default",
        "indemn", "cancel", "discretion",
        "under-performance", "non-performance", "damages", "forfeit",
        # Bond/check instruments (spec-check requirement extraction)
        "bid bond", "performance bond", "payment bond", "maintenance bond",
        "maintenance and labor bond", "labor bond",
        "surety", "certified check", "bank check", "guarantee", "bond form",
        # Common federal wording
        "bid guarantee", "bid security", "bonding", "sf 24", "sf-24",
        "performance and payment bond", "miller act",
    ],
    ExtractionType.MANDATORY_DOCUMENTS: [
        "annexure", "appendix", "form", "emd", "document", "compliance",
        "matrix", "acknowledg", "guarantee", "reference", "cv", "proposal",
        "non-conform",
        # Spec-check acquisition instructions and solicitation identifiers
        "obtain", "download", "acquire", "solicitation", "tender no",
        "proposal submission", "bid submission", "instructions",
        "certified check", "bank check", "bond", "surety",
    ],
    ExtractionType.SET_ASIDES: [
        "mbe", "minority business", "minority owned", "minority enterprise",
        "wbe", "women business", "woman owned", "women owned", "female",
        "dbe", "disadvantaged business", "disadvantaged enterprise",
        "dvbe", "disabled veteran", "service-disabled",
        "hub", "historically underutilized",
        "sbe", "small business enterprise", "small business goal",
        "set-aside", "set aside", "subcontracting goal", "participation goal",
        "diversity", "inclusion goal", "%", "percent",
    ],
    ExtractionType.EVALUATION_CRITERIA: [],
}

# Types that need wide document coverage (not only keyword hits)
BROAD_COVERAGE_TYPES = frozenset(
    {
        ExtractionType.PAYMENT_TERMS,
        ExtractionType.PENALTIES_AND_RISKS,
        ExtractionType.MANDATORY_DOCUMENTS,
        ExtractionType.TECHNICAL_REQUIREMENTS,
        ExtractionType.SCOPE_OF_WORK,
        ExtractionType.ELIGIBILITY_CRITERIA,  # qualif/experience scattered throughout
        ExtractionType.SET_ASIDES,  # goals can appear anywhere in spec
    }
)

DEFAULT_MAX_CHUNKS = 10
BROAD_MAX_CHUNKS = 14
MIN_BROAD_CHUNKS = 8

# Sections that carry service scope / manpower / guarding (security & facilities RFPs).
OPERATIONAL_CONTENT_MARKERS: tuple[str, ...] = (
    "scope of work",
    "security personnel",
    "approximately 275",
    "275 security",
    "transport escort",
    "transport security",
    "standby manpower",
    "guarding",
    "escort guard",
    "bangalore",
    "chennai",
    "headcount",
    "deployment",
    "women associate",
    "24/7",
    "24x7",
    "supplier information",
)

OPERATIONAL_PIN_TYPES = frozenset(
    {
        ExtractionType.SCOPE_OF_WORK,
        ExtractionType.TECHNICAL_REQUIREMENTS,
    }
)

# How many of the document's first chunks to read in the cover-page identity scan.
# These early chunks almost always contain the project title, solicitation numbers,
# engineer/architect names, and owner — the fields most likely to be missed by
# keyword routing which scores on procurement terminology rather than cover-page prose.
_COVER_PAGE_CHUNK_COUNT = 5

# How many of the first parsed pages to include in the cover-page identity scan.
# Prefer page text over "first chunks" because chunk ordering can be skewed when
# section detection splits cover pages into many tiny sections.
_COVER_PAGE_MAX_PAGES = getattr(settings, "INTELLIGENCE_COVER_PAGE_MAX_PAGES", 3)


def _split_bond_items_for_certified_checks(merged: list[dict]) -> list[dict]:
    """
    Post-process bond items: if a bid_bond_information item's source text also
    mentions a certified or cashier's check, add a separate certified_checks item
    so the UI bond section shows it as a distinct row.

    This handles the common tender wording:
      "Bid security … in the form of … a bid bond … OR a certified/cashier's check …"
    which the LLM correctly labels as bid_bond_information but fails to also label
    as certified_checks.
    """
    _CERTIFIED_KWS = (
        "certified check", "cashier's check", "cashier check",
        "certified or cashier", "bank check", "money order",
    )

    already_has_certified = any(
        (item.get("label") or "").strip().lower() == "certified_checks"
        for item in merged
    )
    if already_has_certified:
        return merged

    extra: list[dict] = []
    for item in merged:
        src = (item.get("source_text") or "").lower()
        req = (item.get("requirement") or "").lower()
        if any(kw in src or kw in req for kw in _CERTIFIED_KWS):
            new_item = dict(item)
            new_item["label"] = "certified_checks"
            detail = item.get("value") or item.get("source_text") or ""
            new_item["requirement"] = f"certified_checks: {detail}"
            extra.append(new_item)

    return merged + extra


# ── Opt #5 — paragraph-level context trimmer ─────────────────────────────────

def _trim_chunk_to_relevant_paragraphs(
    text: str,
    extraction_type: str,
    max_chars: int = _CHUNK_TRIM_CHARS,
) -> str:
    """
    Return only the paragraphs most relevant to *extraction_type*, up to *max_chars*.

    Chunks are selected by keyword routing but may still contain large sections of
    irrelevant prose. Filtering to top-scoring paragraphs cuts input tokens by
    30–50% for dense chunks while keeping every sentence that matches the keywords.

    Small chunks (already within budget) pass through unchanged.
    """
    if len(text) <= max_chars:
        return text

    keywords = EXTRACTION_CHUNK_KEYWORDS.get(extraction_type, [])
    if not keywords:
        return text[:max_chars]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return text[:max_chars]

    scored: list[tuple[int, str]] = []
    for para in paragraphs:
        lower = para.lower()
        score = sum(1 for kw in keywords if kw in lower)
        scored.append((score, para))

    # Sort by relevance descending; then rebuild in *original document order*
    # so we don't scramble the narrative structure for the LLM.
    relevant_set = {
        para for score, para in sorted(scored, key=lambda x: -x[0])
        if score > 0
    }
    ordered = [p for p in paragraphs if p in relevant_set]

    # Fill remaining budget with unseen paragraphs (preserves any stray context).
    seen = set(ordered)
    for para in paragraphs:
        if para not in seen:
            ordered.append(para)

    result_parts: list[str] = []
    total = 0
    for para in ordered:
        if total + len(para) + 2 > max_chars:
            break
        result_parts.append(para)
        total += len(para) + 2

    return "\n\n".join(result_parts) if result_parts else text[:max_chars]


def _llm_text_for_chunk(chunk: DocumentChunk) -> str:
    """Return the text to send to the LLM for this chunk.

    Retrieval scores on the small leaf chunk for precision. The LLM gets the
    full parent section so it has enough context to extract correctly.
    parent_text is set to the full section content (up to MAX_CHUNK_CHARS) at
    index time; for single-part sections it equals chunk_text.
    """
    parent = (chunk.metadata or {}).get("parent_text") or ""
    if parent and len(parent) > len(chunk.chunk_text):
        return parent
    return chunk.chunk_text


# ── Opt #6 — chunk batching ───────────────────────────────────────────────────

def _build_batch_groups(
    chunks: list[DocumentChunk],
    batch_size: int,
) -> list[list[DocumentChunk]]:
    """Split *chunks* into consecutive groups of at most *batch_size*."""
    return [chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)]


class ExtractionService:
    @staticmethod
    def _focused_types_for_prompt_version() -> list[str]:
        """
        Return the extraction types to run for the active prompt version.

        In spec-check mode we intentionally skip certain RFQ/RFP-style passes that
        either aren't used or are defined as no-op in prompts (e.g. evaluation_criteria).
        """
        prompt_version = str(getattr(settings, "INTELLIGENCE_PROMPT_VERSION", "") or "")
        is_spec_check = prompt_version.lower().startswith("spec-check")
        if not is_spec_check:
            return list(FOCUSED_EXTRACTION_TYPES)

        return [
            t
            for t in FOCUSED_EXTRACTION_TYPES
            if t
            not in (
                ExtractionType.EVALUATION_CRITERIA,
            )
        ]

    @staticmethod
    def _cover_text_from_pages(page_texts: list[tuple[int, str]]) -> tuple[str, int, int]:
        if not page_texts:
            return "", 1, 1
        max_pages = max(1, int(_COVER_PAGE_MAX_PAGES))
        selected = [(p, t or "") for p, t in page_texts if isinstance(p, int) and p >= 1][:max_pages]
        if not selected:
            return "", 1, 1
        parts = [f"--- Page {p} ---\n{t}".strip() for p, t in selected if (t or "").strip()]
        combined = "\n\n".join(parts).strip()
        return combined, selected[0][0], selected[-1][0]

    @staticmethod
    def _run_cover_page_identity_scan(
        all_chunks: list[DocumentChunk],
        client: "OpenAIService",
        total_pages: int,
        page_texts: list[tuple[int, str]],
    ) -> tuple[list[dict], dict]:
        """
        Dedicated separate OpenAI API call that reads only the first N chunks of
        the document (by chunk_order) to extract cover-page identity fields:
        project_name, project_solicitation_number, project_engineer,
        project_architect, project_owner.

        These fields live on the cover/title page and are often missed when keyword
        routing selects spec-section chunks deep in the document.
        """
        combined_text, page_start, page_end = ExtractionService._cover_text_from_pages(page_texts)

        # Fallback to first chunks when page texts are missing/empty.
        first_chunks: list[DocumentChunk] = []
        if not combined_text:
            first_chunks = sorted(all_chunks, key=lambda c: c.chunk_order)[:_COVER_PAGE_CHUNK_COUNT]
            if not first_chunks:
                return [], {}
            parts = [
                f"=== Pages {c.page_start}–{c.page_end} | {c.section_title} ===\n{c.chunk_text}"
                for c in first_chunks
            ]
            combined_text = "\n\n".join(parts).strip()
            page_start = min(c.page_start for c in first_chunks)
            page_end = max(c.page_end for c in first_chunks)
        if not combined_text:
            return [], {}

        try:
            data, usage = client.chat_json(
                system=COVER_PAGE_IDENTITY_SYSTEM_PROMPT,
                user=cover_page_identity_user_prompt(combined_text),
                model=model_for_tier("fast"),
            )
        except Exception as exc:
            logger.warning("cover_page_identity_scan_failed error=%s", exc)
            return [], {}

        items = data.get("items") or []

        validated = validate_and_score_items(
            items,
            chunk_text=combined_text,
            section_title="cover page / bid notice",
            page_start=page_start,
            page_end=page_end,
            total_pages=total_pages,
            page_texts=page_texts,
        )
        logger.info(
            "cover_page_identity_scan_complete items=%s",
            len(validated),
        )
        return validated, usage

    @staticmethod
    def _chunk_has_operational_content(chunk: DocumentChunk) -> bool:
        blob = f"{chunk.section_title} {chunk.chunk_text}".lower()
        return any(marker in blob for marker in OPERATIONAL_CONTENT_MARKERS)

    @staticmethod
    def _pin_operational_chunks(
        selected: list[DocumentChunk],
        all_chunks: list[DocumentChunk],
        max_chunks: int,
    ) -> list[DocumentChunk]:
        """Ensure scope/technical passes always see manpower & SOW sections first."""
        pinned = [c for c in all_chunks if ExtractionService._chunk_has_operational_content(c)]
        if not pinned:
            return selected

        merged: list[DocumentChunk] = []
        seen: set = set()
        for chunk in pinned + selected:
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            merged.append(chunk)
        return merged[:max_chunks]

    @staticmethod
    def _max_chunks_for_type(extraction_type: str) -> int:
        if extraction_type in BROAD_COVERAGE_TYPES:
            return broad_extraction_chunks()
        return default_extraction_chunks()

    @staticmethod
    def _stratified_fill(
        chunks: list[DocumentChunk],
        exclude_ids: set,
        count: int,
    ) -> list[DocumentChunk]:
        """Sample chunks across the document when keyword routing under-selects."""
        pool = [c for c in chunks if c.id not in exclude_ids]
        if not pool or count <= 0:
            return []
        if len(pool) <= count:
            return pool
        step = len(pool) / count
        picked: list[DocumentChunk] = []
        for i in range(count):
            idx = min(int(i * step), len(pool) - 1)
            chunk = pool[idx]
            if chunk.id not in {c.id for c in picked}:
                picked.append(chunk)
        return picked

    @staticmethod
    def select_chunks(
        chunks: list[DocumentChunk],
        extraction_type: str,
        *,
        hybrid_scores: dict[str, float] | None = None,
        adaptive_terms: list[str] | None = None,
        keyword_only: bool = False,
    ) -> list[DocumentChunk]:
        keyword_selected = ExtractionService._select_chunks_keyword(
            chunks,
            extraction_type,
            adaptive_terms=adaptive_terms,
        )
        if keyword_only or not hybrid_scores or not hybrid_retrieval_enabled():
            return keyword_selected

        max_chunks = ExtractionService._max_chunks_for_type(extraction_type)
        keyword_weight = getattr(settings, "INTELLIGENCE_KEYWORD_RRF_WEIGHT", 1.0)
        hybrid_weight = getattr(settings, "INTELLIGENCE_HYBRID_RRF_WEIGHT", 1.0)
        fused = fuse_chunk_selections(
            keyword_selected=keyword_selected,
            hybrid_scores=hybrid_scores,
            all_chunks=chunks,
            max_chunks=max_chunks,
            keyword_weight=keyword_weight,
            hybrid_weight=hybrid_weight,
        )

        if extraction_type in OPERATIONAL_PIN_TYPES:
            fused = ExtractionService._pin_operational_chunks(fused, chunks, max_chunks)
            operational = [
                c for c in fused if ExtractionService._chunk_has_operational_content(c)
            ]
            other = [c for c in fused if c not in operational]
            operational.sort(key=lambda c: c.chunk_order)
            other.sort(key=lambda c: c.chunk_order)
            return (operational + other)[:max_chunks]

        return fused

    @staticmethod
    def _select_chunks_keyword(
        chunks: list[DocumentChunk],
        extraction_type: str,
        *,
        adaptive_terms: list[str] | None = None,
    ) -> list[DocumentChunk]:
        if not chunks:
            return []

        keywords = list(EXTRACTION_CHUNK_KEYWORDS.get(extraction_type, []))
        adaptive = list(adaptive_terms or [])
        global_weight = getattr(settings, "INTELLIGENCE_ADAPTIVE_TERM_WEIGHT", 1.0)
        static_weight = 1.0
        max_chunks = ExtractionService._max_chunks_for_type(extraction_type)

        scored: list[tuple[int, DocumentChunk]] = []
        type_boosts: dict[str, dict[str, int]] = {
            ExtractionType.ELIGIBILITY_CRITERIA: {"cover_metadata": 8, "general_section": 1},
            ExtractionType.SUBMISSION_DEADLINES: {"schedule_table": 10, "cover_metadata": 6},
            ExtractionType.PENALTIES_AND_RISKS: {"bond_clause": 10},
            ExtractionType.MANDATORY_DOCUMENTS: {"form_annex": 6, "cover_metadata": 3},
            ExtractionType.PAYMENT_TERMS: {"general_section": 1},
        }
        boosts = type_boosts.get(extraction_type, {})

        for chunk in chunks:
            text = f"{chunk.section_title} {chunk.chunk_text}".lower()
            score = sum(static_weight for kw in keywords if kw in text)
            score += sum(global_weight for term in adaptive if term.lower() in text)
            tags = chunk.metadata.get("tags", [])
            for tag in tags:
                tag_lower = str(tag).lower()
                if any(kw in tag_lower or kw in text for kw in keywords):
                    score += 2
                if any(term.lower() in tag_lower or term.lower() in text for term in adaptive):
                    score += 1
            chunk_type = chunk.metadata.get("chunk_type", "")
            score += boosts.get(chunk_type, 0)
            if score > 0:
                scored.append((score, chunk))

        selected: list[DocumentChunk] = []
        seen_ids: set = set()

        if scored:
            scored.sort(key=lambda x: (-x[0], x[1].chunk_order))
            for _, chunk in scored[:max_chunks]:
                if chunk.id not in seen_ids:
                    selected.append(chunk)
                    seen_ids.add(chunk.id)

        min_needed = MIN_BROAD_CHUNKS if extraction_type in BROAD_COVERAGE_TYPES else 4
        if len(selected) < min_needed:
            extra = ExtractionService._stratified_fill(
                chunks, seen_ids, min_needed - len(selected)
            )
            for chunk in extra:
                selected.append(chunk)
                seen_ids.add(chunk.id)

        if not selected:
            selected = ExtractionService._stratified_fill(chunks, set(), min(max_chunks, 6))

        if extraction_type in OPERATIONAL_PIN_TYPES:
            selected = ExtractionService._pin_operational_chunks(
                selected, chunks, max_chunks
            )
            operational = [
                c for c in selected if ExtractionService._chunk_has_operational_content(c)
            ]
            other = [c for c in selected if c not in operational]
            operational.sort(key=lambda c: c.chunk_order)
            other.sort(key=lambda c: c.chunk_order)
            return (operational + other)[:max_chunks]

        selected.sort(key=lambda c: c.chunk_order)
        return selected[:max_chunks]

    @staticmethod
    def _run_extraction_batches(
        extraction_type: str,
        selected: list[DocumentChunk],
        *,
        client: OpenAIService,
        total_pages: int,
        page_texts: list[tuple[int, str]],
        batch_size: int = _EXTRACTION_BATCH_SIZE,
        model: str | None = None,
        known_context: dict | None = None,
    ) -> tuple[list[dict], list[str], dict]:
        """Run LLM extraction over chunk batches; return items, chunk_ids, token usage."""
        deployment = model or extraction_model(extraction_type)
        all_items: list[dict] = []
        chunk_ids: list[str] = []
        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "model": deployment,
        }

        for batch in _build_batch_groups(selected, batch_size):
            trimmed: list[str] = [
                _trim_chunk_to_relevant_paragraphs(_llm_text_for_chunk(c), extraction_type)
                for c in batch
            ]

            if len(batch) == 1:
                prompt_text = trimmed[0]
                prompt_label = batch[0].section_title
            else:
                parts: list[str] = [
                    f"=== Section: {c.section_title} "
                    f"| Pages {c.page_start}–{c.page_end} ===\n{t}"
                    for c, t in zip(batch, trimmed)
                ]
                prompt_text = "\n\n".join(parts)
                prompt_label = f"{batch[0].section_title} (+{len(batch) - 1} more)"

            batch_page_start = min(c.page_start for c in batch)
            batch_page_end = max(c.page_end for c in batch)

            user_prompt = extraction_user_prompt(
                extraction_type,
                prompt_text,
                prompt_label,
                known_context=known_context,
            )
            try:
                if getattr(settings, "INTELLIGENCE_STRUCTURED_OUTPUT_ENABLED", False):
                    from apps.intelligence.prompts.schemas import ExtractionResult

                    data, usage = client.chat_structured(
                        system=EXTRACTION_SYSTEM_PROMPT,
                        user=user_prompt,
                        schema=ExtractionResult,
                        model=deployment,
                    )
                else:
                    data, usage = client.chat_json(
                        system=EXTRACTION_SYSTEM_PROMPT,
                        user=user_prompt,
                        model=deployment,
                    )
            except Exception as exc:
                logger.warning(
                    "extraction_batch_failed type=%s chunks=%s error=%s",
                    extraction_type,
                    [str(c.id) for c in batch],
                    exc,
                )
                continue

            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                total_usage[key] = total_usage.get(key, 0) + usage.get(key, 0)

            items = data.get("items") or []
            validated = validate_and_score_items(
                items,
                chunk_text=prompt_text,
                section_title=prompt_label,
                page_start=batch_page_start,
                page_end=batch_page_end,
                total_pages=total_pages,
                page_texts=page_texts,
            )
            all_items.extend(validated)
            chunk_ids.extend(str(c.id) for c in batch)

        return all_items, chunk_ids, total_usage

    @staticmethod
    def _extract_single_type(
        extraction_type: str,
        selected: list[DocumentChunk],
        document: Document,
        summary: GeneratedSummary,
        total_pages: int,
        page_texts: list[tuple[int, str]],
        all_chunks: list[DocumentChunk] | None = None,
        lexicon: DocumentAdaptiveLexicon | None = None,
        cover_text: str = "",
        initial_hybrid_scores: dict[str, float] | None = None,
        known_context: dict | None = None,
    ) -> ExtractedInsight:
        """
        Run all chunk-level LLM calls for one extraction type and persist the result.
        Designed to run inside a ThreadPoolExecutor worker — each call owns its own
        OpenAIService instance and DB connection to avoid cross-thread sharing.
        """
        # Ensure Django gives this thread a fresh DB connection rather than
        # reusing a stale one from the parent thread.
        close_old_connections()

        client = OpenAIService()
        pool = all_chunks or selected
        primary_model = extraction_model(extraction_type)
        started_with_fast = (
            getattr(settings, "INTELLIGENCE_MODEL_ROUTING_ENABLED", True)
            and EXTRACTION_MODEL_TIER.get(extraction_type) == "fast"
        )

        all_items, chunk_ids, total_usage = ExtractionService._run_extraction_batches(
            extraction_type,
            selected,
            client=client,
            total_pages=total_pages,
            page_texts=page_texts,
            model=primary_model,
            known_context=known_context,
        )

        merged = merge_insight_items(all_items)
        model_used = primary_model

        # ── Spec-check: dedicated cover-page identity scan (separate API call) ──
        # For ELIGIBILITY_CRITERIA in spec-check mode, run an additional focused
        # call against only the first _COVER_PAGE_CHUNK_COUNT chunks.  These cover
        # the title page / bid notice where project_name, solicitation numbers, and
        # engineer/architect names live — fields the keyword-routed batches miss when
        # the document opens with specification sections rather than a cover page.
        prompt_version = str(getattr(settings, "INTELLIGENCE_PROMPT_VERSION", "") or "")
        if (
            extraction_type == ExtractionType.ELIGIBILITY_CRITERIA
            and prompt_version.lower().startswith("spec-check")
            and pool
        ):
            cover_items, cover_usage = ExtractionService._run_cover_page_identity_scan(
                pool, client, total_pages, page_texts
            )
            if cover_items:
                # Cover-page items take priority: put them first so merge_insight_items
                # keeps them when their requirement text conflicts with later items.
                merged = merge_insight_items(cover_items + merged)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                total_usage[key] = total_usage.get(key, 0) + cover_usage.get(key, 0)

        if should_escalate_extraction(
            extraction_type,
            items=merged,
            started_with_fast=started_with_fast,
        ):
            strong_model = extraction_escalation_model(extraction_type)
            logger.info(
                "extraction_model_escalation type=%s from=%s to=%s",
                extraction_type,
                primary_model,
                strong_model,
            )
            retry_items, retry_ids, retry_usage = ExtractionService._run_extraction_batches(
                extraction_type,
                selected,
                client=client,
                total_pages=total_pages,
                page_texts=page_texts,
                model=strong_model,
            )
            merged = merge_insight_items(retry_items)
            chunk_ids = retry_ids
            model_used = f"{primary_model}->{strong_model}"
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                total_usage[key] = total_usage.get(key, 0) + retry_usage.get(key, 0)

        if (
            not merged
            and adaptive_retry_enabled()
            and lexicon is not None
            and cover_text
        ):
            extra_queries = AdaptiveLexiconService.expand_for_empty_type(
                lexicon, extraction_type, cover_text
            )
            if extra_queries:
                retry_hybrid = ExtractionRetrievalService.scores_for_types(
                    str(document.id),
                    [extraction_type],
                    lexicon=lexicon,
                    extra_queries_by_type={extraction_type: extra_queries},
                )
                combined_scores = dict(initial_hybrid_scores or {})
                for cid, score in retry_hybrid.get(extraction_type, {}).items():
                    combined_scores[cid] = max(combined_scores.get(cid, 0.0), score)
                retry_selected = ExtractionService.select_chunks(
                    pool,
                    extraction_type,
                    hybrid_scores=combined_scores,
                    adaptive_terms=lexicon.terms_for(extraction_type),
                )
                if retry_selected:
                    logger.info(
                        "adaptive_empty_retry type=%s chunks=%s queries=%s",
                        extraction_type,
                        len(retry_selected),
                        len(extra_queries),
                    )
                    retry_items, retry_ids, retry_usage = (
                        ExtractionService._run_extraction_batches(
                            extraction_type,
                            retry_selected,
                            client=client,
                            total_pages=total_pages,
                            page_texts=page_texts,
                            model=extraction_escalation_model(extraction_type),
                        )
                    )
                    merged = merge_insight_items(retry_items)
                    chunk_ids = retry_ids
                    model_used = f"{model_used}+adaptive_retry"
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        total_usage[key] = total_usage.get(key, 0) + retry_usage.get(key, 0)

        if not merged and extraction_type in OPERATIONAL_PIN_TYPES:
            fallback = [
                c for c in pool if ExtractionService._chunk_has_operational_content(c)
            ]
            if fallback:
                logger.warning(
                    "extraction_empty_retry type=%s operational_chunks=%s",
                    extraction_type,
                    len(fallback),
                )
                retry_items, retry_ids, retry_usage = (
                    ExtractionService._run_extraction_batches(
                        extraction_type,
                        fallback,
                        client=client,
                        total_pages=total_pages,
                        page_texts=page_texts,
                        batch_size=1,
                        model=extraction_escalation_model(extraction_type),
                    )
                )
                merged = merge_insight_items(retry_items)
                chunk_ids = retry_ids
                model_used = extraction_escalation_model(extraction_type)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    total_usage[key] = total_usage.get(key, 0) + retry_usage.get(key, 0)
        # In spec-check mode we repurpose PENALTIES_AND_RISKS to extract bond/security instruments.
        # Risk-severity postprocessing would mutate bond items; skip when prompt version indicates spec-check.
        if extraction_type == ExtractionType.PENALTIES_AND_RISKS:
            prompt_version = str(getattr(settings, "INTELLIGENCE_PROMPT_VERSION", "") or "")
            if prompt_version.lower().startswith("spec-check"):
                # Split out certified_checks if bid bond text also mentions a certified/cashier's check.
                merged = _split_bond_items_for_certified_checks(merged)
            else:
                from apps.intelligence.services.risk_severity import apply_penalties_severity

                merged = apply_penalties_severity(merged)
        confidence = aggregate_confidence(merged)

        insight = ExtractedInsight.objects.create(
            document=document,
            generated_summary=summary,
            extraction_type=extraction_type,
            payload={"items": merged},
            confidence_score=confidence,
            model_name=model_used,
            prompt_version=settings.INTELLIGENCE_PROMPT_VERSION,
            token_usage=total_usage,
            chunk_ids=chunk_ids,
        )
        ExtractionService._sync_source_references(document, insight)

        logger.info(
            "extraction_complete type=%s items=%s chunks=%s confidence=%s",
            extraction_type,
            len(merged),
            len(selected),
            confidence,
        )
        return insight

    @staticmethod
    def _identity_context(insight: "ExtractedInsight") -> dict:
        """Pull project_name/owner from the identity pass for downstream grounding (A5)."""
        ctx: dict = {}
        wanted = {"project_name", "project_owner"}
        for item in (getattr(insight, "payload", None) or {}).get("items", []):
            label = str(item.get("label") or "").strip().lower()
            value = str(item.get("value") or "").strip()
            if label in wanted and value and label not in ctx:
                ctx[label] = value[:120]
        return ctx

    @staticmethod
    def run_extractions(
        document: Document,
        summary: GeneratedSummary,
        chunks: list[DocumentChunk],
    ) -> list[ExtractedInsight]:
        if group_extraction_enabled():
            from apps.intelligence.services.group_extraction_service import (
                GroupExtractionService,
            )

            logger.info(
                "extraction_mode=document_group_parallel document_id=%s",
                document.id,
            )
            return GroupExtractionService.run_extractions(document, summary, chunks)

        parsed = document.parsed_document
        total_pages = parsed.total_pages
        page_texts = list(
            parsed.pages.order_by("page_number").values_list("page_number", "extracted_text")
        )

        # Pre-compute chunk selection for every type in one pass so we don't
        # re-score the same chunk list 8× inside the thread pool.
        focused_types = ExtractionService._focused_types_for_prompt_version()
        doc_id = str(document.id)
        cover_text = AdaptiveLexiconService.cover_sample_text(chunks, page_texts)

        if fast_extraction_enabled():
            lexicon = DocumentAdaptiveLexicon()
            hybrid_by_type: dict[str, dict[str, float]] = {}
            logger.info(
                "fast_extraction_mode document_id=%s keyword_only=true",
                doc_id,
            )
        else:
            lexicon = AdaptiveLexiconService.build(chunks, page_texts)
            classification = classify_document(cover_text)
            doc_type_overrides = overrides_for_classification(classification)
            logger.info(
                "doc_type_classification document_id=%s detail=%s overrides=%s",
                doc_id,
                classification.to_debug_dict(),
                {k: len(v) for k, v in doc_type_overrides.items()},
            )
            hybrid_by_type = ExtractionRetrievalService.scores_for_types(
                doc_id,
                focused_types,
                lexicon=lexicon,
                extra_queries_by_type=doc_type_overrides or None,
            )
            AdaptiveLexiconService.enrich_from_hybrid_feedback(lexicon, chunks, hybrid_by_type)
            logger.info(
                "adaptive_lexicon_ready document_id=%s detail=%s",
                doc_id,
                lexicon.to_debug_dict(),
            )

        use_keyword_only = keyword_only_extraction()
        chunk_selection: dict[str, list[DocumentChunk]] = {
            etype: ExtractionService.select_chunks(
                chunks,
                etype,
                hybrid_scores=hybrid_by_type.get(etype),
                adaptive_terms=lexicon.terms_for(etype),
                keyword_only=use_keyword_only,
            )
            for etype in focused_types
        }

        results: dict[str, ExtractedInsight] = {}

        # A5 — identity pass first: extract project_name/owner so subsequent passes
        # can ground scattered fields against the correct entity. Reuses the existing
        # cover-page scan inside eligibility_criteria (no extra LLM call).
        identity_type = ExtractionType.ELIGIBILITY_CRITERIA
        known_context: dict = {}
        remaining_types = list(focused_types)
        if identity_type in remaining_types:
            remaining_types.remove(identity_type)
            try:
                results[identity_type] = ExtractionService._extract_single_type(
                    identity_type,
                    chunk_selection[identity_type],
                    document,
                    summary,
                    total_pages,
                    page_texts,
                    chunks,
                    lexicon,
                    cover_text,
                    hybrid_by_type.get(identity_type, {}),
                )
                known_context = ExtractionService._identity_context(results[identity_type])
            except Exception as exc:
                logger.error(
                    "extraction_type_failed type=%s error=%s",
                    identity_type, exc, exc_info=True,
                )

        # Map future → extraction_type so we can log failures with context.
        future_to_type: dict = {}

        with ThreadPoolExecutor(max_workers=_EXTRACTION_WORKERS) as pool:
            for etype in remaining_types:
                fut = pool.submit(
                    ExtractionService._extract_single_type,
                    etype,
                    chunk_selection[etype],
                    document,
                    summary,
                    total_pages,
                    page_texts,
                    chunks,
                    lexicon,
                    cover_text,
                    hybrid_by_type.get(etype, {}),
                    known_context,
                )
                future_to_type[fut] = etype

            for fut in as_completed(future_to_type):
                etype = future_to_type[fut]
                try:
                    results[etype] = fut.result()
                except Exception as exc:
                    logger.error(
                        "extraction_type_failed type=%s error=%s",
                        etype,
                        exc,
                        exc_info=True,
                    )

        # Return insights in the canonical FOCUSED_EXTRACTION_TYPES order so
        # downstream summary building is deterministic regardless of thread finish order.
        finished = [results[etype] for etype in focused_types if etype in results]

        # ── Agentic field verifier: retry low-confidence / missing fields ─────
        if (
            getattr(settings, "INTELLIGENCE_AGENTIC_VERIFIER_ENABLED", True)
            and not fast_extraction_enabled()
        ):
            from apps.intelligence.services.agentic_field_verifier import (
                run as agentic_verify,
            )
            from apps.intelligence.services.summary_postprocess import (
                build_spec_check_fields_from_insights,
            )
            spec_preview = build_spec_check_fields_from_insights(finished)
            finished = agentic_verify(
                insights=finished,
                chunks=chunks,
                spec=spec_preview,
                document=document,
                total_pages=total_pages,
                page_texts=page_texts,
            )

        return finished

    @staticmethod
    @transaction.atomic
    def _sync_source_references(document: Document, insight: ExtractedInsight) -> None:
        version = getattr(document, "version", None)
        for item in insight.payload.get("items", []):
            SourceReference.objects.create(
                document=document,
                document_version=version,
                reference_kind=SourceReferenceKind.EXTRACTION,
                source_document_label=document.original_filename,
                page=item.get("page"),
                section=item.get("section", "")[:512],
                section_path=(item.get("section_path") or "")[:1024],
                excerpt=item.get("source_text", "")[:2000],
                confidence=item.get("confidence"),
                chunk_id=insight.chunk_ids[0] if insight.chunk_ids else "",
                metadata={
                    "extraction_type": insight.extraction_type,
                    "requirement": item.get("requirement", "")[:500],
                    "insight_id": str(insight.id),
                },
            )
