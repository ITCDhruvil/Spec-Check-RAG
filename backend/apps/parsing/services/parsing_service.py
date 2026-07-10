import logging
from pathlib import Path

from django.db import transaction

from apps.documents.models import Document
from apps.documents.services.content_service import DocumentContentService
from apps.documents.utils.paths import get_document_absolute_path
from apps.parsing.choices import ParsingStatus
from apps.parsing.models import DocumentPage, DocumentSection, ParsedDocument
from apps.parsing.parsers import parse_docx, parse_pdf
from apps.parsing.parsers.base import DocumentParseResult
from apps.processing.models import ProcessingJob

logger = logging.getLogger(__name__)


class DocumentParsingService:
    """Orchestrates document parsing and persistence."""

    @staticmethod
    def run_parsing(job: ProcessingJob) -> dict:
        document = job.document
        file_path = get_document_absolute_path(document)
        extension = Path(document.original_filename).suffix.lower()

        parsed_doc = DocumentParsingService._get_or_create_parsed(document)
        parsed_doc.parsing_status = ParsingStatus.PROCESSING
        parsed_doc.save(update_fields=["parsing_status", "updated_at"])

        try:
            if extension == ".pdf":
                result = parse_pdf(file_path)
            elif extension == ".docx":
                from django.conf import settings
                strategy = getattr(settings, "PARSING_PDF_PARSER", "docling").lower()
                if strategy == "docling":
                    from apps.parsing.parsers.docling_parser import _is_available, parse_with_docling
                    if _is_available():
                        try:
                            result = parse_with_docling(file_path)
                        except Exception as exc:
                            import logging as _logging
                            _logging.getLogger(__name__).warning(
                                "docling_docx_failed path=%s error=%s — falling back to python-docx",
                                file_path, exc,
                            )
                            result = parse_docx(file_path)
                    else:
                        result = parse_docx(file_path)
                else:
                    result = parse_docx(file_path)
            else:
                raise ValueError(f"Unsupported file type for parsing: {extension}")

            DocumentParsingService._persist_result(document, parsed_doc, result)
            DocumentParsingService._sync_extracted_content(document, result)
            if extension == ".docx":
                from apps.intelligence.services.fast_mode import defer_docx_preview

                if defer_docx_preview():
                    import threading

                    def _preview_async() -> None:
                        try:
                            from apps.parsing.services.docx_preview_service import (
                                attach_docx_preview_metadata,
                            )

                            attach_docx_preview_metadata(document)
                        except Exception as exc:
                            logger.warning(
                                "docx_preview_deferred_failed document_id=%s error=%s",
                                document.id,
                                exc,
                            )

                    threading.Thread(
                        target=_preview_async,
                        name=f"docx-preview-{document.id}",
                        daemon=True,
                    ).start()
                else:
                    try:
                        from apps.parsing.services.docx_preview_service import (
                            attach_docx_preview_metadata,
                        )

                        attach_docx_preview_metadata(document)
                    except Exception as exc:
                        logger.warning(
                            "docx_preview_skipped document_id=%s error=%s",
                            document.id,
                            exc,
                        )
            summary = DocumentParsingService._build_summary(parsed_doc, result)
            logger.info(
                "parsing_complete document_id=%s pages=%s sections=%s quality=%s",
                document.id,
                result.parsing_metadata.get("total_pages"),
                len(result.sections),
                result.parsing_quality_score,
            )
            return summary
        except Exception:
            parsed_doc.parsing_status = ParsingStatus.FAILED
            parsed_doc.save(update_fields=["parsing_status", "updated_at"])
            raise

    @staticmethod
    def _get_or_create_parsed(document: Document) -> ParsedDocument:
        parsed, _ = ParsedDocument.objects.get_or_create(
            document=document,
            defaults={"parsing_status": ParsingStatus.PENDING},
        )
        return parsed

    @staticmethod
    @transaction.atomic
    def _persist_result(
        document: Document,
        parsed_doc: ParsedDocument,
        result: DocumentParseResult,
    ) -> None:
        parsed_doc.pages.all().delete()
        parsed_doc.sections.all().delete()

        parsed_doc.parsing_status = ParsingStatus.COMPLETED
        parsed_doc.total_pages = len(result.pages)
        parsed_doc.raw_text = result.raw_text
        parsed_doc.structured_text = result.structured_text
        parsed_doc.parsing_metadata = result.parsing_metadata
        parsed_doc.parsing_quality_score = result.parsing_quality_score
        parsed_doc.save()

        DocumentPage.objects.bulk_create(
            [
                DocumentPage(
                    parsed_document=parsed_doc,
                    page_number=p.page_number,
                    extracted_text=p.extracted_text,
                    extraction_method=p.extraction_method,
                    ocr_used=p.ocr_used,
                    quality_score=p.quality_score,
                )
                for p in result.pages
            ]
        )

        DocumentSection.objects.bulk_create(
            [
                DocumentSection(
                    parsed_document=parsed_doc,
                    title=s.title,
                    content=s.content,
                    page_start=s.page_start,
                    page_end=s.page_end,
                    section_order=s.section_order,
                    level=s.level,
                    parent_section_order=s.parent_section_order,
                    section_path=s.section_path,
                )
                for s in result.sections
            ]
        )

    @staticmethod
    def _sync_extracted_content(document: Document, result: DocumentParseResult) -> None:
        content = DocumentContentService.ensure_scaffold(document)
        page_map = [
            {
                "page": p.page_number,
                "start_offset": 0,
                "end_offset": len(p.extracted_text),
                "quality_score": p.quality_score,
                "extraction_method": p.extraction_method,
                "ocr_used": p.ocr_used,
            }
            for p in result.pages
        ]
        section_hierarchy = result.parsing_metadata.get("section_hierarchy") or [
            {
                "title": s.title,
                "level": s.level,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "section_order": s.section_order,
                "section_path": s.section_path,
                "children": [],
            }
            for s in result.sections
        ]
        layout_blocks = result.parsing_metadata.get("layout_blocks") or []
        content.raw_text = result.raw_text
        content.page_map = page_map
        content.layout_structure = {
            "blocks": layout_blocks,
            "tables": result.parsing_metadata.get("tables", []),
            "headers": [s.title for s in result.sections],
        }
        content.section_hierarchy = section_hierarchy
        content.content_ready = bool(result.raw_text.strip())
        content.pipeline_version = "2.1.0"
        content.save()

    @staticmethod
    def _build_summary(parsed_doc: ParsedDocument, result: DocumentParseResult) -> dict:
        return {
            "parsed_document_id": str(parsed_doc.id),
            "parsing_status": parsed_doc.parsing_status,
            "total_pages": parsed_doc.total_pages,
            "section_count": len(result.sections),
            "parsing_quality_score": parsed_doc.parsing_quality_score,
            "ocr_pages": result.parsing_metadata.get("ocr_pages", 0),
            "tables_count": len(result.parsing_metadata.get("tables", [])),
            "layout_blocks_count": result.parsing_metadata.get("layout_blocks_count", 0),
            "parser": result.parsing_metadata.get("parser"),
        }

    @staticmethod
    def get_parsed_for_document(document_id, user=None) -> ParsedDocument:
        from apps.core.exceptions import ValidationServiceError
        from apps.documents.services.document_service import DocumentService

        DocumentService.get_document(document_id, user=user)

        try:
            return (
                ParsedDocument.objects.select_related("document")
                .prefetch_related("pages", "sections")
                .get(document_id=document_id)
            )
        except ParsedDocument.DoesNotExist as exc:
            raise ValidationServiceError(
                "Parsed document not found.",
                code="parsed_not_found",
            ) from exc
