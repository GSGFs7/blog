from datetime import datetime, timezone
from hashlib import sha256
from unittest import IsolatedAsyncioTestCase

import httpx2
from django.test import SimpleTestCase

from core.r2 import (
    EMPTY_PAYLOAD_HASH,
    AsyncR2Client,
    AuthenticationFailed,
    ObjectNotFound,
    ObjectNotModified,
    PreconditionFailed,
    SigV4Signer,
    StorageUnavailable,
)


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

        async def handler(request):
            requests.append(request)
            body = await request.aread()
            self.assertEqual(body, b"hello")

            return httpx2.Response(
                200,
                headers={
                    "etag": '"abc123"',
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
                content_type="text/plain",
                cache_control="public, max-age=3600",
                metadata={"kind": "demo"},
                if_none_match="*",
            )

        self.assertEqual(result.key, "folder/file.txt")
        self.assertEqual(result.etag, '"abc123"')
        self.assertEqual(result.version_id, "version-1")

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
        self.assertIn(
            "AWS4-HMAC-SHA256",
            request.headers["authorization"],
        )

    async def test_put_supports_empty_body(self):
        async def handler(request):
            self.assertEqual(await request.aread(), b"")
            self.assertEqual(
                request.headers["x-amz-content-sha256"],
                EMPTY_PAYLOAD_HASH,
            )
            return httpx2.Response(
                200,
                headers={"etag": '"empty"'},
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
                await client.put(
                    "existing.txt",
                    b"hello",
                    if_none_match="*",
                )

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
            with self.assertRaises(ObjectNotModified) as raised:
                await client.stat(
                    "file.txt",
                    if_none_match='"abc123"',
                )

        self.assertEqual(raised.exception.status_code, 304)
        self.assertEqual(raised.exception.request_id, "request-1")
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
