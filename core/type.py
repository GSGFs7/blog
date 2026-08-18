from typing import Awaitable, Callable

from django.http import HttpRequest, HttpResponse

type SyncGetResponse = Callable[[HttpRequest], HttpResponse]
type AsyncGetResponse = Callable[[HttpRequest], Awaitable[HttpResponse]]
type GetResponse = SyncGetResponse | AsyncGetResponse

__all__ = ("SyncGetResponse", "AsyncGetResponse", "GetResponse")
