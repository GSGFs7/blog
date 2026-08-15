import time
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.sessions.backends.base import SessionBase
from django.http.request import HttpRequest
from django_otp.models import Device

from accounts.services.redirects import safe_next_url


@dataclass(frozen=True, slots=True)
class PreauthContext:
    user: AbstractBaseUser
    login_backend: str
    destination: str | None


PREAUTH_SESSION_KEY = "accounts_preauth"
VERIFY_NEXT_SESSION_KEY = "accounts_verify_next"
SETUP_DEVICE_SESSION_KEY = "accounts_setup_device_id"
RECOVERY_CODES_SESSION_KEY = "accounts_recovery_codes"
RECOVERY_NEXT_SESSION_KEY = "accounts_recovery_next"
REPLACE_DEVICE_SESSION_KEY = "accounts_replace_device"
AUTH_FLOW_SESSION_KEYS = (
    PREAUTH_SESSION_KEY,
    VERIFY_NEXT_SESSION_KEY,
    SETUP_DEVICE_SESSION_KEY,
    RECOVERY_CODES_SESSION_KEY,
    RECOVERY_NEXT_SESSION_KEY,
    REPLACE_DEVICE_SESSION_KEY,
)


def begin_preauth(
    request: HttpRequest,
    user: AbstractBaseUser,
    next_url: str | None,
) -> None:
    request.session.cycle_key()
    request.session[PREAUTH_SESSION_KEY] = {
        "user_id": str(user.pk),
        # auth backend. e.g.: "django.contrib.auth.backends.ModelBackend"
        "backend": getattr(
            user,
            "backend",
            f"{ModelBackend.__module__}.{ModelBackend.__qualname__}",
        ),
        "created_at": int(time.time()),
        "next": safe_next_url(request, next_url),
    }


def get_preauth(request: HttpRequest) -> PreauthContext | None:
    data = request.session.get(PREAUTH_SESSION_KEY)
    if not isinstance(data, dict):
        return None

    try:
        created_at = int(data["created_at"])
        user_id = data["user_id"]
        backend = data["backend"]
    except KeyError, TypeError, ValueError:
        clear_preauth(request)
        return None

    ttl = settings.TWO_FACTOR_PREAUTH_TTL
    if created_at > int(time.time()) or int(time.time()) - created_at > ttl:
        clear_preauth(request)
        return None
    if backend not in settings.AUTHENTICATION_BACKENDS:
        clear_preauth(request)
        return None

    user = get_user_model()._default_manager.filter(pk=user_id, is_active=True).first()
    if user is None:
        clear_preauth(request)
        return None
    return PreauthContext(
        user=user,
        login_backend=backend,
        destination=data.get("next"),
    )


def clear_preauth(request: HttpRequest) -> None:
    request.session.pop(PREAUTH_SESSION_KEY, None)


def clear_auth_flow(session: SessionBase) -> None:
    for key in AUTH_FLOW_SESSION_KEYS:
        session.pop(key, None)


async def aclear_auth_flow(session: SessionBase) -> None:
    for key in AUTH_FLOW_SESSION_KEYS:
        await session.apop(key, None)


def finish_login(
    request: HttpRequest,
    user: AbstractBaseUser,
    backend: str,
    device: Device | None = None,
) -> None:
    clear_preauth(request)
    request.session.pop(VERIFY_NEXT_SESSION_KEY, None)
    if device is not None:
        user.otp_device = device
    # let Django sign a formal session
    login(request, user, backend=backend)
