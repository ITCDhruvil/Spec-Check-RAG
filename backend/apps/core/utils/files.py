import logging
import re
import uuid
from pathlib import Path

from django.conf import settings

from apps.core.exceptions import ValidationServiceError

logger = logging.getLogger(__name__)

try:
    import magic
except ImportError:
    magic = None  # type: ignore


def sanitize_filename(name: str) -> str:
    """Strip path components and unsafe characters from user-supplied names."""
    base = Path(name).name
    safe = re.sub(r"[^\w.\-]", "_", base, flags=re.ASCII)
    return safe[:255] if safe else "document"


def generate_storage_name(extension: str) -> str:
    ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
    return f"{uuid.uuid4().hex}{ext}"


def validate_upload_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationServiceError(
            f"File type '{ext}' is not allowed. Allowed: {', '.join(sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))}",
            code="invalid_file_type",
        )
    return ext


def validate_upload_size(size: int) -> None:
    if size <= 0:
        raise ValidationServiceError("File is empty.", code="empty_file")
    if size > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise ValidationServiceError(
            f"File exceeds maximum size of {max_mb} MB.",
            code="file_too_large",
        )


def detect_mime_type(file_path: Path) -> str:
    if magic is None:
        return ""
    mime = magic.Magic(mime=True)
    return mime.from_file(str(file_path))


def validate_mime_type(file_path: Path, expected_ext: str) -> str:
    ext_mime_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if magic is None:
        logger.warning(
            "python-magic unavailable; using extension-based MIME only path=%s",
            file_path,
        )
        return ext_mime_map.get(expected_ext, "")

    detected = detect_mime_type(file_path)
    if not detected:
        return ext_mime_map.get(expected_ext, "")

    allowed = settings.ALLOWED_UPLOAD_MIME_TYPES
    if detected not in allowed:
        raise ValidationServiceError(
            f"File content type '{detected}' does not match allowed document types.",
            code="invalid_mime_type",
        )

    expected_mime = ext_mime_map.get(expected_ext)
    if expected_mime and detected != expected_mime:
        raise ValidationServiceError(
            "File extension does not match file content.",
            code="mime_extension_mismatch",
        )
    return detected


def ensure_upload_directory() -> Path:
    path = settings.DOCUMENT_UPLOAD_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path
