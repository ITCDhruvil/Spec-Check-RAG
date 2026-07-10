from django.conf import settings
from rest_framework.permissions import BasePermission


def is_admin_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    admin_email = getattr(settings, "ADMIN_EMAIL", "admin@itcube.net").lower()
    return user.email.lower() == admin_email


class IsAdminUser(BasePermission):
    """Only the configured admin email may access user management."""

    message = "Admin access required."

    def has_permission(self, request, view):
        return is_admin_user(request.user)
