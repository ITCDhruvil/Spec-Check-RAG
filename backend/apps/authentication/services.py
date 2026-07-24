from django.contrib.auth import get_user_model

from apps.authentication.models import UserAccountMeta

User = get_user_model()


def set_admin_visible_password(user: User, password: str) -> UserAccountMeta:
    meta, _ = UserAccountMeta.objects.update_or_create(
        user=user,
        defaults={"admin_visible_password": password},
    )
    # Keep the in-memory relation in sync for serializers in the same request.
    user.account_meta = meta
    return meta


def clear_admin_visible_password(user: User) -> None:
    UserAccountMeta.objects.filter(user=user).update(admin_visible_password="")
    if hasattr(user, "account_meta"):
        try:
            user.account_meta.admin_visible_password = ""
        except UserAccountMeta.DoesNotExist:
            pass


def get_admin_visible_password(user: User) -> str:
    password = (
        UserAccountMeta.objects.filter(user_id=user.pk)
        .values_list("admin_visible_password", flat=True)
        .first()
    )
    return password or ""


def set_user_role(user: User, role: str) -> UserAccountMeta:
    meta, _ = UserAccountMeta.objects.update_or_create(
        user=user,
        defaults={"role": role},
    )
    user.account_meta = meta
    return meta


def get_keyword_fields(user: User) -> list:
    """User's Manual keyword map, falling back to seeded defaults."""
    from apps.intelligence.services.keyword_defaults import default_keyword_fields

    meta = getattr(user, "account_meta", None)
    stored = meta.keyword_fields if meta else None
    if stored:
        return stored
    return default_keyword_fields()


def set_keyword_fields(user: User, fields: list) -> UserAccountMeta:
    meta, _ = UserAccountMeta.objects.update_or_create(
        user=user,
        defaults={"keyword_fields": fields},
    )
    user.account_meta = meta
    return meta


def reload_user_for_serialization(user: User) -> User:
    return User.objects.select_related("account_meta").get(pk=user.pk)
