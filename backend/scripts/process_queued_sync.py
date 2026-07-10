"""Process documents stuck in queued (Celery worker down on Windows)."""
import sys

from apps.documents.models import Document
from apps.processing.choices import PipelineStage
from apps.processing.models import ProcessingJob
from apps.processing.tasks import process_document_task


def main() -> int:
    pending = Document.objects.filter(status=PipelineStage.QUEUED).order_by("created_at")
    if not pending.exists():
        print("No queued documents.")
        return 0

    for doc in pending:
        job = ProcessingJob.objects.filter(document=doc).order_by("-created_at").first()
        if not job:
            print(f"SKIP {doc.original_filename}: no job")
            continue
        print(f"Processing {doc.original_filename} ({doc.id})...")
        process_document_task.apply(args=[str(job.id)])
        doc.refresh_from_db()
        print(f"  -> {doc.status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
