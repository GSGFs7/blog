from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction
from django.utils import timezone

from api.models import Guest, OAuthIdentity, OAuthProvider


class OAuthServiceError(Exception):
    pass


class OAuthProviderUnavailable(OAuthServiceError):
    pass


class OAuthProviderResponseError(OAuthServiceError):
    pass


@dataclass(frozen=True, slots=True)
class OAuthToken:
    access_token: str
    token_type: str
    refresh_token: str
    expires_in: int | None
    scope: str
    raw: dict[str, Any]

    @property
    def expires_at(self):
        if self.expires_in is None:
            return None
        return timezone.now() + timedelta(seconds=self.expires_in)


@dataclass(frozen=True, slots=True)
class OAuthUser:
    user_id: str
    name: str
    email: str
    avatar: str
    raw: dict[str, Any]


class OAuthService:
    def __init__(
        self,
        provider: OAuthProvider,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ):
        if not provider.is_active:
            raise OAuthProviderUnavailable(
                f"OAuth provider '{provider.provider_key}' is inactive"
            )

        self.provider = provider
        self.client = client
        self.timeout = timeout

    @classmethod
    async def for_provider(
        cls,
        provider_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> "OAuthService":
        try:
            provider = await OAuthProvider.objects.aget(
                provider_key=provider_key, is_active=True
            )
        except OAuthProvider.DoesNotExist as e:
            raise OAuthProviderUnavailable(
                f"OAuth provider '{provider_key}' is unavailable"
            ) from e
        return cls(provider, client=client, timeout=timeout)

    def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        extra_params: Mapping[str, str] | None = None,
    ) -> str:
        parts = urlsplit(self.provider.authorization_url)
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        params.update(extra_params or {})
        params.update(
            {
                "client_id": self.provider.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "state": state,
            }
        )
        if self.provider.scope:
            params["scope"] = self.provider.scope
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return parts._replace(query=urlencode(params)).geturl()

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        extra_params: Mapping[str, str] | None = None,
    ):
        # request body
        data = dict(extra_params or {})
        data.update(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.provider.client_id,
                "redirect_uri": redirect_uri,
            }
        )
        if self.provider.client_secret:
            data["client_secret"] = self.provider.client_secret
        if code_verifier:
            data["code_verifier"] = code_verifier

        # request
        payload = await self._request_json(
            "POST",
            self.provider.token_url,
            data=data,
            headers={"Accept": "application/json"},
        )
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OAuthProviderResponseError(
                "OAuth token response does not contain an access token"
            )

        # expires
        expires_in = payload.get("expires_in")
        try:
            parsed_expires_in = int(expires_in) if expires_in is not None else None
        except (TypeError, ValueError):
            parsed_expires_in = None

        # re-assemble the data
        return OAuthToken(
            access_token=access_token,
            token_type=str(payload.get("token_type") or "Bearer"),
            refresh_token=str(payload.get("refresh_token") or ""),
            expires_in=parsed_expires_in,
            scope=str(payload.get("scope") or ""),
            raw=payload,
        )

    async def fetch_user(self, token: OAuthToken) -> OAuthUser:
        payload = await self._request_json(
            "GET",
            self.provider.userinfo_url,
            headers={"Authorization": f"{token.token_type} {token.access_token}"},
        )
        user_id = self._first_value(payload, "sub", "id", "user_id")
        if user_id is None:
            raise OAuthProviderResponseError(
                "OAuth user response does not contain a user identifier"
            )

        email = self._first_value(payload, "email") or ""
        name = self._first_value(payload, "name", "login", "username") or ""
        avatar = self._first_value(payload, "avatar_url", "avatar", "picture") or ""
        return OAuthUser(
            user_id=str(user_id),
            name=str(name),
            email=str(email),
            avatar=str(avatar),
            raw=payload,
        )

    async def login(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        token_params: Mapping[str, str] | None = None,
    ) -> OAuthIdentity:
        token = await self.exchange_code(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            extra_params=token_params,
        )
        user = await self.fetch_user(token)
        return await sync_to_async(self._persist_identity, thread_sensitive=True)(
            self.provider.pk, user, token
        )

    async def _request_json(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        try:
            if self.client is None:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(method, url, **kwargs)
            else:
                response = await self.client.request(
                    method,
                    url,
                    **kwargs,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as e:
            raise OAuthProviderResponseError("OAuth provider request failed") from e

        if not isinstance(payload, dict):
            raise OAuthProviderResponseError("OAuth provider returned invalid JSON")
        return payload

    @staticmethod
    def _first_value(payload: Mapping[str, Any], *keys: str) -> Any | None:
        for key in keys:
            value = payload.get(key)
            if value is not None and value != "":
                return value
        return None

    @classmethod
    def _persist_identity(
        cls,
        provider_id: int,
        user: OAuthUser,
        token: OAuthToken,
    ):
        try:
            with transaction.atomic():
                identity = OAuthIdentity.objects.select_related("guest").get(
                    provider_id=provider_id,
                    user_id=user.user_id,
                )
                cls._update_identity(identity, user, token)
                return identity
        except OAuthIdentity.DoesNotExist:
            # new user
            pass

        try:
            with transaction.atomic():
                guest = Guest.objects.create(
                    name=user.name,
                    email=user.email,
                    avatar=user.avatar,
                )
                return OAuthIdentity.objects.create(
                    guest=guest,
                    provider_id=provider_id,
                    user_id=user.user_id,
                    access_token=token.access_token,
                    refresh_token=token.refresh_token,
                    expires_at=token.expires_at,
                    extra_data=user.raw,
                )
        except IntegrityError:
            with transaction.atomic():
                identity = OAuthIdentity.objects.select_related("guest").get(
                    provider_id=provider_id,
                    user_id=user.user_id,
                )
                cls._update_identity(identity, user, token)
                return identity

    @staticmethod
    def _update_identity(
        identity: OAuthIdentity,
        user: OAuthUser,
        token: OAuthToken,
    ) -> None:
        # guest
        guest_updated_fields = []
        for field in ("name", "email", "avatar"):
            value = getattr(user, field)
            # update different field
            if value and getattr(identity.guest, field) != value:
                setattr(identity.guest, field, value)
                guest_updated_fields.append(field)
        if guest_updated_fields:
            identity.guest.save(update_fields=[*guest_updated_fields, "updated_at"])

        # guest oauth identity
        identity.access_token = token.access_token
        if token.refresh_token:
            identity.refresh_token = token.refresh_token
        identity.expires_at = token.expires_at
        identity.extra_data = user.raw
        identity.save(
            update_fields=[
                "access_token",
                "refresh_token",
                "expires_at",
                "extra_data",
                "updated_at",
            ]
        )
