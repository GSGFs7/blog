import secrets

from django.db import models
from django.utils import timezone

from core.field import FernetField

from .base import BaseModel


class ApiClient(BaseModel):
    client_id = models.CharField(max_length=64, unique=True)
    secret = FernetField(blank=True, default="")

    # TODO: API client scopes
    scopes = models.JSONField(default=list, blank=True)

    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # `unique=True` has crated a index
            # this not necessary. remove?
            models.Index(fields=["client_id"]),
        ]

    def __str__(self):
        return self.client_id

    @property
    def is_active(self):
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            return self.expires_at > timezone.now()
        return True

    @staticmethod
    def generate_secret():
        return secrets.token_urlsafe(48)
