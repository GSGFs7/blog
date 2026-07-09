from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from web.middleware import HtmxMiddleware
from web.middleware.htmx import HtmxHttpRequest


class HtmxMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_sync_request_without_htmx_headers(self):
        calls = 0
        request = self.factory.get("/")

        def get_response(req: HtmxHttpRequest):
            nonlocal calls

            calls += 1
            self.assertFalse(req.htmx)
            self.assertFalse(req.htmx.request)
            self.assertFalse(req.htmx.boosted)
            self.assertIsNone(req.htmx.target)
            return HttpResponse("ok")

        # noinspection PyTypeChecker
        middleware = HtmxMiddleware(get_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, 1)

    def test_sync_request_with_htmx_headers(self):
        request = self.factory.get(
            "/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_BOOSTED="true",
            HTTP_HX_CURRENT_URL="https://gsgfs.moe/blog",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
            HTTP_HX_PROMPT="confirm",
            HTTP_HX_TARGET="post-list",
            HTTP_HX_TRIGGER="load-more",
            HTTP_HX_TRIGGER_NAME="load_more_button",
        )

        def get_response(req):
            self.assertTrue(req.htmx)
            self.assertTrue(req.htmx.request)
            self.assertTrue(req.htmx.boosted)
            self.assertEqual(req.htmx.current_url, "https://gsgfs.moe/blog")
            self.assertTrue(req.htmx.history_restore_request)
            self.assertEqual(req.htmx.prompt, "confirm")
            self.assertEqual(req.htmx.target, "post-list")
            self.assertEqual(req.htmx.trigger, "load-more")
            self.assertEqual(req.htmx.trigger_name, "load_more_button")
            return HttpResponse("ok")

        # noinspection PyTypeChecker
        middleware = HtmxMiddleware(get_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)


class HtmxMiddlewareAsyncTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    async def test_async_request_with_htmx_headers(self):
        calls = 0
        request = self.factory.get(
            "/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="comments",
        )

        async def get_response(req: HtmxHttpRequest):
            nonlocal calls

            calls += 1
            self.assertTrue(req.htmx)
            self.assertEqual(req.htmx.target, "comments")
            return HttpResponse("ok")

        # noinspection PyTypeChecker
        middleware = HtmxMiddleware(get_response)
        response = await middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, 1)
