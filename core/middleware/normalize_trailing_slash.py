from inspect import markcoroutinefunction
from typing import Awaitable, cast

from django.http import HttpResponse
from django.http.request import HttpRequest
from django.shortcuts import redirect
from django.urls import Resolver404, resolve

from core.inspect import is_async
from core.type import AsyncGetResponse, GetResponse, SyncGetResponse


class NormalizeTrailingSlashMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response
        self.is_async = is_async(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse | Awaitable[HttpResponse]:
        if self.is_async:
            return self.__acall__(request)

        normalized = self._normalize(request)
        if normalized is not None:
            return normalized

        return cast(SyncGetResponse, self.get_response)(request)

    async def __acall__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        normalized = self._normalize(request)
        if normalized is not None:
            return normalized

        return await cast(AsyncGetResponse, self.get_response)(request)

    @staticmethod
    def _normalize(request: HttpRequest) -> HttpResponse | None:
        path_info = request.path_info
        if path_info == "/" or not path_info.endswith("/"):
            return None

        # bypass if can resolve
        urlconf = getattr(request, "urlconf", None)
        try:
            resolve(path_info, urlconf=urlconf)
        except Resolver404:
            pass
        else:
            return None

        # check if normalized path exist
        normalized_path = path_info.rstrip("/")
        try:
            resolve(normalized_path, urlconf=urlconf)
        except Resolver404:
            return None

        full_path, separator, query = request.get_full_path().partition("?")
        target = full_path.rstrip("/")
        if separator:
            target = f"{target}?{query}"

        return redirect(target, permanent=True, preserve_request=True)
