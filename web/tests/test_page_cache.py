from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.cache import patch_vary_headers

from api.models import Post
from web.cache import private_page_response, public_page_response
from web.middleware import HeadersMiddleware
from web.views import server_error

SIGNED_COOKIE_SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"


class PageCacheHelperTests(SimpleTestCase):
    @patch("web.cache.time_ns", return_value=1_785_124_800_000_000_000)
    def test_public_page_response_adds_cache_contract(self, time_ns):
        response = HttpResponse("<html></html>", content_type="text/html")

        result = public_page_response(
            response,
            edge_max_age=300,
            max_stale=86400,
            stale_while_revalidate=300,
            stale_if_error=300,
        )

        self.assertIs(result, response)
        self.assertEqual(result.headers["Cache-Control"], "no-cache")
        self.assertEqual(
            result.headers["Cloudflare-CDN-Cache-Control"],
            ("public, max-age=300, stale-while-revalidate=300, stale-if-error=300"),
        )
        self.assertEqual(result.headers["X-Page-Cache"], "public")
        self.assertEqual(result.headers["X-Page-Cache-Max-Stale"], "86400")
        self.assertEqual(result.headers["X-Page-Generated-At"], "1785124800000")
        time_ns.assert_called_once_with()

    def test_public_page_response_rejects_non_page_responses(self):
        responses = [
            HttpResponse(status=301, content_type="text/html"),
            HttpResponse("markdown", content_type="text/markdown"),
        ]

        for response in responses:
            with self.subTest(
                status=response.status_code,
                content_type=response.headers["Content-Type"],
            ):
                with self.assertRaisesRegex(ValueError, "200 HTML"):
                    public_page_response(
                        response,
                        edge_max_age=300,
                        max_stale=86400,
                    )

    def test_public_page_response_rejects_invalid_ages(self):
        invalid_values = [-1, True, 1.5]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "edge_max_age"):
                    public_page_response(
                        HttpResponse("<html></html>", content_type="text/html"),
                        edge_max_age=value,
                        max_stale=86400,
                    )

    def test_private_page_response_overwrites_public_contract(self):
        response = public_page_response(
            HttpResponse("<html></html>", content_type="text/html"),
            edge_max_age=300,
            max_stale=86400,
        )

        result = private_page_response(response)

        self.assertEqual(result.headers["Cache-Control"], "private, no-store")
        self.assertEqual(
            result.headers["Cloudflare-CDN-Cache-Control"],
            "private, no-store",
        )
        self.assertEqual(result.headers["X-Page-Cache"], "private")
        self.assertNotIn("X-Page-Cache-Max-Stale", result.headers)
        self.assertNotIn("X-Page-Generated-At", result.headers)


@override_settings(SESSION_ENGINE=SIGNED_COOKIE_SESSION_ENGINE)
class PageCacheMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_headers_middleware_runs_after_session_response_processing(self):
        headers_index = settings.MIDDLEWARE.index("web.middleware.HeadersMiddleware")
        session_index = settings.MIDDLEWARE.index(
            "django.contrib.sessions.middleware.SessionMiddleware"
        )

        self.assertLess(headers_index, session_index)

    def test_session_cookie_downgrades_public_response(self):
        def view(request):
            request.session["identity"] = "secret"
            return public_page_response(
                HttpResponse("<html></html>", content_type="text/html"),
                edge_max_age=300,
                max_stale=86400,
            )

        middleware = HeadersMiddleware(SessionMiddleware(view))
        response = middleware(self.factory.get("/"))

        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(response.headers["X-Page-Cache"], "private")
        self.assertIn("sessionid", response.cookies)
        self.assertIn("Cookie", response.headers["Vary"])

    def test_vary_cookie_downgrades_public_response(self):
        response = public_page_response(
            HttpResponse("<html></html>", content_type="text/html"),
            edge_max_age=300,
            max_stale=86400,
        )
        patch_vary_headers(response, ["Cookie"])
        middleware = HeadersMiddleware(lambda request: response)

        result = middleware(self.factory.get("/"))

        self.assertEqual(result.headers["X-Page-Cache"], "private")
        self.assertEqual(result.headers["Cache-Control"], "private, no-store")

    def test_unmarked_html_defaults_to_private(self):
        middleware = HeadersMiddleware(
            lambda request: HttpResponse("<html></html>", content_type="text/html")
        )

        response = middleware(self.factory.get("/account/login/"))

        self.assertEqual(response.headers["X-Page-Cache"], "private")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_unmarked_api_response_defaults_to_private(self):
        middleware = HeadersMiddleware(lambda request: JsonResponse({"ok": True}))

        response = middleware(self.factory.get("/api/status"))

        self.assertEqual(response.headers["X-Page-Cache"], "private")
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_unmarked_non_html_response_preserves_cache_policy(self):
        response = HttpResponse("feed", content_type="application/atom+xml")
        response.headers["Cache-Control"] = "public, max-age=60"
        middleware = HeadersMiddleware(lambda request: response)

        result = middleware(self.factory.get("/blog/feed.atom"))

        self.assertEqual(result.headers["Cache-Control"], "public, max-age=60")
        self.assertNotIn("Cloudflare-CDN-Cache-Control", result.headers)
        self.assertNotIn("X-Page-Cache", result.headers)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_ENGINE=SIGNED_COOKIE_SESSION_ENGINE,
)
class PageCacheViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.post = Post.objects.create(
            title="Cacheable post",
            slug="cacheable-post",
            content="# Cacheable post",
            meta_description="Cacheable post",
            keywords="cache",
            status="published",
        )
        cls.user = get_user_model().objects.create_user(
            username="cache-user",
            password="test-password",
        )

    def assert_public_page(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        self.assertEqual(
            response.headers["Cloudflare-CDN-Cache-Control"],
            "public, max-age=300",
        )
        self.assertEqual(response.headers["X-Page-Cache"], "public")
        self.assertEqual(response.headers["X-Page-Cache-Max-Stale"], "86400")
        self.assertGreaterEqual(int(response.headers["X-Page-Generated-At"]), 0)
        self.assertFalse(response.cookies)
        vary = {
            item.strip().lower()
            for item in response.headers.get("Vary", "").split(",")
            if item.strip()
        }
        self.assertNotIn("cookie", vary)

    def assert_private_page(self, response):
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(
            response.headers["Cloudflare-CDN-Cache-Control"],
            "private, no-store",
        )
        self.assertEqual(response.headers["X-Page-Cache"], "private")
        self.assertNotIn("X-Page-Cache-Max-Stale", response.headers)
        self.assertNotIn("X-Page-Generated-At", response.headers)

    def public_paths(self):
        return [
            reverse("index"),
            reverse("blog"),
            reverse("blog_post_slug", args=[self.post.slug]),
            reverse("about"),
            reverse("entertainment"),
            reverse("privacy"),
        ]

    def test_public_pages_expose_cache_contract_for_get_and_head(self):
        for path in self.public_paths():
            for method in ("get", "head"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path)
                    self.assert_public_page(response)

    def test_public_page_is_identity_neutral(self):
        anonymous_response = self.client.get(reverse("index"))
        self.client.force_login(self.user)
        authenticated_response = self.client.get(reverse("index"))

        self.assert_public_page(anonymous_response)
        self.assert_public_page(authenticated_response)
        self.assertEqual(anonymous_response.content, authenticated_response.content)

    def test_private_pages_expose_no_store_contract(self):
        paths = [
            reverse("test"),
            reverse("login"),
            reverse("user"),
            reverse("blog_random_post"),
            reverse("blog_post_id", args=[self.post.pk]),
        ]

        for path in paths:
            with self.subTest(path=path):
                self.assert_private_page(self.client.get(path))

    def test_non_public_pages_reject_head(self):
        paths = [
            reverse("test"),
            reverse("blog_random_post"),
            reverse("blog_post_id", args=[self.post.pk]),
            reverse("blog_post_markdown", args=[self.post.slug]),
            reverse("favicon"),
            reverse("robots"),
            reverse("llms"),
        ]

        for path in paths:
            with self.subTest(path=path):
                response = self.client.head(path)
                self.assertEqual(response.status_code, 405)
                self.assert_private_page(response)

    def test_markdown_feed_and_sitemap_are_outside_page_cache_protocol(self):
        paths = [
            reverse("blog_post_markdown", args=[self.post.slug]),
            reverse("blog_feed"),
            reverse("django.contrib.sitemaps.views.sitemap"),
        ]

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-Page-Cache", response.headers)
                self.assertNotIn(
                    "Cloudflare-CDN-Cache-Control",
                    response.headers,
                )

    def test_redirect_and_error_responses_are_private(self):
        redirect_responses = [
            self.client.get(reverse("favicon")),
            self.client.get(reverse("robots")),
            self.client.get(reverse("llms")),
        ]
        responses = [
            *redirect_responses,
            self.client.get("/missing-page"),
            server_error(RequestFactory().get("/broken-page")),
        ]

        for response in redirect_responses:
            self.assertEqual(response.status_code, 301)
        self.assertEqual(responses[-2].status_code, 404)
        self.assertEqual(responses[-1].status_code, 500)
        for response in responses:
            self.assert_private_page(response)

    @override_settings(
        DEBUG=False,
        STATIC_URL="https://static.gsgfs.moe/static/",
    )
    def test_static_redirects_use_remote_hashed_assets(self):
        assets = {
            "favicon": r"favicon\.[0-9a-f]{12}\.ico",
            "robots": r"robots\.[0-9a-f]{12}\.txt",
            "llms": r"llms\.[0-9a-f]{12}\.txt",
        }

        for view_name, asset_pattern in assets.items():
            with self.subTest(view_name=view_name):
                response = self.client.get(reverse(view_name))
                self.assertEqual(response.status_code, 301)
                self.assertRegex(
                    response.headers["Location"],
                    rf"^https://static\.gsgfs\.moe/static/{asset_pattern}$",
                )

    def test_api_response_is_private(self):
        response = self.client.get("/api/auth/oauth/providers")

        self.assertEqual(response.status_code, 200)
        self.assert_private_page(response)
