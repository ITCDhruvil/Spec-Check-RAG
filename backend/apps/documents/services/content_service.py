import logging

from apps.documents.models import Document, DocumentExtractedContent

logger = logging.getLogger(__name__)

EMPTY_PAGE_MAP: list = []
EMPTY_LAYOUT: dict = {"blocks": [], "tables": [], "headers": []}
EMPTY_SECTIONS: list = []


class DocumentContentService:
    """Scaffold for Phase 2 raw text, page mapping, and section hierarchy."""

    @staticmethod
    def ensure_scaffold(document: Document) -> DocumentExtractedContent:
        content, created = DocumentExtractedContent.objects.get_or_create(
            document=document,
            defaults={
                "raw_text": "",
                "page_map": EMPTY_PAGE_MAP,
                "layout_structure": EMPTY_LAYOUT,
                "section_hierarchy": EMPTY_SECTIONS,
                "content_ready": False,
            },
        )
        if created:
            logger.info("content_scaffold_created document_id=%s", document.id)
        return content

    @staticmethod
    def content_summary(document: Document) -> dict:
        try:
            content = document.extracted_content
        except DocumentExtractedContent.DoesNotExist:
            return {
                "content_ready": False,
                "raw_text_length": 0,
                "page_count": 0,
                "section_count": 0,
            }
        sections = content.section_hierarchy or []
        return {
            "content_ready": content.content_ready,
            "raw_text_length": len(content.raw_text or ""),
            "page_count": len(content.page_map or []),
            "section_count": DocumentContentService._count_sections(sections),
            "pipeline_version": content.pipeline_version,
        }

    @staticmethod
    def _count_sections(sections: list) -> int:
        count = 0
        for section in sections:
            count += 1
            count += DocumentContentService._count_sections(section.get("children", []))
        return count
