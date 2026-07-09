from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from django.test import Client, TransactionTestCase, override_settings

from api.models import Guest, OAuthIdentity, OAuthProvider
from api.routers.auth import OAUTH_FLOW_SESSION_KEY


@override_settings(SECURE_SSL_REDIRECT=False)
class OAuthEndpointTest(TransactionTestCase):
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
        self.guest = Guest.objects.create(
            name="Test User",
            email="user@example.com",
            avatar="https://example.com/avatar.png",
        )
        self.identity = OAuthIdentity.objects.create(
            guest=self.guest,
            provider=self.provider,
            user_id="provider-user-id",
        )
        self.client = Client(enforce_csrf_checks=True)

    def start_login(self, return_to="/"):
        response = self.client.get(
            "/api/auth/oauth/example/login",
            {"return_to": return_to},
        )
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlsplit(response["Location"]).query)
        return response, query["state"][0]

    def test_lists_active_providers(self):
        OAuthProvider.objects.create(
            provider_key="inactive",
            name="Inactive",
            client_id="",
            client_secret="",
            authorization_url="https://inactive.example/authorize",
            token_url="https://inactive.example/token",
            userinfo_url="https://inactive.example/user",
            is_active=False,
        )

        response = self.client.get("/api/auth/oauth/providers")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), [{"provider_key": "example", "name": "Example"}]
        )

    def test_login_redirect_stores_state_and_pkce(self):
        response, state = self.start_login("https://evil.example/redirect")

        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["state"], [state])
        flow = self.client.session[OAUTH_FLOW_SESSION_KEY][state]
        self.assertEqual(flow["provider_key"], "example")
        self.assertEqual(
            flow["redirect_uri"],
            "http://testserver/api/auth/oauth/example/callback",
        )
        self.assertEqual(flow["return_to"], "/")
        self.assertTrue(flow["code_verifier"])

    def test_callback_creates_session_and_logout_clears_it(self):
        _, state = self.start_login("/posts/1")

        with patch(
            "api.routers.auth.OAuthService.login",
            new=AsyncMock(return_value=self.identity),
        ) as login:
            response = self.client.get(
                "/api/auth/oauth/example/callback",
                {"state": state, "code": "authorization-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/posts/1")
        login.assert_awaited_once()
        self.assertEqual(
            login.await_args.kwargs["redirect_uri"],
            "http://testserver/api/auth/oauth/example/callback",
        )
        self.assertTrue(login.await_args.kwargs["code_verifier"])

        response = self.client.get("/api/auth/oauth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "identity_id": self.identity.pk,
                "guest_id": self.guest.pk,
                "provider_key": "example",
                "user_id": "provider-user-id",
                "name": "Test User",
                "email": "user@example.com",
                "avatar": "https://example.com/avatar.png",
            },
        )

        response = self.client.post("/api/auth/oauth/logout")
        self.assertEqual(response.status_code, 403)

        csrf_token = self.client.cookies["csrftoken"].value
        response = self.client.post(
            "/api/auth/oauth/logout",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/oauth/me").status_code, 401)

    def test_callback_rejects_unknown_and_replayed_state(self):
        response = self.client.get(
            "/api/auth/oauth/example/callback",
            {"state": "unknown", "code": "authorization-code"},
        )
        self.assertEqual(response.status_code, 400)

        _, state = self.start_login()
        with patch(
            "api.routers.auth.OAuthService.login",
            new=AsyncMock(return_value=self.identity),
        ):
            response = self.client.get(
                "/api/auth/oauth/example/callback",
                {"state": state, "code": "authorization-code"},
            )
            replay = self.client.get(
                "/api/auth/oauth/example/callback",
                {"state": state, "code": "authorization-code"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(replay.status_code, 400)
