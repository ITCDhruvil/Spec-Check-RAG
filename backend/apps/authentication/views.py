from django.contrib.auth import get_user_model
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
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(target).data,
            }
        )

