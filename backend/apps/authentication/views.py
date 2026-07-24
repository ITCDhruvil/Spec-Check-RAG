from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.authentication.permissions import IsAdminUser, is_admin_user
from apps.authentication.serializers import (
    ChangePasswordSerializer,
    EmailTokenObtainPairSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.authentication.services import reload_user_for_serialization
from apps.authentication.utils import generate_password

User = get_user_model()


def _user_payload(user: User) -> dict:
    return UserSerializer(reload_user_for_serialization(user)).data


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = EmailTokenObtainPairSerializer


class RefreshTokenView(TokenRefreshView):
    permission_classes = [AllowAny]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "Password updated successfully.",
                "user": _user_payload(user),
            }
        )


class GeneratePasswordView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({"password": generate_password()})


class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    queryset = User.objects.select_related("account_meta").order_by("-date_joined")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return UserCreateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(_user_payload(user), status=status.HTTP_201_CREATED)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = User.objects.select_related("account_meta").all()

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(_user_payload(user))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        admin_email = settings.ADMIN_EMAIL.lower()
        if instance.email.lower() == admin_email:
            return Response(
                {"error": {"code": "forbidden", "message": "The admin account cannot be deleted."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


class ImpersonateUserView(APIView):
    """Admin-only: issue JWT tokens for another user (login as)."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            target = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "message": "User not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not target.is_active:
            return Response(
                {"error": {"code": "forbidden", "message": "Cannot sign in as a disabled user."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(target)
        update_last_login(None, target)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(target).data,
            }
        )



class KeywordFieldsView(APIView):
    """
    GET /api/v1/auth/keyword-fields/  -> the user's Manual keyword map
    PUT /api/v1/auth/keyword-fields/  -> replace it (add/remove keywords)
    POST .../reset/                   -> restore seeded defaults
    Empty stored map falls back to the seeded defaults.
    """

    permission_classes = [IsAuthenticated]

    def _resolve(self, request) -> list:
        from apps.authentication.services import get_keyword_fields

        return get_keyword_fields(request.user)

    def get(self, request):
        return Response({"fields": self._resolve(request)})

    def put(self, request):
        from apps.authentication.services import set_keyword_fields

        raw = request.data.get("fields")
        if not isinstance(raw, list):
            return Response(
                {"error": {"code": "invalid", "message": "fields must be a list."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cleaned = []
        for f in raw:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("id") or "").strip()
            label = str(f.get("label") or "").strip()
            kws = [
                str(k).strip()
                for k in (f.get("keywords") or [])
                if str(k).strip()
            ]
            if fid and label:
                cleaned.append({"id": fid, "label": label, "keywords": kws})
        set_keyword_fields(request.user, cleaned)
        return Response({"fields": cleaned})


class KeywordFieldsResetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.authentication.services import set_keyword_fields
        from apps.intelligence.services.keyword_defaults import default_keyword_fields

        set_keyword_fields(request.user, [])
        return Response({"fields": default_keyword_fields()})
