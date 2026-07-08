from django.test import AsyncClient, TestCase, override_settings

from api.auth import TimeBaseAuth


@override_settings(SECURE_SSL_REDIRECT=False)
class TestAuth(TestCase):
    def setUp(self) -> None:
        return super().setUp()

    def test_auth_get_client_id(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

        token = TimeBaseAuth.create_token("test_client_114")
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

        token = TimeBaseAuth.create_token("test_client_114")
        response = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
