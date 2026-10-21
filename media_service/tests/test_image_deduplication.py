import tempfile
from io import BytesIO
from unittest.mock import patch

import httpx2
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from PIL import Image as PILImage

from core.r2 import AuthenticationFailed, StorageUnavailable, SyncR2Client
from media_service.models import Image, ImageResource


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    }
)
class ImageDeduplicationTest(TestCase):
    def setUp(self):
        self.uploader = get_user_model().objects.create_user(username="dedup-test")
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        data = BytesIO()
        PILImage.new("RGB", (12, 8), "blue").save(data, format="PNG")
        self.data = data.getvalue()
        for target in (
            "media_service.signals.process_image.delay",
            "media_service.signals.invalidate_image_render_metadata",
        ):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        cleaner = patch.object(
            Image,
            "_process_clean_metadata",
            side_effect=lambda *args, **kwargs: BytesIO(self.data),
        )
        cleaner.start()
        self.addCleanup(cleaner.stop)
        async_cleaner = patch.object(
            Image,
            "_aprocess_clean_metadata",
            side_effect=lambda *args, **kwargs: BytesIO(self.data),
        )
        async_cleaner.start()
        self.addCleanup(async_cleaner.stop)

    def upload(self, filename="first.png"):
        return Image.create_from_file(
            BytesIO(self.data), filename, uploader=self.uploader
        )

    def test_duplicate_with_existing_file_does_not_upload_again(self):
        first, resource, created = self.upload()
        self.assertTrue(created)
        with patch.object(resource.file.storage, "save") as save:
            second, reused, created = self.upload("second.png")
        save.assert_not_called()
        self.assertFalse(created)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(resource.pk, reused.pk)
        self.assertEqual(ImageResource.objects.count(), 1)

    def test_duplicate_restores_missing_file_at_original_key(self):
        _, resource, _ = self.upload()
        key = resource.file.name
        storage = resource.file.storage
        storage.delete(key)
        self.assertFalse(storage.exists(key))
        image, reused, created = self.upload("different-name.jpg")
        self.assertFalse(created)
        self.assertEqual(reused.pk, resource.pk)
        self.assertEqual(image.resource_id, resource.pk)
        self.assertEqual(reused.file.name, key)
        resource.refresh_from_db()
        self.assertEqual(resource.file.name, key)
        with resource.file.open("rb") as file:
            self.assertEqual(file.read(), self.data)
        self.assertEqual(ImageResource.objects.count(), 1)
        self.assertEqual(Image.objects.count(), 2)

    def test_duplicate_restores_file_after_switching_storage_location(self):
        _, resource, _ = self.upload()
        key = resource.file.name
        with tempfile.TemporaryDirectory() as destination:
            with override_settings(MEDIA_ROOT=destination):
                self.assertFalse(resource.file.storage.exists(key))
                _, reused, created = self.upload("second.png")
                self.assertFalse(created)
                self.assertEqual(reused.pk, resource.pk)
                self.assertEqual(reused.file.name, key)
                with reused.file.open("rb") as file:
                    self.assertEqual(file.read(), self.data)
        self.assertTrue(resource.file.storage.exists(key))

    def test_duplicate_uploads_local_file_to_new_r2_backend(self):
        _, resource, _ = self.upload()
        key = resource.file.name
        requests = []

        def handler(request):
            requests.append(request)
            self.assertEqual(request.url.path, f"/media/{key}")
            if request.method == "HEAD":
                return httpx2.Response(404)
            self.assertEqual(request.method, "PUT")
            self.assertEqual(request.content, self.data)
            self.assertEqual(request.headers["content-type"], "image/png")
            self.assertEqual(
                request.headers["cache-control"],
                "public, max-age=31536000, immutable",
            )
            return httpx2.Response(200)

        config = {
            "default": {
                "BACKEND": "media_service.backends.MediaStorage",
                "OPTIONS": {
                    "bucket_name": "media",
                    "endpoint_url": "https://example.com",
                    "access_key": "access",
                    "secret_key": "secret",
                },
            }
        }
        with (
            SyncR2Client(
                "https://example.com",
                "access",
                "secret",
                "media",
                transport=httpx2.MockTransport(handler),
            ) as client,
            patch(
                "media_service.backends.MediaStorage.SyncR2Client", return_value=client
            ),
            override_settings(STORAGES=config),
        ):
            _, reused, created = self.upload("second.jpg")
            self.assertFalse(created)
            self.assertEqual(reused.pk, resource.pk)
            self.assertEqual(reused.file.name, key)
        self.assertEqual([request.method for request in requests], ["HEAD", "PUT"])

    def test_storage_errors_do_not_trigger_restore_or_create_image(self):
        _, resource, _ = self.upload()
        storage = resource.file.storage
        for error in (AuthenticationFailed("denied"), StorageUnavailable("offline")):
            with (
                self.subTest(error=type(error).__name__),
                patch.object(storage, "exists", side_effect=error),
                patch.object(storage, "save") as save,
                self.assertRaises(type(error)),
            ):
                self.upload("second.png")
            save.assert_not_called()
        self.assertEqual(Image.objects.count(), 1)
        self.assertEqual(ImageResource.objects.count(), 1)

    def test_failed_restore_does_not_create_image(self):
        _, resource, _ = self.upload()
        storage = resource.file.storage
        storage.delete(resource.file.name)
        with (
            patch.object(storage, "save", side_effect=StorageUnavailable("offline")),
            self.assertRaises(StorageUnavailable),
        ):
            self.upload("second.png")
        self.assertEqual(Image.objects.count(), 1)
        self.assertEqual(ImageResource.objects.count(), 1)

    async def test_async_upload_restores_missing_file(self):
        image, resource, _ = await Image.acreate_from_file(
            BytesIO(self.data), "first.png", uploader=self.uploader
        )
        key = resource.file.name
        storage = resource.file.storage
        storage.delete(key)
        second, reused, created = await Image.acreate_from_file(
            BytesIO(self.data), "second.png", uploader=self.uploader
        )
        self.assertFalse(created)
        self.assertNotEqual(image.pk, second.pk)
        self.assertEqual(resource.pk, reused.pk)
        self.assertEqual(reused.file.name, key)
        with storage.open(key) as file:
            self.assertEqual(file.read(), self.data)
