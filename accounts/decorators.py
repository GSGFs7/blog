from typing import Any, Callable

from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import AbstractUser

from accounts.services.otp import is_otp_verified


def _is_verified_staff(user: AbstractUser) -> bool:
    return user.is_staff and is_otp_verified(user)


def otp_staff_required(view_func: Callable[..., Any]) -> Callable[..., Any]:
    return user_passes_test(_is_verified_staff)(view_func)
