from pathlib import Path

from django.conf import settings

from apps.documents.models import Document


def get_document_absolute_path(document: Document) -> Path:
    return Path(settings.MEDIA_ROOT) / document.file_path
