import logging
from pathlib import Path

from django.conf import settings

from apps.documents.services.content_service import DocumentContentService
from apps.documents.utils.paths import get_document_absolute_path
from apps.processing.choices import PipelineStage
from apps.processing.models import ProcessingJob
from apps.processing.services.job_service import ProcessingJobService

logger = logging.getLogger(__name__)


class DocumentPipelineService:
    """
    Phase 1 intake pipeline: validate stored file, scaffold content storage.
    Phase 2+ adds OCR → sectioning → chunking → embedding → extraction → summary stages.
    """

    @staticmethod
    def run_intake_validation(job: ProcessingJob) -> dict:
        ProcessingJobService.transition_to(job, PipelineStage.INTAKE_PROCESSING)

        document = job.document
        file_path = get_document_absolute_path(document)

        if not file_path.exists():
            raise FileNotFoundError(f"Stored file missing: {file_path}")

        if not file_path.is_file():
            raise ValueError("Stored path is not a regular file.")

        actual_size = file_path.stat().st_size
        if actual_size != document.size_bytes:
            logger.warning(
                "size_mismatch document_id=%s expected=%s actual=%s",
                document.id,
                document.size_bytes,
                actual_size,
            )

        content = DocumentContentService.ensure_scaffold(document)
        content_summary = DocumentContentService.content_summary(document)

        pipeline_metadata = {
            "pipeline_version": "1.1.0",
            "stages_completed": list(job.completed_stages or []) + [PipelineStage.INTAKE_COMPLETED],
            "storage_verified": True,
            "content_scaffold": content_summary,
            "media_root": str(settings.MEDIA_ROOT),
            "ready_for_ocr": True,
        }

        document.metadata = {
            **document.metadata,
            "processing": pipeline_metadata,
        }
        document.save(update_fields=["metadata", "updated_at"])

        ProcessingJobService.complete_stage(job, PipelineStage.INTAKE_COMPLETED)

        logger.info(
            "intake_validation_complete job_id=%s document_id=%s",
            job.id,
            document.id,
        )
        return pipeline_metadata

    @staticmethod
    def run_document_parsing(job: ProcessingJob) -> dict:
        from apps.parsing.services.parsing_service import DocumentParsingService

        ProcessingJobService.transition_to(job, PipelineStage.PARSING_PROCESSING)
        summary = DocumentParsingService.run_parsing(job)
        ProcessingJobService.complete_stage(job, PipelineStage.PARSING_COMPLETED)

        document = job.document
        document.metadata = {
            **document.metadata,
            "parsing": summary,
        }
        document.save(update_fields=["metadata", "updated_at"])

        logger.info("document_parsing_complete job_id=%s document_id=%s", job.id, document.id)
        return summary

    @staticmethod
    def run_chunking_and_indexing(job: ProcessingJob) -> dict:
        """Phase 2+3: build chunks and index embeddings after parse (RAG-ready before summary)."""
        from apps.chat.services.index_service import VectorIndexService
        from apps.intelligence.services.chunking_service import ChunkingService

        document = job.document

        ProcessingJobService.transition_to(job, PipelineStage.CHUNKING_PROCESSING)
        chunks = ChunkingService.build_chunks(document)
        ProcessingJobService.complete_stage(job, PipelineStage.CHUNKING_COMPLETED)

        ProcessingJobService.transition_to(job, PipelineStage.EMBEDDING_PROCESSING)
        index_record = VectorIndexService.index_document(document, force=True)
        ProcessingJobService.complete_stage(job, PipelineStage.EMBEDDING_COMPLETED)

        summary = {
            "chunk_count": len(chunks),
            "vector_backend": index_record.vector_backend,
            "embedding_model": index_record.embedding_model,
            "indexed_at": index_record.indexed_at.isoformat(),
            "collection_name": index_record.collection_name,
        }

        document.metadata = {
            **document.metadata,
            "chunking_indexing": summary,
        }
        document.save(update_fields=["metadata", "updated_at"])

        logger.info(
            "chunking_indexing_complete job_id=%s document_id=%s chunks=%s backend=%s",
            job.id,
            document.id,
            len(chunks),
            index_record.vector_backend,
        )
        return summary
