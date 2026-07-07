import inspect

from django.contrib.auth.models import AnonymousUser
from django.core.handlers.exception import response_for_exception
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings

TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(DEBUG=False, STORAGES=TEST_STORAGES)
class ErrorViewTests(SimpleTestCase):
    def test_missing_path_exception_returns_404_response(self):
        request = RequestFactory().get("/.env")
        request.user = AnonymousUser()

        response = response_for_exception(request, Http404("missing"))

        self.assertFalse(inspect.isawaitable(response))
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "404: RESOURCE NOT FOUND", status_code=404)
