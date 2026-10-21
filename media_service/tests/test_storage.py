from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape

import httpx2
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.utils.module_loading import import_string
from PIL import Image as PILImage

from core.r2 import (
    AuthenticationFailed,
    ObjectMetadata,
    ObjectPage,
    StorageUnavailable,
    SyncObjectBody,
    SyncR2Client,
)
from media_service.backends import MediaStorage
from media_service.models import ImageResource


@override_settings(
    S3_BUCKET_NAME="media",
    S3_ENDPOINT_URL="https://example.com",
    S3_ACCESS_KEY_ID="access",
    S3_SECRET_ACCESS_KEY="secret",
    S3_PUBLIC_DOMAIN="",
)
class MediaStorageTest(SimpleTestCase):
    def setUp(self):
        self.objects = {}
        self.requests = []
        self.client = SyncR2Client(
            "https://example.com",
            "access",
            "secret",
            "media",
            transport=httpx2.MockTransport(self.handle),
            max_retries=0,
        )
        self.factory_patch = patch(
            "media_service.backends.MediaStorage.SyncR2Client", return_value=self.client
        )
        self.factory = self.factory_patch.start()
        self.addCleanup(self.factory_patch.stop)
        self.addCleanup(self.client.close)
        self.storage = MediaStorage(querystring_auth=False, max_memory_size=8)
        self.addCleanup(self.storage.close)

    def handle(self, request):
        self.requests.append(request)
        key = request.url.path.removeprefix("/media/")
        if request.method == "PUT":
            self.objects[key] = (request.content, dict(request.headers))
            return httpx2.Response(200, headers={"etag": '"uploaded"'})
        if request.method == "DELETE":
            self.objects.pop(key, None)
            return httpx2.Response(204)
        if key not in self.objects:
            return httpx2.Response(404)
        data, headers = self.objects[key]
        return httpx2.Response(
            200,
            headers={
                "content-length": str(len(data)),
                "content-type": headers["content-type"],
                "last-modified": "Wed, 21 Oct 2026 04:00:00 GMT",
            },
            content=data if request.method == "GET" else b"",
        )

    def test_client_is_lazy_reused_and_closed(self):
        self.assertIsInstance(self.storage, Storage)
        self.factory.assert_not_called()
        self.assertIs(self.storage.client, self.storage.client)
        self.factory.assert_called_once()
        self.storage.close()
        self.assertTrue(self.client.client.is_closed)
        self.storage.close()

    def test_client_is_recreated_after_fork(self):
        parent = self.storage.client
        child = Mock()
        self.factory.return_value = child
        with patch("media_service.backends.MediaStorage.os.getpid", return_value=-1):
            self.assertIs(self.storage.client, child)
            self.assertIs(self.storage.client, child)
        self.assertTrue(parent.client.is_closed)
        self.assertEqual(self.factory.call_count, 2)

    def test_save_rewinds_overwrites_and_preserves_cache_policy(self):
        for name, policy in (
            ("images/raw/a.png", "public, max-age=31536000, immutable"),
            ("musics/a.mp3", "public, max-age=31536000, immutable"),
            ("images/avif/a.avif", "public, max-age=604800"),
            ("images/webp/a.webp", "public, max-age=604800"),
            ("images/thumbnails/a.jpg", "public, max-age=604800"),
            ("images/responsive/a.webp", "public, max-age=604800"),
            ("other/file.unknown-extension", None),
        ):
            with self.subTest(name=name):
                file = ContentFile(b"first")
                file.seek(3)
                self.assertEqual(self.storage.save(name, file), name)
                data, headers = self.objects[name]
                self.assertEqual(data, b"first")
                self.assertEqual(headers.get("cache-control"), policy)
                self.assertEqual(self.storage.save(name, ContentFile(b"second")), name)
                self.assertEqual(self.objects[name][0], b"second")
        self.assertTrue(all(request.method == "PUT" for request in self.requests))
        self.assertEqual(
            self.objects["images/raw/a.png"][1]["content-type"], "image/png"
        )
        self.assertEqual(
            self.objects["other/file.unknown-extension"][1]["content-type"],
            "application/octet-stream",
        )

    def test_uploaded_content_type_and_empty_file(self):
        uploaded = SimpleUploadedFile("file.bin", b"data", content_type="audio/ogg")
        self.storage.save("musics/file.bin", uploaded)
        self.assertEqual(
            self.objects["musics/file.bin"][1]["content-type"], "audio/ogg"
        )
        self.storage.save("empty.bin", ContentFile(b""))
        self.assertEqual(self.storage.size("empty.bin"), 0)

    def test_open_spools_seeks_and_reopens(self):
        self.storage.save("file", ContentFile(b"0123456789"))
        with self.storage.open("file") as file:
            self.assertTrue(file.file._rolled)
            self.assertEqual(file.read(3), b"012")
            file.seek(7)
            self.assertEqual(file.read(), b"789")
        with file.open():
            self.assertEqual(file.read(), b"0123456789")
        self.assertEqual(sum(request.method == "GET" for request in self.requests), 2)

    def test_open_text_and_reject_write_modes(self):
        self.storage.save("file.txt", ContentFile("你好".encode()))
        with self.storage.open("file.txt", "r") as file:
            self.assertEqual(file.read(), "你好")
        requests = len(self.requests)
        with self.assertRaises(ValueError):
            self.storage.open("file.txt", "wb")
        self.assertEqual(len(self.requests), requests)

    def test_filefield_and_pillow_round_trip(self):
        data = BytesIO()
        PILImage.new("RGB", (12, 8), "blue").save(data, format="PNG")
        storage_patch = patch.object(
            ImageResource._meta.get_field("file"), "storage", self.storage
        )
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        resource = ImageResource(checksum="a" * 64)
        resource.file.save("picture.png", ContentFile(data.getvalue()), save=False)
        expected = f"images/raw/aa/aa/{'a' * 64}.png"
        self.assertEqual(resource.file.name, expected)
        for _ in range(2):
            with resource.file.open("rb") as file:
                with PILImage.open(file) as image:
                    self.assertEqual(image.size, (12, 8))
                    image.load()
        self.assertEqual(resource.file.url, f"https://example.com/media/{expected}")
        resource.file.delete(save=False)
        self.assertNotIn(expected, self.objects)

    def test_missing_object_and_metadata(self):
        self.assertFalse(self.storage.exists("missing"))
        with self.assertRaises(FileNotFoundError):
            self.storage.open("missing")
        self.storage.save("file", ContentFile(b"data"))
        self.assertTrue(self.storage.exists("file"))
        self.assertEqual(self.storage.size("file"), 4)
        modified = datetime(2026, 10, 21, 4, tzinfo=timezone.utc)
        self.assertEqual(self.storage.get_modified_time("file"), modified)
        with override_settings(USE_TZ=False, TIME_ZONE="Asia/Shanghai"):
            self.assertEqual(
                self.storage.get_modified_time("file"), datetime(2026, 10, 21, 12)
            )
        self.storage.delete("file")
        self.storage.delete("file")
        self.assertFalse(self.storage.exists("file"))

    def test_exists_does_not_hide_authentication_errors(self):
        self.client.stat = Mock(side_effect=AuthenticationFailed("denied"))
        with self.assertRaises(AuthenticationFailed):
            self.storage.exists("file")

    def test_failed_download_closes_temporary_file_and_response(self):
        class BrokenStream(httpx2.SyncByteStream):
            def __iter__(self):
                yield b"partial"
                raise httpx2.ReadError("interrupted")

        response = httpx2.Response(200, stream=BrokenStream())
        with (
            patch.object(
                self.client,
                "get",
                return_value=SyncObjectBody("file", response, ObjectMetadata("file")),
            ),
            patch(
                "media_service.backends.MediaStorage.SpooledTemporaryFile"
            ) as temporary,
        ):
            with self.assertRaises(StorageUnavailable):
                self.storage.open("file")
            temporary.return_value.close.assert_called_once()
        self.assertTrue(response.is_closed)

    def test_listdir_paginates_and_returns_relative_names(self):
        def handler(request):
            self.assertEqual(request.url.params["prefix"], "images/")
            self.assertEqual(request.url.params["delimiter"], "/")
            cursor = request.url.params.get("continuation-token")
            key = "images/b.png" if cursor else "images/a.png"
            body = f"""<ListBucketResult>
                <IsTruncated>{"false" if cursor else "true"}</IsTruncated>
                <NextContinuationToken>next</NextContinuationToken>
                <Contents><Key>{escape(key)}</Key><Size>1</Size>
                <LastModified>2026-10-21T04:00:00Z</LastModified></Contents>
                <CommonPrefixes><Prefix>images/raw/</Prefix></CommonPrefixes>
                </ListBucketResult>"""
            return httpx2.Response(200, content=body.encode())

        client = SyncR2Client(
            "https://example.com",
            "access",
            "secret",
            "media",
            transport=httpx2.MockTransport(handler),
        )
        self.factory.return_value = client
        self.assertEqual(self.storage.listdir("images/"), (["raw"], ["a.png", "b.png"]))

    def test_listdir_rejects_repeated_cursor(self):
        self.client.list = Mock(return_value=ObjectPage((), True, "next"))
        with self.assertRaises(StorageUnavailable):
            self.storage.listdir("")
        self.assertEqual(self.client.list.call_args.kwargs["prefix"], "")

    def test_urls_encode_keys_and_support_presigning(self):
        key = "images/中文 +?#%.png"
        self.storage.custom_domain = "img.example.com"
        self.assertEqual(
            self.storage.url(key),
            "https://img.example.com/images/%E4%B8%AD%E6%96%87%20%2B%3F%23%25.png",
        )
        self.factory.assert_not_called()
        self.storage.custom_domain = ""
        self.storage.querystring_auth = True
        url = httpx2.URL(self.storage.url(key))
        self.assertEqual(url.params["X-Amz-Expires"], "3600")
        self.assertIn("X-Amz-Signature", url.params)

    def test_names_are_validated_before_network_access(self):
        for name in ("../file", "images/../file", "/absolute", "images\\..\\file"):
            with self.subTest(name=name):
                for action in (
                    self.storage.exists,
                    self.storage.delete,
                    self.storage.open,
                    self.storage.url,
                ):
                    with self.assertRaises(SuspiciousFileOperation):
                        action(name)
                with self.assertRaises(SuspiciousFileOperation):
                    self.storage.save(name, ContentFile(b"data"))
        self.factory.assert_not_called()
        self.assertEqual(
            self.storage.get_available_name("images/longname.png", max_length=15),
            "images/long.png",
        )
        with self.assertRaises(SuspiciousFileOperation):
            self.storage.get_available_name("images/name.png", max_length=8)

    def test_storage_configuration_and_deconstruction(self):
        config = {
            "default": {
                "BACKEND": "media_service.backends.MediaStorage",
                "OPTIONS": {
                    "bucket_name": "media",
                    "endpoint_url": "https://example.com",
                    "access_key": "access",
                    "secret_key": "secret",
                    "custom_domain": "img.example.com",
                    "querystring_auth": False,
                },
            }
        }
        with override_settings(STORAGES=config):
            storage = storages["default"]
            self.assertIsInstance(storage, MediaStorage)
            self.assertEqual(storage.url("a.png"), "https://img.example.com/a.png")
            path, args, kwargs = storage.deconstruct()
            self.assertIsInstance(import_string(path)(*args, **kwargs), MediaStorage)
        with override_settings(
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}
            }
        ):
            self.assertIsInstance(storages["default"], FileSystemStorage)
