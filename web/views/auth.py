"""
"/login" is unified login page.

guest(OAuth) & staff(passwd) identity can't hold together.
it's intentional, not a bug.

DO NOT login guest as a User. keep it as a AnonymousUser.
get guest from "request.guest". (privide by OAuthGuestMiddleware middleware)
"""

from django.contrib.auth import logout as django_logout
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_GET,
    require_POST,
)

from accounts.forms import AdminLoginForm
from accounts.services.login_flow import (
    VERIFY_NEXT_SESSION_KEY,
    begin_preauth,
    clear_auth_flow,
)
from accounts.services.login_throttle import (
    login_throttle_failure,
    login_throttle_is_locked,
    login_throttle_reset,
)
from accounts.services.otp import (
    is_otp_verified,
    usable_devices,
)
from accounts.services.redirects import safe_next_url
from api.models import OAuthProvider
from api.services import OAuthError, safe_oauth_return_url
from api.services.oauth_session import clear_oauth_session, session_identity
from web.cache import private_page_response

OAUTH_ERROR_MESSAGES: dict[OAuthError, str] = {
    OAuthError.AUTHORIZATION_REJECTED: "OAuth authorization was canceled.",
    OAuthError.INVALID_REQUEST: "Invalid OAuth login request. Please try again.",
    OAuthError.PROVIDER_UNAVAILABLE: (
        "This OAuth login method is temporarily unavailable."
    ),
    OAuthError.PROVIDER_ERROR: (
        "The OAuth service could not complete the login. Please try again later."
    ),
    OAuthError.SESSION_EXPIRED: "The OAuth login session expired. Please try again.",
}


@never_cache
@require_POST
def logout(request: HttpRequest) -> HttpResponse:
    django_logout(request)
    return private_page_response(redirect("index"))


@never_cache
@require_GET
def login(request: HttpRequest) -> HttpResponse:
    if response := _redirect_authenticated_admin(request):
        return response

    return _render_login_page(request, AdminLoginForm(request))


# asynchronization will produce multiple thread switches.
# keep it sync is enough.
@never_cache
@require_POST
def admin_login(request: HttpRequest) -> HttpResponse:
    if response := _redirect_authenticated_admin(request):
        return response

    username = request.POST.get("username", "")
    throttle_locked = login_throttle_is_locked(request, username)
    form = AdminLoginForm(
        request,
        data=request.POST,
        throttle_locked=throttle_locked,
    )
    if form.is_valid():
        login_throttle_reset(request, username)
        return _begin_admin_login(request, form.get_user())
    if not throttle_locked:
        login_throttle_failure(request, username)

    # render admin login error
    return _render_login_page(request, form)


# --- helper ---


def _redirect_authenticated_admin(
    request: HttpRequest,
) -> HttpResponse | None:
    """auto redirect to 2FA (if necessary)"""

    if not request.user.is_authenticated or not request.user.is_staff:
        return None

    clear_oauth_session(request.session)
    admin_next = _admin_next_url(request)
    if is_otp_verified(request.user):
        return private_page_response(redirect(admin_next))
    if usable_devices(request.user):
        request.session[VERIFY_NEXT_SESSION_KEY] = admin_next
        return private_page_response(redirect("accounts:verify"))
    return private_page_response(redirect("accounts:setup"))


def _begin_admin_login(
    request: HttpRequest,
    user: AbstractBaseUser,
) -> HttpResponse:
    """sign a pre-auth session. (next step: 2FA)"""

    # clean session
    if request.user.is_authenticated:
        django_logout(request)
    else:
        clear_oauth_session(request.session)
        clear_auth_flow(request.session)

    begin_preauth(request, user, _admin_next_url(request))
    destination = "accounts:verify" if usable_devices(user) else "accounts:setup"
    return private_page_response(redirect(destination))


def _render_login_page(
    request: HttpRequest,
    form: AdminLoginForm,
) -> HttpResponse:
    admin_next = _admin_next_url(request)
    oauth_return_to = _oauth_return_url(request)
    providers = (
        OAuthProvider.objects.filter(is_active=True)
        .only("provider_key", "name")
        .order_by("name")
    )
    context = {
        "form": form,
        "admin_next": admin_next,
        "oauth_return_to": oauth_return_to,
        "oauth_providers": providers,
        "oauth_identity": session_identity(request.session),
        "oauth_error": _oauth_error_message(request.GET.get("oauth_error")),
    }
    return private_page_response(
        render(request, "web/pages/login.html", context),
    )


def _admin_next_url(request: HttpRequest) -> str:
    requested = (
        request.POST.get("admin_next")
        or request.POST.get("next")
        or request.GET.get("next")
    )
    return safe_next_url(request, requested)


def _oauth_return_url(request: HttpRequest) -> str:
    requested = (
        request.POST.get("oauth_return_to")
        or request.GET.get("return_to")
        or request.GET.get("next")
    )
    return safe_oauth_return_url(request, requested)


def _oauth_error_message(value: str | None) -> str | None:
    try:
        error = OAuthError(value)
    except TypeError, ValueError:
        return None
    return OAUTH_ERROR_MESSAGES[error]
