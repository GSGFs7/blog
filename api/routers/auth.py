import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import alogout
from django.http import HttpRequest, HttpResponseRedirect
from django.middleware import csrf
from django.urls import reverse
from ninja import Router, Status
from ninja.security import APIKeyCookie

from accounts.services.login_flow import aclear_auth_flow
from api.auth import AsyncTimeBaseAuth
from api.models import OAuthIdentity, OAuthProvider
from api.schemas import (
    ClientIdSchema,
    MessageSchema,
    OAuthProviderSchema,
    OAuthSessionSchema,
)
from api.services import (
    OAuthError,
    OAuthProviderResponseError,
    OAuthProviderUnavailable,
    OAuthService,
    safe_oauth_return_url,
)
from api.services.oauth_session import (
    OAUTH_FLOW_SESSION_KEY,
    OAUTH_FLOW_TTL,
    OAUTH_IDENTITY_SESSION_KEY,
    aclear_oauth_session,
)

router = Router()


@router.get("/me", auth=AsyncTimeBaseAuth(), response={200: ClientIdSchema})
async def get_client_id(request: HttpRequest) -> dict[str, str]:
    return {"client_id": str(request.auth)}


# --- OAuth ---

# oauth_router -> "/api/auth/oauth"
oauth_router = Router()
router.add_router("/oauth", oauth_router)


# require Django session cookie
class OAuthSessionCookie(APIKeyCookie):
    param_name = settings.SESSION_COOKIE_NAME

    def authenticate(
        self,
        request: HttpRequest,
        key: str | None,
    ) -> str | None:
        return key


oauth_session = OAuthSessionCookie()


@oauth_router.get("/providers", response=list[OAuthProviderSchema])
async def oauth_providers(request: HttpRequest) -> list[OAuthProvider]:
    return [
        provider
        async for provider in OAuthProvider.objects.filter(is_active=True).order_by(
            "name"
        )
    ]


@oauth_router.get(
    "/{provider_key}/login",
    response={302: None},
)
async def oauth_login(
    request: HttpRequest,
    provider_key: str,
    return_to: str = "/",
) -> HttpResponseRedirect:
    # 0. create the service instance
    try:
        service = await OAuthService.for_provider(provider_key)
    except OAuthProviderUnavailable:
        return _oauth_error_redirect(
            OAuthError.PROVIDER_UNAVAILABLE,
            safe_oauth_return_url(request, return_to),
        )

    user = await request.auser()
    if user.is_authenticated:
        await alogout(request)
    else:
        await aclear_oauth_session(request.session)
        await aclear_auth_flow(request.session)
    await request.session.acycle_key()

    # random
    state = secrets.token_urlsafe(32)
    # PKCE
    verifier, challenge = _pkce_pair()
    # "/api/auth/oauth/github/login" -> "/api/auth/oauth/github/callback"
    callback_path = request.path.removesuffix("/login") + "/callback"
    # absolute it, "https://gsgfs.moe/api/auth/oauth/github/callback"
    redirect_uri = request.build_absolute_uri(callback_path)
    # update state
    await _store_oauth_flow(
        request,
        state,
        {
            "provider_key": provider_key,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "return_to": safe_oauth_return_url(request, return_to),
            "created_at": int(time.time()),
        },
    )

    # add provider id e.g.
    redirect = service.authorization_url(
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=challenge,
    )
    return HttpResponseRedirect(redirect)


@oauth_router.get(
    "/{provider_key}/callback",
    response={302: None},
)
async def oauth_callback(
    request: HttpRequest,
    provider_key: str,
    state: str = "",
    code: str = "",
    error: str = "",
) -> HttpResponseRedirect:
    if not state:
        return _oauth_error_redirect(OAuthError.INVALID_REQUEST)

    flow = await _take_oauth_flow(request, state)
    if flow is None or flow.get("provider_key") != provider_key:
        return _oauth_error_redirect(OAuthError.SESSION_EXPIRED)

    if error:
        return _oauth_error_redirect(
            OAuthError.AUTHORIZATION_REJECTED,
            flow["return_to"],
        )

    if not code:
        return _oauth_error_redirect(OAuthError.INVALID_REQUEST, flow["return_to"])

    # find value
    redirect_uri = flow.get("redirect_uri", "")
    code_verifier = flow.get("code_verifier", "")
    if not redirect_uri or not code_verifier:
        return _oauth_error_redirect(OAuthError.SESSION_EXPIRED, flow["return_to"])

    # code -> user session
    try:
        service = await OAuthService.for_provider(provider_key)
        identity = await service.login(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
    except OAuthProviderUnavailable:
        return _oauth_error_redirect(
            OAuthError.PROVIDER_UNAVAILABLE,
            flow["return_to"],
        )
    except OAuthProviderResponseError:
        return _oauth_error_redirect(OAuthError.PROVIDER_ERROR, flow["return_to"])

    user = await request.auser()
    if user.is_authenticated:
        await alogout(request)
    else:
        await aclear_oauth_session(request.session)
        await aclear_auth_flow(request.session)
    await request.session.acycle_key()
    await request.session.aset(OAUTH_IDENTITY_SESSION_KEY, identity.pk)
    csrf.get_token(request)
    return HttpResponseRedirect(flow["return_to"])


@oauth_router.get(
    "/me",
    auth=oauth_session,
    response={200: OAuthSessionSchema, 401: MessageSchema},
)
async def oauth_me(
    request: HttpRequest,
) -> dict[str, Any] | Status[dict[str, str]]:
    identity_id = await request.session.aget(OAUTH_IDENTITY_SESSION_KEY)
    if not isinstance(identity_id, int):
        return Status(401, {"message": "Not authenticated"})

    try:
        identity = await OAuthIdentity.objects.select_related("guest", "provider").aget(
            pk=identity_id
        )
    except OAuthIdentity.DoesNotExist:
        await request.session.apop(OAUTH_IDENTITY_SESSION_KEY, None)
        return Status(401, {"message": "Not authenticated"})

    return {
        "identity_id": identity.pk,
        "guest_id": identity.guest_id,
        "provider_key": identity.provider.provider_key,
        "user_id": identity.user_id,
        "name": identity.guest.name,
        "email": identity.guest.email,
        "avatar": identity.guest.avatar,
    }


@oauth_router.post(
    "/logout",
    auth=oauth_session,
    response={204: None},
)
async def oauth_logout(request: HttpRequest) -> Status[None]:
    await request.session.apop(OAUTH_IDENTITY_SESSION_KEY, None)
    await request.session.apop(OAUTH_FLOW_SESSION_KEY, None)
    await request.session.acycle_key()
    return Status(204, None)


# --- utils ---


def _pkce_pair() -> tuple[str, str]:
    """
    OAuth PKCE (RFC 7636)

    0. when user login, server create a verifier & verifier's hash(challenge)
    1. user redirect to OAuth server with the 'challenge'
    2. when server use the code which provide by OAuth server, must add the verifier
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def _store_oauth_flow(
    request: HttpRequest,
    state: str,
    flow: dict[str, Any],
) -> None:
    # try get the key from session (in redis)
    flows_old = await request.session.aget(OAUTH_FLOW_SESSION_KEY, {})
    if not isinstance(flows_old, dict):
        flows_old = {}

    # delete expired oauth flow
    now = int(time.time())
    flows = {}
    for key, value in flows_old.items():
        if (
            isinstance(value, dict)
            and now - int(value.get("created_at", 0)) <= OAUTH_FLOW_TTL
        ):
            flows[key] = value

    # add a new flow
    flows[state] = flow
    await request.session.aset(OAUTH_FLOW_SESSION_KEY, flows)


async def _take_oauth_flow(
    request: HttpRequest,
    state: str,
) -> dict[str, Any] | None:
    # try get flows
    flows = await request.session.aget(OAUTH_FLOW_SESSION_KEY, {})
    if not isinstance(flows, dict):
        return None

    # consume the flow
    flow = flows.pop(state, None)
    if flows:
        await request.session.aset(OAUTH_FLOW_SESSION_KEY, flows)
    else:
        await request.session.apop(OAUTH_FLOW_SESSION_KEY, None)
    if not isinstance(flow, dict):
        return None

    # expired?
    try:
        if int(time.time()) - int(flow["created_at"]) > OAUTH_FLOW_TTL:
            return None
    except KeyError, TypeError, ValueError:
        return None
    return flow


# if something goes wrong, back to login page and show a error message
def _oauth_error_redirect(
    error: OAuthError,
    next_url: str = "",
) -> HttpResponseRedirect:
    params = {"oauth_error": error.value}
    if next_url:
        params["next"] = next_url
    return HttpResponseRedirect(f"{reverse('login')}?{urlencode(params)}")
