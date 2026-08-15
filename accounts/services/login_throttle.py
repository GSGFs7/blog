import logging

from django.conf import settings
from django.core.cache import cache
from django.http.request import HttpRequest

from core.hash import calculate_blake3_hash
from core.request import get_client_ip

logger = logging.getLogger(__name__)


def _throttle_keys(
    request: HttpRequest,
    username: str,
) -> tuple[tuple[str, int], ...]:
    # be careful when handling usernames
    normalized_username = username.strip().casefold()
    account_key = calculate_blake3_hash(normalized_username.encode())
    keys = [
        (
            f"accounts:login:account:{account_key}",
            settings.LOGIN_THROTTLE_ACCOUNT_LIMIT,
        )
    ]

    # if ip is credible, add to keys
    client_ip = get_client_ip(request)
    if client_ip is not None:
        address_key = calculate_blake3_hash(client_ip.encode())
        keys.append(
            (
                f"accounts:login:address:{address_key}",
                settings.LOGIN_THROTTLE_ADDRESS_LIMIT,
            )
        )
    return tuple(keys)


def login_throttle_is_locked(request: HttpRequest, username: str) -> bool:
    try:
        return any(
            cache.get(key, 0) >= limit
            for key, limit in _throttle_keys(request, username)
        )
    except Exception:
        logger.exception("Unable to read the login throttle cache")
        return False


def login_throttle_failure(request: HttpRequest, username: str) -> None:
    try:
        for key, _ in _throttle_keys(request, username):
            if not cache.add(key, 1, timeout=settings.LOGIN_THROTTLE_WINDOW):
                cache.incr(key)
    except Exception:
        logger.exception("Unable to update the login throttle cache")


def login_throttle_reset(request: HttpRequest, username: str) -> None:
    try:
        cache.delete_many([key for key, _ in _throttle_keys(request, username)])
    except Exception:
        logger.exception("Unable to reset the login throttle cache")
