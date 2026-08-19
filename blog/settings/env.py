"""makesure this file NOT imported other settings file"""

import os
from pathlib import Path
from typing import overload

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

_TRUE_VALUE = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


@overload
def get_str(name: str) -> str | None: ...


@overload
def get_str(name: str, default: str) -> str: ...


def get_str(name: str, default: str | None = None) -> str | None:
    """DO NOT set default to an empty str. it will case some type hint error"""

    value = os.environ.get(name)
    return value.strip() if value is not None and value.strip() else default


def get_bool(name: str, default: bool = False) -> bool:
    value = get_str(name)
    if value is None:
        return default

    normalized = value.lower()
    if normalized in _TRUE_VALUE:
        return True
    if normalized in _FALSE_VALUES:
        return False

    raise RuntimeError(f"{name} must be a boolean, got {value!r}")


def get_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}") from exc


def get_list(name: str, default: str = "") -> list[str]:
    return [
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    ]


def require(name: str) -> str:
    value = get_str(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def is_docker_env() -> bool:
    return get_bool("DOCKER_ENV")


def is_k8s_env() -> bool:
    return get_bool("K8S_ENV")


def is_debug() -> bool:
    return get_bool("DEBUG")
