from django.conf import settings
from django.http.request import HttpRequest
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect_url(
    request: HttpRequest,
    value: str | None,
    fallback: str,
) -> str:
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return resolve_url(fallback)


def safe_next_url(request: HttpRequest, value: str | None) -> str:
    return safe_redirect_url(request, value, settings.LOGIN_REDIRECT_URL)
