from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.documents.models import Document

User = get_user_model()


class Command(BaseCommand):
    help = "Assign existing documents without an owner to the admin user."

    def handle(self, *args, **options):
        admin_email = settings.ADMIN_EMAIL.lower()
        try:
            admin = User.objects.get(email__iexact=admin_email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Admin user not found: {admin_email}"))
            return

        updated = Document.objects.filter(uploaded_by__isnull=True).update(uploaded_by=admin)
        self.stdout.write(self.style.SUCCESS(f"Assigned {updated} document(s) to {admin_email}"))
