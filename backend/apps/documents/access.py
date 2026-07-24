from django.contrib.auth.models import AbstractBaseUser

from apps.authentication.permissions import is_admin_user, is_management_user
from apps.documents.models import Document, Tender


def user_is_admin(user: AbstractBaseUser | None) -> bool:
    return bool(user and user.is_authenticated and is_admin_user(user))


def user_is_management(user: AbstractBaseUser | None) -> bool:
    """Admin / manager / team leader — full document visibility."""
    return bool(user and user.is_authenticated and is_management_user(user))


def documents_queryset_for_user(user: AbstractBaseUser | None):
    qs = Document.objects.select_related("version__tender")
    if user and user.is_authenticated and not user_is_management(user):
        qs = qs.filter(uploaded_by=user)
    return qs


def tenders_queryset_for_user(user: AbstractBaseUser | None):
    qs = Tender.objects.prefetch_related("document_versions__document")
    if user and user.is_authenticated and not user_is_management(user):
        qs = qs.filter(document_versions__document__uploaded_by=user).distinct()
    return qs


def user_can_access_document(user: AbstractBaseUser | None, document: Document) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user_is_management(user):
        return True
    return document.uploaded_by_id == user.id
