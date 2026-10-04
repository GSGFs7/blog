from datetime import timedelta

from django.test import AsyncClient, TestCase, override_settings
from django.utils import timezone

from api.auth import create_client_token
from api.models import ApiClient, ApiClientCredential
from core.fernet import get_fernet


@override_settings(SECURE_SSL_REDIRECT=False)
class TestAuth(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.api_client = ApiClient.objects.create(client_id="test_client_114")
        self.credential = ApiClientCredential.objects.create(
            client=self.api_client, kid="test-key", secret="test-secret"
        )

    def test_auth_get_client_id(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

        token = create_client_token(
            self.api_client.client_id, self.credential.kid, self.credential.secret
        )
        self.assertTrue(token.startswith("v1."))
        response = self.client.get(
            "/api/auth/me",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"client_id": "test_client_114"})

    async def test_async_auth(self):
        async_client = AsyncClient()

        response = await async_client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

        token = create_client_token(
            self.api_client.client_id, self.credential.kid, self.credential.secret
        )
        response = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)

    def test_legacy_token_is_rejected(self):
        token = get_fernet().encrypt(b"test_client_114:legacy-nonce").decode()
        response = self.client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 401)

    def test_credential_rotation_and_revocation(self):
        client = ApiClient.objects.create(client_id="rotating-client")
        first = ApiClientCredential.objects.create(
            client=client, kid="first", secret="first-secret"
        )
        second = ApiClientCredential.objects.create(
            client=client, kid="second", secret="second-secret"
        )

        for credential in (first, second):
            token = create_client_token(
                client.client_id, credential.kid, credential.secret
            )
            response = self.client.get(
                "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"client_id": client.client_id})

        first.revoked_at = timezone.now()
        first.save(update_fields=["revoked_at"])
        old_token = create_client_token(client.client_id, first.kid, first.secret)
        new_token = create_client_token(client.client_id, second.kid, second.secret)
        self.assertEqual(
            self.client.get(
                "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {old_token}"
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {new_token}"
            ).status_code,
            200,
        )

    def test_credential_expiry_replay_and_client_revocation(self):
        client = ApiClient.objects.create(client_id="client")
        credential = ApiClientCredential.objects.create(
            client=client, kid="key", secret="secret"
        )
        token = create_client_token(client.client_id, credential.kid, credential.secret)
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        self.assertEqual(self.client.get("/api/auth/me", **headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me", **headers).status_code, 401)

        credential.expires_at = timezone.now() - timedelta(seconds=1)
        credential.save(update_fields=["expires_at"])
        fresh_token = create_client_token(
            client.client_id, credential.kid, credential.secret
        )
        self.assertEqual(
            self.client.get(
                "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {fresh_token}"
            ).status_code,
            401,
        )

        credential.expires_at = None
        credential.save(update_fields=["expires_at"])
        client.revoked_at = timezone.now()
        client.save(update_fields=["revoked_at"])
        fresh_token = create_client_token(
            client.client_id, credential.kid, credential.secret
        )
        self.assertEqual(
            self.client.get(
                "/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {fresh_token}"
            ).status_code,
            401,
        )

    def test_credential_scope_and_wrong_secret(self):
        client = ApiClient.objects.create(client_id="scoped-client", scopes=[])
        credential = ApiClientCredential.objects.create(
            client=client, kid="scoped-key", secret="right-secret"
        )
        token = create_client_token(client.client_id, credential.kid, "wrong-secret")
        self.assertEqual(
            self.client.post(
                "/api/comment/new", HTTP_AUTHORIZATION=f"Bearer {token}"
            ).status_code,
            401,
        )

        token = create_client_token(client.client_id, credential.kid, credential.secret)
        self.assertEqual(
            self.client.post(
                "/api/comment/new", HTTP_AUTHORIZATION=f"Bearer {token}"
            ).status_code,
            403,
        )
