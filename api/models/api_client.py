import secrets

from django.db import models
from django.utils import timezone

from core.field import FernetField

from .base import BaseModel


class ApiClient(BaseModel):
    client_id = models.CharField(max_length=64, unique=True)

    # TODO: API client scopes
    scopes = models.JSONField(default=list, blank=True)

    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.client_id

    @property
    def is_active(self):
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            return self.expires_at > timezone.now()
        return True


class ApiClientCredential(BaseModel):
    client = models.ForeignKey(
        ApiClient,
        on_delete=models.CASCADE,
        related_name="credentials",
    )

    kid = models.CharField(
        max_length=32, unique=True, editable=False, help_text="key ID"
    )
    secret = FernetField()

    description = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.kid

    @property
    def is_active(self):
        return self.revoked_at is None and (
            self.expires_at is None or self.expires_at > timezone.now()
        )

    @staticmethod
    def generate_kid():
        return secrets.token_urlsafe(18)

    @staticmethod
    def generate_secret():
        return secrets.token_urlsafe(48)
