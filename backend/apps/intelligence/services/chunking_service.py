import logging

from django.conf import settings
from django.db import transaction

from apps.documents.models import Document
from apps.intelligence.models import DocumentChunk
from apps.intelligence.services.chunking_strategy import (
    build_section_chunks,
    build_table_chunks,
    consolidate_sections,
    dedupe_table_against_sections,
)
from apps.intelligence.services.citation_service import extract_section_prefix
from apps.parsing.choices import ParsingStatus
from apps.parsing.models import DocumentSection, ParsedDocument

logger = logging.getLogger(__name__)

# Section keywords → extraction relevance (for metadata tags)
SECTION_TAGS = {
    "eligibility": ["eligibility", "qualification", "bidder", "pre-qualif"],
    "deadline": ["deadline", "submission", "closing", "due date", "validity", "etender"],
    "technical": [
        "technical", "specification", "sla", "architecture", "integration",
        "security", "guard", "escort", "manpower", "deployment", "training",
    ],
    "scope": [
        "scope", "work", "deliverable", "statement of work", "implementation",
        "security service", "transport", "guarding", "personnel", "operational",
    ],
    "payment": ["payment", "commercial", "price", "invoice", "guarantee", "bond"],
    "risk": ["penalty", "liquidated", "termination", "liability", "reject", "compliance"],
    "documents": ["annexure", "appendix", "form", "mandatory", "compliance matrix"],
    "evaluation": ["evaluation", "weightage", "scoring", "criteria", "marks"],
    "support": ["support", "maintenance", "warranty", "training", "handover"],
    "general": ["general", "condition", "instruction", "provision", "governing"],
}


def _infer_tags(title: str) -> list[str]:
    lower = title.lower()
    tags = []
    for tag, keywords in SECTION_TAGS.items():
        if any(k in lower for k in keywords):
            tags.append(tag)
    return tags


class ChunkingService:
    @staticmethod
    @transaction.atomic
    def build_chunks(document: Document) -> list[DocumentChunk]:
        parsed = ParsedDocument.objects.get(
            document=document,
            parsing_status=ParsingStatus.COMPLETED,
        )
        sections = list(
            DocumentSection.objects.filter(parsed_document=parsed).order_by("section_order")
        )

        DocumentChunk.objects.filter(document=document).delete()

        logical = consolidate_sections(sections)
        table_drafts = build_table_chunks(parsed)
        section_drafts = build_section_chunks(
            logical,
            section_tags_fn=_infer_tags,
            section_prefix_fn=extract_section_prefix,
        )
        table_drafts = dedupe_table_against_sections(table_drafts, section_drafts)

        # Tables first (cover schedule) then section order
        all_drafts = table_drafts + section_drafts

        if not all_drafts and parsed.structured_text:
            from apps.intelligence.services.chunking_strategy import ChunkDraft

            max_chars = settings.INTELLIGENCE_MAX_CHUNK_CHARS
            all_drafts = [
                ChunkDraft(
                    section_title="Full Document",
                    chunk_text=parsed.structured_text[: max_chars * 3],
                    page_start=1,
                    page_end=parsed.total_pages or 1,
                    metadata={"chunk_type": "general_section", "fallback": True},
                )
            ]

        created: list[DocumentChunk] = []
        type_counts: dict[str, int] = {}

        for chunk_order, draft in enumerate(all_drafts, start=1):
            ctype = draft.metadata.get("chunk_type", "general_section")
            type_counts[ctype] = type_counts.get(ctype, 0) + 1
            chunk = DocumentChunk.objects.create(
                document=document,
                parsed_document=parsed,
                section_title=draft.section_title[:512],
                page_start=draft.page_start,
                page_end=draft.page_end,
                chunk_order=chunk_order,
                chunk_text=draft.chunk_text,
                char_count=len(draft.chunk_text),
                metadata=draft.metadata,
            )
            created.append(chunk)

        logger.info(
            "chunks_created document_id=%s count=%s types=%s",
            document.id,
            len(created),
            type_counts,
        )

        if getattr(settings, "CONTEXTUAL_RETRIEVAL_ENABLED", False) and created:
            doc_text = parsed.structured_text or ""
            if doc_text:
                from apps.intelligence.services import contextual_chunk_service

                contextual_chunk_service.generate_and_save(created, doc_text)
            else:
                logger.warning(
                    "contextual_retrieval_skip_no_text document_id=%s",
                    document.id,
                )

        return created
