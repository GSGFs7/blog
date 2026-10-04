import asyncio
import base64
import binascii
import json
import uuid

from cryptography.fernet import InvalidToken
from django.core.cache import cache
from django.http.request import HttpRequest
from ninja.errors import HttpError
from ninja.security import HttpBearer

from api.models import ApiClientCredential
from core.fernet import get_fernet


def create_client_token(
    client_id: str,
    kid: str,
    secret: str,
    nonce: str | None = None,
) -> str:
    """
    token: v1.<client_id>.<kid>.<token>
    """

    encoded_id = base64.urlsafe_b64encode(client_id.encode()).decode().rstrip("=")
    payload = json.dumps([client_id, kid, nonce or uuid.uuid4().hex]).encode()
    ciphertext = get_fernet(secret).encrypt(payload).decode()
    return f"v1.{encoded_id}.{kid}.{ciphertext}"


class ApiClientAuth(HttpBearer):
    def __init__(self, required_scope: str | None = None):
        super().__init__()
        self.required_scope = required_scope

    async def authenticate(self, request: HttpRequest, token: str):
        try:
            version, encoded_id, kid, ciphertext = token.split(".", 3)
            if version != "v1" or not encoded_id or not kid or not ciphertext:
                return None
            if len(encoded_id) > 88 or len(kid) > 32 or len(ciphertext) > 4096:
                return None

            client_id = base64.urlsafe_b64decode(
                encoded_id + "=" * (-len(encoded_id) % 4)
            ).decode()
            credential = await ApiClientCredential.objects.select_related(
                "client"
            ).aget(kid=kid, client__client_id=client_id)
            if (
                not credential.secret
                or not credential.is_active
                or not credential.client.is_active
            ):
                return None

            payload = await asyncio.to_thread(
                get_fernet(credential.secret).decrypt, ciphertext.encode(), ttl=30
            )
            authenticated_id, authenticated_kid, nonce = json.loads(payload)
            if authenticated_id != client_id or authenticated_kid != kid or not nonce:
                return None
            if not await cache.aadd(
                f"api_client_auth_token:v1:{credential.pk}:{nonce}", 1, timeout=30
            ):
                return None
        except (
            ValueError,
            UnicodeError,
            binascii.Error,
            InvalidToken,
            ApiClientCredential.DoesNotExist,
        ):
            return None

        scopes = credential.client.scopes
        if self.required_scope and (
            not isinstance(scopes, list) or self.required_scope not in scopes
        ):
            raise HttpError(403, "Insufficient API client scope")
        return client_id
