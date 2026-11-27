from io import BytesIO, StringIO
from ipaddress import IPv4Address, IPv6Address
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

import httpx2
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image as PILImage

from api.models import Guest
from api.services.avatar import (
    AvatarRetryableError,
    AvatarService,
    AvatarValidationError,
)
from api.tasks import sync_guest_avatar_task
from core.r2 import RateLimited

# Public IP (former example.com); cannot use RFC 5737 (is_global=False).
PUBLIC_IPS = [IPv4Address("93.184.216.34")]


def _public_resolver(_host: str, _port: int):
    return PUBLIC_IPS


def _make_image(
    fmt: str = "PNG",
    size: tuple[int, int] = (320, 200),
    mode: str = "RGB",
    color="blue",
) -> bytes:
    buf = BytesIO()
    PILImage.new(mode, size, color).save(buf, format=fmt)
    return buf.getvalue()


class AvatarServiceTest(SimpleTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage = FileSystemStorage(
            location=self.temp_dir.name,
            base_url="/media/",
        )
        self.service = AvatarService(
            storage=self.storage,
            resolver=_public_resolver,
        )

    def test_mirror_converts_crops_and_deduplicates(self):
        png_bytes = _make_image("PNG", (320, 200), "RGBA", (10, 20, 30, 128))
        requests = []

        def handler(request):
            requests.append(request)
            return httpx2.Response(200, content=png_bytes)

        service = AvatarService(
            storage=self.storage,
            resolver=_public_resolver,
            transport=httpx2.MockTransport(handler),
        )

        with patch.object(self.storage, "save", wraps=self.storage.save) as save_mock:
            url1 = service.mirror("https://avatars.example/u/1")
            url2 = service.mirror("https://avatars.example/u/1?v=2")

        self.assertEqual(
            [str(request.url) for request in requests],
            ["https://93.184.216.34/u/1", "https://93.184.216.34/u/1?v=2"],
        )
        for request in requests:
            self.assertEqual(request.headers["Host"], "avatars.example")
            self.assertEqual(request.extensions["sni_hostname"], "avatars.example")

        self.assertEqual(url1, url2)
        self.assertTrue(url1.startswith("/media/avatars/"))
        self.assertTrue(url1.endswith(".webp"))
        self.assertEqual(save_mock.call_count, 1)

        key = url1.removeprefix("/media/")
        with self.storage.open(key, "rb") as stored:
            with PILImage.open(stored) as img:
                self.assertEqual(img.format, "WEBP")
                self.assertEqual(img.size, (160, 160))
                self.assertEqual(img.mode, "RGBA")

    def test_mirror_does_not_upscale_small_images(self):
        png_bytes = _make_image("PNG", (64, 48), "RGB", "red")
        service = AvatarService(
            storage=self.storage,
            resolver=_public_resolver,
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(200, content=png_bytes)
            ),
        )

        url = service.mirror("https://avatars.example/small")
        key = url.removeprefix("/media/")
        with self.storage.open(key, "rb") as stored:
            with PILImage.open(stored) as img:
                self.assertEqual(img.size, (48, 48))

    def test_normalize_preserves_png_color_key_transparency(self):
        for mode, transparent, opaque in (
            ("RGB", (0, 0, 0), (255, 0, 0)),
            ("L", 0, 255),
        ):
            with self.subTest(mode=mode):
                source = BytesIO()
                with PILImage.new(mode, (2, 2), opaque) as image:
                    image.putpixel((0, 0), transparent)
                    image.save(source, format="PNG", transparency=transparent)

                normalized = self.service._normalizer.normalize(source.getvalue())
                with PILImage.open(BytesIO(normalized)) as image:
                    self.assertEqual(image.format, "WEBP")
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.getpixel((0, 0))[3], 0)
                    self.assertEqual(image.getpixel((1, 1))[3], 255)

    async def test_amirror_follows_redirects_and_returns_managed_url(self):
        png_bytes = _make_image("PNG", (200, 200), "RGB", "green")
        requests = []
        lookups = []

        def resolver(host, port):
            lookups.append((host, port))
            if host == "cdn.example":
                return [IPv6Address("2606:4700::1111"), *PUBLIC_IPS]
            return PUBLIC_IPS

        async def handler(request):
            requests.append(request)
            self.assertNotIn("Cookie", request.headers)
            if request.url.path == "/redirect":
                return httpx2.Response(
                    302,
                    headers={
                        "location": "https://cdn.example:8443/relative",
                        "set-cookie": "session=avatar; Path=/",
                    },
                )
            if request.url.host == "2606:4700::1111":
                raise httpx2.ConnectError("Address unavailable")
            if request.url.path == "/relative":
                return httpx2.Response(302, headers={"location": "final?a=%2B"})
            return httpx2.Response(200, content=png_bytes)

        service = AvatarService(
            storage=self.storage,
            resolver=resolver,
            async_transport=httpx2.MockTransport(handler),
        )
        url = await service.amirror("https://avatars.example/redirect")

        self.assertEqual(
            lookups,
            [("avatars.example", 443), ("cdn.example", 8443), ("cdn.example", 8443)],
        )
        self.assertEqual(
            [
                (
                    str(request.url),
                    request.headers["Host"],
                    request.extensions["sni_hostname"],
                )
                for request in requests
            ],
            [
                (
                    "https://93.184.216.34/redirect",
                    "avatars.example",
                    "avatars.example",
                ),
                (
                    "https://[2606:4700::1111]:8443/relative",
                    "cdn.example:8443",
                    "cdn.example",
                ),
                (
                    "https://93.184.216.34:8443/relative",
                    "cdn.example:8443",
                    "cdn.example",
                ),
                (
                    "https://[2606:4700::1111]:8443/final?a=%2B",
                    "cdn.example:8443",
                    "cdn.example",
                ),
                (
                    "https://93.184.216.34:8443/final?a=%2B",
                    "cdn.example:8443",
                    "cdn.example",
                ),
            ],
        )
        self.assertTrue(url.startswith("/media/avatars/"))
        self.assertTrue(AvatarService.is_managed_url(url))

    @override_settings(
        MEDIA_URL="/media/",
        IMAGE_CDN_ORIGIN="https://img.gsgfs.moe",
        S3_PUBLIC_DOMAIN="",
    )
    def test_mirror_skips_already_managed_url(self):
        for url in (
            "https://img.gsgfs.moe/avatars/ab/cd/abcd.webp",
            "/media/avatars/aa/bb/aabb.webp",
            "/media/avatars/" + "a" * (500 - len("/media/avatars/")),
        ):
            with self.subTest(url=url):
                self.assertTrue(self.service.is_managed_url(url))
                self.assertEqual(self.service.mirror(url), url)

    @override_settings(
        MEDIA_URL="/media/",
        IMAGE_CDN_ORIGIN="https://img.gsgfs.moe",
        S3_PUBLIC_DOMAIN="",
    )
    def test_is_managed_url_rejects_invalid_urls(self):
        for url in (
            "",
            "javascript://img.gsgfs.moe/avatars/x",
            "http://img.gsgfs.moe/avatars/x",
            "https://user@img.gsgfs.moe/avatars/ab/cd/abcd.webp",
            "https://img.gsgfs.moe:443/avatars/x",
            "https://img.gsgfs.moe/avatars/ab/cd/abcd.webp?v=1",
            "https://img.gsgfs.moe/avatars/ab/cd/abcd.webp#x",
            "/media/avatars/x?",
            "/media/avatars/x#",
            "/media/avatars/../../secret",
            "/media/avatars/%2e%2e/secret",
            "/media/avatars/./x",
            "/media/avatars/a//x",
            "/media/avatars/a%2f%2fx",
            "/media/avatars/a\\x",
            "/media/avatars/a%5cx",
            "/media/avatars/a b",
            "/media/avatars/x\t",
            "/media/avatars/x\x1f",
            "/media/avatars/x\x7f",
            "/media/avatars/x\u00a0",
            "/media/avatars/",
            "///media/avatars/x",
            "/media/avatars/" + "a" * 500,
        ):
            with self.subTest(url=url):
                self.assertFalse(self.service.is_managed_url(url))

    @override_settings(
        MEDIA_URL="https://media.example/custom/",
        IMAGE_CDN_ORIGIN="https://cdn.example:8443/custom/",
        S3_PUBLIC_DOMAIN="storage.example/bucket/",
    )
    def test_is_managed_url_matches_configured_origins_and_paths(self):
        for url in (
            "HTTPS://MEDIA.EXAMPLE/custom/avatars/x",
            "https://cdn.example:8443/custom/avatars/x",
            "https://storage.example/bucket/avatars/x",
        ):
            with self.subTest(url=url):
                self.assertTrue(self.service.is_managed_url(url))

        for url in (
            "/custom/avatars/x",
            "http://media.example/custom/avatars/x",
            "https://cdn.example/custom/avatars/x",
            "https://cdn.example:8443/avatars/x",
            "https://storage.example/avatars/x",
        ):
            with self.subTest(url=url):
                self.assertFalse(self.service.is_managed_url(url))

    def test_mirror_rejects_invalid_managed_prefix_urls_before_dns(self):
        with patch.object(self.service._downloader, "_resolver") as resolver:
            for url in (
                "javascript://img.gsgfs.moe/avatars/x",
                "http://img.gsgfs.moe/avatars/x",
                "/media/avatars/../x",
                "/media/avatars/" + "a" * 500,
            ):
                with self.subTest(url=url), self.assertRaises(AvatarValidationError):
                    self.service.mirror(url)

        resolver.assert_not_called()

    def test_ssrf_and_url_validation(self):
        def handler(request):
            self.fail(f"Unexpected avatar request: {request.url}")

        transport = httpx2.MockTransport(handler)
        default_service = AvatarService(storage=self.storage, transport=transport)
        for bad_url in (
            "http://avatars.example/a.png",
            "file:///etc/passwd",
            "https://user:pass@avatars.example/a.png",
            "https://127.0.0.1/a.png",
            "https://10.0.0.1/a.png",
            "https://169.254.169.254/latest/meta-data",
            "https://[::1]/a.png",
            "https://[::ffff:127.0.0.1]/a.png",
            "https://224.0.0.1/a.png",
            "https://avatars.example:99999/a.png",
        ):
            with self.subTest(url=bad_url):
                with self.assertRaises(AvatarValidationError):
                    default_service.mirror(bad_url)

        private_v4_service = AvatarService(
            storage=self.storage,
            resolver=lambda _h, _p: [IPv4Address("192.168.1.10")],
            transport=transport,
        )
        with self.assertRaises(AvatarValidationError):
            private_v4_service.mirror("https://internal.example/a.png")

        private_v6_service = AvatarService(
            storage=self.storage,
            resolver=lambda _h, _p: [IPv6Address("::ffff:10.0.0.2")],
            transport=transport,
        )
        with self.assertRaises(AvatarValidationError):
            private_v6_service.mirror("https://internal6.example/a.png")

    def test_rejects_redirect_to_private_host(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx2.Response(
                302, headers={"location": "https://unavailable.example/final"}
            )

        def resolver(host: str, _port: int):
            if host == "unavailable.example":
                return [*PUBLIC_IPS, IPv4Address("127.0.0.1")]
            return PUBLIC_IPS

        service = AvatarService(
            storage=self.storage,
            resolver=resolver,
            transport=httpx2.MockTransport(handler),
        )
        with self.assertRaises(AvatarValidationError):
            service.mirror("https://avatars.example/start")

        self.assertEqual([request.url.path for request in requests], ["/start"])

    def test_mirror_rejects_private_embedded_ipv4(self):
        def handler(request):
            self.fail(f"Unexpected avatar request: {request.url}")

        transport = httpx2.MockTransport(handler)
        literal_service = AvatarService(transport=transport)
        resolved_service = AvatarService(transport=transport)

        for address in (
            "64:ff9b::127.0.0.1",
            "64:ff9b::169.254.169.254",
            "::ffff:0:127.0.0.1",
        ):
            with self.subTest(address=address):
                with self.assertRaises(AvatarValidationError):
                    literal_service.mirror(f"https://[{address}]/a.png")
                with (
                    patch.object(
                        resolved_service._downloader,
                        "_resolver",
                        return_value=[IPv6Address(address)],
                    ),
                    self.assertRaises(AvatarValidationError),
                ):
                    resolved_service.mirror("https://avatars.example/a.png")

        for address in ("64:ff9b::93.184.216.34", "::ffff:0:93.184.216.34"):
            with self.subTest(address=address):
                self.assertTrue(
                    self.service._downloader.is_public_ip(IPv6Address(address))
                )

    def test_mirror_shares_timeout_across_redirects_ip_attempts_and_chunks(self):
        now = 0.0
        requests = []

        class SlowStream(httpx2.SyncByteStream):
            def __iter__(self):
                nonlocal now
                now += 1
                yield b"first chunk"
                now += 1
                yield b"second chunk"
                raise AssertionError("Read continued past the deadline")

        def resolver(host, port):
            if host == "cdn.example":
                return [IPv6Address("2606:4700::1111"), *PUBLIC_IPS]
            return PUBLIC_IPS

        def handler(request):
            nonlocal now
            requests.append((request.url.path, request.extensions["timeout"]))
            if request.url.path == "/start":
                now += 1
                return httpx2.Response(
                    302, headers={"location": "https://cdn.example/final"}
                )
            if request.url.host == "2606:4700::1111":
                now += 1
                raise httpx2.ConnectError("Address unavailable")
            return httpx2.Response(200, stream=SlowStream())

        service = AvatarService(
            timeout=4,
            resolver=resolver,
            transport=httpx2.MockTransport(handler),
        )
        with (
            patch("api.services.avatar.monotonic", side_effect=lambda: now),
            self.assertRaisesMessage(AvatarRetryableError, "Avatar download timed out"),
        ):
            service.mirror("https://avatars.example/start")

        self.assertEqual(
            requests,
            [
                (path, dict.fromkeys(("connect", "read", "write", "pool"), timeout))
                for path, timeout in (("/start", 4), ("/final", 3), ("/final", 2))
            ],
        )

    async def test_rejects_malformed_redirect_location(self):
        def handler(request):
            self.assertEqual(request.url.path, "/start")
            return httpx2.Response(302, headers={"location": "https://["})

        async def async_handler(request):
            return handler(request)

        service = AvatarService(
            resolver=_public_resolver,
            transport=httpx2.MockTransport(handler),
            async_transport=httpx2.MockTransport(async_handler),
        )
        url = "https://avatars.example/start"
        with self.assertRaisesMessage(
            AvatarValidationError, "Avatar redirect URL is invalid"
        ):
            service.mirror(url)
        with self.assertRaisesMessage(
            AvatarValidationError, "Avatar redirect URL is invalid"
        ):
            await service.amirror(url)

    def test_mirror_treats_storage_rate_limit_as_retryable(self):
        png_bytes = _make_image()
        service = AvatarService(
            storage=self.storage,
            resolver=_public_resolver,
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(200, content=png_bytes)
            ),
        )
        with (
            patch.object(self.storage, "save", side_effect=RateLimited("rate limited")),
            self.assertRaisesMessage(
                AvatarRetryableError, "Avatar storage unavailable"
            ),
        ):
            service.mirror("https://avatars.example/avatar")

    def test_rejects_oversized_and_invalid_responses(self):
        small_limit_service = AvatarService(
            max_bytes=100,
            storage=self.storage,
            resolver=_public_resolver,
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(200, content=b"x" * 200)
            ),
        )
        with self.assertRaises(AvatarValidationError):
            small_limit_service.mirror("https://avatars.example/big")

        service = AvatarService(
            storage=self.storage,
            resolver=_public_resolver,
            transport=httpx2.MockTransport(
                lambda request: httpx2.Response(
                    200,
                    headers={"content-type": "image/svg+xml"},
                    content=b"<svg xmlns='http://www.w3.org/2000/svg'/>",
                )
            ),
        )
        with self.assertRaises(AvatarValidationError):
            service.mirror("https://avatars.example/vector.svg")

    def test_status_code_error_classification(self):
        for status, error in (
            (404, AvatarValidationError),
            (503, AvatarRetryableError),
        ):
            with self.subTest(status=status):
                service = AvatarService(
                    storage=self.storage,
                    resolver=_public_resolver,
                    transport=httpx2.MockTransport(
                        lambda request: httpx2.Response(status)
                    ),
                )
                with self.assertRaises(error):
                    service.mirror("https://avatars.example/avatar")


class SyncGuestAvatarTaskAndCommandTest(TestCase):
    @override_settings(MEDIA_URL="/media/")
    def test_sync_guest_avatars_command_limits_eligible_guests(self):
        managed_url = "/media/avatars/11/22/1122.webp"
        Guest.objects.create(name="Managed", email="ok@example.com", avatar=managed_url)
        Guest.objects.create(name="Empty", email="empty@example.com")
        later_guest = Guest.objects.create(
            pk=UUID(int=2),
            name="Later",
            email="later@example.com",
            avatar="https://avatars.example/later.png",
        )
        first_guest = Guest.objects.create(
            pk=UUID(int=1),
            name="First",
            email="first@example.com",
            avatar="https://avatars.example/first.png",
        )
        Guest.objects.filter(pk=later_guest.pk).update(
            created_at=first_guest.created_at
        )

        out = StringIO()
        with patch.object(AvatarService, "mirror", return_value=managed_url) as mirror:
            call_command("sync_guest_avatars", "--limit", "1", stdout=out)
            mirror.assert_called_once_with("https://avatars.example/first.png")

        self.assertIn("synced=1, skipped=2, failed=0", out.getvalue())
        first_guest.refresh_from_db()
        later_guest.refresh_from_db()
        self.assertEqual(first_guest.avatar, managed_url)
        self.assertEqual(
            first_guest.avatar_source_url, "https://avatars.example/first.png"
        )
        self.assertEqual(later_guest.avatar, "https://avatars.example/later.png")
        self.assertEqual(later_guest.avatar_source_url, "")

    def test_sync_guest_avatars_command_rejects_negative_limit(self):
        with self.assertRaisesMessage(CommandError, "--limit must be non-negative"):
            call_command("sync_guest_avatars", "--limit", "-1")

    def test_sync_guest_avatar_task_updates_guest_and_ignores_stale(self):
        guest = Guest.objects.create(
            name="Alice",
            email="alice@example.com",
            avatar="",
            avatar_source_url="https://avatars.example/current.png",
        )

        with patch.object(
            AvatarService,
            "mirror",
            return_value="https://img.gsgfs.moe/avatars/aa/bb/aabb.webp",
        ) as mirror_mock:
            stale_result = sync_guest_avatar_task(
                str(guest.pk), "https://avatars.example/old.png"
            )
            self.assertIsNone(stale_result)
            mirror_mock.assert_not_called()

            result = sync_guest_avatar_task(
                str(guest.pk), "https://avatars.example/current.png"
            )
            self.assertEqual(result, "https://img.gsgfs.moe/avatars/aa/bb/aabb.webp")

        guest.refresh_from_db()
        self.assertEqual(guest.avatar, "https://img.gsgfs.moe/avatars/aa/bb/aabb.webp")

    def test_sync_guest_avatar_task_does_not_overwrite_concurrent_login(self):
        guest = Guest.objects.create(
            name="Bob",
            email="bob@example.com",
            avatar="",
            avatar_source_url="https://avatars.example/old.png",
        )

        def concurrent_mirror(_self, _url: str) -> str:
            Guest.objects.filter(pk=guest.pk).update(
                avatar="https://img.gsgfs.moe/avatars/ne/ww/neww.webp",
                avatar_source_url="https://avatars.example/new.png",
            )
            return "https://img.gsgfs.moe/avatars/ol/dd/oldd.webp"

        with patch.object(AvatarService, "mirror", concurrent_mirror):
            result = sync_guest_avatar_task(
                str(guest.pk), "https://avatars.example/old.png"
            )

        self.assertIsNone(result)
        guest.refresh_from_db()
        self.assertEqual(guest.avatar, "https://img.gsgfs.moe/avatars/ne/ww/neww.webp")
        self.assertEqual(guest.avatar_source_url, "https://avatars.example/new.png")

    def test_sync_guest_avatars_command_skips_concurrently_updated_guest(self):
        guest = Guest.objects.create(
            name="Charlie",
            email="charlie@example.com",
            avatar="https://avatars.githubusercontent.com/u/3?v=4",
        )

        def concurrent_mirror(_self, _url: str) -> str:
            Guest.objects.filter(pk=guest.pk).update(
                avatar="https://img.gsgfs.moe/avatars/ne/ww/neww.webp",
                avatar_source_url="https://avatars.githubusercontent.com/u/3?v=5",
            )
            return "https://img.gsgfs.moe/avatars/ol/dd/oldd.webp"

        out = StringIO()
        with patch.object(AvatarService, "mirror", concurrent_mirror):
            call_command("sync_guest_avatars", stdout=out)

        self.assertIn("synced=0, skipped=1, failed=0", out.getvalue())
        guest.refresh_from_db()
        self.assertEqual(guest.avatar, "https://img.gsgfs.moe/avatars/ne/ww/neww.webp")
        self.assertEqual(
            guest.avatar_source_url, "https://avatars.githubusercontent.com/u/3?v=5"
        )

    def test_sync_guest_avatars_command_migrates_external_only(self):
        external_guest = Guest.objects.create(
            name="External",
            email="ext@example.com",
            avatar="https://avatars.githubusercontent.com/u/1?v=4",
        )
        managed_guest = Guest.objects.create(
            name="Managed",
            email="ok@example.com",
            avatar="https://img.gsgfs.moe/avatars/11/22/1122.webp",
            avatar_source_url="https://avatars.githubusercontent.com/u/2?v=4",
        )

        dry_out = StringIO()
        with patch.object(AvatarService, "mirror") as mirror_mock:
            call_command("sync_guest_avatars", "--dry-run", stdout=dry_out)
            mirror_mock.assert_not_called()
        self.assertIn("synced=1, skipped=1, failed=0", dry_out.getvalue())

        out = StringIO()
        with patch.object(
            AvatarService,
            "mirror",
            return_value="https://img.gsgfs.moe/avatars/cc/dd/ccdd.webp",
        ) as mirror_mock:
            call_command("sync_guest_avatars", stdout=out)
            mirror_mock.assert_called_once_with(
                "https://avatars.githubusercontent.com/u/1?v=4"
            )

        external_guest.refresh_from_db()
        managed_guest.refresh_from_db()
        self.assertEqual(
            external_guest.avatar, "https://img.gsgfs.moe/avatars/cc/dd/ccdd.webp"
        )
        self.assertEqual(
            external_guest.avatar_source_url,
            "https://avatars.githubusercontent.com/u/1?v=4",
        )
        self.assertEqual(
            managed_guest.avatar, "https://img.gsgfs.moe/avatars/11/22/1122.webp"
        )
