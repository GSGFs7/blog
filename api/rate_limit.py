from functools import wraps
from typing import Callable

from django.core.cache import cache
from django.http import HttpRequest

from core.inspect import is_async
from core.request import get_client_ip

__all__ = ["rate_limit"]


def _generate_cache_key(key_prefix: str, client_ip: str) -> str:
    return f"rate_limit:{key_prefix}:{client_ip}"


def rate_limit(key_prefix: str, max_requests: int, window: int):
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(request: HttpRequest, *args, **kwargs):
            # get ip
            client_ip = get_client_ip(request)
            if client_ip is None:
                return await func(request, *args, **kwargs)

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
            client_ip = get_client_ip(request)
            if client_ip is None:
                return func(request, *args, **kwargs)

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
