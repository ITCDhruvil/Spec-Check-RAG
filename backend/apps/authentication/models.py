from django.conf import settings
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "admin", "Admin"
    MANAGER = "manager", "Manager"
    TEAM_LEADER = "team_leader", "Team Leader"
    USER = "user", "General User"


# Roles that may see all documents, the feedback page, and the insights dashboard.
MANAGEMENT_ROLES = frozenset({UserRole.ADMIN, UserRole.MANAGER, UserRole.TEAM_LEADER})


class UserAccountMeta(models.Model):
    """Admin-visible password copy + role for user management (not used for authentication)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_meta",
    )
    admin_visible_password = models.CharField(max_length=128, blank=True, default="")
    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.USER,
        db_index=True,
    )
    # Per-user override of the Manual keyword map. Empty = use seeded defaults.
    keyword_fields = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user account meta"
        verbose_name_plural = "user account meta"

    def __str__(self) -> str:
        return f"Account meta for {self.user_id}"
