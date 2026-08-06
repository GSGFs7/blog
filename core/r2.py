import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from types import TracebackType
from typing import Literal, Mapping, Protocol
from urllib.parse import quote, quote_from_bytes, unquote_to_bytes, urlsplit
from xml.etree import ElementTree

import httpx2

__all__ = (
    "AsyncObjectStore",
    "AsyncR2Client",
    "AuthenticationFailed",
    "InvalidObjectRequest",
    "ObjectBody",
    "ObjectMetadata",
    "ObjectNotFound",
    "ObjectNotModified",
    "ObjectPage",
    "ObjectPutResult",
    "PreconditionFailed",
    "RateLimited",
    "SignatureMismatch",
    "StorageUnavailable",
    "SyncObjectStore",
    "SyncR2Client",
)

EMPTY_PAYLOAD_HASH = sha256(b"").hexdigest()


# --- results ---


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    key: str
    size: int | None = None
    etag: str | None = None
    content_type: str | None = None
    cache_control: str | None = None
    content_disposition: str | None = None
    content_encoding: str | None = None
    last_modified: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_response(cls, key: str, response: httpx2.Response):
        headers = response.headers
        size = None
        if value := headers.get("content-length"):
            try:
                size = int(value)
            except ValueError:
                pass

        last_modified = None
        if value := headers.get("last-modified"):
            try:
                last_modified = parsedate_to_datetime(value)
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=timezone.utc)
                else:
                    last_modified = last_modified.astimezone(timezone.utc)
            except TypeError, ValueError:
                pass

        metadata = {
            name.removeprefix("x-amz-meta-"): value
            for name, value in headers.items()
            if name.lower().startswith("x-amz-meta-")
        }
        return cls(
            key=key,
            size=size,
            etag=headers.get("etag"),
            content_type=headers.get("content-type"),
            cache_control=headers.get("cache-control"),
            content_disposition=headers.get("content-disposition"),
            content_encoding=headers.get("content-encoding"),
            last_modified=last_modified,
            metadata=metadata,
        )


class ObjectBody:
    def __init__(self, key: str, response: httpx2.Response, metadata: ObjectMetadata):
        self.key = key
        self.response = response
        self.metadata = metadata

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        await self.aclose()

    async def aclose(self):
        await self.response.aclose()

    async def aiter_bytes(self, chunk_size: int = 64 * 1024):
        async for chunk in self.response.aiter_bytes(chunk_size):
            yield chunk

    async def read(self) -> bytes:
        return await self.response.aread()


class ObjectPutResult:
    pass


class ObjectPage:
    pass


# --- exceptions ---


class ObjectStoreError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        super().__init__(message)


class ObjectNotFound(ObjectStoreError):
    pass


class PreconditionFailed(ObjectStoreError):
    pass


class AuthenticationFailed(ObjectStoreError):
    pass


class RateLimited(ObjectStoreError):
    pass


class StorageUnavailable(ObjectStoreError):
    pass


class ObjectNotModified(ObjectStoreError):
    pass


class SignatureMismatch(ObjectStoreError):
    pass


class InvalidObjectRequest(ObjectStoreError):
    pass


# --- protocol ---


class SyncObjectStore(Protocol):
    def stat(self, key: str) -> ObjectMetadata: ...
    def get(
        self,
        key: str,
        *,
        byte_range: str | None = None,
        if_none_match: str | None = None,
    ) -> ObjectBody: ...
    def put(
        self,
        key: str,
        body,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
        metadata: Mapping[str, str] | None = None,
        if_none_match: str | None = None,
    ) -> ObjectPutResult: ...
    def delete(self, key: str) -> None: ...
    def list(
        self,
        *,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 1000,
    ) -> ObjectPage: ...


class AsyncObjectStore(Protocol):
    async def stat(self, key: str) -> ObjectMetadata: ...
    async def get(
        self,
        key: str,
        *,
        byte_range: str | None = None,
        if_none_match: str | None = None,
    ) -> ObjectBody: ...
    async def put(
        self,
        key: str,
        body,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
        metadata: Mapping[str, str] | None = None,
        if_none_match: str | None = None,
    ) -> ObjectPutResult: ...
    async def delete(self, key: str) -> None: ...
    async def list(
        self,
        *,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 1000,
    ) -> ObjectPage: ...


# --- implement ---


class SyncR2Client(SyncObjectStore):
    pass


class AsyncR2Client(AsyncObjectStore):
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        *,
        session_token: str | None = None,
        timeout: float = 30.0,
        client: httpx2.AsyncClient | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
    ):
        # endpoint accept "https://hostname[:port]"
        endpoint_parts = urlsplit(endpoint)
        try:
            # urlsplit("https://example.com:bad") <- it will raise an Exception
            _ = endpoint_parts.port
        except ValueError as exc:
            raise ValueError("R2 endpoint contains an invalid port") from exc
        if (
            endpoint != endpoint.strip()
            or endpoint_parts.scheme != "https"
            or endpoint_parts.hostname is None
            or endpoint_parts.username is not None
            or endpoint_parts.password is not None
            or endpoint_parts.path not in {"", "/"}
            or endpoint_parts.query
            or endpoint_parts.fragment
        ):
            raise ValueError(
                "R2 endpoint must be an HTTPS origin without "
                "credentials, path, query, or fragment"
            )

        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.signer = SigV4Signer(
            access_key=access_key,
            secret_key=secret_key,
            region="auto",
            service="s3",
            session_token=session_token,
        )
        self.client = client or httpx2.AsyncClient(timeout=timeout, transport=transport)
        self._owns_client = client is None

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        await self.aclose()

    async def aclose(self):
        if self._owns_client:
            await self.client.aclose()

    async def get(
        self,
        key: str,
        *,
        byte_range: str | None = None,
        if_none_match: str | None = None,
    ) -> ObjectBody:
        url = self._object_url(key)

        headers = {
            "x-amz-content-sha256": EMPTY_PAYLOAD_HASH,
        }
        if byte_range is not None:
            headers["range"] = byte_range
        if if_none_match is not None:
            headers["if-none-match"] = if_none_match

        headers = self.signer.sign("GET", url, headers, EMPTY_PAYLOAD_HASH)
        try:
            request = self.client.build_request("GET", url, headers=headers)
            response = await self.client.send(request, stream=True)
        except httpx2.HTTPError as exc:
            raise StorageUnavailable("R2 GET request failed") from exc

        if response.status_code == 304:
            await response.aclose()
            raise ObjectNotModified(key, status_code=response.status_code)
        if response.status_code >= 400:
            try:
                error_body = await response.aread()
            except httpx2.HTTPError as exc:
                await response.aclose()
                raise StorageUnavailable("R2 error response could not be read") from exc
            error = self._map_error(response, error_body, key=key)
            await response.aclose()
            raise error

        return ObjectBody(
            key=key,
            response=response,
            metadata=ObjectMetadata.from_response(key, response),
        )

    def _object_url(self, key: str) -> str:
        return (
            f"{self.endpoint.rstrip('/')}/"
            f"{quote(self.bucket, safe='')}/"
            f"{self._quote_key(key)}"
        )

    @staticmethod
    def _quote_key(key: str) -> str:
        return "/".join(
            "%2E"
            if segment == "."
            else "%2E%2E"
            if segment == ".."
            else quote(segment, safe="~")
            for segment in key.split("/")
        )

    @staticmethod
    def _map_error(
        response: httpx2.Response,
        body: bytes,
        *,
        key: str | None = None,
    ) -> ObjectStoreError:
        code = response.headers.get("x-amz-error-code")
        message = None
        request_id = response.headers.get("x-amz-request-id") or response.headers.get(
            "cf-ray"
        )

        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            root = None
        if root is not None:
            for element in root.iter():
                name = element.tag.rsplit("}", 1)[-1]
                if name == "Code" and element.text:
                    code = element.text
                elif name == "Message" and element.text:
                    message = element.text
                elif name == "RequestId" and element.text:
                    request_id = element.text

        status_code = response.status_code
        if code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket", "NotFound"} or (
            status_code == 404
        ):
            error_type = ObjectNotFound
        elif code == "PreconditionFailed" or status_code == 412:
            error_type = PreconditionFailed
        elif code == "SignatureDoesNotMatch":
            error_type = SignatureMismatch
        elif status_code in {401, 403} or code in {
            "AccessDenied",
            "InvalidAccessKeyId",
        }:
            error_type = AuthenticationFailed
        elif status_code == 429 or code in {"SlowDown", "Throttling"}:
            error_type = RateLimited
        elif status_code >= 500 or status_code == 408:
            error_type = StorageUnavailable
        else:
            error_type = InvalidObjectRequest

        if error_type is ObjectNotFound and key:
            detail = key
        else:
            detail = message or code or f"R2 request failed with HTTP {status_code}"
        return error_type(
            detail,
            status_code=status_code,
            code=code,
            request_id=request_id,
        )


# --- signer ---
# docs: https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sig-v4-authenticating-requests.html
#       https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html


@dataclass(frozen=True, slots=True)
class SigV4Signer:
    access_key: str
    secret_key: str
    region: str = "auto"
    service: str = "s3"
    session_token: str | None = None  # temporary certificate need this

    def sign(
        self,
        method: Literal["DELETE", "GET", "HEAD", "POST", "PUT"],
        url: str,
        headers: Mapping[str, str],
        payload_hash: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, str]:
        now = self._utc_now(now)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        parts = urlsplit(url)

        request_headers = {
            name.strip().lower(): self._normalize_header_value(str(value))
            for name, value in headers.items()
            if name.strip().lower() != "authorization"
        }
        request_headers["host"] = self._host(parts)
        request_headers["x-amz-date"] = amz_date
        request_headers["x-amz-content-sha256"] = payload_hash
        if self.session_token is not None:
            request_headers["x-amz-security-token"] = self.session_token

        # generate the signature
        canonical_request = self._canonical_request(
            request_headers, method, parts.path, parts.query, payload_hash
        )
        credential_scope = self._credential_scope(date_stamp)
        string_to_sign = self._string_to_sign(
            amz_date, canonical_request, credential_scope
        )
        signing_key = self._signature_key(date_stamp)
        signature = self._signature(signing_key, string_to_sign)

        request_headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{credential_scope},"
            f"SignedHeaders={';'.join(sorted(request_headers))},"
            f"Signature={signature}"
        )
        return request_headers

    def _canonical_request(
        self,
        request_headers: Mapping[str, str],
        method: str,
        path: str,
        query: str,
        payload_hash: str,
    ):
        signed_header_names: list[str] = sorted(request_headers)
        signed_headers = ";".join(signed_header_names)
        canonical_headers = "".join(
            f"{name}:{request_headers[name]}\n" for name in signed_header_names
        )
        canonical_request = "\n".join(
            (
                method.upper(),
                self._canonical_uri(path),
                self._canonical_query(query),
                canonical_headers,
                signed_headers,
                payload_hash,
            )
        )
        return canonical_request

    def _credential_scope(self, date_stamp: str):
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/aws4_request"
        return credential_scope

    @staticmethod
    def _string_to_sign(
        amz_date: str,
        canonical_request: str,
        credential_scope: str,
    ):
        string_to_sign = (
            f"AWS4-HMAC-SHA256\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        return string_to_sign

    def _signature_key(self, date_stamp: str) -> bytes:
        k_date = self._hmac(f"AWS4{self.secret_key}".encode("utf-8"), date_stamp)
        k_region = self._hmac(k_date, self.region)
        k_service = self._hmac(k_region, self.service)
        return self._hmac(k_service, "aws4_request")

    @staticmethod
    def _signature(signing_key: bytes, string_to_sign: str):
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            sha256,
        ).hexdigest()
        return signature

    # --- helper ---

    @staticmethod
    def _host(parts) -> str:
        if parts.hostname is None:
            raise ValueError("SigV4 signing requires an absolute URL")

        host = parts.hostname.encode("idna").decode("ascii")
        if ":" in host:
            host = f"[{host}]"

        default_port = {"http": 80, "https": 443}.get(parts.scheme.lower())
        if parts.port is not None and parts.port != default_port:
            host = f"{host}:{parts.port}"
        return host

    @staticmethod
    def _validate_percent_encoding(value: str) -> None:
        position = 0

        while position < len(value):
            if value[position] != "%":
                position += 1
                continue

            encoded_byte = value[position + 1 : position + 3]
            if len(encoded_byte) != 2 or any(
                character not in "0123456789ABCDEF" for character in encoded_byte
            ):
                raise ValueError(
                    "SigV4 URL path contains invalid or non-uppercase percent-encoding"
                )

            position += 3

    @classmethod
    def _canonical_uri(cls, path: str) -> str:
        if not path:
            return "/"

        cls._validate_percent_encoding(path)
        return "/".join(quote(part, safe="-_.~%") for part in path.split("/"))

    @classmethod
    def _canonical_query(cls, query: str) -> str:
        if not query:
            return ""

        parameters = []
        for query_field in query.split("&"):
            name, separator, value = query_field.partition("=")
            if not separator:
                value = ""
            parameters.append((cls._uri_encode(name), cls._uri_encode(value)))

        parameters.sort()
        return "&".join(f"{name}={value}" for name, value in parameters)

    @staticmethod
    def _uri_encode(value: str) -> str:
        return quote_from_bytes(unquote_to_bytes(value), safe="-_.~")

    @staticmethod
    def _normalize_header_value(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _hmac(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode("utf-8"), sha256).digest()

    @staticmethod
    def _utc_now(now: datetime | None = None) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)
