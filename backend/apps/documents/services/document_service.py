import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from apps.core.exceptions import ServiceError, ValidationServiceError
from apps.core.utils.files import (
    ensure_upload_directory,
    generate_storage_name,
    sanitize_filename,
    validate_mime_type,
    validate_upload_extension,
    validate_upload_size,
)
from apps.chat.services.chroma_service import ChromaVectorStore
from apps.documents.access import documents_queryset_for_user, user_can_access_document
from apps.documents.models import Document, DocumentVersion, Tender
from apps.documents.services.content_service import DocumentContentService
from apps.documents.services.tender_service import TenderService, TenderUploadContext
from apps.documents.utils.paths import get_document_absolute_path
from apps.processing.choices import PipelineStage
from apps.processing.services.job_service import ProcessingJobService

logger = logging.getLogger(__name__)


class DuplicateDocumentError(ServiceError):
    """Identical file content already uploaded."""

    def __init__(self, existing: "Document"):
        self.existing = existing
        super().__init__(
            "This document has already been uploaded.",
            code="duplicate_document",
            status_code=409,
        )


class DocumentService:
    """Business logic for document upload and retrieval."""

    @staticmethod
    def upload(
        file: UploadedFile,
        *,
        uploaded_by=None,
        tender_id: UUID | None = None,
        tender_reference: str | None = None,
        tender_title: str | None = None,
        organization: str = "",
        version_type: str | None = None,
        version_label: str | None = None,
        supersedes_version_id: UUID | None = None,
        version_notes: str = "",
    ) -> Document:
        if not file or not file.name:
            raise ValidationServiceError("No file provided.", code="missing_file")

        resolved_reference = tender_reference
        if not tender_id and not resolved_reference:
            resolved_reference = f"AUTO-{uuid4().hex[:10].upper()}"

        ctx = TenderUploadContext(
            tender_id=tender_id,
            tender_reference=resolved_reference,
            tender_title=tender_title or resolved_reference,
            organization=organization,
            version_type=version_type or "original",
            version_label=version_label,
            supersedes_version_id=supersedes_version_id,
            notes=version_notes,
        )

        original_name = sanitize_filename(file.name)
        extension = validate_upload_extension(original_name)
        validate_upload_size(file.size)

        upload_dir = ensure_upload_directory()
        stored_name = generate_storage_name(extension)
        destination = upload_dir / stored_name

        try:
            with destination.open("wb") as dest:
                digest = hashlib.sha256()
                for chunk in file.chunks():
                    digest.update(chunk)
                    dest.write(chunk)
        except OSError as exc:
            logger.exception("file_write_failed name=%s", stored_name)
            raise ServiceError(
                "Failed to store uploaded file.",
                code="storage_error",
                status_code=500,
            ) from exc

        mime_type = validate_mime_type(destination, extension)
        checksum = digest.hexdigest()
        relative_path = str(destination.relative_to(upload_dir.parent))

        # Duplicate guard: identical file content already uploaded → reject with
        # a pointer to the existing document instead of creating a new version.
        existing = (
            Document.objects.filter(checksum_sha256=checksum)
            .order_by("-created_at")
            .first()
        )
        if existing is not None:
            try:
                destination.unlink()
            except OSError:
                pass
            raise DuplicateDocumentError(existing)

        with transaction.atomic():
            tender = TenderService.resolve_tender(ctx, user=uploaded_by)
            document = Document.objects.create(
                original_filename=original_name,
                stored_filename=stored_name,
                file_path=relative_path,
                mime_type=mime_type,
                size_bytes=file.size,
                status=PipelineStage.UPLOADED,
                checksum_sha256=checksum,
                uploaded_by=uploaded_by,
                metadata={
                    "extension": extension,
                    "upload_source": "api",
                },
            )
            TenderService.attach_document_version(tender, document, ctx)
            DocumentContentService.ensure_scaffold(document)
            job = ProcessingJobService.create_job(document)
            # Enqueue only after commit: keeps broker I/O out of the DB
            # transaction and guarantees the worker sees the committed rows.
            transaction.on_commit(lambda: ProcessingJobService.enqueue_job(job))

        logger.info(
            "document_uploaded document_id=%s tender=%s filename=%s",
            document.id,
            tender.reference_code,
            original_name,
        )
        return document

    @staticmethod
    def get_document(document_id, user=None) -> Document:
        try:
            document = (
                Document.objects.select_related("version__tender", "extracted_content")
                .get(pk=document_id)
            )
        except Document.DoesNotExist as exc:
            raise ValidationServiceError(
                "Document not found.",
                code="document_not_found",
            ) from exc

        if user is not None and not user_can_access_document(user, document):
            raise ValidationServiceError(
                "Document not found.",
                code="document_not_found",
            )
        return document

    @staticmethod
    def list_documents(user=None):
        return documents_queryset_for_user(user)

    @staticmethod
    def delete_document(document_id, user=None) -> None:
        """Remove document, related DB rows (CASCADE), vectors, and stored file."""
        document = DocumentService.get_document(document_id, user=user)
        doc_id = str(document.id)
        file_path = get_document_absolute_path(document)
        version = getattr(document, "version", None)
        tender_id = version.tender_id if version else None

        with transaction.atomic():
            ChromaVectorStore.delete_document_vectors(doc_id)
            document.delete()
            if tender_id and not DocumentVersion.objects.filter(tender_id=tender_id).exists():
                Tender.objects.filter(pk=tender_id).delete()

        if file_path.exists():
            try:
                file_path.unlink()
            except OSError as exc:
                logger.warning(
                    "document_file_delete_failed document_id=%s path=%s error=%s",
                    doc_id,
                    file_path,
                    exc,
                )

        logger.info("document_deleted document_id=%s", doc_id)

    @staticmethod
    def get_absolute_path(document: Document) -> Path:
        return get_document_absolute_path(document)

    @staticmethod
    def _compute_checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()
