from copy import deepcopy

from django.core.management.base import BaseCommand

from apps.intelligence.models import ExtractedInsight, GeneratedSummary
from apps.intelligence.services.summary_postprocess import reapply_summary_citations


class Command(BaseCommand):
    help = "Persist verbatim-only citations on stored summaries (drops paraphrased quotes)."

    def add_arguments(self, parser):
        parser.add_argument("--document-id", type=str, help="Single document UUID")
        parser.add_argument(
            "--all-current",
            action="store_true",
            help="Update every current completed summary",
        )

    def handle(self, *args, **options):
        doc_id = options.get("document_id")
        all_current = options.get("all_current")

        if not doc_id and not all_current:
            self.stderr.write("Pass --document-id=<uuid> or --all-current")
            return

        qs = GeneratedSummary.objects.filter(is_current=True, status="completed")
        if doc_id:
            qs = qs.filter(document_id=doc_id)

        updated = 0
        for summary in qs.select_related("document"):
            insights = list(
                ExtractedInsight.objects.filter(generated_summary=summary)
            )
            if not insights:
                insights = list(
                    ExtractedInsight.objects.filter(document_id=summary.document_id)
                )
            payload = deepcopy(summary.summary_json or {})
            before = str(payload)
            reapply_summary_citations(payload, insights, summary.document)
            if str(payload) != before:
                summary.summary_json = payload
                summary.save(update_fields=["summary_json", "updated_at"])
                updated += 1
                self.stdout.write(
                    f"Updated summary {summary.id} ({summary.document.original_filename})"
                )

        self.stdout.write(self.style.SUCCESS(f"Done. {updated} summary(s) updated."))
