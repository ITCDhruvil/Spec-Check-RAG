from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.authentication.models import UserRole
from apps.authentication.permissions import is_admin_user, is_management_user, role_of
from apps.authentication.services import (
    get_admin_visible_password,
    set_admin_visible_password,
    set_user_role,
)
from apps.authentication.utils import MIN_PASSWORD_LENGTH, generate_password

User = get_user_model()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login with email instead of username."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False
        self.fields["email"] = serializers.EmailField(write_only=True)

    def validate(self, attrs):
        email = attrs.pop("email", "").strip().lower()
        attrs.pop(self.username_field, None)

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"detail": "Invalid email or password."}) from None

        if not user.is_active:
            raise serializers.ValidationError({"detail": "This account is disabled."})

        attrs[self.username_field] = user.get_username()
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()
    is_management = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    display_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
            "last_login",
            "is_admin",
            "is_management",
            "role",
            "display_password",
        )
        read_only_fields = (
            "id",
            "date_joined",
            "last_login",
            "is_admin",
            "is_management",
            "role",
            "display_password",
        )

    def get_is_admin(self, obj) -> bool:
        return is_admin_user(obj)

    def get_is_management(self, obj) -> bool:
        return is_management_user(obj)

    def get_role(self, obj) -> str:
        return role_of(obj)

    def get_display_password(self, obj) -> str | None:
        password = get_admin_visible_password(obj)
        return password or None


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(
        choices=UserRole.choices, required=False, default=UserRole.USER
    )
    password = serializers.CharField(
        min_length=MIN_PASSWORD_LENGTH,
        required=False,
        allow_blank=True,
        write_only=True,
    )

    def validate_role(self, value: str) -> str:
        # Admin is unique — only the configured admin account holds it.
        if value == UserRole.ADMIN:
            raise serializers.ValidationError(
                "The admin role cannot be assigned; there is exactly one admin account."
            )
        return value

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_username(self, value: str) -> str:
        username = value.strip()
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return username

    def validate_password(self, value: str) -> str:
        if value:
            validate_password(value)
        return value

    def create(self, validated_data):
        raw_password = validated_data.pop("password", "").strip()
        role = validated_data.pop("role", UserRole.USER)
        generated = not raw_password
        password = raw_password or generate_password()

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=password,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            is_active=True,
        )
        set_admin_visible_password(user, password)
        set_user_role(user, role)
        user._generated_password = password if generated else None  # noqa: SLF001
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        min_length=MIN_PASSWORD_LENGTH,
        required=False,
        allow_blank=True,
        write_only=True,
    )
    regenerate_password = serializers.BooleanField(required=False, default=False, write_only=True)
    role = serializers.ChoiceField(choices=UserRole.choices, required=False, write_only=True)

    def validate_role(self, value: str) -> str:
        # Admin is unique — only the configured admin account holds it.
        if value == UserRole.ADMIN:
            raise serializers.ValidationError(
                "The admin role cannot be assigned; there is exactly one admin account."
            )
        return value

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "password",
            "regenerate_password",
            "role",
        )

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_username(self, value: str) -> str:
        username = value.strip()
        qs = User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return username

    def validate_password(self, value: str) -> str:
        if value:
            validate_password(value)
        return value

    def update(self, instance, validated_data):
        regenerate = validated_data.pop("regenerate_password", False)
        raw_password = validated_data.pop("password", "").strip()
        role = validated_data.pop("role", None)
        if role:
            set_user_role(instance, role)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        new_password = None
        if regenerate:
            new_password = generate_password()
            instance.set_password(new_password)
        elif raw_password:
            new_password = raw_password
            instance.set_password(raw_password)

        instance.save()
        if new_password:
            set_admin_visible_password(instance, new_password)
            instance._generated_password = new_password  # noqa: SLF001
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    """Let the signed-in user choose their own password (min length only)."""

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=MIN_PASSWORD_LENGTH, write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "New password and confirmation do not match."}
            )
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "New password must be different from your current password."}
            )
        return attrs

    def save(self):
        user = self.context["request"].user
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save()
        set_admin_visible_password(user, new_password)
        return user

