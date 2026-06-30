import base64
import hashlib
import secrets
import time

from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect
from django.middleware import csrf
from django.utils.http import url_has_allowed_host_and_scheme
from ninja import Router
from ninja.security import APIKeyCookie

from api.auth import AsyncTimeBaseAuth
from api.models import OAuthIdentity, OAuthProvider
from api.schemas import (
    ClientIdSchema,
    MessageSchema,
    OAuthProviderSchema,
    OAuthSessionSchema,
)
from api.services import (
    OAuthProviderResponseError,
    OAuthProviderUnavailable,
    OAuthService,
)

router = Router()


@router.get("/me", auth=AsyncTimeBaseAuth(), response={200: ClientIdSchema})
async def get_client_id(request):
    return {"client_id": str(request.auth)}


# --- OAuth ---

# oauth_router -> "/api/auth/oauth"
oauth_router = Router()
router.add_router("/oauth", oauth_router)


OAUTH_FLOW_SESSION_KEY = "oauth_flows"
OAUTH_IDENTITY_SESSION_KEY = "oauth_identity_id"
OAUTH_FLOW_TTL = 600


# require Django session cookie
class OAuthSessionCookie(APIKeyCookie):
    param_name = settings.SESSION_COOKIE_NAME

    def authenticate(self, request: HttpRequest, key: str | None):
        return key


oauth_session = OAuthSessionCookie()


@oauth_router.get("/providers", response=list[OAuthProviderSchema])
async def oauth_providers(request: HttpRequest):
    return [
        provider
        async for provider in OAuthProvider.objects.filter(is_active=True).order_by(
            "name"
        )
    ]


@oauth_router.get(
    "/{provider_key}/login",
    response={302: None, 404: MessageSchema},
)
async def oauth_login(request: HttpRequest, provider_key: str, return_to: str = "/"):
    # 0. create the service instance
    try:
        service = await OAuthService.for_provider(provider_key)
    except OAuthProviderUnavailable:
        return 404, {"message": "OAuth provider not found"}

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
            "return_to": _safe_return_url(request, return_to),
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
    response={302: None, 400: MessageSchema, 404: MessageSchema, 502: MessageSchema},
)
async def oauth_callback(
    request: HttpRequest,
    provider_key: str,
    state: str = "",
    code: str = "",
    error: str = "",
):
    if not state:
        return 400, {"message": "Missing OAuth state"}

    flow = await _take_oauth_flow(request, state)
    if flow is None or flow.get("provider_key") != provider_key:
        return 400, {"message": "Invalid or expired OAuth state"}

    if error:
        return 400, {"message": "OAuth authorization was rejected"}

    if not code:
        return 400, {"message": "Missing OAuth authorization code"}

    # find value
    redirect_uri = flow.get("redirect_uri", "")
    code_verifier = flow.get("code_verifier", "")
    if not redirect_uri or not code_verifier:
        return 400, {"message": "invalid session state"}

    # code -> user session
    try:
        service = await OAuthService.for_provider(provider_key)
        identity = await service.login(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
    except OAuthProviderUnavailable:
        return 404, {"message": "OAuth provider not found"}
    except OAuthProviderResponseError:
        return 502, {"message": "OAuth provider request failed"}

    # session fixation protect. never trust the session id before user login
    await request.session.acycle_key()
    # set identity
    await request.session.aset(OAUTH_IDENTITY_SESSION_KEY, identity.pk)
    # init csrf
    csrf.get_token(request)
    return HttpResponseRedirect(flow["return_to"])


@oauth_router.get(
    "/me",
    auth=oauth_session,
    response={200: OAuthSessionSchema, 401: MessageSchema},
)
async def oauth_me(request: HttpRequest):
    identity_id = await request.session.aget(OAUTH_IDENTITY_SESSION_KEY)
    if not isinstance(identity_id, int):
        return 401, {"message": "Not authenticated"}

    try:
        identity = await OAuthIdentity.objects.select_related("guest", "provider").aget(
            pk=identity_id
        )
    except OAuthIdentity.DoesNotExist:
        await request.session.apop(OAUTH_IDENTITY_SESSION_KEY, None)
        return 401, {"message": "Not authenticated"}

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
async def oauth_logout(request):
    await request.session.apop(OAUTH_IDENTITY_SESSION_KEY, None)
    await request.session.apop(OAUTH_FLOW_SESSION_KEY, None)
    await request.session.acycle_key()
    return 204, None


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


def _safe_return_url(request: HttpRequest, return_to: str) -> str:
    if url_has_allowed_host_and_scheme(
        return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return return_to
    return "/"


async def _store_oauth_flow(request: HttpRequest, state: str, flow: dict) -> None:
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


async def _take_oauth_flow(request: HttpRequest, state: str) -> dict | None:
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
    except (KeyError, TypeError, ValueError):
        return None
    return flow
