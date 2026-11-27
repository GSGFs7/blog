import asyncio
import ipaddress
import socket
import warnings
from collections.abc import Callable
from contextlib import ExitStack, aclosing, closing
from io import BytesIO
from time import monotonic
from typing import NamedTuple, TypedDict
from urllib.parse import unquote, urljoin, urlsplit

import httpx2
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from PIL import Image as PILImage
from PIL import ImageOps

from core.hash import calculate_blake3_hash
from core.r2 import RateLimited, StorageUnavailable
from media_service.constants import allowed_pil_formats
from media_service.models import Image

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
HostResolver = Callable[[str, int], list[IPAddress]]

__all__ = [
    "AvatarRetryableError",
    "AvatarService",
    "AvatarTransferError",
    "AvatarValidationError",
]


class _Redirect(NamedTuple):
    url: str


class _ClientKwargs(TypedDict):
    timeout: float
    follow_redirects: bool
    trust_env: bool
    limits: httpx2.Limits


_NAT64_WELL_KNOWN_NETWORK = ipaddress.IPv6Network("64:ff9b::/96")
_IPV4_TRANSLATED_NETWORK = ipaddress.IPv6Network("::ffff:0:0:0/96")


class AvatarTransferError(Exception):
    pass


class AvatarValidationError(AvatarTransferError):
    pass


class AvatarRetryableError(AvatarTransferError):
    pass


class _AvatarDownloader:
    MAX_BYTES = 5 * 1024 * 1024
    DEFAULT_TIMEOUT = 10.0
    MAX_REDIRECTS = 3

    REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
    RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = MAX_BYTES,
        allow_http: bool = False,
        resolver: HostResolver | None = None,
        transport: httpx2.BaseTransport | None = None,
        async_transport: httpx2.AsyncBaseTransport | None = None,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.allow_http = allow_http
        self._resolver = resolver
        self._transport = transport
        self._async_transport = async_transport

    @staticmethod
    def is_public_ip(ip: IPAddress) -> bool:
        if isinstance(ip, ipaddress.IPv6Address):
            if ip.scope_id is not None:
                return False
            if ip.ipv4_mapped is not None:
                ip = ip.ipv4_mapped
            elif ip in _NAT64_WELL_KNOWN_NETWORK or ip in _IPV4_TRANSLATED_NETWORK:
                ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        return ip.is_global and not ip.is_multicast

    @staticmethod
    def _resolve_host_ips(hostname: str, port: int) -> list[IPAddress]:
        try:
            return [ipaddress.ip_address(hostname)]
        except ValueError:
            pass

        try:
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise AvatarRetryableError("Failed to resolve avatar host") from exc

        ips: list[IPAddress] = []
        for info in infos:
            sockaddr = info[4]
            if sockaddr:
                ips.append(ipaddress.ip_address(sockaddr[0]))

        if not ips:
            raise AvatarRetryableError("Avatar host resolved to no addresses")
        return ips

    def _resolve_remote_url(self, url: str) -> tuple[httpx2.URL, list[IPAddress]]:
        try:
            authority = urlsplit(url).netloc
            parsed = httpx2.URL(url)
        except (ValueError, httpx2.InvalidURL) as exc:
            raise AvatarValidationError("Avatar URL is invalid") from exc
        allowed_schemes = {"https", "http"} if self.allow_http else {"https"}
        if parsed.scheme not in allowed_schemes:
            raise AvatarValidationError("Avatar URL scheme is not allowed")
        if not parsed.raw_host or parsed.userinfo or "@" in authority:
            raise AvatarValidationError("Avatar URL is invalid")

        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80
        if not 1 <= port <= 65535:
            raise AvatarValidationError("Avatar URL port is invalid")

        resolver = self._resolver or self._resolve_host_ips
        ips = resolver(parsed.raw_host.decode("ascii"), port)
        if not ips or any(not self.is_public_ip(ip) for ip in ips):
            raise AvatarValidationError("Avatar host is not allowed")

        return parsed, list(dict.fromkeys(ips))

    @staticmethod
    def _remaining_timeout(deadline: float) -> float:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AvatarRetryableError("Avatar download timed out")
        return remaining

    @staticmethod
    def _avatar_request(
        client: httpx2.Client | httpx2.AsyncClient,
        url: httpx2.URL,
        ip: IPAddress,
        timeout: float,
    ) -> httpx2.Request:
        return client.build_request(
            "GET",
            url.copy_with(host=str(ip)),
            headers={"Accept": "image/*", "Host": url.netloc.decode("ascii")},
            extensions={"sni_hostname": url.raw_host.decode("ascii")},
            timeout=timeout,
        )

    def _send_avatar_request(
        self,
        client: httpx2.Client,
        url: httpx2.URL,
        ips: list[IPAddress],
        deadline: float,
    ) -> httpx2.Response:
        last_error = None
        for ip in ips:
            request = self._avatar_request(
                client, url, ip, self._remaining_timeout(deadline)
            )
            try:
                return client.send(request, stream=True)
            except (httpx2.ConnectError, httpx2.ConnectTimeout) as exc:
                last_error = exc
        self._remaining_timeout(deadline)
        raise AvatarRetryableError("Failed to connect to avatar host") from last_error

    async def _asend_avatar_request(
        self,
        client: httpx2.AsyncClient,
        url: httpx2.URL,
        ips: list[IPAddress],
        deadline: float,
    ) -> httpx2.Response:
        last_error = None
        for ip in ips:
            request = self._avatar_request(
                client, url, ip, self._remaining_timeout(deadline)
            )
            try:
                return await client.send(request, stream=True)
            except (httpx2.ConnectError, httpx2.ConnectTimeout) as exc:
                last_error = exc
        self._remaining_timeout(deadline)
        raise AvatarRetryableError("Failed to connect to avatar host") from last_error

    def _check_response_headers(self, response: httpx2.Response) -> None:
        if (
            response.status_code in self.RETRYABLE_STATUS_CODES
            or response.status_code >= 500
        ):
            raise AvatarRetryableError(
                f"Upstream avatar error: HTTP {response.status_code}"
            )
        if response.status_code != 200:
            raise AvatarValidationError(
                f"Unexpected avatar status: HTTP {response.status_code}"
            )

        content_length = response.headers.get("content-length")
        if content_length is None:
            return
        try:
            if int(content_length) > self.max_bytes:
                raise AvatarValidationError("Avatar exceeds maximum size")
        except ValueError:
            return

    @staticmethod
    def _resolve_redirect_url(original_url: httpx2.URL, location: str) -> str:
        try:
            return urljoin(str(original_url), location)
        except ValueError as exc:
            raise AvatarValidationError("Avatar redirect URL is invalid") from exc

    def _client_kwargs(self) -> _ClientKwargs:
        return {
            "timeout": self.timeout,
            "follow_redirects": False,
            "trust_env": False,
            "limits": httpx2.Limits(max_keepalive_connections=0),
        }

    def _get_redirect_url(
        self, original_url: httpx2.URL, response: httpx2.Response
    ) -> str | None:
        if response.status_code not in self.REDIRECT_STATUS_CODES:
            return None
        location = response.headers.get("location")
        if not location:
            raise AvatarValidationError("Avatar redirect missing location")
        return self._resolve_redirect_url(original_url, location)

    def _append_chunk(self, buffer: BytesIO, chunk: bytes, deadline: float) -> None:
        self._remaining_timeout(deadline)
        if buffer.tell() + len(chunk) > self.max_bytes:
            raise AvatarValidationError("Avatar exceeds maximum size")
        buffer.write(chunk)

    def _finalize_body(self, buffer: BytesIO, deadline: float) -> bytes:
        self._remaining_timeout(deadline)
        if buffer.tell() == 0:
            raise AvatarValidationError("Avatar response is empty")
        return buffer.getvalue()

    def _read_response_body(self, response: httpx2.Response, deadline: float) -> bytes:
        buffer = BytesIO()
        for chunk in response.iter_bytes():
            self._append_chunk(buffer, chunk, deadline)
        return self._finalize_body(buffer, deadline)

    async def _aread_response_body(
        self, response: httpx2.Response, deadline: float
    ) -> bytes:
        buffer = BytesIO()
        async for chunk in response.aiter_bytes():
            self._append_chunk(buffer, chunk, deadline)
        return self._finalize_body(buffer, deadline)

    def _fetch_once(
        self, client: httpx2.Client, url: str, deadline: float
    ) -> bytes | _Redirect:
        self._remaining_timeout(deadline)
        original_url, ips = self._resolve_remote_url(url)
        try:
            with closing(
                self._send_avatar_request(client, original_url, ips, deadline)
            ) as response:
                self._remaining_timeout(deadline)
                if next_url := self._get_redirect_url(original_url, response):
                    return _Redirect(next_url)
                self._check_response_headers(response)
                return self._read_response_body(response, deadline)
        except httpx2.HTTPError as exc:
            raise AvatarRetryableError("Failed to download avatar") from exc

    async def _afetch_once(
        self, client: httpx2.AsyncClient, url: str, deadline: float
    ) -> bytes | _Redirect:
        self._remaining_timeout(deadline)
        original_url, ips = await asyncio.to_thread(self._resolve_remote_url, url)
        try:
            async with aclosing(
                await self._asend_avatar_request(client, original_url, ips, deadline)
            ) as response:
                self._remaining_timeout(deadline)
                if next_url := self._get_redirect_url(original_url, response):
                    return _Redirect(next_url)
                self._check_response_headers(response)
                return await self._aread_response_body(response, deadline)
        except httpx2.HTTPError as exc:
            raise AvatarRetryableError("Failed to download avatar") from exc

    def download(self, url: str) -> bytes:
        deadline = monotonic() + self.timeout
        current_url = url
        with httpx2.Client(
            **self._client_kwargs(), transport=self._transport
        ) as client:
            for _ in range(self.MAX_REDIRECTS + 1):
                result = self._fetch_once(client, current_url, deadline)
                if isinstance(result, bytes):
                    return result
                client.cookies.clear()
                current_url = result.url

        raise AvatarValidationError("Too many avatar redirects")

    async def adownload(self, url: str) -> bytes:
        deadline = monotonic() + self.timeout
        current_url = url
        async with httpx2.AsyncClient(
            **self._client_kwargs(), transport=self._async_transport
        ) as client:
            for _ in range(self.MAX_REDIRECTS + 1):
                result = await self._afetch_once(client, current_url, deadline)
                if isinstance(result, bytes):
                    return result
                client.cookies.clear()
                current_url = result.url

        raise AvatarValidationError("Too many avatar redirects")


class _AvatarNormalizer:
    AVATAR_SIZE = 160
    WEBP_QUALITY = 85

    def __init__(
        self,
        *,
        size: int = AVATAR_SIZE,
        webp_quality: int = WEBP_QUALITY,
    ):
        self.size = size
        self.webp_quality = webp_quality

    def normalize(self, raw_bytes: bytes) -> bytes:
        source_io = BytesIO(raw_bytes)
        try:
            Image._inspect_image(source_io)
        except ValidationError as exc:
            raise AvatarValidationError("; ".join(exc.messages)) from exc
        except Exception as exc:
            raise AvatarValidationError("Invalid or corrupted avatar image") from exc

        try:
            with ExitStack() as stack:
                stack.enter_context(warnings.catch_warnings(record=False))
                warnings.simplefilter("error", PILImage.DecompressionBombWarning)
                source_io.seek(0)
                opened = stack.enter_context(
                    PILImage.open(source_io, formats=allowed_pil_formats())
                )
                if getattr(opened, "is_animated", False):
                    opened.seek(0)
                image = ImageOps.exif_transpose(opened)
                if image is not opened:
                    stack.callback(image.close)
                has_alpha = (
                    image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info
                )
                converted = stack.enter_context(
                    image.convert("RGBA" if has_alpha else "RGB")
                )
                side = min(converted.width, converted.height, self.size)
                fitted = stack.enter_context(
                    ImageOps.fit(
                        converted,
                        (side, side),
                        method=PILImage.Resampling.LANCZOS,
                    )
                )
                output = BytesIO()
                fitted.save(
                    output,
                    format="WEBP",
                    quality=self.webp_quality,
                    method=4,
                )
                return output.getvalue()
        except (
            PILImage.DecompressionBombWarning,
            PILImage.DecompressionBombError,
        ) as exc:
            raise AvatarValidationError("Avatar exceeds safe decoding limit") from exc
        except Exception as exc:
            raise AvatarValidationError("Failed to process avatar image") from exc


class _AvatarStore:
    MAX_MANAGED_URL_LENGTH = 500

    def __init__(self, *, storage: Storage | None = None):
        self._storage = storage

    @property
    def storage(self) -> Storage:
        return self._storage or default_storage

    @classmethod
    def is_managed_url(cls, url: str) -> bool:
        if (
            not url
            or len(url) > cls.MAX_MANAGED_URL_LENGTH
            or "?" in url
            or "#" in url
            or any(c.isspace() or ord(c) <= 0x20 or ord(c) == 0x7F for c in url)
        ):
            return False

        try:
            parsed = urlsplit(url)
            media = urlsplit(f"{settings.MEDIA_URL.rstrip('/')}/avatars/")
        except ValueError:
            return False
        if "@" in parsed.netloc or (url.startswith("//") and not parsed.netloc):
            return False

        origins = [(media.scheme.lower(), media.netloc.lower(), media.path)]
        s3_domain = getattr(settings, "S3_PUBLIC_DOMAIN", "")
        if s3_domain and "://" not in s3_domain:
            s3_domain = f"https://{s3_domain}"
        for origin in (settings.IMAGE_CDN_ORIGIN, s3_domain):
            try:
                base = urlsplit(origin)
            except ValueError:
                continue
            if base.scheme in {"http", "https"} and base.netloc:
                origins.append(
                    (
                        base.scheme,
                        base.netloc.lower(),
                        f"{base.path.rstrip('/')}/avatars/",
                    )
                )

        url_origin = (parsed.scheme.lower(), parsed.netloc.lower())
        for scheme, netloc, prefix in origins:
            if url_origin == (scheme, netloc) and parsed.path.startswith(prefix):
                subpath = parsed.path.removeprefix(prefix)
                if all(
                    "\\" not in path
                    and not any(
                        segment in {"", ".", ".."} for segment in path.split("/")
                    )
                    for path in (subpath, unquote(subpath))
                ):
                    return True
        return False

    def save(self, webp_bytes: bytes) -> str:
        checksum = calculate_blake3_hash(webp_bytes)
        key = f"avatars/{checksum[:2]}/{checksum[2:4]}/{checksum}.webp"
        target_storage = self.storage
        try:
            if not target_storage.exists(key):
                content = ContentFile(webp_bytes, name=f"{checksum}.webp")
                content.content_type = "image/webp"
                key = target_storage.save(key, content)
            return target_storage.url(key)
        except (StorageUnavailable, RateLimited) as exc:
            raise AvatarRetryableError("Avatar storage unavailable") from exc
        except OSError as exc:
            raise AvatarRetryableError("Failed to write avatar to storage") from exc


class AvatarService:
    AVATAR_SIZE = _AvatarNormalizer.AVATAR_SIZE
    MAX_BYTES = _AvatarDownloader.MAX_BYTES
    MAX_MANAGED_URL_LENGTH = _AvatarStore.MAX_MANAGED_URL_LENGTH
    LOGIN_TIMEOUT = 2.5
    BACKGROUND_TIMEOUT = _AvatarDownloader.DEFAULT_TIMEOUT
    MAX_REDIRECTS = _AvatarDownloader.MAX_REDIRECTS
    WEBP_QUALITY = _AvatarNormalizer.WEBP_QUALITY

    def __init__(
        self,
        *,
        timeout: float = BACKGROUND_TIMEOUT,
        max_bytes: int = MAX_BYTES,
        allow_http: bool = False,
        storage: Storage | None = None,
        resolver: HostResolver | None = None,
        transport: httpx2.BaseTransport | None = None,
        async_transport: httpx2.AsyncBaseTransport | None = None,
    ):
        self._downloader = _AvatarDownloader(
            timeout=timeout,
            max_bytes=max_bytes,
            allow_http=allow_http,
            resolver=resolver,
            transport=transport,
            async_transport=async_transport,
        )
        self._normalizer = _AvatarNormalizer()
        self._store = _AvatarStore(storage=storage)

    @property
    def timeout(self) -> float:
        return self._downloader.timeout

    @property
    def storage(self) -> Storage:
        return self._store.storage

    @classmethod
    def is_managed_url(cls, url: str) -> bool:
        return _AvatarStore.is_managed_url(url)

    def mirror(self, url: str) -> str:
        if self._store.is_managed_url(url):
            return url

        raw_bytes = self._downloader.download(url)
        webp_bytes = self._normalizer.normalize(raw_bytes)
        return self._store.save(webp_bytes)

    async def amirror(self, url: str) -> str:
        if self._store.is_managed_url(url):
            return url

        raw_bytes = await self._downloader.adownload(url)
        webp_bytes = await asyncio.to_thread(self._normalizer.normalize, raw_bytes)
        return await asyncio.to_thread(self._store.save, webp_bytes)
