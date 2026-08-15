from functools import lru_cache
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)
from typing import Any

from django.conf import settings
from django.http import HttpRequest

IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network


def get_client_ip(request: HttpRequest) -> str | None:
    """get user ip. optimized for CF CDN( & k8s)"""

    remote_address = _parse_ip(request.META.get("REMOTE_ADDR"))
    if remote_address is None:
        return None
    # check is proxied by ingress
    if not _is_trusted_proxy(remote_address):
        return remote_address.compressed

    # if proxied is trusted, check CF's header
    for header in ("HTTP_CF_CONNECTING_IPV6", "HTTP_CF_CONNECTING_IP"):
        client_address = _parse_ip(request.META.get(header))
        if client_address is not None:
            return client_address.compressed
    return None


def _parse_ip(value: Any) -> IPAddress | None:
    if not isinstance(value, str) or "%" in value:
        return None
    try:
        return ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted_proxy(address: IPAddress) -> bool:
    cidrs = tuple(getattr(settings, "TRUSTED_PROXY_CIDRS", ()))
    return any(address in network for network in _proxy_networks(cidrs))


@lru_cache
def _proxy_networks(cidrs: tuple[str, ...]) -> tuple[IPNetwork, ...]:
    return tuple(ip_network(cidr) for cidr in cidrs)
