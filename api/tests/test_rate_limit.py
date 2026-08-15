from unittest.mock import AsyncMock, patch

from django.http import HttpRequest
from django.test import RequestFactory, SimpleTestCase, override_settings

from api.rate_limit import rate_limit


class RateLimitTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/")
        self.request.META["REMOTE_ADDR"] = "127.0.0.1"

    # mock the cache service, not use really redis service
    @patch("api.rate_limit.cache")
    def test_sync_rate_limit_pass(self, mock_cache):
        mock_cache.incr.return_value = 1

        @rate_limit(key_prefix="test_sync", max_requests=2, window=60)
        def test_view(request: HttpRequest):
            return 200, "ok"

        status, res = test_view(self.request)
        self.assertEqual(status, 200)
        self.assertEqual(mock_cache.add.call_count, 1)
        self.assertEqual(mock_cache.incr.call_count, 1)

    @patch("api.rate_limit.cache")
    def test_sync_rate_limit_black(self, mock_cache):
        mock_cache.incr.return_value = 3

        @rate_limit(key_prefix="test_sync", max_requests=2, window=60)
        def test_view(request: HttpRequest):
            return 200, "ok"

        status, res = test_view(self.request)
        self.assertEqual(status, 429)
        self.assertEqual(res.get("message"), "Too many request")

    @override_settings(TRUSTED_PROXY_CIDRS=("10.42.0.0/16",))
    @patch("api.rate_limit.cache")
    def test_sync_rate_limit_uses_cloudflare_client_ip(self, mock_cache):
        mock_cache.incr.return_value = 1
        self.request.META["REMOTE_ADDR"] = "10.42.0.33"
        self.request.META["HTTP_CF_CONNECTING_IP"] = "203.0.113.10"

        @rate_limit(key_prefix="test_sync", max_requests=2, window=60)
        def test_view(request: HttpRequest):
            return 200, "ok"

        test_view(self.request)

        mock_cache.add.assert_called_once_with(
            "rate_limit:test_sync:203.0.113.10",
            0,
            timeout=60,
        )

    @override_settings(TRUSTED_PROXY_CIDRS=("10.42.0.0/16",))
    @patch("api.rate_limit.cache")
    def test_sync_rate_limit_skips_unattributable_proxy_request(self, mock_cache):
        self.request.META["REMOTE_ADDR"] = "10.42.0.33"

        @rate_limit(key_prefix="test_sync", max_requests=2, window=60)
        def test_view(request: HttpRequest):
            return 200, "ok"

        status, _ = test_view(self.request)

        self.assertEqual(status, 200)
        mock_cache.add.assert_not_called()
        mock_cache.incr.assert_not_called()

    @patch("api.rate_limit.cache")
    async def test_async_rate_limit_pass(self, mock_cache):
        mock_cache.aincr = AsyncMock(return_value=1)
        mock_cache.aadd = AsyncMock()

        @rate_limit(key_prefix="test_async", max_requests=2, window=60)
        async def test_view(request: HttpRequest):
            return 200, "ok"

        status, res = await test_view(self.request)
        self.assertEqual(status, 200)
        mock_cache.aadd.assert_called_once()
        mock_cache.aincr.assert_called_once()

    @patch("api.rate_limit.cache")
    async def test_async_rate_limit_block(self, mock_cache):
        mock_cache.aincr = AsyncMock(return_value=3)
        mock_cache.aadd = AsyncMock()

        @rate_limit(key_prefix="test_async", max_requests=2, window=60)
        async def test_view(request: HttpRequest):
            return 200, "ok"

        status, res = await test_view(self.request)
        self.assertEqual(status, 429)
        self.assertEqual(res.get("message"), "Too many request")
