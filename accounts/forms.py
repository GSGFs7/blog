from typing import Any

from django import forms
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.forms import AuthenticationForm
from django_otp import verify_token
from django_otp.models import Device
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.services.otp import usable_devices

INPUT_CLASSES = (
    "mt-2 w-full bg-white/5 px-3 py-2 text-gray-100 outline-none "
    "transition-colors focus:bg-white/10"
)


class AdminLoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Username or password incorrect.",
        "inactive": "Username or password incorrect.",
    }
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
                "class": INPUT_CLASSES,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "class": INPUT_CLASSES,
            }
        ),
    )

    def __init__(
        self,
        *args: Any,
        throttle_locked: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.throttle_locked = throttle_locked

    def clean(self) -> dict[str, Any]:
        if self.throttle_locked:
            raise forms.ValidationError(
                "Too many login attempts. Please try again later."
            )
        return super().clean()

    def confirm_login_allowed(self, user: AbstractBaseUser) -> None:
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
            )


class OTPVerificationForm(forms.Form):
    device = forms.ChoiceField(
        label="Verification method",
        widget=forms.Select(attrs={"class": INPUT_CLASSES}),
    )
    token = forms.CharField(
        label="Verification code or recovery code",
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "autofocus": True,
                "class": INPUT_CLASSES,
            }
        ),
    )

    def __init__(
        self,
        user: AbstractBaseUser,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["device"].choices = [
            (device.persistent_id, _device_label(device))
            for device in usable_devices(user)
        ]
        self.verified_device = None

    def clean_token(self) -> str:
        return _normalize_token(self.cleaned_data["token"])

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        device_id = cleaned_data.get("device")
        token = cleaned_data.get("token")
        if not device_id or not token:
            return cleaned_data

        self.verified_device = verify_token(self.user, device_id, token)
        if self.verified_device is None:
            raise forms.ValidationError(
                "The verification code is invalid, has been used, "
                "or is temporarily restricted. Please try again."
            )
        return cleaned_data


class OTPSetupForm(forms.Form):
    token = forms.CharField(
        label="Verification code",
        min_length=6,
        max_length=8,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "autofocus": True,
                "inputmode": "numeric",
                "pattern": "[0-9]*",
                "class": INPUT_CLASSES,
            }
        ),
    )

    def __init__(
        self,
        *args: Any,
        user: AbstractBaseUser | None = None,
        require_password: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        self.require_password = require_password
        if require_password:
            self.fields["password"] = forms.CharField(
                label="Current Password",
                strip=False,
                widget=forms.PasswordInput(
                    attrs={
                        "autocomplete": "current-password",
                        "class": INPUT_CLASSES,
                    }
                ),
            )
            self.order_fields(["password", "token"])

    def clean_token(self) -> str:
        return _normalize_token(self.cleaned_data["token"])

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Incorrect password.")
        return password


class SensitiveActionForm(OTPVerificationForm):
    password = forms.CharField(
        label="Current Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "class": INPUT_CLASSES,
            }
        ),
    )

    def clean(self) -> dict[str, Any]:
        password = self.cleaned_data.get("password")
        if "password" not in self.cleaned_data:
            return self.cleaned_data
        if password and not self.user.check_password(password):
            self.add_error("password", "Incorrect password.")
            return self.cleaned_data
        return super().clean()


def _normalize_token(token: str) -> str:
    return token.replace(" ", "").replace("-", "").strip()


def _device_label(device: Device) -> str:
    if isinstance(device, TOTPDevice):
        return f"Authenticator（{device.name}）"
    if isinstance(device, StaticDevice):
        return "One-time recovery code"
    return device.name
