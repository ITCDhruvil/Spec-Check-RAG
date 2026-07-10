from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.authentication.services import set_admin_visible_password
from apps.authentication.utils import generate_password

User = get_user_model()


class Command(BaseCommand):
    help = "Ensure the platform admin user exists (admin@itcube.net)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Set a specific admin password (min 10 chars). If omitted, a random password is generated.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Reset password for an existing admin user.",
        )

    def handle(self, *args, **options):
        admin_email = settings.ADMIN_EMAIL.lower()
        username = "admin"
        password = options.get("password") or generate_password()

        try:
            user = User.objects.get(email__iexact=admin_email)
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=username,
                email=admin_email,
                password=password,
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            set_admin_visible_password(user, password)
            self.stdout.write(self.style.SUCCESS(f"Admin user created: {admin_email}"))
            self.stdout.write(f"Password: {password}")
            return

        user.username = user.username or username
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True

        if options.get("reset_password") or options.get("password"):
            user.set_password(password)
            user.save()
            set_admin_visible_password(user, password)
            action = "updated"
            self.stdout.write(self.style.SUCCESS(f"Admin user {action}: {admin_email}"))
            self.stdout.write(f"Password: {password}")
        else:
            self.stdout.write(self.style.SUCCESS(f"Admin user already exists: {admin_email}"))
