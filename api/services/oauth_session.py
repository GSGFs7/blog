from django.contrib.sessions.backends.base import SessionBase

from api.models import OAuthIdentity

OAUTH_FLOW_SESSION_KEY = "oauth_flows"
OAUTH_IDENTITY_SESSION_KEY = "oauth_identity_id"
OAUTH_FLOW_TTL = 600


def clear_oauth_session(session: SessionBase) -> None:
    session.pop(OAUTH_IDENTITY_SESSION_KEY, None)
    session.pop(OAUTH_FLOW_SESSION_KEY, None)


async def aclear_oauth_session(session: SessionBase) -> None:
    await session.apop(OAUTH_IDENTITY_SESSION_KEY, None)
    await session.apop(OAUTH_FLOW_SESSION_KEY, None)


def session_identity(session: SessionBase) -> OAuthIdentity | None:
    identity_id = session.get(OAUTH_IDENTITY_SESSION_KEY)
    if not isinstance(identity_id, int):
        return None

    identity = (
        OAuthIdentity.objects.select_related("guest", "provider")
        .defer("access_token", "refresh_token", "extra_data")
        .filter(pk=identity_id)
        .first()
    )
    if identity is None:
        session.pop(OAUTH_IDENTITY_SESSION_KEY, None)
    return identity


async def asession_identity(session: SessionBase) -> OAuthIdentity | None:
    identity_id = await session.aget(OAUTH_IDENTITY_SESSION_KEY)
    if not isinstance(identity_id, int):
        return None

    identity = await (
        OAuthIdentity.objects.select_related("guest", "provider")
        .defer("access_token", "refresh_token", "extra_data")
        .filter(pk=identity_id)
        .afirst()
    )
    if identity is None:
        await session.apop(OAUTH_IDENTITY_SESSION_KEY, None)
    return identity
