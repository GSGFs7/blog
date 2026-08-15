from collections.abc import Awaitable, Callable
from functools import partial
from inspect import markcoroutinefunction
from typing import cast

from django.http import HttpRequest, HttpResponse
from django.utils.functional import SimpleLazyObject

from api.models import Guest, OAuthIdentity
from api.services.oauth_session import asession_identity, session_identity
from core.inspect import is_async

type SyncGetResponse = Callable[[HttpRequest], HttpResponse]
type AsyncGetResponse = Callable[[HttpRequest], Awaitable[HttpResponse]]
type GetResponse = SyncGetResponse | AsyncGetResponse


def get_oauth_identity(request: HttpRequest) -> OAuthIdentity | None:
    if not hasattr(request, "_cached_oauth_identity"):
        request._cached_oauth_identity = session_identity(request.session)
    return request._cached_oauth_identity


async def aget_oauth_identity(request: HttpRequest) -> OAuthIdentity | None:
    if not hasattr(request, "_acached_oauth_identity"):
        request._acached_oauth_identity = await asession_identity(request.session)
    return request._acached_oauth_identity


def get_guest(request: HttpRequest) -> Guest | None:
    identity = get_oauth_identity(request)
    return identity.guest if identity is not None else None


async def aget_guest(request: HttpRequest) -> Guest | None:
    identity = await aget_oauth_identity(request)
    return identity.guest if identity is not None else None


class OAuthGuestMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response
        self.is_async = is_async(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    @staticmethod
    def _attach_identity(request: HttpRequest) -> None:
        request.oauth_identity = SimpleLazyObject(lambda: get_oauth_identity(request))
        request.aoauth_identity = partial(aget_oauth_identity, request)
        request.guest = SimpleLazyObject(lambda: get_guest(request))
        request.aguest = partial(aget_guest, request)

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse | Awaitable[HttpResponse]:
        if self.is_async:
            return self.__acall__(request)

        self._attach_identity(request)
        return cast(SyncGetResponse, self.get_response)(request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        self._attach_identity(request)
        return await cast(AsyncGetResponse, self.get_response)(request)
