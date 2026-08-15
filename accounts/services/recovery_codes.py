from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.http.request import HttpRequest
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

from accounts.services.login_flow import RECOVERY_CODES_SESSION_KEY


def create_recovery_codes(
    user: AbstractBaseUser,
    replace: bool = False,
) -> list[str]:
    device = (
        StaticDevice.objects.filter(user=user, confirmed=True).order_by("pk").first()
    )
    if device is None:
        device = StaticDevice.objects.create(
            user=user,
            name="backup",
            confirmed=True,
        )

    if replace:
        StaticToken.objects.filter(device__user=user).delete()
    elif StaticToken.objects.filter(device__user=user).exists():
        return []

    codes = [
        StaticToken.random_token()
        for _ in range(settings.TWO_FACTOR_RECOVERY_CODE_COUNT)
    ]
    StaticToken.objects.bulk_create(
        [StaticToken(device=device, token=code) for code in codes]
    )
    return codes


def recovery_code_count(user: AbstractBaseUser) -> int:
    return StaticToken.objects.filter(device__user=user).count()


def store_recovery_codes(request: HttpRequest, codes: list[str]) -> None:
    request.session[RECOVERY_CODES_SESSION_KEY] = codes


def take_recovery_codes(request: HttpRequest) -> list[str] | None:
    return request.session.pop(RECOVERY_CODES_SESSION_KEY, None)
