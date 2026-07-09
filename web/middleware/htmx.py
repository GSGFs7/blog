from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import markcoroutinefunction
from typing import cast

from django.http import HttpRequest, HttpResponse

from core.inspect import is_async

type SyncGetResponse = Callable[[HttpRequest], HttpResponse]
type AsyncGetResponse = Callable[[HttpRequest], Awaitable[HttpResponse]]
type GetResponse = SyncGetResponse | AsyncGetResponse


@dataclass(frozen=True)
class HtmxDetails:
    request: bool
    boosted: bool
    current_url: str | None
    history_restore_request: bool
    prompt: str | None
    target: str | None
    trigger: str | None
    trigger_name: str | None

    def __bool__(self):
        return self.request


class HtmxHttpRequest(HttpRequest):
    htmx: HtmxDetails


class HtmxMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response
        self.is_async = is_async(get_response)

        if self.is_async:
            markcoroutinefunction(self)

    @staticmethod
    def _attach_htmx_header(request: HttpRequest) -> HtmxHttpRequest:
        headers = request.headers
        request.htmx = HtmxDetails(
            request=headers.get("HX-Request") == "true",
            boosted=headers.get("HX-Boosted") == "true",
            current_url=headers.get("HX-Current-URL"),
            history_restore_request=headers.get("HX-History-Restore-Request") == "true",
            prompt=headers.get("HX-Prompt"),
            target=headers.get("HX-Target"),
            trigger=headers.get("HX-Trigger"),
            trigger_name=headers.get("HX-Trigger-Name"),
        )
        return cast(HtmxHttpRequest, request)

    def __call__(self, request: HttpRequest) -> HttpResponse | Awaitable[HttpResponse]:
        if self.is_async:
            return self.__acall__(request)

        htmx_request = self._attach_htmx_header(request)
        sync_get_response = cast(GetResponse, self.get_response)
        return sync_get_response(htmx_request)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        htmx_request = self._attach_htmx_header(request)
        async_get_response = cast(AsyncGetResponse, self.get_response)
        return await async_get_response(htmx_request)
