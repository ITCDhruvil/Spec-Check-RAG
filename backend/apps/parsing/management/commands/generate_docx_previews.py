"""Generate PDF previews for existing DOCX documents."""

from django.core.management.base import BaseCommand

from apps.documents.models import Document
from apps.parsing.services.docx_preview_service import (
    _resolve_soffice_path,
    attach_docx_preview_metadata,
)


class Command(BaseCommand):
    help = "Convert existing DOCX uploads to cached preview PDFs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--document-id",
            dest="document_id",
            help="Only process this document UUID.",
        )

    def handle(self, *args, **options):
        soffice = _resolve_soffice_path()
        if soffice:
            self.stdout.write(f"Using LibreOffice: {soffice}")
        else:
            self.stdout.write(
                self.style.WARNING(
                    "LibreOffice not found. Set LIBREOFFICE_PATH or install LibreOffice."
                )
            )

        qs = Document.objects.filter(original_filename__iendswith=".docx")
        if options.get("document_id"):
            qs = qs.filter(pk=options["document_id"])

        ok_count = 0
        for document in qs.order_by("created_at"):
            success = attach_docx_preview_metadata(document)
            if success:
                ok_count += 1
                self.stdout.write(self.style.SUCCESS(f"OK {document.id} {document.original_filename}"))
            else:
                self.stdout.write(
                    self.style.ERROR(f"FAIL {document.id} {document.original_filename}")
                )

        self.stdout.write(f"Done: {ok_count}/{qs.count()} previews generated.")
