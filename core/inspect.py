import inspect
from typing import Callable


def is_async(func: Callable):
    is_async_function = inspect.iscoroutinefunction(func)
    is_async_callable_object = inspect.iscoroutinefunction(
        getattr(func, "__call__", None)
    )
    return is_async_function or is_async_callable_object
