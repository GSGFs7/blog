from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase

import httpx2
from django.test import SimpleTestCase

from core.r2 import (
    EMPTY_PAYLOAD_HASH,
    AsyncR2Client,
    ObjectNotFound,
    SigV4Signer,
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
