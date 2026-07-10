"""
Generate a layout-faithful PDF preview for uploaded DOCX files.

Uses LibreOffice headless when LIBREOFFICE_PATH is set, or docx2pdf on Windows
(Microsoft Word required). The preview PDF is served to the existing PDF.js viewer.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings

from apps.documents.models import Document
from apps.documents.utils.paths import get_document_absolute_path

logger = logging.getLogger(__name__)

_WINDOWS_SOFFICE_CANDIDATES = (
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
)


def _resolve_soffice_path() -> str:
    configured = (getattr(settings, "LIBREOFFICE_PATH", None) or "").strip()
    if configured:
        if Path(configured).is_file() or configured == "soffice":
            return configured
        logger.warning("libreoffice_configured_path_missing path=%s", configured)

    if sys.platform == "win32":
        for candidate in _WINDOWS_SOFFICE_CANDIDATES:
            if candidate.is_file():
                return str(candidate)

    from_path = shutil.which("soffice")
    if from_path:
        return from_path

    return ""


def preview_pdf_relative_path(document_id) -> str:
    return f"documents/previews/{document_id}.pdf"


def _resolved_media_root() -> Path:
    root = Path(settings.MEDIA_ROOT)
    if not root.is_absolute():
        root = Path(settings.BASE_DIR) / root
    return root.resolve()


def preview_pdf_absolute_path(document_id) -> Path:
    return _resolved_media_root() / preview_pdf_relative_path(document_id)


def _convert_with_libreoffice(source: Path, destination: Path) -> bool:
    soffice = _resolve_soffice_path()
    if not soffice:
        return False
    if not Path(soffice).is_file() and soffice != "soffice":
        logger.warning("libreoffice_not_found path=%s", soffice)
        return False

    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Temp dir on same drive as destination (Windows cannot os.replace across drives).
    with tempfile.TemporaryDirectory(dir=str(destination.parent)) as tmp:
        out_dir = Path(tmp)
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(source.resolve()),
        ]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                timeout=getattr(settings, "DOCX_PREVIEW_TIMEOUT_SEC", 120),
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            stderr = getattr(exc, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            logger.warning("libreoffice_convert_failed error=%s stderr=%s", exc, stderr)
            return False

        produced = out_dir / f"{source.stem}.pdf"
        if not produced.is_file():
            pdfs = sorted(out_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
            produced = pdfs[0] if pdfs else None
        if not produced or not produced.is_file() or produced.stat().st_size == 0:
            logger.warning(
                "libreoffice_no_output source=%s stdout=%s stderr=%s",
                source,
                result.stdout.decode("utf-8", errors="replace") if result.stdout else "",
                result.stderr.decode("utf-8", errors="replace") if result.stderr else "",
            )
            return False

        try:
            shutil.copy2(produced, destination)
        except OSError as exc:
            logger.warning("libreoffice_copy_failed error=%s", exc)
            return False
    return destination.is_file() and destination.stat().st_size > 0


def _convert_with_docx2pdf(source: Path, destination: Path) -> bool:
    try:
        from docx2pdf import convert
    except ImportError:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        convert(str(source), str(destination))
    except Exception as exc:
        logger.warning("docx2pdf_convert_failed error=%s", exc)
        return False
    return destination.is_file() and destination.stat().st_size > 0


def convert_docx_to_pdf(source: Path, destination: Path) -> bool:
    """Return True when a PDF was written to destination."""
    if not source.is_file():
        return False

    if _convert_with_libreoffice(source, destination):
        return True

    use_word = getattr(settings, "DOCX_PREVIEW_USE_WORD", sys.platform == "win32")
    if use_word and _convert_with_docx2pdf(source, destination):
        return True

    return False


def generate_docx_preview_pdf(document: Document) -> Path | None:
    if not getattr(settings, "DOCX_PREVIEW_ENABLED", True):
        return None
    if not document.original_filename.lower().endswith(".docx"):
        return None

    source = get_document_absolute_path(document)
    destination = preview_pdf_absolute_path(document.id)
    if destination.is_file() and destination.stat().st_size > 0:
        return destination

    if not convert_docx_to_pdf(source, destination):
        return None

    logger.info(
        "docx_preview_generated document_id=%s bytes=%s",
        document.id,
        destination.stat().st_size,
    )
    return destination


def attach_docx_preview_metadata(document: Document) -> bool:
    """Build preview PDF and store path on document.metadata. Returns success."""
    pdf_path = generate_docx_preview_pdf(document)
    if not pdf_path:
        meta = dict(document.metadata or {})
        meta["preview_pdf_ready"] = False
        document.metadata = meta
        document.save(update_fields=["metadata", "updated_at"])
        return False

    rel = preview_pdf_relative_path(document.id)
    document.metadata = {
        **(document.metadata or {}),
        "preview_pdf_path": rel,
        "preview_pdf_ready": True,
    }
    document.save(update_fields=["metadata", "updated_at"])
    return True


def get_preview_pdf_path(document: Document) -> Path | None:
    """Return cached preview PDF if it exists on disk."""
    standard = preview_pdf_absolute_path(document.id)
    if standard.is_file() and standard.stat().st_size > 0:
        return standard

    meta = document.metadata or {}
    rel = meta.get("preview_pdf_path")
    if rel:
        path = _resolved_media_root() / str(rel)
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None
