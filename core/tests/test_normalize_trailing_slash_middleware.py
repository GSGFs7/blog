from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.middleware import NormalizeTrailingSlashMiddleware


class NormalizeTrailingSlashMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    def get_response(request):
        return HttpResponse(status=204)

    def test_redirects_resolvable_path_with_trailing_slash(self):
        middleware = NormalizeTrailingSlashMiddleware(self.get_response)

        response = middleware(self.factory.get("/about/"))

        self.assertEqual(response.status_code, 308)
        self.assertEqual(response.headers["Location"], "/about")

    def test_preserves_query_string(self):
        middleware = NormalizeTrailingSlashMiddleware(self.get_response)

        response = middleware(self.factory.get("/blog/?page=2&tag=django%2Fninja"))

        self.assertEqual(response.status_code, 308)
        self.assertEqual(
            response.headers["Location"],
            "/blog?page=2&tag=django%2Fninja",
        )

    def test_uses_method_preserving_redirect_for_post(self):
        middleware = NormalizeTrailingSlashMiddleware(self.get_response)

        response = middleware(self.factory.post("/login/", {"username": "test"}))

        self.assertEqual(response.status_code, 308)
        self.assertEqual(response.headers["Location"], "/login")

    def test_passes_canonical_and_unresolvable_paths_to_next_middleware(self):
        middleware = NormalizeTrailingSlashMiddleware(self.get_response)

        for path in (
            "/",
            "/about",
            "/missing/",
            "/not-admin/",
            "/not-admin/login/",
            "/prometheus/",
        ):
            with self.subTest(path=path):
                response = middleware(self.factory.get(path))

                self.assertEqual(response.status_code, 204)

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_is_registered_in_project_middleware(self):
        response = self.client.get("/about/?page=2")

        self.assertEqual(response.status_code, 308)
        self.assertEqual(response.headers["Location"], "/about?page=2")

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_does_not_redirect_admin_urls(self):
        index_response = self.client.get("/not-admin/")
        login_response = self.client.get("/not-admin/login/?next=/not-admin/")

        self.assertEqual(index_response.status_code, 302)
        self.assertEqual(
            index_response.headers["Location"],
            "/not-admin/login/?next=/not-admin/",
        )
        self.assertNotEqual(login_response.status_code, 308)

    async def test_supports_async_response_chain(self):
        async def get_response(request):
            return HttpResponse(status=204)

        middleware = NormalizeTrailingSlashMiddleware(get_response)

        redirect_response = await middleware(self.factory.get("/about/"))
        downstream_response = await middleware(self.factory.get("/about"))

        self.assertEqual(redirect_response.status_code, 308)
        self.assertEqual(redirect_response.headers["Location"], "/about")
        self.assertEqual(downstream_response.status_code, 204)
