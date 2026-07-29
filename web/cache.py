from time import time_ns
from typing import TypeVar

from django.http.response import HttpResponseBase

ResponseT = TypeVar("ResponseT", bound=HttpResponseBase)


def _validate(name: str, value: int | None) -> None:
    if value is None:
        return
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _is_html_response(response: HttpResponseBase) -> bool:
    content_type = (
        response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    )
    return content_type == "text/html"


def public_page_response(
    response: ResponseT,
    *,
    edge_max_age: int,
    max_stale: int,
    stale_while_revalidate: int | None = None,
    stale_if_error: int | None = None,
) -> ResponseT:
    ages = {
        "edge_max_age": edge_max_age,
        "max_stale": max_stale,
        "stale_while_revalidate": stale_while_revalidate,
        "stale_if_error": stale_if_error,
    }
    for name, value in ages.items():
        _validate(name, value)

    # avoid cache the error message
    if response.status_code != 200 or not _is_html_response(response):
        raise ValueError("public page response must be a 200 HTML response")

    directive = ["public", f"max-age={edge_max_age}"]
    if stale_while_revalidate is not None:
        # tell CDN send the outdated page & async fetch the new page
        # (prevent cache avalanches)
        directive.append(f"stale-while-revalidate={stale_while_revalidate}")
    if stale_if_error is not None:
        # tell CDN send the outdated page when origin server error
        # (e.g. site version update)
        directive.append(f"stale-if-error={stale_if_error}")

    # tell browser do not cache the page
    # (prevent navigation always based on a outdated page)
    # no-transform: tell CDN do not change the origin server's response (delete CF JSD)
    response.headers["Cache-Control"] = "no-cache, no-transform"
    # tell CF CDN cache the page (cover the above rule)
    response.headers["Cloudflare-CDN-Cache-Control"] = ", ".join(directive)
    response.headers["X-Page-Cache"] = "public"
    response.headers["X-Page-Cache-Max-Stale"] = str(max_stale)
    response.headers["X-Page-Generated-At"] = str(time_ns() // 1_000_000)
    return response


def private_page_response(response: ResponseT) -> ResponseT:
    cache_control = ["private", "no-store"]
    if _is_html_response(response):
        cache_control.append("no-transform")
    response.headers["Cache-Control"] = ", ".join(cache_control)
    response.headers["Cloudflare-CDN-Cache-Control"] = "private, no-store"
    response.headers["X-Page-Cache"] = "private"
    response.headers.pop("X-Page-Cache-Max-Stale", None)
    response.headers.pop("X-Page-Generated-At", None)
    return response
