from django.http import HttpResponse
from django.test import RequestFactory, TransactionTestCase

from api.middleware import OAuthGuestMiddleware
from api.models import Guest, OAuthIdentity, OAuthProvider
from api.services.oauth_session import OAUTH_IDENTITY_SESSION_KEY


class AsyncSession(dict):
    async def aget(self, key, default=None):
        return self.get(key, default)

    async def apop(self, key, default=None):
        return self.pop(key, default)


class OAuthGuestMiddlewareTests(TransactionTestCase):
    def setUp(self):
        provider = OAuthProvider.objects.create(
            provider_key="example",
            name="Example",
            client_id="client-id",
            client_secret="client-secret",
            authorization_url="https://oauth.example/authorize",
            token_url="https://oauth.example/token",
            userinfo_url="https://oauth.example/user",
        )
        self.guest = Guest.objects.create(
            name="Test User",
            email="user@example.com",
        )
        self.identity = OAuthIdentity.objects.create(
            guest=self.guest,
            provider=provider,
            user_id="provider-user-id",
        )
        self.factory = RequestFactory()

    def test_attaches_oauth_identity_and_guest_for_sync_requests(self):
        request = self.factory.get("/")
        request.session = {OAUTH_IDENTITY_SESSION_KEY: self.identity.pk}

        def get_response(request):
            self.assertNotIn("_cached_oauth_identity", request.__dict__)
            return HttpResponse()

        middleware = OAuthGuestMiddleware(get_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.oauth_identity.pk, self.identity.pk)
        self.assertEqual(request.guest.pk, self.guest.pk)

    async def test_attaches_oauth_identity_and_guest_for_async_requests(self):
        request = self.factory.get("/")
        request.session = AsyncSession({OAUTH_IDENTITY_SESSION_KEY: self.identity.pk})

        async def get_response(request):
            self.assertNotIn("_acached_oauth_identity", request.__dict__)
            identity = await request.aoauth_identity()
            guest = await request.aguest()
            self.assertEqual(identity.pk, self.identity.pk)
            self.assertEqual(guest.pk, self.guest.pk)
            return HttpResponse()

        middleware = OAuthGuestMiddleware(get_response)
        response = await middleware(request)

        self.assertEqual(response.status_code, 200)

    def test_attaches_empty_identity_for_anonymous_requests(self):
        request = self.factory.get("/")
        request.session = {}

        middleware = OAuthGuestMiddleware(lambda request: HttpResponse())
        middleware(request)

        self.assertEqual(request.oauth_identity, None)
        self.assertEqual(request.guest, None)
