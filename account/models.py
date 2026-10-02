from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# =============================================================================
# Custom User
# =============================================================================


class CustomUserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("An email address is required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):

    class AssistedTier(models.TextChoices):
        BASIC = "basic", "Basic"
        ENHANCED = "enhanced", "Enhanced"

    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    # Capability entitlement gating Assisted (AI-driven) execution -- not a
    # billing/subscription model. BASIC is the safe default for both new and
    # pre-existing rows: see account.services.entitlement.user_can_run_assisted
    # for the single place this is turned into an allow/deny decision.
    assisted_tier = models.CharField(
        max_length=20,
        choices=AssistedTier.choices,
        default=AssistedTier.BASIC,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email
