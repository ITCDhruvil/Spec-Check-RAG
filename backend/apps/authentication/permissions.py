from django.conf import settings
from rest_framework.permissions import BasePermission

from apps.authentication.models import MANAGEMENT_ROLES, UserRole


def role_of(user) -> str:
    """Resolve the user's role. The configured admin email is always admin."""
    if not user or not user.is_authenticated:
        return ""
    admin_email = getattr(settings, "ADMIN_EMAIL", "admin@itcube.net").lower()
    if user.email.lower() == admin_email:
        return UserRole.ADMIN
    meta = getattr(user, "account_meta", None)
    return meta.role if meta else UserRole.USER


def is_admin_user(user) -> bool:
    return role_of(user) == UserRole.ADMIN


def is_management_user(user) -> bool:
    """Admin, manager, or team leader — see all docs, feedback, insights."""
    return role_of(user) in MANAGEMENT_ROLES


class IsAdminUser(BasePermission):
    """Only admins may access user management."""

    message = "Admin access required."

    def has_permission(self, request, view):
        return is_admin_user(request.user)


class IsManagementUser(BasePermission):
    """Admin, manager, or team leader."""

    message = "Management access required."

    def has_permission(self, request, view):
        return is_management_user(request.user)
