from django.db import models

from core.field import FernetField

from .base import BaseModel


class OAuthIdentity(BaseModel):
    guest = models.ForeignKey(
        "api.Guest",
        on_delete=models.CASCADE,
        related_name="oauth_identities",
    )
    provider = models.ForeignKey(
        "api.OAuthProvider",
        on_delete=models.CASCADE,
        related_name="oauth_identities",
    )
    user_id = models.CharField(max_length=128)

    access_token = FernetField(blank=True, default="")
    refresh_token = FernetField(blank=True, default="")
    expires_at = models.DateTimeField(blank=True, null=True)

    extra_data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "OAuth Identity"
        verbose_name_plural = "OAuth Identities"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "user_id"],
                name="unique_oauth_provider_user",
            )
        ]

    def __str__(self):
        return f"{self.guest.name} via {self.provider.provider_key}"


class OAuthProvider(BaseModel):
    provider_key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)

    authorization_url = models.URLField(max_length=500)
    token_url = models.URLField(max_length=500)
    userinfo_url = models.URLField(max_length=500)

    scope = models.CharField(max_length=255, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "OAuth Provider"
        verbose_name_plural = "OAuth Providers"

    def __str__(self):
        return f"{self.name} ({self.provider_key})"
