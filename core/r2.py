"""
simple R2 service

If unless necessary, these functions will not be implemented:
    - resume upload
    - parallel upload

reason: disgusting code
"""

import hmac
from base64 import b64encode
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from hashlib import sha256
from operator import index
from types import TracebackType
from typing import AsyncIterable, Literal, Mapping, Never, Protocol, Sequence
from urllib.parse import (
    SplitResult,
    quote,
    quote_from_bytes,
    unquote,
    unquote_to_bytes,
    urlsplit,
)
from xml.etree import ElementTree

import httpx2

__all__ = (
    "AsyncObjectBody",
    "AsyncObjectStore",
    "AsyncR2Client",
    "AuthenticationFailed",
    "IntegrityCheckFailed",
    "InvalidObjectRequest",
    "ObjectMetadata",
    "ObjectNotFound",
    "ObjectNotModified",
    "ObjectPage",
    "ObjectPutResult",
    "ObjectStoreError",
    "PreconditionFailed",
    "RateLimited",
    "SignatureMismatch",
    "StorageUnavailable",
    "SyncObjectStore",
    "SyncR2Client",
)

EMPTY_PAYLOAD_HASH = sha256(b"").hexdigest()

UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"

PRESIGN_QUERY_NAMES = frozenset(
    {
        b"x-amz-algorithm",
        b"x-amz-credential",
        b"x-amz-date",
        b"x-amz-expires",
        b"x-amz-security-token",
        b"x-amz-signature",
        b"x-amz-signedheaders",
    }
)

# upload limits
# docs: https://developers.cloudflare.com/r2/objects/upload-objects/
MIN_MULTIPART_PART_SIZE = 5 * 1024**2  # 5MiB
MAX_MULTIPART_PART_SIZE = 5 * 1024**3 - 5 * 1024**2  # 5GiB - 5MiB
MAX_MULTIPART_OBJECT_SIZE = 5 * 1024**4 - 5 * 1024**3  # 5TiB - 5GiB
MAX_MULTIPART_PARTS = 10_000

type AsyncUploadBody = bytes | AsyncIterable[bytes]
type UploadStrategy = Literal["auto", "single", "multipart"]


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
    def from_response(cls, key: str, response: httpx2.Response) -> ObjectMetadata:
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


class AsyncObjectBody:
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


class SyncObjectBody:
    pass


@dataclass(frozen=True, slots=True)
class ObjectPutResult:
    key: str
    etag: str | None = None
    # useless for R2 (newest version only)
    version_id: str | None = None
    checksum_crc64nvme: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectPage:
    # R2 provide `key, size, ETag, LastModified, StorageClass` only
    objects: tuple[ObjectMetadata, ...]
    is_truncated: bool
    next_cursor: str | None = None
    common_prefixes: tuple[str, ...] = ()


# --- upload internals ---


@dataclass(frozen=True, slots=True)
class _PutOptions:
    cache_control: str | None = None
    content_type: str | None = None
    if_none_match: str | None = None
    metadata: Mapping[str, str] | None = None

    def headers(self) -> dict[str, str]:
        headers = {}
        if self.content_type is not None:
            headers["content-type"] = self.content_type
        if self.cache_control is not None:
            headers["cache-control"] = self.cache_control
        if self.if_none_match is not None:
            headers["if-none-match"] = self.if_none_match
        for name, value in (self.metadata or {}).items():
            headers[f"x-amz-meta-{name}"] = value
        return headers


@dataclass(frozen=True, slots=True)
class _UploadedPart:
    number: int
    etag: str


class _UploadSource:
    def __init__(self, body: AsyncUploadBody, content_length: int | None):
        if content_length is not None:
            if isinstance(content_length, bool) or not isinstance(content_length, int):
                raise TypeError("'content_length' must be an integer")
            if content_length < 0:
                raise ValueError("'content_length' must not be negative")

        if isinstance(body, bytes):
            length = len(body)
            if content_length is not None and content_length != length:
                raise ValueError(f"expected {content_length} bytes, received {length}")
            self._body: bytes | AsyncIterable[bytes] = body
            self.length = length
        else:
            self._body = aiter(body)
            self.length = content_length

    @property
    def is_stream(self) -> bool:
        return not isinstance(self._body, bytes)

    async def read_all(self) -> bytes:
        chunks = bytearray()
        async for chunk in self.iter_body():
            chunks.extend(chunk)
        return bytes(chunks)

    def single_body(self) -> bytes:
        if not isinstance(self._body, bytes):
            raise RuntimeError("async upload body requires multipart upload")
        return self._body

    async def iter_body(self) -> AsyncIterable[bytes]:
        if isinstance(self._body, bytes):
            yield self._body
            return

        received = 0
        async for chunk in self._body:
            received = self._validate_chunk(chunk, received)
            if self.length is not None and received > self.length:
                raise ValueError(f"expected {self.length} bytes, received more data")
            yield chunk

        self._validate_received_length(received)

    async def iter_parts(
        self,
        part_size: int,
    ) -> AsyncIterable[tuple[int, bytes]]:
        if isinstance(self._body, bytes):
            for offset in range(0, len(self._body), part_size):
                yield offset // part_size + 1, self._body[offset : offset + part_size]
            return

        buffer = bytearray()
        received = 0
        part_number = 1
        async for chunk in self._body:
            received = self._validate_chunk(chunk, received)
            if self.length is not None and received > self.length:
                raise ValueError(f"expected {self.length} bytes, received more data")

            view = memoryview(chunk)
            offset = 0
            while offset < len(view):
                take = min(part_size - len(buffer), len(view) - offset)
                buffer.extend(view[offset : offset + take])
                offset += take
                if len(buffer) == part_size:
                    yield part_number, bytes(buffer)
                    buffer.clear()
                    part_number += 1

        self._validate_received_length(received)
        if buffer:
            yield part_number, bytes(buffer)

    @staticmethod
    def _validate_chunk(chunk: bytes, received: int) -> int:
        if not isinstance(chunk, bytes):
            raise TypeError("async upload body must yield bytes")
        return received + len(chunk)

    def _validate_received_length(self, received: int) -> None:
        if self.length is not None and received != self.length:
            raise ValueError(f"expected {self.length} bytes, received {received}")


@dataclass(frozen=True, slots=True)
class _UploadPolicy:
    multipart_threshold: int
    multipart_part_size: int

    def use_multipart(
        self,
        source: _UploadSource,
        strategy: UploadStrategy,
    ) -> bool:
        if strategy == "single":
            if source.is_stream:
                raise ValueError(
                    "single async upload cannot provide atomic integrity verification"
                )
            return False
        if strategy == "multipart":
            return True
        return source.is_stream or source.length > self.multipart_threshold

    def part_size(self, content_length: int | None) -> int:
        configured_size = self.multipart_part_size
        if isinstance(configured_size, bool) or not isinstance(configured_size, int):
            raise TypeError("'multipart_part_size' must be an integer")
        if not MIN_MULTIPART_PART_SIZE <= configured_size <= MAX_MULTIPART_PART_SIZE:
            raise ValueError(
                "'multipart_part_size' must be between 5 MiB and 4.995 GiB"
            )

        if content_length is None:
            return configured_size
        if content_length > MAX_MULTIPART_OBJECT_SIZE:
            raise ValueError("multipart object exceeds the R2 object size limit")

        required_size = (
            content_length + MAX_MULTIPART_PARTS - 1
        ) // MAX_MULTIPART_PARTS
        part_size = max(configured_size, required_size)
        if part_size > MAX_MULTIPART_PART_SIZE:
            raise ValueError("object cannot fit within 10,000 multipart parts")
        return part_size


class _MultipartSession(Protocol):
    async def upload_part(self, number: int, body: bytes) -> _UploadedPart: ...

    async def complete(
        self,
        parts: Sequence[_UploadedPart],
        *,
        checksum_crc64nvme: str,
    ) -> ObjectPutResult: ...

    async def abort(self) -> None: ...


class _UploadBackend(Protocol):
    async def put_single(
        self,
        key: str,
        body: bytes,
        options: _PutOptions,
    ) -> ObjectPutResult: ...

    async def begin_multipart(
        self,
        key: str,
        options: _PutOptions,
    ) -> _MultipartSession: ...


@dataclass(slots=True)
class _UploadCoordinator:
    backend: _UploadBackend
    policy: _UploadPolicy
    key: str
    source: _UploadSource
    options: _PutOptions
    strategy: UploadStrategy

    @classmethod
    def create(
        cls,
        backend: _UploadBackend,
        policy: _UploadPolicy,
        key: str,
        body: AsyncUploadBody,
        content_length: int | None,
        options: _PutOptions,
        strategy: UploadStrategy,
    ) -> "_UploadCoordinator":
        if strategy not in {"auto", "single", "multipart"}:
            raise ValueError("'strategy' must be 'auto', 'single', or 'multipart'")
        return cls(
            backend=backend,
            policy=policy,
            key=key,
            source=_UploadSource(body, content_length),
            options=options,
            strategy=strategy,
        )

    async def run(self) -> ObjectPutResult:
        if self.policy.use_multipart(self.source, self.strategy):
            return await self._put_multipart()

        return await self.backend.put_single(
            self.key,
            self.source.single_body(),
            self.options,
        )

    async def _put_multipart(self) -> ObjectPutResult:
        part_size = self.policy.part_size(self.source.length)
        session = await self.backend.begin_multipart(self.key, self.options)

        try:
            completed_parts, checksum = await self._upload_parts(session, part_size)
            return await session.complete(
                completed_parts,
                checksum_crc64nvme=checksum,
            )
        except BaseException as exc:
            try:
                await session.abort()
            except ObjectNotFound:
                pass
            except BaseException as abort_exc:
                exc.add_note(f"multipart abort failed: {abort_exc}")
            raise

    async def _upload_parts(
        self,
        session: _MultipartSession,
        part_size: int,
    ) -> tuple[list[_UploadedPart], str]:
        completed_parts = []
        checksum = 0
        async for part_number, body in self.source.iter_parts(part_size):
            if part_number > MAX_MULTIPART_PARTS:
                raise ValueError("multipart upload exceeds 10,000 parts")
            checksum = crc64nvme(body, checksum)
            completed_parts.append(await session.upload_part(part_number, body))

        # if upload content is empty (b""), the for loop will exit immediately.
        # add this to finish this upload task.
        if not completed_parts:
            completed_parts.append(await session.upload_part(1, b""))
        return completed_parts, crc64nvme_base64(checksum)


@dataclass(frozen=True, slots=True)
class _R2MultipartSession:
    transport: _R2Transport
    key: str
    upload_id: str
    if_none_match: str | None

    async def upload_part(self, number: int, body: bytes) -> _UploadedPart:
        url = self.transport.multipart_url(
            self.key,
            self.upload_id,
            part_number=number,
        )
        payload_hash = sha256(body).hexdigest()
        response = await self.transport.send_signed_request(
            "PUT",
            url,
            {"x-amz-content-sha256": payload_hash},
            payload_hash,
            content=body,
            error_message=f"R2 multipart part {number} upload failed",
        )

        if response.status_code != 200:
            await self.transport.raise_response_error(response, key=self.key)

        try:
            etag = response.headers.get("etag")
            if not etag:
                raise StorageUnavailable(f"R2 multipart part {number} returned no ETag")
            return _UploadedPart(number, etag)
        finally:
            await response.aclose()

    async def abort(self) -> None:
        url = self.transport.multipart_url(self.key, self.upload_id)
        response = await self.transport.send_signed_request(
            "DELETE",
            url,
            {"x-amz-content-sha256": EMPTY_PAYLOAD_HASH},
            EMPTY_PAYLOAD_HASH,
            error_message="R2 multipart abort failed",
        )

        if response.status_code != 204:
            await self.transport.raise_response_error(response, key=self.key)
        await response.aclose()

    async def complete(
        self,
        parts: Sequence[_UploadedPart],
        *,
        checksum_crc64nvme: str,
    ) -> ObjectPutResult:
        root = ElementTree.Element("CompleteMultipartUpload")
        for part in parts:
            part_element = ElementTree.SubElement(root, "Part")
            ElementTree.SubElement(part_element, "PartNumber").text = str(part.number)
            ElementTree.SubElement(part_element, "ETag").text = part.etag

        body = ElementTree.tostring(root, encoding="utf-8")
        payload_hash = sha256(body).hexdigest()
        url = self.transport.multipart_url(self.key, self.upload_id)
        headers = {
            "content-type": "application/xml",
            "x-amz-content-sha256": payload_hash,
            "x-amz-checksum-crc64nvme": checksum_crc64nvme,
            "x-amz-checksum-type": "FULL_OBJECT",
        }
        if self.if_none_match is not None:
            headers["if-none-match"] = self.if_none_match
        response = await self.transport.send_signed_request(
            "POST",
            url,
            headers,
            payload_hash,
            content=body,
            error_message="R2 multipart completion failed",
        )

        if response.status_code != 200:
            await self.transport.raise_response_error(response, key=self.key)

        try:
            try:
                result_root = ElementTree.fromstring(response.content)
            except ElementTree.ParseError as exc:
                raise StorageUnavailable(
                    "R2 multipart completion returned invalid XML"
                ) from exc

            root_name = result_root.tag.rsplit("}", 1)[-1]
            if root_name == "Error":
                raise self.transport.map_error(
                    response,
                    response.content,
                    key=self.key,
                )
            if root_name != "CompleteMultipartUploadResult":
                raise StorageUnavailable(
                    "R2 multipart completion returned an invalid response"
                )

            etag = _xml_child_text(result_root, "ETag")
            etag = etag or response.headers.get("etag")
            if not etag:
                raise StorageUnavailable("R2 multipart completion returned no ETag")

            checksum = _xml_child_text(result_root, "ChecksumCRC64NVME")
            checksum = checksum or response.headers.get("x-amz-checksum-crc64nvme")
            checksum = _verified_checksum_value(
                checksum,
                self.key,
                checksum_crc64nvme,
            )

            return ObjectPutResult(
                key=self.key,
                etag=etag,
                version_id=response.headers.get("x-amz-version-id"),
                checksum_crc64nvme=checksum,
            )
        finally:
            await response.aclose()


@dataclass(frozen=True, slots=True)
class _R2Transport:
    endpoint: str
    bucket: str
    signer: "SigV4Signer"
    client: httpx2.AsyncClient

    async def send_signed_request(
        self,
        method: Literal["DELETE", "GET", "HEAD", "POST", "PUT"],
        url: str,
        headers: Mapping[str, str],
        payload_hash: str,
        *,
        content: bytes | AsyncIterable[bytes] | None = None,
        stream: bool = False,
        error_message: str,
    ) -> httpx2.Response:
        signed_headers = self.signer.sign(method, url, headers, payload_hash)
        try:
            if content is None:
                request = self.client.build_request(
                    method,
                    url,
                    headers=signed_headers,
                )
            else:
                request = self.client.build_request(
                    method,
                    url,
                    headers=signed_headers,
                    content=content,
                )
            return await self.client.send(request, stream=stream)
        except httpx2.HTTPError as exc:
            raise StorageUnavailable(error_message) from exc

    async def raise_response_error(
        self,
        response: httpx2.Response,
        *,
        key: str | None = None,
    ) -> Never:
        try:
            try:
                body = await response.aread()
            except httpx2.HTTPError as exc:
                raise StorageUnavailable("R2 error response could not be read") from exc
            error = self.map_error(response, body, key=key)
        finally:
            await response.aclose()
        raise error

    def object_url(self, key: str) -> str:
        return (
            f"{self.endpoint.rstrip('/')}/"
            f"{quote(self.bucket, safe='')}/"
            f"{self._quote_key(key)}"
        )

    def multipart_url(
        self,
        key: str,
        upload_id: str,
        *,
        part_number: int | None = None,
    ) -> str:
        encoded_upload_id = quote(upload_id, safe="-_.~")
        if part_number is None:
            return f"{self.object_url(key)}?uploadId={encoded_upload_id}"
        return (
            f"{self.object_url(key)}"
            f"?partNumber={part_number}&uploadId={encoded_upload_id}"
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
    def map_error(
        response: httpx2.Response,
        body: bytes,
        *,
        key: str | None = None,
    ) -> ObjectStoreError:
        code = response.headers.get("x-amz-error-code")
        message = None
        request_id = response.headers.get("x-amz-request-id")
        cf_ray = response.headers.get("cf-ray")

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
        elif code in {"BadDigest", "XAmzContentSHA256Mismatch"}:
            error_type = IntegrityCheckFailed
        elif status_code in {401, 403} or code in {
            "AccessDenied",
            "InvalidAccessKeyId",
        }:
            error_type = AuthenticationFailed
        elif status_code == 429 or code in {"SlowDown", "Throttling"}:
            error_type = RateLimited
        elif (
            status_code >= 500
            or status_code == 408
            or code in {"InternalError", "ServiceUnavailable"}
        ):
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
            cf_ray=cf_ray,
        )


@dataclass(frozen=True, slots=True)
class _R2UploadBackend:
    transport: _R2Transport

    async def put_single(
        self,
        key: str,
        body: bytes,
        options: _PutOptions,
    ) -> ObjectPutResult:
        url = self.transport.object_url(key)
        payload_hash = sha256(body).hexdigest()
        checksum = crc64nvme_base64(body)

        headers = {
            "x-amz-content-sha256": payload_hash,
            "x-amz-checksum-crc64nvme": checksum,
            **options.headers(),
        }
        response = await self.transport.send_signed_request(
            "PUT",
            url,
            headers,
            payload_hash,
            content=body,
            error_message="R2 PUT request failed",
        )

        if response.status_code != 200:
            await self.transport.raise_response_error(response, key=key)

        try:
            response_checksum = _verified_checksum(response, key, checksum)
            return ObjectPutResult(
                key=key,
                etag=response.headers.get("etag"),
                version_id=response.headers.get("x-amz-version-id"),
                checksum_crc64nvme=response_checksum,
            )
        finally:
            await response.aclose()

    async def begin_multipart(
        self,
        key: str,
        options: _PutOptions,
    ) -> _MultipartSession:
        url = f"{self.transport.object_url(key)}?uploads="
        headers = {
            "x-amz-content-sha256": EMPTY_PAYLOAD_HASH,
            "x-amz-checksum-algorithm": "CRC64NVME",
            "x-amz-checksum-type": "FULL_OBJECT",
            **options.headers(),
        }
        response = await self.transport.send_signed_request(
            "POST",
            url,
            headers,
            EMPTY_PAYLOAD_HASH,
            content=b"",
            error_message="R2 multipart initialization failed",
        )

        if response.status_code != 200:
            await self.transport.raise_response_error(response, key=key)

        try:
            try:
                root = ElementTree.fromstring(response.content)
            except ElementTree.ParseError as exc:
                raise StorageUnavailable(
                    "R2 multipart initialization returned invalid XML"
                ) from exc
            if root.tag.rsplit("}", 1)[-1] != "InitiateMultipartUploadResult":
                raise StorageUnavailable(
                    "R2 multipart initialization returned an invalid response"
                )

            upload_id = _xml_child_text(root, "UploadId")
            if not upload_id:
                raise StorageUnavailable(
                    "R2 multipart initialization returned no upload ID"
                )
            return _R2MultipartSession(
                transport=self.transport,
                key=key,
                upload_id=upload_id,
                if_none_match=options.if_none_match,
            )
        finally:
            await response.aclose()


# --- exceptions ---


class ObjectStoreError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
        cf_ray: str | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.cf_ray = cf_ray
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


class IntegrityCheckFailed(ObjectStoreError):
    pass


class ObjectNotModified(ObjectStoreError):
    pass


class SignatureMismatch(ObjectStoreError):
    pass


class InvalidObjectRequest(ObjectStoreError):
    pass


# --- protocol ---


class SyncObjectStore(Protocol):
    def stat(
        self,
        key: str,
        *,
        if_none_match: str | None = None,
        if_modified_since: datetime | None = None,
    ) -> ObjectMetadata: ...

    def get(
        self,
        key: str,
        *,
        byte_range: str | None = None,
        if_none_match: str | None = None,
    ) -> SyncObjectBody: ...

    def put(
        self,
        key: str,
        body: bytes,
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
        delimiter: str | None = None,
    ) -> ObjectPage: ...

    def presign(
        self,
        method: Literal["DELETE", "GET", "HEAD", "PUT"],
        key: str,
        *,
        expires_in: int = 300,
    ) -> str: ...


class AsyncObjectStore(Protocol):
    async def stat(
        self,
        key: str,
        *,
        if_none_match: str | None = None,
        if_modified_since: datetime | None = None,
    ) -> ObjectMetadata: ...

    async def get(
        self,
        key: str,
        *,
        byte_range: str | None = None,
        if_none_match: str | None = None,
    ) -> AsyncObjectBody: ...

    async def put(
        self,
        key: str,
        body: AsyncUploadBody,
        *,
        cache_control: str | None = None,
        content_length: int | None = None,
        content_type: str | None = None,
        if_none_match: str | None = None,
        metadata: Mapping[str, str] | None = None,
        strategy: UploadStrategy = "auto",
    ) -> ObjectPutResult: ...

    async def delete(self, key: str) -> None: ...

    async def list(
        self,
        *,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 1000,
        delimiter: str | None = None,
    ) -> ObjectPage: ...

    def presign(
        self,
        method: Literal["DELETE", "GET", "HEAD", "PUT"],
        key: str,
        *,
        expires_in: int = 300,
    ) -> str: ...


# --- implement ---


class SyncR2Client(SyncObjectStore):
    def __init__(self):
        raise NotImplementedError("SyncR2Client not implemented yet")


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
        multipart_threshold: int = 32 * 1024**2,
        multipart_part_size: int = 8 * 1024**2,
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
        self.multipart_threshold = multipart_threshold
        self.multipart_part_size = multipart_part_size
        self.signer = SigV4Signer(
            access_key=access_key,
            secret_key=secret_key,
            region="auto",
            service="s3",
            session_token=session_token,
        )
        self.client = client or httpx2.AsyncClient(timeout=timeout, transport=transport)
        self._owns_client = client is None
        self._transport = _R2Transport(
            endpoint=self.endpoint,
            bucket=self.bucket,
            signer=self.signer,
            client=self.client,
        )
        self._upload_backend = _R2UploadBackend(self._transport)

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
    ) -> AsyncObjectBody:
        url = self._object_url(key)

        headers = {
            "x-amz-content-sha256": EMPTY_PAYLOAD_HASH,
        }
        if byte_range is not None:
            headers["range"] = byte_range
        if if_none_match is not None:
            headers["if-none-match"] = if_none_match

        response = await self._transport.send_signed_request(
            "GET",
            url,
            headers,
            EMPTY_PAYLOAD_HASH,
            stream=True,
            error_message="R2 GET request failed",
        )

        if response.status_code == 304:
            await self._raise_not_modified(response, key)
        if response.status_code not in {200, 206}:
            await self._transport.raise_response_error(response, key=key)

        return AsyncObjectBody(
            key=key,
            response=response,
            metadata=ObjectMetadata.from_response(key, response),
        )

    async def put(
        self,
        key: str,
        body: AsyncUploadBody,
        *,
        cache_control: str | None = None,
        content_length: int | None = None,
        content_type: str | None = None,
        if_none_match: str | None = None,
        metadata: Mapping[str, str] | None = None,
        strategy: UploadStrategy = "auto",
    ) -> ObjectPutResult:
        options = _PutOptions(
            cache_control=cache_control,
            content_type=content_type,
            if_none_match=if_none_match,
            metadata=metadata,
        )
        upload = _UploadCoordinator.create(
            self._upload_backend,
            _UploadPolicy(
                multipart_threshold=self.multipart_threshold,
                multipart_part_size=self.multipart_part_size,
            ),
            key,
            body,
            content_length,
            options,
            strategy,
        )
        return await upload.run()

    async def delete(self, key: str) -> None:
        url = self._object_url(key)

        headers = {
            "x-amz-content-sha256": EMPTY_PAYLOAD_HASH,
        }
        response = await self._transport.send_signed_request(
            "DELETE",
            url,
            headers,
            EMPTY_PAYLOAD_HASH,
            error_message="R2 DELETE request failed",
        )

        if response.status_code != 204:
            await self._transport.raise_response_error(response, key=key)

        await response.aclose()

    async def stat(
        self,
        key: str,
        *,
        if_none_match: str | None = None,
        if_modified_since: datetime | None = None,
    ) -> ObjectMetadata:
        url = self._object_url(key)

        headers = {
            "x-amz-content-sha256": EMPTY_PAYLOAD_HASH,
        }
        if if_none_match is not None:
            headers["if-none-match"] = if_none_match
        if if_modified_since is not None:
            if if_modified_since.tzinfo is None:
                if_modified_since = if_modified_since.replace(tzinfo=timezone.utc)
            else:
                if_modified_since = if_modified_since.astimezone(timezone.utc)
            headers["if-modified-since"] = format_datetime(
                if_modified_since, usegmt=True
            )
        response = await self._transport.send_signed_request(
            "HEAD",
            url,
            headers,
            EMPTY_PAYLOAD_HASH,
            error_message="R2 HEAD request failed",
        )

        if response.status_code == 304:
            await self._raise_not_modified(response, key)
        if response.status_code != 200:
            await self._transport.raise_response_error(response, key=key)

        metadata = ObjectMetadata.from_response(key, response)
        await response.aclose()
        return metadata

    async def list(
        self,
        *,
        prefix: str = "",
        cursor: str | None = None,
        limit: int = 1000,
        delimiter: str | None = None,
    ) -> ObjectPage:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("'limit' must be an integer")
        if not 1 <= limit <= 1000:
            raise ValueError("'limit' must be between 1 and 1000")

        parameters = [
            ("list-type", "2"),
            ("encoding-type", "url"),
            ("max-keys", str(limit)),
            ("prefix", prefix),
        ]
        if cursor is not None:
            parameters.append(("continuation-token", cursor))
        if delimiter is not None:
            parameters.append(("delimiter", delimiter))

        query = "&".join(
            f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}"
            for name, value in parameters
        )
        url = f"{self._object_url('')}?{query}"

        headers = {
            "x-amz-content-sha256": EMPTY_PAYLOAD_HASH,
        }
        response = await self._transport.send_signed_request(
            "GET",
            url,
            headers,
            EMPTY_PAYLOAD_HASH,
            error_message="R2 LIST request failed",
        )

        if response.status_code != 200:
            await self._transport.raise_response_error(response)

        try:
            return self._parse_list_response(response.content)
        finally:
            await response.aclose()

    def presign(
        self,
        method: Literal["DELETE", "GET", "HEAD", "PUT"],
        key: str,
        *,
        expires_in: int = 300,
    ) -> str:
        return self.signer.presign(
            method,
            self._object_url(key),
            expires_in=expires_in,
        )

    # --- helper ---

    @staticmethod
    async def _raise_not_modified(
        response: httpx2.Response,
        key: str,
    ) -> Never:
        error = ObjectNotModified(
            key,
            status_code=response.status_code,
            request_id=response.headers.get("x-amz-request-id"),
            cf_ray=response.headers.get("cf-ray"),
        )
        await response.aclose()
        raise error

    def _object_url(self, key: str) -> str:
        return self._transport.object_url(key)

    @staticmethod
    def _parse_list_response(body: bytes) -> ObjectPage:
        try:
            root = ElementTree.fromstring(body)
            if root.tag.rsplit("}", 1)[-1] != "ListBucketResult":
                raise ValueError("unexpected XML root")

            truncated_text = _xml_child_text(root, "IsTruncated")
            if truncated_text not in {"true", "false"}:
                raise ValueError("invalid IsTruncated")

            is_truncated = truncated_text == "true"
            next_cursor = _xml_child_text(root, "NextContinuationToken")
            if is_truncated and not next_cursor:
                raise ValueError("missing NextContinuationToken")

            objects = []
            common_prefixes = []
            for element in root:
                name = element.tag.rsplit("}", 1)[-1]
                if name == "Contents":
                    key = _xml_child_text(element, "Key")
                    size = _xml_child_text(element, "Size")
                    last_modified = _xml_child_text(element, "LastModified")
                    if key is None or size is None or last_modified is None:
                        raise ValueError("incomplete object entry")

                    modified_at = datetime.fromisoformat(
                        last_modified.replace("Z", "+00:00")
                    )
                    if modified_at.tzinfo is None:
                        modified_at = modified_at.replace(tzinfo=timezone.utc)
                    else:
                        modified_at = modified_at.astimezone(timezone.utc)

                    objects.append(
                        ObjectMetadata(
                            key=unquote(key, errors="strict"),
                            size=int(size),
                            etag=_xml_child_text(element, "ETag"),
                            last_modified=modified_at,
                        )
                    )
                elif name == "CommonPrefixes":
                    common_prefix = _xml_child_text(element, "Prefix")
                    if common_prefix is not None:
                        common_prefixes.append(unquote(common_prefix, errors="strict"))
            return ObjectPage(
                objects=tuple(objects),
                is_truncated=is_truncated,
                next_cursor=next_cursor if is_truncated else None,
                common_prefixes=tuple(common_prefixes),
            )
        except (ElementTree.ParseError, TypeError, ValueError) as exc:
            raise StorageUnavailable("R2 LIST returned an invalid response") from exc


def _xml_child_text(element: ElementTree.Element, name: str) -> str | None:
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == name:
            return child.text or ""
    return None


def _verified_checksum_value(
    received: str | None,
    key: str,
    expected: str,
) -> str:
    if received is not None and not hmac.compare_digest(received, expected):
        raise IntegrityCheckFailed(f"R2 checksum mismatch for {key}")
    return received or expected


def _verified_checksum(
    response: httpx2.Response,
    key: str,
    expected: str,
) -> str:
    return _verified_checksum_value(
        response.headers.get("x-amz-checksum-crc64nvme"),
        key,
        expected,
    )


# --- signer ---
# docs: https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sig-v4-authenticating-requests.html
#       https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html


@dataclass(frozen=True, slots=True)
class SigV4Signer:
    access_key: str
    secret_key: str = field(repr=False)
    region: str = "auto"
    service: str = "s3"
    # temporary certificate need this
    session_token: str | None = field(default=None, repr=False)

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

    # R2 presigned URL accept R2 S3 API endpoint only. (custom domain is invalid)
    # docs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
    # solutions: https://developers.cloudflare.com/waf/custom-rules/use-cases/configure-token-authentication/
    def presign(
        self,
        method: Literal["DELETE", "GET", "HEAD", "PUT"],
        url: str,
        *,
        expires_in: int = 300,
        now: datetime | None = None,
    ) -> str:
        method = method.upper()
        if method not in {"DELETE", "GET", "HEAD", "PUT"}:
            raise ValueError("R2 does not support presigning this HTTP method")
        if (
            isinstance(expires_in, bool)
            or not isinstance(expires_in, int)
            or not 1 <= expires_in <= 604800
        ):
            raise ValueError("expires_in must be between 1 and 604800 seconds")

        now = self._utc_now(now)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        credential_scope = self._credential_scope(date_stamp)

        parts = urlsplit(url)
        if parts.hostname is None:
            raise ValueError("SigV4 presigning requires an absolute URL")
        if parts.fragment:
            raise ValueError("SigV4 presigned URLs cannot contain a fragment")

        self._validate_presign_query(parts.query)

        parameters: list[tuple[str, str]] = [
            ("X-Amz-Algorithm", "AWS4-HMAC-SHA256"),
            ("X-Amz-Credential", f"{self.access_key}/{credential_scope}"),
            ("X-Amz-Date", amz_date),
            ("X-Amz-Expires", str(expires_in)),
            ("X-Amz-SignedHeaders", "host"),
        ]
        if self.session_token is not None:
            parameters.append(("X-Amz-Security-Token", self.session_token))

        authentication_query = "&".join(
            f"{self._uri_encode(name)}={self._uri_encode(value)}"
            for name, value in parameters
        )
        unsigned_query = "&".join(
            query for query in (parts.query, authentication_query) if query
        )
        canonical_query = self._canonical_query(unsigned_query)
        canonical_request = self._canonical_request(
            {"host": self._host(parts)},
            method,
            parts.path,
            canonical_query,
            UNSIGNED_PAYLOAD,
        )
        string_to_sign = self._string_to_sign(
            amz_date, canonical_request, credential_scope
        )
        signature = self._signature(self._signature_key(date_stamp), string_to_sign)

        signed_query = f"{canonical_query}&X-Amz-Signature={signature}"
        return parts._replace(query=signed_query, fragment="").geturl()

    def _canonical_request(
        self,
        request_headers: Mapping[str, str],
        method: str,
        path: str,
        query: str,
        payload_hash: str,
    ) -> str:
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

    def _credential_scope(self, date_stamp: str) -> str:
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/aws4_request"
        return credential_scope

    @staticmethod
    def _string_to_sign(
        amz_date: str,
        canonical_request: str,
        credential_scope: str,
    ) -> str:
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
    def _signature(signing_key: bytes, string_to_sign: str) -> str:
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            sha256,
        ).hexdigest()
        return signature

    # --- helper ---

    @staticmethod
    def _host(parts: SplitResult) -> str:
        if parts.hostname is None:
            raise ValueError("SigV4 signing requires an absolute URL")

        host = parts.hostname.encode("idna").decode("ascii")
        if ":" in host:
            host = f"[{host}]"

        # noinspection bad-argument-type
        default_port = {"http": 80, "https": 443}.get(parts.scheme.lower())
        if parts.port is not None and parts.port != default_port:
            host = f"{host}:{parts.port}"
        return host

    @staticmethod
    def _validate_presign_query(query: str) -> None:
        if not query:
            return

        for query_field in query.split("&"):
            name = query_field.partition("=")[0]
            decoded_name = unquote_to_bytes(name).lower()

            if decoded_name in PRESIGN_QUERY_NAMES:
                raise ValueError("URL already contains SigV4 authentication parameters")

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


# --- CRC-64/NVME ---
# due to python poor performance, 'awscrt' lib is recommended
# in 16MiB data test:
#  - pure python: 10.5 MiB/s
#  - native/crc64nvme: 0.49 GiB/s
#  - awscrt: 14 GiB/s  (C impl)

try:
    from _crc64nvme import crc64nvme as _native_crc64nvme
except ModuleNotFoundError:
    _native_crc64nvme = None

_MASK = 0xFFFFFFFFFFFFFFFF
_POLY = 0x9A6C9329AC4BC9B5


def _make_crc64nvme_table() -> tuple[int, ...]:
    table = []
    for value in range(256):
        crc = value
        for _ in range(8):
            crc = (crc >> 1) ^ (_POLY if crc & 1 else 0)
        table.append(crc)
    return tuple(table)


_CRC64NVME_TABLE = _make_crc64nvme_table()


def crc64nvme(data: bytes, previous: int = 0) -> int:
    previous = index(previous)
    if not 0 <= previous <= _MASK:
        raise OverflowError("previous must fit in an unsigned 64-bit integer")

    if _native_crc64nvme is not None:
        return _native_crc64nvme(data, previous)

    crc = previous ^ _MASK
    for byte in data:
        table_index = (crc ^ byte) & 0xFF
        crc = _CRC64NVME_TABLE[table_index] ^ (crc >> 8)
    return crc ^ _MASK


def crc64nvme_base64(checksum: int | bytes) -> str:
    checksum = crc64nvme(checksum) if isinstance(checksum, bytes) else checksum
    return b64encode(checksum.to_bytes(8, "big")).decode("ascii")
