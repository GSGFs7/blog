import asyncio
from io import BytesIO
from ipaddress import IPv4Address
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx2
from django.core.files.storage import FileSystemStorage
from django.test import TransactionTestCase, override_settings
from PIL import Image as PILImage

from api.models import Guest, OAuthIdentity, OAuthProvider
from api.services.avatar import AvatarService
from api.services.oauth import OAuthService


def _make_png_bytes(color: str, size: tuple[int, int] = (200, 120)) -> bytes:
    buf = BytesIO()
    PILImage.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _public_resolver(_host: str, _port: int):
    # Public IP (former example.com); cannot use RFC 5737 (is_global=False).
    return [IPv4Address("93.184.216.34")]


class OAuthServiceTest(TransactionTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage = FileSystemStorage(
            location=self.temp_dir.name,
            base_url="/media/",
        )
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

    def _avatar_service(self, handler):
        return AvatarService(
            timeout=AvatarService.LOGIN_TIMEOUT,
            storage=self.storage,
            resolver=_public_resolver,
            async_transport=httpx2.MockTransport(handler),
        )

    def _oauth_client(self, handler):
        async def oauth_handler(request):
            self.assertEqual(request.url.host, "oauth.example")
            return await handler(request)

        return httpx2.AsyncClient(transport=httpx2.MockTransport(oauth_handler))

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
        avatar_bytes = _make_png_bytes("red")

        async def handler(request):
            nonlocal user_name, avatar_bytes
            if request.url.path == "/token":
                return httpx2.Response(
                    200,
                    json={
                        "access_token": "access-token",
                        "refresh_token": "refresh-token",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            if request.url.path == "/avatar.png":
                return httpx2.Response(
                    200,
                    headers={"content-type": "image/png"},
                    content=avatar_bytes,
                )
            return httpx2.Response(
                200,
                json={
                    "sub": "provider-user-id",
                    "name": user_name,
                    "email": "user@example.com",
                    "picture": "https://example.com/avatar.png",
                },
            )

        async with self._oauth_client(handler) as client:
            service = OAuthService(
                self.provider,
                client=client,
                avatar_service=self._avatar_service(handler),
            )
            identity = await service.login(
                code="authorization-code",
                redirect_uri="https://blog.example/callback",
            )
            first_avatar = identity.guest.avatar

            user_name = "Updated User"
            avatar_bytes = _make_png_bytes("blue")
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
        self.assertTrue(first_avatar.startswith("/media/avatars/"))
        self.assertTrue(identity.guest.avatar.startswith("/media/avatars/"))
        self.assertTrue(identity.guest.avatar.endswith(".webp"))
        self.assertNotEqual(first_avatar, identity.guest.avatar)
        self.assertEqual(
            identity.guest.avatar_source_url, "https://example.com/avatar.png"
        )
        self.assertEqual(identity.extra_data["sub"], "provider-user-id")

    async def test_login_schedules_retry_on_avatar_failure_without_leaking_external_url(
        self,
    ):
        fail_avatar = True
        avatar_bytes = _make_png_bytes("green")

        async def handler(request):
            if request.url.path == "/token":
                return httpx2.Response(
                    200,
                    json={
                        "access_token": "access-token",
                        "token_type": "Bearer",
                    },
                )
            if request.url.path == "/avatar.png":
                if fail_avatar:
                    return httpx2.Response(503)
                return httpx2.Response(
                    200,
                    headers={"content-type": "image/png"},
                    content=avatar_bytes,
                )
            return httpx2.Response(
                200,
                json={
                    "sub": "provider-user-id",
                    "name": "Test User",
                    "email": "user@example.com",
                    "picture": "https://example.com/avatar.png",
                },
            )

        with (
            patch("api.tasks.sync_guest_avatar_task.delay") as delay_mock,
            self.assertLogs("api.services.oauth", level="WARNING") as logs,
        ):
            async with self._oauth_client(handler) as client:
                service = OAuthService(
                    self.provider,
                    client=client,
                    avatar_service=self._avatar_service(handler),
                )
                identity = await service.login(
                    code="first-code",
                    redirect_uri="https://blog.example/callback",
                )
                self.assertEqual(identity.guest.avatar, "")
                self.assertEqual(
                    identity.guest.avatar_source_url, "https://example.com/avatar.png"
                )
                delay_mock.assert_called_once_with(
                    str(identity.guest_id), "https://example.com/avatar.png"
                )

                fail_avatar = False
                identity = await service.login(
                    code="second-code",
                    redirect_uri="https://blog.example/callback",
                )
                mirrored = identity.guest.avatar
                self.assertTrue(mirrored.startswith("/media/avatars/"))

                fail_avatar = True
                delay_mock.reset_mock()
                identity = await service.login(
                    code="third-code",
                    redirect_uri="https://blog.example/callback",
                )
                self.assertEqual(identity.guest.avatar, mirrored)
                delay_mock.assert_called_once_with(
                    str(identity.guest_id), "https://example.com/avatar.png"
                )

        self.assertEqual(len(logs.output), 2)
        self.assertTrue(all("HTTP 503" in entry for entry in logs.output))

    async def test_login_does_not_schedule_retry_for_invalid_avatar(self):
        async def handler(request):
            if request.url.path == "/token":
                return httpx2.Response(
                    200,
                    json={"access_token": "access-token", "token_type": "Bearer"},
                )
            if request.url.path == "/avatar.svg":
                return httpx2.Response(
                    200,
                    headers={"content-type": "image/svg+xml"},
                    content=b"<svg xmlns='http://www.w3.org/2000/svg'/>",
                )
            return httpx2.Response(
                200,
                json={
                    "sub": "provider-user-id",
                    "name": "Test User",
                    "email": "user@example.com",
                    "picture": "https://example.com/avatar.svg",
                },
            )

        with (
            patch("api.tasks.sync_guest_avatar_task.delay") as delay_mock,
            self.assertLogs("api.services.oauth", level="WARNING") as logs,
        ):
            async with self._oauth_client(handler) as client:
                service = OAuthService(
                    self.provider,
                    client=client,
                    avatar_service=self._avatar_service(handler),
                )
                identity = await service.login(
                    code="code",
                    redirect_uri="https://blog.example/callback",
                )

        self.assertEqual(identity.guest.avatar, "")
        self.assertTrue(any("Rejected OAuth avatar" in entry for entry in logs.output))
        delay_mock.assert_not_called()

    async def test_login_ignores_broker_error_when_scheduling_avatar_retry(self):
        async def handler(request):
            if request.url.path == "/token":
                return httpx2.Response(
                    200,
                    json={"access_token": "access-token", "token_type": "Bearer"},
                )
            if request.url.path == "/avatar.png":
                return httpx2.Response(503)
            return httpx2.Response(
                200,
                json={
                    "sub": "broker-down-user",
                    "name": "Test User",
                    "email": "user@example.com",
                    "picture": "https://example.com/avatar.png",
                },
            )

        with (
            patch(
                "api.tasks.sync_guest_avatar_task.delay",
                side_effect=RuntimeError("broker unavailable"),
            ) as delay_mock,
            self.assertLogs("api.services.oauth", level="WARNING") as logs,
        ):
            async with self._oauth_client(handler) as client:
                service = OAuthService(
                    self.provider,
                    client=client,
                    avatar_service=self._avatar_service(handler),
                )
                identity = await service.login(
                    code="code",
                    redirect_uri="https://blog.example/callback",
                )

        self.assertEqual(identity.guest.avatar, "")
        self.assertTrue(any("broker unavailable" in entry for entry in logs.output))
        delay_mock.assert_called_once_with(
            str(identity.guest_id), "https://example.com/avatar.png"
        )

    @override_settings(IMAGE_CDN_ORIGIN="https://img.gsgfs.moe")
    async def test_login_rejects_oversized_managed_prefix_avatar_url(self):
        long_avatar_url = (
            "https://img.gsgfs.moe/avatars/ab/cd/abcd.webp?sig=" + "a" * 600
        )

        async def handler(request):
            if request.url.path == "/token":
                return httpx2.Response(
                    200,
                    json={"access_token": "access-token", "token_type": "Bearer"},
                )
            if request.url.path == "/avatars/ab/cd/abcd.webp":
                return httpx2.Response(404)
            return httpx2.Response(
                200,
                json={
                    "sub": "long-managed-url-user",
                    "name": "Test User",
                    "picture": long_avatar_url,
                },
            )

        with (
            patch("api.tasks.sync_guest_avatar_task.delay") as delay_mock,
            self.assertLogs("api.services.oauth", level="WARNING") as logs,
        ):
            async with self._oauth_client(handler) as client:
                service = OAuthService(
                    self.provider,
                    client=client,
                    avatar_service=self._avatar_service(handler),
                )
                identity = await service.login(
                    code="code",
                    redirect_uri="https://blog.example/callback",
                )

        guest = await Guest.objects.aget(pk=identity.guest_id)
        self.assertEqual(guest.avatar, "")
        self.assertEqual(guest.avatar_source_url, long_avatar_url)
        self.assertTrue(any("HTTP 404" in entry for entry in logs.output))
        delay_mock.assert_not_called()

    async def test_login_handles_long_avatar_source_url(self):
        long_avatar_url = "https://example.com/avatar.png?sig=" + ("a" * 600)
        avatar_bytes = _make_png_bytes("purple")

        async def handler(request):
            if request.url.path == "/token":
                return httpx2.Response(
                    200,
                    json={"access_token": "access-token", "token_type": "Bearer"},
                )
            if request.url.path == "/avatar.png":
                return httpx2.Response(
                    200,
                    headers={"content-type": "image/png"},
                    content=avatar_bytes,
                )
            return httpx2.Response(
                200,
                json={
                    "sub": "long-url-user",
                    "name": "Long Url User",
                    "email": "long@example.com",
                    "picture": long_avatar_url,
                },
            )

        async with self._oauth_client(handler) as client:
            service = OAuthService(
                self.provider,
                client=client,
                avatar_service=self._avatar_service(handler),
            )
            identity = await service.login(
                code="code",
                redirect_uri="https://blog.example/callback",
            )

        self.assertTrue(identity.guest.avatar.startswith("/media/avatars/"))
        self.assertEqual(identity.guest.avatar_source_url, long_avatar_url)

    async def test_login_enforces_total_timeout_for_avatar_mirroring(self):
        async def handler(request):
            if request.url.path == "/token":
                return httpx2.Response(
                    200,
                    json={"access_token": "access-token", "token_type": "Bearer"},
                )
            return httpx2.Response(
                200,
                json={
                    "sub": "slow-storage-user",
                    "name": "Slow User",
                    "email": "slow@example.com",
                    "picture": "https://example.com/avatar.png",
                },
            )

        async def slow_amirror(url: str) -> str:
            await asyncio.sleep(0.3)
            return "/media/avatars/aa/bb/aabb.webp"

        short_timeout_service = AvatarService(
            timeout=0.05,
            storage=self.storage,
            resolver=_public_resolver,
        )

        with (
            patch.object(short_timeout_service, "amirror", side_effect=slow_amirror),
            patch("api.tasks.sync_guest_avatar_task.delay") as delay_mock,
            self.assertLogs("api.services.oauth", level="WARNING") as logs,
        ):
            async with self._oauth_client(handler) as client:
                service = OAuthService(
                    self.provider,
                    client=client,
                    avatar_service=short_timeout_service,
                )
                identity = await service.login(
                    code="code",
                    redirect_uri="https://blog.example/callback",
                )

        self.assertEqual(identity.guest.avatar, "")
        self.assertTrue(any("TimeoutError" in entry for entry in logs.output))
        delay_mock.assert_called_once_with(
            str(identity.guest_id), "https://example.com/avatar.png"
        )
