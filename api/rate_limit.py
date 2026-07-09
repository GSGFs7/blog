from functools import wraps
from typing import Callable

from django.core.cache import cache
from django.http import HttpRequest

from core.inspect import is_async

__all__ = ["rate_limit"]


def _generate_cache_key(key_prefix: str, client_ip: str) -> str:
    return f"rate_limit:{key_prefix}:{client_ip}"


def _get_client_ip(request: HttpRequest) -> str:
    client_ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if client_ip:
        return client_ip.split(",")[0]
    return request.META.get("REMOTE_ADDR")


def rate_limit(key_prefix: str, max_requests: int, window: int):
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(request: HttpRequest, *args, **kwargs):
            # get ip
            client_ip = _get_client_ip(request)

            cache_key = _generate_cache_key(key_prefix, client_ip)
            await cache.aadd(cache_key, 0, timeout=window)
            current_requests = await cache.aincr(cache_key)
            if current_requests > max_requests:
                return 429, {"message": "Too many request"}

            # run the raw func
            return await func(request, *args, **kwargs)

        @wraps(func)
        def sync_wrapper(request: HttpRequest, *args, **kwargs):
            # get ip
            client_ip = _get_client_ip(request)

            cache_key = _generate_cache_key(key_prefix, client_ip)
            cache.add(cache_key, 0, timeout=window)
            current_requests = cache.incr(cache_key)
            if current_requests > max_requests:
                return 429, {"message": "Too many request"}

            # run the raw func
            return func(request, *args, **kwargs)

        if is_async(func):
            return async_wrapper
        return sync_wrapper

    return decorator
