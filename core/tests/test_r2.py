from datetime import datetime, timezone
from hashlib import sha256
from unittest import IsolatedAsyncioTestCase
from xml.etree import ElementTree

import httpx2
from django.test import SimpleTestCase

from core import r2
from core.r2 import (
    EMPTY_PAYLOAD_HASH,
    AsyncR2Client,
    AuthenticationFailed,
    IntegrityCheckFailed,
    InvalidObjectRequest,
    ObjectNotFound,
    ObjectNotModified,
    PreconditionFailed,
    SigV4Signer,
    StorageUnavailable,
    _UploadSource,
    crc64nvme,
    crc64nvme_base64,
)


class PublicApiTest(SimpleTestCase):
    def test_sync_object_body_is_not_exported(self):
        self.assertNotIn("SyncObjectBody", r2.__all__)


class SigV4SignerTest(SimpleTestCase):
    def test_matches_aws_s3_get_object_example(self):
        signer = SigV4Signer(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-east-1",
            service="s3",
        )

        headers = signer.sign(
            "GET",
            "https://examplebucket.s3.amazonaws.com/test.txt",
            {
                "Range": " bytes=0-9 ",
                "x-amz-content-sha256": EMPTY_PAYLOAD_HASH,
            },
            EMPTY_PAYLOAD_HASH,
            now=datetime(2013, 5, 24, tzinfo=timezone.utc),
        )

        self.assertEqual(headers["host"], "examplebucket.s3.amazonaws.com")
        self.assertEqual(headers["range"], "bytes=0-9")
        self.assertEqual(headers["x-amz-date"], "20130524T000000Z")
        self.assertEqual(
            headers["Authorization"],
            "AWS4-HMAC-SHA256 "
            "Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request,"
            "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date,"
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41",
        )

    def test_canonicalizes_query_parameters(self):
        self.assertEqual(
            SigV4Signer._canonical_query("b=two&a=hello+world&a=%2f&empty&encoded=%7e"),
            "a=%2F&a=hello%2Bworld&b=two&empty=&encoded=~",
        )

    def test_canonicalizes_encoded_path_without_collapsing_slashes(self):
        self.assertEqual(
            SigV4Signer._canonical_uri("/bucket/a%2Fb//%E7%A9%BA%20%E6%A0%BC"),
            "/bucket/a%2Fb//%E7%A9%BA%20%E6%A0%BC",
        )


class UploadSourceTest(IsolatedAsyncioTestCase):
    async def test_rechunks_async_body(self):
        async def upload_body():
            yield b"ab"
            yield b"cdefg"
            yield b"h"

        source = _UploadSource(upload_body(), 8)
        parts = [part async for part in source.iter_parts(4)]

        self.assertEqual(parts, [(1, b"abcd"), (2, b"efgh")])

    async def test_validates_async_body(self):
        async def short_body():
            yield b"data"

        source = _UploadSource(short_body(), 5)
        with self.assertRaisesRegex(ValueError, "expected 5 bytes, received 4"):
            await source.read_all()

        async def long_body():
            yield b"too long"

        source = _UploadSource(long_body(), 4)
        with self.assertRaisesRegex(ValueError, "expected 4 bytes, received more data"):
            await source.read_all()

        async def invalid_body():
            yield "not bytes"

        source = _UploadSource(invalid_body(), 9)
        with self.assertRaisesRegex(TypeError, "must yield bytes"):
            await source.read_all()


class AsyncR2ClientTest(IsolatedAsyncioTestCase):
    def test_object_url_preserves_dot_segments(self):
        client = AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
        )
        self.assertEqual(
            client._object_url("a/../b"),
            "https://example.r2.cloudflarestorage.com/bucket/a/%2E%2E/b",
        )

        async def close_client():
            await client.aclose()

        self.addAsyncCleanup(close_client)

    async def test_get_streams_object_and_parses_metadata(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx2.Response(
                200,
                headers={
                    "content-length": "5",
                    "content-type": "text/plain",
                    "etag": '"abc"',
                    "x-amz-meta-kind": "demo",
                },
                content=b"hello",
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            body = await client.get("folder/file.txt")
            async with body:
                self.assertEqual(await body.read(), b"hello")
                self.assertEqual(body.metadata.size, 5)
                self.assertEqual(body.metadata.content_type, "text/plain")
                self.assertEqual(body.metadata.metadata, {"kind": "demo"})

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(
            requests[0].url,
            "https://example.r2.cloudflarestorage.com/bucket/folder/file.txt",
        )
        self.assertIn("AWS4-HMAC-SHA256", requests[0].headers["authorization"])

    async def test_get_maps_not_found_error(self):
        async def handler(request):
            return httpx2.Response(
                404,
                headers={"x-amz-request-id": "request-1"},
                content=b"<Error><Code>NoSuchKey</Code><Message>missing</Message></Error>",
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(ObjectNotFound) as raised:
                await client.get("missing.txt")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.code, "NoSuchKey")
        self.assertEqual(raised.exception.request_id, "request-1")

    async def test_get_accepts_partial_content_response(self):
        async def handler(request):
            return httpx2.Response(
                206,
                headers={
                    "content-length": "5",
                    "content-range": "bytes 0-4/10",
                },
                content=b"hello",
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            body = await client.get("file.txt", byte_range="bytes=0-4")
            async with body:
                self.assertEqual(await body.read(), b"hello")

    async def test_get_raises_not_modified_with_request_metadata(self):
        async def handler(request):
            return httpx2.Response(
                304,
                headers={
                    "x-amz-request-id": "request-1",
                    "cf-ray": "ray-1",
                },
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(ObjectNotModified) as raised:
                await client.get("file.txt", if_none_match='"abc123"')

        self.assertEqual(raised.exception.status_code, 304)
        self.assertEqual(raised.exception.request_id, "request-1")
        self.assertEqual(raised.exception.cf_ray, "ray-1")

    async def test_rejects_redirect_responses(self):
        operations = (
            ("get", lambda client: client.get("file.txt")),
            ("put", lambda client: client.put("file.txt", b"hello")),
            ("delete", lambda client: client.delete("file.txt")),
            ("stat", lambda client: client.stat("file.txt")),
            ("list", lambda client: client.list()),
        )

        for name, operation in operations:
            with self.subTest(operation=name):

                async def handler(request):
                    return httpx2.Response(
                        301,
                        headers={"location": "https://other.example/file.txt"},
                        content=b"redirect",
                        request=request,
                    )

                async with AsyncR2Client(
                    "https://example.r2.cloudflarestorage.com",
                    "access",
                    "secret",
                    "bucket",
                    transport=httpx2.MockTransport(handler),
                ) as client:
                    with self.assertRaises(InvalidObjectRequest) as raised:
                        await operation(client)

                self.assertEqual(raised.exception.status_code, 301)
                self.assertEqual(
                    str(raised.exception),
                    "R2 request failed with HTTP 301",
                )

    def test_normalizes_endpoint(self):
        client = AsyncR2Client(
            "https://example.r2.cloudflarestorage.com/",
            "access",
            "secret",
            "bucket",
        )
        self.assertEqual(
            client._object_url("file.txt"),
            "https://example.r2.cloudflarestorage.com/bucket/file.txt",
        )
        self.addAsyncCleanup(client.aclose)

    def test_rejects_invalid_endpoints(self):
        invalid_endpoints = [
            "http://example.com",
            "https://user:password@example.com",
            "https://example.com/base",
            "https://example.com?region=auto",
            "https://example.com#fragment",
            "https://example.com:invalid",
            " https://example.com",
        ]

        for endpoint in invalid_endpoints:
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    AsyncR2Client(
                        endpoint,
                        "access",
                        "secret",
                        "bucket",
                    )

    def test_signs_session_token(self):
        signer = SigV4Signer(
            access_key="access",
            secret_key="secret",
            region="auto",
            service="s3",
            session_token="session-token",
        )

        headers = signer.sign(
            "GET",
            "https://example.r2.cloudflarestorage.com/bucket/file.txt",
            {},
            EMPTY_PAYLOAD_HASH,
            now=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(
            headers["x-amz-security-token"],
            "session-token",
        )
        self.assertIn(
            "x-amz-security-token",
            headers["Authorization"],
        )

    def test_session_token_changes_signature(self):
        now = datetime(2026, 8, 6, tzinfo=timezone.utc)
        url = "https://example.r2.cloudflarestorage.com/bucket/file.txt"

        first = SigV4Signer(
            "access",
            "secret",
            session_token="token-1",
        ).sign("GET", url, {}, EMPTY_PAYLOAD_HASH, now=now)

        second = SigV4Signer(
            "access",
            "secret",
            session_token="token-2",
        ).sign("GET", url, {}, EMPTY_PAYLOAD_HASH, now=now)

        self.assertNotEqual(
            first["Authorization"],
            second["Authorization"],
        )

    def test_rejects_invalid_path_percent_encoding(self):
        invalid_paths = [
            "/bucket/a%",
            "/bucket/a%2",
            "/bucket/a%GG",
            "/bucket/a%2f",
        ]

        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    SigV4Signer._canonical_uri(path)

    def test_preserves_encoded_dot_segments(self):
        self.assertEqual(
            SigV4Signer._canonical_uri("/bucket/a/%2E%2E/b"),
            "/bucket/a/%2E%2E/b",
        )

    def test_encodes_literal_path_characters(self):
        self.assertEqual(
            SigV4Signer._canonical_uri("/bucket/空 格"),
            "/bucket/%E7%A9%BA%20%E6%A0%BC",
        )

    def test_matches_aws_s3_presigned_get_example(self):
        signer = SigV4Signer(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-east-1",
            service="s3",
        )

        url = signer.presign(
            "GET",
            "https://examplebucket.s3.amazonaws.com/test.txt",
            expires_in=86400,
            now=datetime(
                2013,
                5,
                24,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            url,
            "https://examplebucket.s3.amazonaws.com/test.txt?"
            "X-Amz-Algorithm=AWS4-HMAC-SHA256&"
            "X-Amz-Credential="
            "AKIAIOSFODNN7EXAMPLE%2F20130524%2F"
            "us-east-1%2Fs3%2Faws4_request&"
            "X-Amz-Date=20130524T000000Z&"
            "X-Amz-Expires=86400&"
            "X-Amz-SignedHeaders=host&"
            "X-Amz-Signature="
            "aeeed9bbccd4d02ee5c0109b86d86835"
            "f995330da4c265957d157751f604d404",
        )

    async def test_put_uploads_signed_body_and_returns_result(self):
        requests = []
        checksum = crc64nvme_base64(b"hello")

        async def handler(request):
            requests.append(request)
            body = await request.aread()
            self.assertEqual(body, b"hello")

            return httpx2.Response(
                200,
                headers={
                    "etag": '"abc123"',
                    "x-amz-checksum-crc64nvme": checksum,
                    "x-amz-version-id": "version-1",
                },
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            result = await client.put(
                "folder/file.txt",
                b"hello",
                cache_control="public, max-age=3600",
                content_type="text/plain",
                if_none_match="*",
                metadata={"kind": "demo"},
            )

        self.assertEqual(result.key, "folder/file.txt")
        self.assertEqual(result.etag, '"abc123"')
        self.assertEqual(result.version_id, "version-1")
        self.assertEqual(result.checksum_crc64nvme, checksum)

        self.assertEqual(len(requests), 1)
        request = requests[0]

        self.assertEqual(request.method, "PUT")
        self.assertEqual(
            request.url,
            "https://example.r2.cloudflarestorage.com/bucket/folder/file.txt",
        )
        self.assertEqual(request.headers["content-length"], "5")
        self.assertEqual(request.headers["content-type"], "text/plain")
        self.assertEqual(
            request.headers["cache-control"],
            "public, max-age=3600",
        )
        self.assertEqual(request.headers["x-amz-meta-kind"], "demo")
        self.assertEqual(request.headers["if-none-match"], "*")
        self.assertEqual(
            request.headers["x-amz-content-sha256"],
            sha256(b"hello").hexdigest(),
        )
        self.assertEqual(request.headers["x-amz-checksum-crc64nvme"], checksum)
        self.assertIn(
            "AWS4-HMAC-SHA256",
            request.headers["authorization"],
        )

    async def test_put_supports_empty_body(self):
        checksum = crc64nvme_base64(b"")

        async def handler(request):
            self.assertEqual(await request.aread(), b"")
            self.assertEqual(
                request.headers["x-amz-content-sha256"],
                EMPTY_PAYLOAD_HASH,
            )
            self.assertEqual(request.headers["x-amz-checksum-crc64nvme"], checksum)
            return httpx2.Response(
                200,
                headers={
                    "etag": '"empty"',
                    "x-amz-checksum-crc64nvme": checksum,
                },
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            result = await client.put("empty.txt", b"")

        self.assertEqual(result.etag, '"empty"')
        self.assertEqual(result.checksum_crc64nvme, checksum)

    async def test_put_rejects_mismatched_checksum_response(self):
        async def handler(request):
            return httpx2.Response(
                200,
                headers={
                    "etag": '"bad"',
                    "x-amz-checksum-crc64nvme": crc64nvme_base64(b"other"),
                },
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(IntegrityCheckFailed):
                await client.put("file.txt", b"hello")

    async def test_put_maps_bad_digest(self):
        async def handler(request):
            return httpx2.Response(
                400,
                content=(
                    b"<Error>"
                    b"<Code>BadDigest</Code>"
                    b"<Message>checksum mismatch</Message>"
                    b"</Error>"
                ),
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(IntegrityCheckFailed) as raised:
                await client.put("file.txt", b"hello")

        self.assertEqual(raised.exception.code, "BadDigest")

    async def test_put_maps_precondition_failed(self):
        async def handler(request):
            return httpx2.Response(
                412,
                headers={"x-amz-request-id": "request-1"},
                content=(
                    b"<Error>"
                    b"<Code>PreconditionFailed</Code>"
                    b"<Message>object already exists</Message>"
                    b"</Error>"
                ),
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(PreconditionFailed) as raised:
                await client.put("existing.txt", b"hello", if_none_match="*")

        self.assertEqual(raised.exception.status_code, 412)
        self.assertEqual(
            raised.exception.code,
            "PreconditionFailed",
        )
        self.assertEqual(
            raised.exception.request_id,
            "request-1",
        )

    async def test_put_maps_transport_error(self):
        async def handler(request):
            raise httpx2.ConnectError(
                "connection failed",
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(StorageUnavailable) as raised:
                await client.put("file.txt", b"hello")

        self.assertEqual(
            str(raised.exception),
            "R2 PUT request failed",
        )

    async def test_put_multipart_uploads_parts_and_metadata(self):
        part_size = 5 * 1024 * 1024
        body = b"a" * part_size + b"tail"
        checksum = crc64nvme_base64(body)
        requests = []

        async def handler(request):
            requests.append(request)

            if request.method == "POST" and "uploads" in request.url.params:
                self.assertEqual(request.headers["content-type"], "text/plain")
                self.assertEqual(request.headers["cache-control"], "public")
                self.assertEqual(request.headers["if-none-match"], "*")
                self.assertEqual(request.headers["x-amz-meta-kind"], "demo")
                self.assertEqual(
                    request.headers["x-amz-checksum-algorithm"],
                    "CRC64NVME",
                )
                self.assertEqual(request.headers["x-amz-checksum-type"], "FULL_OBJECT")
                return httpx2.Response(
                    200,
                    content=(
                        b"<InitiateMultipartUploadResult>"
                        b"<UploadId>upload/id+=</UploadId>"
                        b"</InitiateMultipartUploadResult>"
                    ),
                    request=request,
                )

            if request.method == "PUT":
                part_number = int(request.url.params["partNumber"])
                self.assertEqual(request.url.params["uploadId"], "upload/id+=")
                part = await request.aread()
                expected = body[:part_size] if part_number == 1 else b"tail"
                self.assertEqual(part, expected)
                self.assertEqual(
                    request.headers["x-amz-content-sha256"],
                    sha256(expected).hexdigest(),
                )
                return httpx2.Response(
                    200,
                    headers={"etag": f'"part-{part_number}"'},
                    request=request,
                )

            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.params["uploadId"], "upload/id+=")
            self.assertEqual(request.headers["if-none-match"], "*")
            self.assertEqual(
                request.headers["x-amz-checksum-crc64nvme"],
                checksum,
            )
            self.assertEqual(request.headers["x-amz-checksum-type"], "FULL_OBJECT")
            complete_body = await request.aread()
            complete_root = ElementTree.fromstring(complete_body)
            completed_parts = [
                (
                    int(part.findtext("PartNumber")),
                    part.findtext("ETag"),
                )
                for part in complete_root.findall("Part")
            ]
            self.assertEqual(
                completed_parts,
                [(1, '"part-1"'), (2, '"part-2"')],
            )
            return httpx2.Response(
                200,
                headers={"x-amz-version-id": "version-1"},
                content=(
                    b"<CompleteMultipartUploadResult>"
                    b"<ETag>&quot;complete-2&quot;</ETag>"
                    b"<ChecksumCRC64NVME>" + checksum.encode() + b"</ChecksumCRC64NVME>"
                    b"</CompleteMultipartUploadResult>"
                ),
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
            multipart_part_size=part_size,
        ) as client:
            result = await client.put(
                "large.txt",
                body,
                cache_control="public",
                content_type="text/plain",
                if_none_match="*",
                metadata={"kind": "demo"},
                strategy="multipart",
            )

        self.assertEqual(result.etag, '"complete-2"')
        self.assertEqual(result.version_id, "version-1")
        self.assertEqual(result.checksum_crc64nvme, checksum)
        self.assertEqual(
            [request.method for request in requests],
            ["POST", "PUT", "PUT", "POST"],
        )

    async def test_put_multipart_supports_empty_body(self):
        checksum = crc64nvme_base64(b"")
        requests = []

        async def handler(request):
            requests.append(request)

            if request.method == "POST" and "uploads" in request.url.params:
                self.assertEqual(
                    request.headers["x-amz-checksum-algorithm"],
                    "CRC64NVME",
                )
                self.assertEqual(request.headers["x-amz-checksum-type"], "FULL_OBJECT")
                return httpx2.Response(
                    200,
                    content=(
                        b"<InitiateMultipartUploadResult>"
                        b"<UploadId>empty-upload</UploadId>"
                        b"</InitiateMultipartUploadResult>"
                    ),
                    request=request,
                )
            if request.method == "PUT":
                self.assertEqual(request.url.params["partNumber"], "1")
                self.assertEqual(await request.aread(), b"")
                return httpx2.Response(
                    200,
                    headers={"etag": '"empty-part"'},
                    request=request,
                )

            complete_root = ElementTree.fromstring(await request.aread())
            self.assertEqual(request.headers["x-amz-checksum-crc64nvme"], checksum)
            self.assertEqual(request.headers["x-amz-checksum-type"], "FULL_OBJECT")
            self.assertEqual(
                complete_root.findtext("Part/PartNumber"),
                "1",
            )
            self.assertEqual(
                complete_root.findtext("Part/ETag"),
                '"empty-part"',
            )
            return httpx2.Response(
                200,
                content=(
                    b"<CompleteMultipartUploadResult>"
                    b"<ETag>&quot;empty&quot;</ETag>"
                    b"</CompleteMultipartUploadResult>"
                ),
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            result = await client.put("empty.txt", b"", strategy="multipart")

        self.assertEqual(result.etag, '"empty"')
        self.assertEqual(result.checksum_crc64nvme, checksum)
        self.assertEqual(
            [request.method for request in requests],
            ["POST", "PUT", "POST"],
        )

    async def test_put_multipart_aborts_after_part_failure(self):
        methods = []

        async def handler(request):
            methods.append(request.method)

            if request.method == "POST":
                return httpx2.Response(
                    200,
                    content=(
                        b"<InitiateMultipartUploadResult>"
                        b"<UploadId>failed-upload</UploadId>"
                        b"</InitiateMultipartUploadResult>"
                    ),
                    request=request,
                )
            if request.method == "PUT":
                return httpx2.Response(
                    500,
                    content=(
                        b"<Error><Code>InternalError</Code>"
                        b"<Message>try again</Message></Error>"
                    ),
                    request=request,
                )

            self.assertEqual(request.method, "DELETE")
            self.assertEqual(request.url.params["uploadId"], "failed-upload")
            return httpx2.Response(204, request=request)

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(StorageUnavailable):
                await client.put("file.txt", b"data", strategy="multipart")

        self.assertEqual(methods, ["POST", "PUT", "DELETE"])

    async def test_put_multipart_handles_error_inside_success_response(self):
        methods = []

        async def handler(request):
            methods.append(request.method)

            if request.method == "POST" and "uploads" in request.url.params:
                return httpx2.Response(
                    200,
                    content=(
                        b"<InitiateMultipartUploadResult>"
                        b"<UploadId>embedded-error</UploadId>"
                        b"</InitiateMultipartUploadResult>"
                    ),
                    request=request,
                )
            if request.method == "PUT":
                return httpx2.Response(
                    200,
                    headers={"etag": '"part-1"'},
                    request=request,
                )
            if request.method == "DELETE":
                return httpx2.Response(204, request=request)

            return httpx2.Response(
                200,
                content=(
                    b"<Error><Code>InternalError</Code>"
                    b"<Message>completion failed</Message></Error>"
                ),
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(StorageUnavailable) as raised:
                await client.put("file.txt", b"data", strategy="multipart")

        self.assertEqual(raised.exception.code, "InternalError")
        self.assertEqual(methods, ["POST", "PUT", "POST", "DELETE"])

    async def test_put_known_length_async_body_uses_multipart(self):
        async def upload_body():
            yield b"he"
            yield b"llo"

        requests = []
        checksum = crc64nvme_base64(b"hello")

        async def handler(request):
            requests.append(request)
            if request.method == "POST" and "uploads" in request.url.params:
                return httpx2.Response(
                    200,
                    content=(
                        b"<InitiateMultipartUploadResult>"
                        b"<UploadId>stream-upload</UploadId>"
                        b"</InitiateMultipartUploadResult>"
                    ),
                    request=request,
                )
            if request.method == "PUT":
                self.assertEqual(request.headers["content-length"], "5")
                self.assertEqual(await request.aread(), b"hello")
                return httpx2.Response(
                    200,
                    headers={"etag": '"stream-part"'},
                    request=request,
                )

            self.assertEqual(request.headers["x-amz-checksum-crc64nvme"], checksum)
            return httpx2.Response(
                200,
                content=(
                    b"<CompleteMultipartUploadResult>"
                    b"<ETag>&quot;stream&quot;</ETag>"
                    b"<ChecksumCRC64NVME>" + checksum.encode() + b"</ChecksumCRC64NVME>"
                    b"</CompleteMultipartUploadResult>"
                ),
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            result = await client.put(
                "stream.txt",
                upload_body(),
                content_length=5,
            )

        self.assertEqual(result.etag, '"stream"')
        self.assertEqual(result.checksum_crc64nvme, checksum)
        self.assertEqual(
            [request.method for request in requests],
            ["POST", "PUT", "POST"],
        )

    async def test_put_validates_strategy_and_content_length(self):
        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
        ) as client:
            with self.assertRaisesRegex(ValueError, "strategy"):
                await client.put("file.txt", b"data", strategy="invalid")
            with self.assertRaisesRegex(ValueError, "expected 5 bytes"):
                await client.put("file.txt", b"data", content_length=5)

            async def upload_body():
                yield b"data"

            with self.assertRaisesRegex(ValueError, "integrity verification"):
                await client.put(
                    "file.txt",
                    upload_body(),
                    content_length=4,
                    strategy="single",
                )

    async def test_delete_signs_request(self):
        requests = []

        async def handler(request):
            requests.append(request)
            self.assertEqual(await request.aread(), b"")

            return httpx2.Response(
                204,
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            result = await client.delete("folder/file.txt")

        self.assertIsNone(result)
        self.assertEqual(len(requests), 1)

        request = requests[0]
        self.assertEqual(request.method, "DELETE")
        self.assertEqual(
            request.url,
            "https://example.r2.cloudflarestorage.com/bucket/folder/file.txt",
        )
        self.assertEqual(
            request.headers["x-amz-content-sha256"],
            EMPTY_PAYLOAD_HASH,
        )
        self.assertIn(
            "AWS4-HMAC-SHA256",
            request.headers["authorization"],
        )

    async def test_delete_maps_authentication_error(self):
        async def handler(request):
            return httpx2.Response(
                403,
                headers={"x-amz-request-id": "request-1"},
                content=(
                    b"<Error>"
                    b"<Code>AccessDenied</Code>"
                    b"<Message>access denied</Message>"
                    b"</Error>"
                ),
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(AuthenticationFailed) as raised:
                await client.delete("folder/file.txt")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.code, "AccessDenied")
        self.assertEqual(raised.exception.request_id, "request-1")

    async def test_delete_maps_transport_error(self):
        async def handler(request):
            raise httpx2.ConnectError(
                "connection failed",
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(StorageUnavailable) as raised:
                await client.delete("folder/file.txt")

        self.assertEqual(
            str(raised.exception),
            "R2 DELETE request failed",
        )

    async def test_stat_returns_object_metadata(self):
        requests = []

        async def handler(request):
            requests.append(request)

            return httpx2.Response(
                200,
                headers={
                    "content-length": "1024",
                    "content-type": "image/png",
                    "cache-control": "public, max-age=3600",
                    "content-disposition": 'inline; filename="image.png"',
                    "content-encoding": "gzip",
                    "etag": '"abc123"',
                    "last-modified": "Thu, 06 Aug 2026 10:30:00 GMT",
                    "x-amz-meta-kind": "avatar",
                    "x-amz-meta-owner": "42",
                },
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            metadata = await client.stat("images/avatar.png")

        self.assertEqual(metadata.key, "images/avatar.png")
        self.assertEqual(metadata.size, 1024)
        self.assertEqual(metadata.etag, '"abc123"')
        self.assertEqual(metadata.content_type, "image/png")
        self.assertEqual(
            metadata.cache_control,
            "public, max-age=3600",
        )
        self.assertEqual(
            metadata.content_disposition,
            'inline; filename="image.png"',
        )
        self.assertEqual(metadata.content_encoding, "gzip")
        self.assertEqual(
            metadata.last_modified,
            datetime(
                2026,
                8,
                6,
                10,
                30,
                tzinfo=timezone.utc,
            ),
        )
        self.assertEqual(
            metadata.metadata,
            {
                "kind": "avatar",
                "owner": "42",
            },
        )

        self.assertEqual(len(requests), 1)
        request = requests[0]

        self.assertEqual(request.method, "HEAD")
        self.assertEqual(
            request.url,
            "https://example.r2.cloudflarestorage.com/bucket/images/avatar.png",
        )
        self.assertEqual(
            request.headers["x-amz-content-sha256"],
            EMPTY_PAYLOAD_HASH,
        )
        self.assertIn(
            "AWS4-HMAC-SHA256",
            request.headers["authorization"],
        )

    async def test_stat_maps_not_found_error(self):
        async def handler(request):
            return httpx2.Response(
                404,
                headers={"x-amz-request-id": "request-1"},
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(ObjectNotFound) as raised:
                await client.stat("missing.txt")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.request_id, "request-1")
        self.assertEqual(str(raised.exception), "missing.txt")

    async def test_stat_maps_transport_error(self):
        async def handler(request):
            raise httpx2.ConnectError(
                "connection failed",
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(StorageUnavailable) as raised:
                await client.stat("file.txt")

        self.assertEqual(
            str(raised.exception),
            "R2 HEAD request failed",
        )

    async def test_stat_raises_not_modified_for_matching_etag(self):
        requests = []

        async def handler(request):
            requests.append(request)

            return httpx2.Response(
                304,
                headers={
                    "x-amz-request-id": "request-1",
                    "cf-ray": "ray-1",
                },
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(ObjectNotModified) as raised:
                await client.stat(
                    "file.txt",
                    if_none_match='"abc123"',
                )

        self.assertEqual(raised.exception.status_code, 304)
        self.assertEqual(raised.exception.request_id, "request-1")
        self.assertEqual(raised.exception.cf_ray, "ray-1")
        self.assertEqual(str(raised.exception), "file.txt")

        request = requests[0]
        self.assertEqual(
            request.headers["if-none-match"],
            '"abc123"',
        )
        self.assertIn(
            "if-none-match",
            request.headers["authorization"],
        )

    async def test_stat_sends_if_modified_since(self):
        requests = []

        async def handler(request):
            requests.append(request)

            return httpx2.Response(
                304,
                request=request,
            )

        modified_at = datetime(
            2026,
            8,
            6,
            10,
            30,
            tzinfo=timezone.utc,
        )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            with self.assertRaises(ObjectNotModified):
                await client.stat(
                    "file.txt",
                    if_modified_since=modified_at,
                )

        request = requests[0]
        self.assertEqual(
            request.headers["if-modified-since"],
            "Thu, 06 Aug 2026 10:30:00 GMT",
        )
        self.assertIn(
            "if-modified-since",
            request.headers["authorization"],
        )

    async def test_list_returns_objects_and_next_cursor(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx2.Response(
                200,
                content=b"""\
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>bucket</Name>
  <Prefix>images%2F</Prefix>
  <KeyCount>2</KeyCount>
  <MaxKeys>2</MaxKeys>
  <IsTruncated>true</IsTruncated>
  <NextContinuationToken>next/token+=</NextContinuationToken>
  <Contents>
    <Key>images%2Fa.png</Key>
    <LastModified>2026-08-06T10:30:00.000Z</LastModified>
    <ETag>&quot;etag-a&quot;</ETag>
    <Size>123</Size>
    <StorageClass>STANDARD</StorageClass>
  </Contents>
  <CommonPrefixes>
    <Prefix>images%2Farchive%2F</Prefix>
  </CommonPrefixes>
</ListBucketResult>
""",
                request=request,
            )

        async with AsyncR2Client(
            "https://example.r2.cloudflarestorage.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
        ) as client:
            page = await client.list(
                prefix="images/",
                cursor="current/token+=",
                limit=2,
                delimiter="/",
            )

        self.assertTrue(page.is_truncated)
        self.assertEqual(page.next_cursor, "next/token+=")
        self.assertEqual(len(page.objects), 1)
        self.assertEqual(page.objects[0].key, "images/a.png")
        self.assertEqual(page.objects[0].size, 123)
        self.assertEqual(page.objects[0].etag, '"etag-a"')
        self.assertEqual(
            page.common_prefixes,
            ("images/archive/",),
        )

        request = requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url.params["list-type"], "2")
        self.assertEqual(request.url.params["prefix"], "images/")
        self.assertEqual(
            request.url.params["continuation-token"],
            "current/token+=",
        )
        self.assertEqual(request.url.params["max-keys"], "2")
        self.assertEqual(request.url.params["delimiter"], "/")
        self.assertIn(
            "AWS4-HMAC-SHA256",
            request.headers["authorization"],
        )

    def test_crc(self):
        assert crc64nvme(b"") == 0
        assert crc64nvme(b"123456789") == 0xAE8B14860A799888
        assert crc64nvme_base64(crc64nvme(b"123456789")) == "rosUhgp5mIg="
