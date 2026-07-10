from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.authentication.services import get_admin_visible_password, set_admin_visible_password
from apps.authentication.utils import generate_password

User = get_user_model()


class Command(BaseCommand):
    help = "Generate and store visible passwords for users missing admin password records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show which users would be updated without changing passwords.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0

        for user in User.objects.order_by("id"):
            if get_admin_visible_password(user):
                continue

            password = generate_password()
            updated += 1

            if dry_run:
                self.stdout.write(f"Would set password for {user.email}")
                continue

            user.set_password(password)
            user.save(update_fields=["password"])
            set_admin_visible_password(user, password)
            self.stdout.write(self.style.SUCCESS(f"{user.email}: {password}"))

        if updated == 0:
            self.stdout.write(self.style.SUCCESS("All users already have stored passwords."))
        elif dry_run:
            self.stdout.write(f"{updated} user(s) would be updated. Run without --dry-run to apply.")
