from inspect import markcoroutinefunction

from django.http import HttpRequest, HttpResponse

from core.inspect import is_async
from web.middleware.htmx import GetResponse


class HeadersMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse):
        self.get_response = get_response
        self.is_async = is_async(get_response)

        if self.is_async:
            markcoroutinefunction(self)

    @staticmethod
    def _add_custom_headers(response: HttpResponse) -> HttpResponse:
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        return response

    def __call__(self, request: HttpRequest):
        if self.is_async:
            return self.__acall__(request)

        return self._add_custom_headers(self.get_response(request))

    async def __acall__(self, request: HttpRequest):
        return self._add_custom_headers(await self.get_response(request))
