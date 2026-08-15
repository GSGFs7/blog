from enum import StrEnum
from urllib.parse import urlsplit

from django.http import HttpRequest
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

OAUTH_BLOCKED_RETURN_PATHS = (
    "/not-admin/",
    "/account/two_factor/",
)


class OAuthError(StrEnum):
    AUTHORIZATION_REJECTED = "authorization_rejected"
    INVALID_REQUEST = "invalid_request"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    SESSION_EXPIRED = "session_expired"


def safe_oauth_return_url(
    request: HttpRequest,
    value: str | None,
    fallback: str = "index",
) -> str:
    fallback_url = resolve_url(fallback)
    if not value or not url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return fallback_url

    path = urlsplit(value).path
    if any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in OAUTH_BLOCKED_RETURN_PATHS
    ):
        return fallback_url
    return value
