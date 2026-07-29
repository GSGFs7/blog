from inspect import markcoroutinefunction

from django.http import HttpRequest, HttpResponse
from django.utils.cache import has_vary_header

from core.inspect import is_async
from web.cache import private_page_response
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
    def _is_html_response(response: HttpResponse) -> bool:
        content_type = (
            response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        return content_type == "text/html"

    @classmethod
    def _add_custom_headers(
        cls,
        request: HttpRequest,
        response: HttpResponse,
    ) -> HttpResponse:
        # Cross-Origin Isolation
        # add there two to unlock high permission API
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        # COEP: all external resources must explicitly authorize
        #       (them must respond with CORS header)
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

        # mark as private if not public
        page_cache = response.headers.get("X-Page-Cache")
        if page_cache == "public":
            cache_control = response.headers.get("Cache-Control", "").lower()
            if (
                response.status_code != 200
                or not cls._is_html_response(response)
                or bool(response.cookies)
                or has_vary_header(response, "Cookie")
                or "no-store" in cache_control
            ):
                return private_page_response(response)
            return response

        if page_cache is not None:
            return private_page_response(response)

        is_api = request.path_info == "/api" or request.path_info.startswith("/api/")
        if cls._is_html_response(response) or response.status_code >= 400 or is_api:
            return private_page_response(response)

        return response

    def __call__(self, request: HttpRequest):
        if self.is_async:
            return self.__acall__(request)

        return self._add_custom_headers(request, self.get_response(request))

    async def __acall__(self, request: HttpRequest):
        return self._add_custom_headers(request, await self.get_response(request))
