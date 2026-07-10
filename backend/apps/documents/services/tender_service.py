import logging
import re
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ValidationServiceError
from apps.documents.access import tenders_queryset_for_user, user_is_admin
from apps.documents.choices import DocumentVersionType, TenderStatus
from apps.documents.models import Document, DocumentVersion, Tender

logger = logging.getLogger(__name__)


class TenderUploadContext:
    def __init__(
        self,
        *,
        tender_id: UUID | None = None,
        tender_reference: str | None = None,
        tender_title: str | None = None,
        organization: str = "",
        version_type: str = DocumentVersionType.ORIGINAL,
        version_label: str | None = None,
        supersedes_version_id: UUID | None = None,
        notes: str = "",
    ):
        self.tender_id = tender_id
        self.tender_reference = tender_reference
        self.tender_title = tender_title
        self.organization = organization
        self.version_type = version_type
        self.version_label = version_label
        self.supersedes_version_id = supersedes_version_id
        self.notes = notes


class TenderService:
    @staticmethod
    def normalize_reference(reference: str) -> str:
        ref = reference.strip().upper()
        ref = re.sub(r"\s+", "-", ref)
        return ref[:128]

    @staticmethod
    def get_tender(tender_id: UUID, user=None) -> Tender:
        try:
            tender = Tender.objects.get(pk=tender_id)
        except Tender.DoesNotExist as exc:
            raise ValidationServiceError("Tender not found.", code="tender_not_found") from exc

        if user is not None and not user_is_admin(user):
            owns_doc = Document.objects.filter(
                version__tender=tender,
                uploaded_by=user,
            ).exists()
            if not owns_doc:
                raise ValidationServiceError("Tender not found.", code="tender_not_found")
        return tender

    @staticmethod
    def list_tenders(user=None):
        return tenders_queryset_for_user(user)

    @staticmethod
    @transaction.atomic
    def resolve_tender(ctx: TenderUploadContext, user=None) -> Tender:
        if ctx.tender_id:
            return TenderService.get_tender(ctx.tender_id, user=user)

        if not ctx.tender_reference:
            raise ValidationServiceError(
                "tender_reference or tender_id is required for versioned uploads.",
                code="missing_tender_reference",
            )

        reference = TenderService.normalize_reference(ctx.tender_reference)
        tender, created = Tender.objects.get_or_create(
            reference_code=reference,
            defaults={
                "title": ctx.tender_title or reference,
                "organization": ctx.organization,
                "status": TenderStatus.ACTIVE,
            },
        )
        if created:
            logger.info("tender_created reference=%s id=%s", reference, tender.id)
        return tender

    @staticmethod
    @transaction.atomic
    def attach_document_version(
        tender: Tender,
        document: Document,
        ctx: TenderUploadContext,
    ) -> DocumentVersion:
        supersedes = None
        if ctx.supersedes_version_id:
            try:
                supersedes = DocumentVersion.objects.get(
                    pk=ctx.supersedes_version_id,
                    tender=tender,
                )
            except DocumentVersion.DoesNotExist as exc:
                raise ValidationServiceError(
                    "supersedes_version_id not found for this tender.",
                    code="invalid_supersedes_version",
                ) from exc

        next_sequence = (
            DocumentVersion.objects.filter(tender=tender)
            .order_by("-version_sequence")
            .values_list("version_sequence", flat=True)
            .first()
            or 0
        ) + 1

        version_label = ctx.version_label or TenderService._default_version_label(
            ctx.version_type, next_sequence
        )

        DocumentVersion.objects.filter(tender=tender, is_current=True).update(is_current=False)

        version = DocumentVersion.objects.create(
            tender=tender,
            document=document,
            version_type=ctx.version_type,
            version_label=version_label,
            version_sequence=next_sequence,
            supersedes=supersedes,
            is_current=True,
            published_at=timezone.now(),
            notes=ctx.notes,
            metadata={
                "supersedes_version_id": str(supersedes.id) if supersedes else None,
            },
        )

        document.metadata = {
            **document.metadata,
            "tender_id": str(tender.id),
            "tender_reference": tender.reference_code,
            "version_id": str(version.id),
            "version_label": version_label,
            "version_type": ctx.version_type,
        }
        document.save(update_fields=["metadata", "updated_at"])

        logger.info(
            "document_version_created tender=%s version=%s document=%s",
            tender.reference_code,
            version_label,
            document.id,
        )
        return version

    @staticmethod
    def _default_version_label(version_type: str, sequence: int) -> str:
        labels = {
            DocumentVersionType.ORIGINAL: f"Version {sequence}",
            DocumentVersionType.REVISION: f"Revision {sequence}",
            DocumentVersionType.CORRIGENDUM: f"Corrigendum {chr(64 + sequence) if sequence <= 26 else sequence}",
            DocumentVersionType.ADDENDUM: f"Addendum {sequence}",
            DocumentVersionType.CLARIFICATION: f"Clarification {sequence}",
            DocumentVersionType.ANNEXURE: f"Annexure {sequence}",
        }
        return labels.get(version_type, f"Document {sequence}")
