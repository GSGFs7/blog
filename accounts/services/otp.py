from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django_otp import devices_for_user
from django_otp.models import Device
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice


def is_otp_verified(user: AbstractBaseUser | AnonymousUser) -> bool:
    verifier = getattr(user, "is_verified", None)
    return user.is_authenticated and callable(verifier) and verifier()


def usable_devices(user: AbstractBaseUser | AnonymousUser) -> list[Device]:
    result: list[Device] = []
    # if user is anonymous, "devices_for_user" will return with None
    for device in devices_for_user(user):
        if isinstance(device, StaticDevice) and not device.token_set.exists():
            continue
        result.append(device)
    return result


def has_totp_device(user: AbstractBaseUser) -> bool:
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()
