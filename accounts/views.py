"""
staff's 2FA state machine. (process pre-auth session)
"""

import base64
from dataclasses import dataclass
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_http_methods,
    require_safe,
)
from django_otp import login as otp_login
from django_otp import verify_token
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.forms import OTPSetupForm, OTPVerificationForm
from accounts.services.login_flow import (
    RECOVERY_NEXT_SESSION_KEY,
    SETUP_DEVICE_SESSION_KEY,
    VERIFY_NEXT_SESSION_KEY,
    finish_login,
    get_preauth,
)
from accounts.services.otp import (
    has_totp_device,
    is_otp_verified,
    usable_devices,
)
from accounts.services.recovery_codes import (
    create_recovery_codes,
    store_recovery_codes,
)
from accounts.services.redirects import safe_next_url
from web.cache import private_page_response


@dataclass(frozen=True, slots=True)
class SetupContext:
    user: AbstractBaseUser
    login_backend: str | None
    destination: str


@never_cache
@require_http_methods(["GET", "POST"])
def verify_view(request: HttpRequest) -> HttpResponse:
    # parse pre-auth session
    if request.user.is_authenticated:
        user = request.user
        backend = None
        destination = safe_next_url(
            request,
            request.session.get(VERIFY_NEXT_SESSION_KEY),
        )
    else:
        preauth = get_preauth(request)
        if preauth is None:
            return redirect("login")
        user = preauth.user
        backend = preauth.login_backend
        destination = safe_next_url(request, preauth.destination)

    if not user.is_staff:
        return redirect("login")

    devices = usable_devices(user)
    if not devices:
        return redirect("accounts:setup")

    # form validation
    form = OTPVerificationForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        if backend is None:
            # user already has Django login status, only lacking OTP marking.
            otp_login(request, form.verified_device)
            request.session.pop(VERIFY_NEXT_SESSION_KEY, None)
        else:
            finish_login(request, user, backend, form.verified_device)
        return redirect(destination)

    return private_page_response(
        render(request, "accounts/verify.html", {"form": form})
    )


@never_cache
@require_http_methods(["GET", "POST"])
def setup_view(request: HttpRequest) -> HttpResponse:
    context = _resolve_setup_context(request)
    if context is None:
        return redirect("login")
    if _setup_requires_verification(context):
        request.session[VERIFY_NEXT_SESSION_KEY] = reverse("accounts:setup")
        return redirect("accounts:verify")

    user = context.user
    backend = context.login_backend
    destination = context.destination
    if has_totp_device(user):
        return redirect("admin:account_security")

    device = _setup_device(request, user)
    secret = base64.b32encode(device.bin_key).decode().rstrip("=")
    require_password = backend is None and not is_otp_verified(user)
    form = OTPSetupForm(
        request.POST or None,
        user=user,
        require_password=require_password,
    )
    if request.method == "POST" and form.is_valid():
        verified_device = verify_token(
            user, device.persistent_id, form.cleaned_data["token"]
        )
        if verified_device is None:
            form.add_error(
                "token",
                "The verification code is invalid, has been used, or is temporarily "
                "restricted. Please try again.",
            )
        else:
            verified_device.confirmed = True
            verified_device.save(update_fields=["confirmed"])
            codes = create_recovery_codes(user)
            request.session.pop(SETUP_DEVICE_SESSION_KEY, None)
            if codes:
                store_recovery_codes(request, codes)
                request.session[RECOVERY_NEXT_SESSION_KEY] = destination
            if backend is None:
                otp_login(request, verified_device)
            else:
                finish_login(request, user, backend, verified_device)
            messages.success(request, "Two-factor authentication has been enabled.")
            if codes:
                return redirect("admin:account_recovery_codes")
            return redirect("admin:account_security")

    return private_page_response(
        render(
            request,
            "accounts/setup.html",
            {"form": form, "secret": secret},
        )
    )


@never_cache
@require_safe
def qr_code_view(request: HttpRequest) -> HttpResponse:
    context = _resolve_setup_context(request)
    if context is None or _setup_requires_verification(context):
        raise PermissionDenied

    device = _existing_setup_device(request, context.user)
    if device is None:
        raise PermissionDenied

    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(device.config_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    output = BytesIO()
    image.save(output)
    return private_page_response(
        HttpResponse(output.getvalue(), content_type="image/svg+xml")
    )


# --- helper ---


def _resolve_setup_context(request: HttpRequest) -> SetupContext | None:
    if request.user.is_authenticated:
        user = request.user
        if not user.is_staff:
            return None
        return SetupContext(
            user=user,
            login_backend=None,
            destination=safe_next_url(
                request,
                request.session.get(VERIFY_NEXT_SESSION_KEY),
            ),
        )

    preauth = get_preauth(request)
    if preauth is None:
        return None

    if not preauth.user.is_staff:
        return None
    return SetupContext(
        user=preauth.user,
        login_backend=preauth.login_backend,
        destination=safe_next_url(request, preauth.destination),
    )


def _setup_requires_verification(context: SetupContext) -> bool:
    return (
        context.login_backend is None
        and bool(usable_devices(context.user))
        and not is_otp_verified(context.user)
    )


def _existing_setup_device(
    request: HttpRequest,
    user: AbstractBaseUser,
) -> TOTPDevice | None:
    device_id = request.session.get(SETUP_DEVICE_SESSION_KEY)
    if not isinstance(device_id, int):
        return None
    return TOTPDevice.objects.filter(
        pk=device_id,
        user=user,
        confirmed=False,
    ).first()


def _setup_device(request: HttpRequest, user: AbstractBaseUser) -> TOTPDevice:
    device = _existing_setup_device(request, user)
    if device is None:
        with transaction.atomic():
            TOTPDevice.objects.filter(user=user, confirmed=False).delete()
            device = TOTPDevice.objects.create(
                user=user,
                name="default",
                confirmed=False,
            )
        request.session[SETUP_DEVICE_SESSION_KEY] = device.pk
    return device
