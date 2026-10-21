from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

import httpx2
from django.test import SimpleTestCase

from core.r2 import (
    EMPTY_PAYLOAD_HASH,
    AsyncR2Client,
    AuthenticationFailed,
    ObjectNotFound,
    PreconditionFailed,
    RateLimited,
    StorageUnavailable,
    SyncR2Client,
    _RetryPolicy,
)


class RetryPolicyTest(SimpleTestCase):
    def test_validates_retry_count(self):
        for value in (True, 1.5, "2"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                _RetryPolicy(value)
        for value in (-1, 11):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _RetryPolicy(value)

    def test_retry_after_seconds_and_date(self):
        policy = _RetryPolicy()
        self.assertEqual(
            policy.delay(0, httpx2.Response(429, headers={"Retry-After": "3"})), 3
        )
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=20)
        delay = policy.delay(
            0, httpx2.Response(503, headers={"Retry-After": format_datetime(retry_at)})
        )
        self.assertGreater(delay, 18)
        self.assertLessEqual(delay, 20)

    def test_invalid_retry_after_uses_bounded_jitter(self):
        with patch("core.r2.random.uniform", return_value=0.25) as jitter:
            for value in ("invalid", "-2", "nan", "inf"):
                self.assertEqual(
                    _RetryPolicy().delay(
                        2, httpx2.Response(429, headers={"Retry-After": value})
                    ),
                    0.25,
                )
            jitter.assert_called_with(0, 2.0)

    def test_non_replayable_operations_are_excluded(self):
        policy = _RetryPolicy()
        for method, headers, body in (
            ("POST", {}, b"complete"),
            ("PUT", {"x-amz-copy-source": "/source"}, None),
            ("PUT", {}, iter([b"data"])),
        ):
            self.assertFalse(policy.allows(method, headers, body))


class BrokenStream(httpx2.SyncByteStream):
    def __iter__(self):
        yield b"first"
        raise httpx2.ReadError("interrupted")


class AsyncBrokenStream(httpx2.AsyncByteStream):
    async def __aiter__(self):
        yield b"first"
        raise httpx2.ReadError("interrupted")


class SyncReliabilityTest(SimpleTestCase):
    def make_client(self, handler, **options):
        client = SyncR2Client(
            "https://example.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
            **options,
        )
        self.addCleanup(client.close)
        return client

    @patch("core.r2.time.sleep")
    def test_retries_status_and_closes_response(self, sleep):
        for status in (408, 429, 500, 502, 503, 504):
            responses = [
                httpx2.Response(status, headers={"Retry-After": "2"}),
                httpx2.Response(200),
            ]
            handler = Mock(side_effect=responses)
            self.make_client(handler).stat("file")
            self.assertEqual(handler.call_count, 2)
            self.assertTrue(responses[0].is_closed)
        sleep.assert_called_with(2)

    @patch("core.r2.time.sleep")
    def test_transport_retry_and_exhaustion(self, sleep):
        handler = Mock(
            side_effect=[httpx2.ConnectError("offline"), httpx2.Response(200)]
        )
        self.make_client(handler).stat("file")
        self.assertEqual(handler.call_count, 2)
        handler = Mock(side_effect=httpx2.ConnectError("offline"))
        with self.assertRaises(StorageUnavailable):
            self.make_client(handler).stat("file")
        self.assertEqual(handler.call_count, 3)

    @patch("core.r2.time.sleep")
    def test_terminal_status_and_disabled_retry(self, sleep):
        for status, error in (
            (403, AuthenticationFailed),
            (404, ObjectNotFound),
            (412, PreconditionFailed),
            (429, RateLimited),
        ):
            handler = Mock(side_effect=lambda request: httpx2.Response(status))
            with self.assertRaises(error):
                self.make_client(handler, max_retries=0 if status == 429 else 2).stat(
                    "file"
                )
            self.assertEqual(handler.call_count, 1)
        sleep.assert_not_called()

    @patch("core.r2.time.sleep")
    def test_small_stream_is_buffered_once_and_replayed(self, sleep):
        reads = []
        requests = []

        def chunks():
            for chunk in (b"da", b"ta"):
                reads.append(chunk)
                yield chunk

        def handler(request):
            requests.append(request)
            return httpx2.Response(503 if len(requests) == 1 else 200)

        self.make_client(handler).put(
            "file", chunks(), content_length=4, if_none_match="*"
        )
        self.assertEqual(reads, [b"da", b"ta"])
        self.assertEqual([request.content for request in requests], [b"data", b"data"])
        self.assertTrue(
            all(request.headers["if-none-match"] == "*" for request in requests)
        )

    def test_empty_and_threshold_streams_support_explicit_single_upload(self):
        for data in (b"", b"data"):
            requests = []

            def handler(request):
                requests.append(request)
                self.assertEqual(request.method, "PUT")
                self.assertFalse(request.url.query)
                self.assertEqual(request.content, data)
                return httpx2.Response(200)

            self.make_client(handler, multipart_threshold=4).put(
                "file", iter([data]), content_length=len(data), strategy="single"
            )
            self.assertEqual(len(requests), 1)

    def test_small_stream_length_failure_sends_nothing(self):
        handler = Mock()
        for size in (3, 5):
            with self.assertRaises(ValueError):
                self.make_client(handler).put(
                    "file", iter([b"data"]), content_length=size
                )
        handler.assert_not_called()

    @patch("core.r2.time.sleep")
    def test_non_replayable_requests_are_not_retried(self, sleep):
        handler = Mock(side_effect=lambda request: httpx2.Response(503))
        client = self.make_client(handler)
        for method, headers, content in (
            ("POST", {}, b"complete"),
            ("PUT", {"x-amz-copy-source": "/source"}, None),
            ("PUT", {}, iter([b"data"])),
        ):
            response = client._transport.send_signed_request(
                method,
                client._object_url("file"),
                headers,
                EMPTY_PAYLOAD_HASH,
                content=content,
                error_message="failed",
            )
            response.close()
        self.assertEqual(handler.call_count, 3)
        sleep.assert_not_called()

    def test_stream_errors_are_mapped_without_replaying(self):
        for read_all in (True, False):
            handler = Mock(
                side_effect=lambda request: httpx2.Response(200, stream=BrokenStream())
            )
            with self.make_client(handler).get("file") as body:
                with self.assertRaises(StorageUnavailable) as raised:
                    if read_all:
                        body.read()
                    else:
                        chunks = body.iter_bytes(5)
                        self.assertEqual(next(chunks), b"first")
                        next(chunks)
                self.assertIsInstance(raised.exception.__cause__, httpx2.ReadError)
            self.assertTrue(body.response.is_closed)
            self.assertEqual(handler.call_count, 1)


class AsyncReliabilityTest(IsolatedAsyncioTestCase):
    async def make_client(self, handler, **options):
        client = AsyncR2Client(
            "https://example.com",
            "access",
            "secret",
            "bucket",
            transport=httpx2.MockTransport(handler),
            **options,
        )
        self.addAsyncCleanup(client.aclose)
        return client

    @patch("core.r2.asyncio.sleep", new_callable=AsyncMock)
    async def test_status_transport_and_exhaustion(self, sleep):
        first = httpx2.Response(429, headers={"Retry-After": "2"})
        handler = Mock(
            side_effect=[first, httpx2.ConnectError("offline"), httpx2.Response(200)]
        )
        client = await self.make_client(handler)
        await client.stat("file")
        self.assertEqual(handler.call_count, 3)
        self.assertTrue(first.is_closed)
        self.assertEqual(sleep.await_args_list[0].args, (2,))
        handler = Mock(side_effect=lambda request: httpx2.Response(503))
        client = await self.make_client(handler)
        with self.assertRaises(StorageUnavailable):
            await client.stat("file")
        self.assertEqual(handler.call_count, 3)

    @patch("core.r2.asyncio.sleep", new_callable=AsyncMock)
    async def test_small_stream_is_buffered_once_and_replayed(self, sleep):
        reads = []
        requests = []

        async def chunks():
            for chunk in (b"da", b"ta"):
                reads.append(chunk)
                yield chunk

        def handler(request):
            requests.append(request)
            return httpx2.Response(503 if len(requests) == 1 else 200)

        client = await self.make_client(handler)
        await client.put("file", chunks(), content_length=4)
        self.assertEqual(reads, [b"da", b"ta"])
        self.assertEqual([request.content for request in requests], [b"data", b"data"])

    async def test_empty_and_threshold_streams_support_explicit_single_upload(self):
        for data in (b"", b"data"):
            requests = []

            async def chunks():
                yield data

            def handler(request):
                requests.append(request)
                self.assertEqual(request.method, "PUT")
                self.assertFalse(request.url.query)
                self.assertEqual(request.content, data)
                return httpx2.Response(200)

            client = await self.make_client(handler, multipart_threshold=4)
            await client.put(
                "file", chunks(), content_length=len(data), strategy="single"
            )
            self.assertEqual(len(requests), 1)

    async def test_small_stream_length_failure_sends_nothing(self):
        handler = Mock()
        client = await self.make_client(handler)
        for size in (3, 5):

            async def chunks():
                yield b"data"

            with self.assertRaises(ValueError):
                await client.put("file", chunks(), content_length=size)
        handler.assert_not_called()

    @patch("core.r2.asyncio.sleep", new_callable=AsyncMock)
    async def test_terminal_status_and_non_replayable_requests(self, sleep):
        handler = Mock(side_effect=lambda request: httpx2.Response(412))
        client = await self.make_client(handler)
        with self.assertRaises(PreconditionFailed):
            await client.put("file", b"data", if_none_match="*")
        self.assertEqual(handler.call_count, 1)
        handler = Mock(side_effect=lambda request: httpx2.Response(503))
        client = await self.make_client(handler)

        async def chunks():
            yield b"data"

        for method, headers, content in (
            ("POST", {}, b"complete"),
            ("PUT", {"x-amz-copy-source": "/source"}, None),
            ("PUT", {}, chunks()),
        ):
            response = await client._transport.send_signed_request(
                method,
                client._object_url("file"),
                headers,
                EMPTY_PAYLOAD_HASH,
                content=content,
                error_message="failed",
            )
            await response.aclose()
        self.assertEqual(handler.call_count, 3)
        sleep.assert_not_awaited()

    async def test_stream_errors_are_mapped_without_replaying(self):
        for read_all in (True, False):
            handler = Mock(
                side_effect=lambda request: httpx2.Response(
                    200, stream=AsyncBrokenStream()
                )
            )
            client = await self.make_client(handler)
            async with await client.get("file") as body:
                with self.assertRaises(StorageUnavailable) as raised:
                    if read_all:
                        await body.read()
                    else:
                        chunks = body.aiter_bytes(5)
                        self.assertEqual(await anext(chunks), b"first")
                        await anext(chunks)
                self.assertIsInstance(raised.exception.__cause__, httpx2.ReadError)
            self.assertTrue(body.response.is_closed)
            self.assertEqual(handler.call_count, 1)
