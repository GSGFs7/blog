from typing import Any
from urllib.parse import urlencode

from django.contrib.admin import AdminSite
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.shortcuts import redirect
from django.urls import path, reverse

from accounts import admin_views


class TwoFactorAdminSite(AdminSite):
    def get_urls(self):
        # add urls to django admin
        return [
            path(
                "account/security/",
                self.admin_view(admin_views.security_view),
                name="account_security",
            ),
            path(
                "account/security/recovery-codes/",
                self.admin_view(admin_views.recovery_codes_view),
                name="account_recovery_codes",
            ),
            path(
                "account/security/recovery-codes/regenerate/",
                self.admin_view(admin_views.regenerate_recovery_codes_view),
                name="account_regenerate_recovery_codes",
            ),
            path(
                "account/security/authenticator/replace/",
                self.admin_view(admin_views.replace_authenticator_view),
                name="account_replace_authenticator",
            ),
            path(
                "account/security/authenticator/replace/setup/",
                self.admin_view(admin_views.replace_authenticator_setup_view),
                name="account_replace_authenticator_setup",
            ),
            path(
                "account/security/authenticator/replace/qrcode/",
                self.admin_view(admin_views.replace_authenticator_qr_view),
                name="account_replace_authenticator_qr",
            ),
        ] + super().get_urls()

    def has_permission(self, request: HttpRequest) -> bool:
        # this method inject by django-otp middleware
        # https://github.com/django-otp/django-otp/blob/fc0d50b6f66da10fad250ce1640f0385f3229f48/src/django_otp/middleware.py#L66
        is_verified = getattr(request.user, "is_verified", None)
        # active staff & 2FA
        return (
            super().has_permission(request)
            and is_verified is not None
            and callable(is_verified)
            and is_verified()
        )

    def login(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        if self.has_permission(request):
            return redirect("admin:index")

        destination = (
            request.POST.get(REDIRECT_FIELD_NAME)
            or request.GET.get(REDIRECT_FIELD_NAME)
            or request.get_full_path()
        )
        query = urlencode({REDIRECT_FIELD_NAME: destination})
        return redirect(f"{reverse('login')}?{query}")
