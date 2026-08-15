import base64
import time
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_safe
from django_otp import login as otp_login
from django_otp import verify_token
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.forms import OTPSetupForm, SensitiveActionForm
from accounts.services.login_flow import (
    RECOVERY_NEXT_SESSION_KEY,
    REPLACE_DEVICE_SESSION_KEY,
)
from accounts.services.recovery_codes import (
    create_recovery_codes,
    recovery_code_count,
    store_recovery_codes,
    take_recovery_codes,
)


@require_safe
def security_view(request: HttpRequest) -> HttpResponse:
    return _admin_response(
        request,
        "admin/accounts/security.html",
        title="Account security",
        totp_devices=TOTPDevice.objects.filter(
            user=request.user,
            confirmed=True,
        ).order_by("pk"),
        recovery_count=recovery_code_count(request.user),
    )


@require_GET
def recovery_codes_view(request: HttpRequest) -> HttpResponse:
    codes = take_recovery_codes(request)
    if not codes:
        return redirect("admin:account_security")

    destination = request.session.pop(
        RECOVERY_NEXT_SESSION_KEY,
        None,
    ) or reverse("admin:account_security")
    return _admin_response(
        request,
        "admin/accounts/recovery_codes.html",
        title="Save recovery codes",
        codes=codes,
        destination=destination,
    )


@require_http_methods(["GET", "POST"])
def regenerate_recovery_codes_view(request: HttpRequest) -> HttpResponse:
    form = SensitiveActionForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        otp_login(request, form.verified_device)
        with transaction.atomic():
            codes = create_recovery_codes(request.user, replace=True)
        store_recovery_codes(request, codes)
        request.session[RECOVERY_NEXT_SESSION_KEY] = reverse("admin:account_security")
        messages.success(
            request,
            "Old recovery codes were invalidated and a new set was generated.",
        )
        return redirect("admin:account_recovery_codes")

    return _sensitive_action_response(
        request,
        form,
        title="Regenerate recovery codes",
        description="This action immediately invalidates all existing recovery codes.",
        submit_label="Regenerate",
    )


@require_http_methods(["GET", "POST"])
def replace_authenticator_view(request: HttpRequest) -> HttpResponse:
    form = SensitiveActionForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        otp_login(request, form.verified_device)
        _start_replacement(request)
        return redirect("admin:account_replace_authenticator_setup")

    return _sensitive_action_response(
        request,
        form,
        title="Replace authenticator",
        description=(
            "The existing authenticator remains active until the new one is verified."
        ),
        submit_label="Continue",
    )


@require_http_methods(["GET", "POST"])
def replace_authenticator_setup_view(request: HttpRequest) -> HttpResponse:
    device = _replacement_device(request)
    if device is None:
        return redirect("admin:account_replace_authenticator")

    form = OTPSetupForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        verified_device = verify_token(
            request.user,
            device.persistent_id,
            form.cleaned_data["token"],
        )
        if verified_device is None:
            form.add_error(
                "token",
                "The verification code is invalid, has been used, or is temporarily "
                "restricted. Please try again.",
            )
        else:
            with transaction.atomic():
                verified_device.confirmed = True
                verified_device.save(update_fields=["confirmed"])
                TOTPDevice.objects.filter(user=request.user).exclude(
                    pk=verified_device.pk
                ).delete()
            request.session.pop(REPLACE_DEVICE_SESSION_KEY, None)
            otp_login(request, verified_device)
            messages.success(request, "The authenticator has been replaced.")
            return redirect("admin:account_security")

    secret = base64.b32encode(device.bin_key).decode().rstrip("=")
    return _admin_response(
        request,
        "admin/accounts/replace_authenticator.html",
        title="Set up the new authenticator",
        form=form,
        secret=secret,
    )


@require_safe
def replace_authenticator_qr_view(request: HttpRequest) -> HttpResponse:
    device = _replacement_device(request)
    if device is None:
        raise PermissionDenied

    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(device.config_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    output = BytesIO()
    image.save(output)
    return HttpResponse(output.getvalue(), content_type="image/svg+xml")


def _start_replacement(request: HttpRequest) -> TOTPDevice:
    _clear_replacement(request)
    with transaction.atomic():
        TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()
        device = TOTPDevice.objects.create(
            user=request.user,
            name="default",
            confirmed=False,
        )
    request.session[REPLACE_DEVICE_SESSION_KEY] = {
        "user_id": str(request.user.pk),
        "device_id": device.pk,
        "created_at": int(time.time()),
    }
    return device


def _replacement_device(request: HttpRequest) -> TOTPDevice | None:
    data = request.session.get(REPLACE_DEVICE_SESSION_KEY)
    if not isinstance(data, dict):
        return None

    try:
        device_id = int(data["device_id"])
        created_at = int(data["created_at"])
        matches_user = data["user_id"] == str(request.user.pk)
    except KeyError, TypeError, ValueError:
        _clear_replacement(request)
        return None

    now = int(time.time())
    if (
        not matches_user
        or created_at > now
        or now - created_at > settings.TWO_FACTOR_PREAUTH_TTL
    ):
        _clear_replacement(request)
        return None

    device = TOTPDevice.objects.filter(
        pk=device_id,
        user=request.user,
        confirmed=False,
    ).first()
    if device is None:
        request.session.pop(REPLACE_DEVICE_SESSION_KEY, None)
    return device


def _clear_replacement(request: HttpRequest) -> None:
    data = request.session.pop(REPLACE_DEVICE_SESSION_KEY, None)
    if not isinstance(data, dict):
        return
    device_id = data.get("device_id")
    if isinstance(device_id, int):
        TOTPDevice.objects.filter(
            pk=device_id,
            user=request.user,
            confirmed=False,
        ).delete()


def _sensitive_action_response(
    request: HttpRequest,
    form: SensitiveActionForm,
    *,
    title: str,
    description: str,
    submit_label: str,
) -> HttpResponse:
    return _admin_response(
        request,
        "admin/accounts/sensitive_action.html",
        title=title,
        form=form,
        description=description,
        submit_label=submit_label,
    )


def _admin_response(
    request: HttpRequest,
    template_name: str,
    **context,
) -> HttpResponse:
    return TemplateResponse(
        request,
        template_name,
        {
            **admin.site.each_context(request),
            **context,
        },
    )
