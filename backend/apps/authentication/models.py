from django.conf import settings
from django.db import models


class UserAccountMeta(models.Model):
    """Admin-visible password copy for user management (not used for authentication)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_meta",
    )
    admin_visible_password = models.CharField(max_length=128, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user account meta"
        verbose_name_plural = "user account meta"

    def __str__(self) -> str:
        return f"Account meta for {self.user_id}"
