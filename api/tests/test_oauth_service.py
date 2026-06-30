from urllib.parse import parse_qs, urlsplit

import httpx
from django.test import TransactionTestCase

from api.models import Guest, OAuthIdentity, OAuthProvider
from api.services.oauth import OAuthService


class OAuthServiceTest(TransactionTestCase):
    def setUp(self):
        self.provider = OAuthProvider.objects.create(
            provider_key="example",
            name="Example",
            client_id="client-id",
            client_secret="client-secret",
            authorization_url="https://oauth.example/authorize",
            token_url="https://oauth.example/token",
            userinfo_url="https://oauth.example/user",
            scope="openid profile email",
        )

    async def test_authorization_url(self):
        service = OAuthService(self.provider)

        url = service.authorization_url(
            redirect_uri="https://blog.example/callback",
            state="state-value",
            code_challenge="challenge-value",
        )

        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], ["https://blog.example/callback"])
        self.assertEqual(query["state"], ["state-value"])
        self.assertEqual(query["scope"], ["openid profile email"])
        self.assertEqual(query["code_challenge"], ["challenge-value"])
        self.assertEqual(query["code_challenge_method"], ["S256"])

    async def test_complete_login_creates_and_updates_identity(self):
        user_name = "Test User"

        async def handler(request):
            nonlocal user_name
            if request.url.path == "/token":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "access-token",
                        "refresh_token": "refresh-token",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "sub": "provider-user-id",
                    "name": user_name,
                    "email": "user@example.com",
                    "picture": "https://example.com/avatar.png",
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OAuthService(self.provider, client=client)
            identity = await service.login(
                code="authorization-code",
                redirect_uri="https://blog.example/callback",
            )
            user_name = "Updated User"
            updated_identity = await service.login(
                code="new-authorization-code",
                redirect_uri="https://blog.example/callback",
            )

        self.assertEqual(identity.pk, updated_identity.pk)
        self.assertEqual(await Guest.objects.acount(), 1)
        self.assertEqual(await OAuthIdentity.objects.acount(), 1)
        identity = await OAuthIdentity.objects.select_related("guest").aget()
        self.assertEqual(identity.user_id, "provider-user-id")
        self.assertEqual(identity.access_token, "access-token")
        self.assertEqual(identity.refresh_token, "refresh-token")
        self.assertEqual(identity.guest.name, "Updated User")
        self.assertEqual(identity.guest.email, "user@example.com")
        self.assertEqual(identity.guest.avatar, "https://example.com/avatar.png")
        self.assertEqual(identity.extra_data["sub"], "provider-user-id")
