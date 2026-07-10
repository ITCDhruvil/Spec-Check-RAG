from django.urls import path

from apps.authentication.views import (
    ChangePasswordView,
    GeneratePasswordView,
    ImpersonateUserView,
    LoginView,
    MeView,
    RefreshTokenView,
    UserDetailView,
    UserListCreateView,
)

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/token/refresh/", RefreshTokenView.as_view(), name="auth-token-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/me/change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("auth/users/generate-password/", GeneratePasswordView.as_view(), name="auth-generate-password"),
    path("auth/login-as/<int:pk>/", ImpersonateUserView.as_view(), name="auth-user-login-as"),
    path("auth/users/", UserListCreateView.as_view(), name="auth-users"),
    path("auth/users/<int:pk>/", UserDetailView.as_view(), name="auth-user-detail"),
]
