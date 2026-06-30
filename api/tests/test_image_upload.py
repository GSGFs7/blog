import shutil
import tempfile
import time
from io import BytesIO
from unittest import skipIf
from unittest.mock import patch

import blake3
import requests
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image as PILImage

from api.auth import TimeBaseAuth
from api.models import Guest
from media_service.exiftool import SyncExifTool
from media_service.models import Image

# TODO: more test cases

TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


class BaseImageUploadTest(TestCase):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES=TEST_STORAGES,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.process_image_delay = patch("media_service.signals.process_image.delay")
        self.mock_process_image_delay = self.process_image_delay.start()
        self.addCleanup(self.process_image_delay.stop)


@override_settings(SECURE_SSL_REDIRECT=False)
class ImageUploadTest(BaseImageUploadTest):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.guest = Guest.objects.create(
            name="tester",
            email="tester@gsgfs.moe",
            avatar="https://img.gsgfs.moe/img/f56806663519c6680691407d0d8fa7ed.png",
        )

    @staticmethod
    def generate_test_image(name="test.png", size=(100, 100), color="red"):
        file = BytesIO()
        image = PILImage.new("RGB", size, color)
        image.save(file, format="PNG")
        file.seek(0)
        return SimpleUploadedFile(name, file.read(), content_type="image/png")

    def test_upload(self):
        file = self.generate_test_image()
        client_id = f"test_{time.time()}"
        token = TimeBaseAuth.create_token(client_id)
        response = self.client.post(
            "/api/image/upload",
            {
                "file": file,
                "uploader_type": "api.Guest",
                "uploader_id": self.guest.id,
            },
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201)
        image = Image.objects.get(original_name="test.png")
        self.assertEqual(image.uploader, self.guest)
        self.assertEqual(image.metadata["uploaded_via"], client_id)
        self.assertEqual(image.metadata["uploader_type"], "api.Guest")
        self.assertEqual(image.metadata["uploader_id"], self.guest.id)

        hasher = blake3.blake3()
        for chunk in file.chunks():
            hasher.update(chunk)
        checksum = hasher.hexdigest()
        self.assertTrue(Image.objects.filter(resource__checksum=checksum).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class ImageDeduplicationTest(BaseImageUploadTest):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.guest = Guest.objects.create(
            name="tester",
            email="tester2@example.com",
            avatar="https://img.gsgfs.moe/img/f56806663519c6680691407d0d8fa7ed.png",
        )

    @staticmethod
    def generate_test_image(name="test.png", size=(100, 100), color="red"):
        file = BytesIO()
        image = PILImage.new("RGB", size, color)
        image.save(file, format="PNG")
        file.seek(0)
        return SimpleUploadedFile(name, file.read(), content_type="image/png")

    @skipIf(settings.USE_S3, "Duplicate storage assertions are skipped for S3")
    def test_duplicate_file_not_stored_twice(self):
        """Test that uploading the same image twice doesn't create duplicate files."""
        file1 = self.generate_test_image(name="first.png")
        token = TimeBaseAuth.create_token(f"test_{time.time()}")

        # First upload
        response1 = self.client.post(
            "/api/image/upload",
            {
                "file": file1,
                "uploader_type": "api.Guest",
                "uploader_id": self.guest.id,
            },
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response1.status_code, 201)

        # Get the storage name of first upload
        image1 = Image.objects.get(id=response1.json()["id"])
        file_name_1 = image1.resource.file.name

        # Second upload with same content but different name
        file2 = self.generate_test_image(name="second.png")
        token2 = TimeBaseAuth.create_token(f"test_{time.time()}_2")

        response2 = self.client.post(
            "/api/image/upload",
            {
                "file": file2,
                "uploader_type": "api.Guest",
                "uploader_id": self.guest.id,
            },
            HTTP_AUTHORIZATION=f"Bearer {token2}",
        )
        self.assertEqual(response2.status_code, 201)

        # Get the storage name of second upload
        image2 = Image.objects.get(id=response2.json()["id"])
        file_name_2 = image2.resource.file.name

        # TODO: better way to test it?
        # Both should reference the same stored resource
        self.assertEqual(image1.resource_id, image2.resource_id)
        self.assertEqual(image1.resource.checksum, image2.resource.checksum)
        self.assertEqual(file_name_1, file_name_2)

        # Check that the file exists in the configured storage backend
        self.assertTrue(image1.resource.file.storage.exists(file_name_1))


@override_settings(SECURE_SSL_REDIRECT=False)
class WebImageUploadTest(BaseImageUploadTest):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.guest = Guest.objects.create(
            name="tester",
            email="tester3@example.com",
            avatar="https://img.gsgfs.moe/img/f56806663519c6680691407d0d8fa7ed.png",
        )
        # NOTE: it a PNG file actually
        self.image_src = (
            "https://img.gsgfs.moe/img/1b987606005d9dc83312b987bad854a6.jpg"
        )

        try:
            resp = requests.get(self.image_src, timeout=5)
            resp.raise_for_status()
            self.image_content = resp.content
        except Exception as e:
            self.skipTest(f"Failed to fetch image: {e}")

    def test_image_upload(self):
        file = SimpleUploadedFile("test_image.png", self.image_content, "image/png")
        token = TimeBaseAuth.create_token(f"test_{time.time()}")
        response = self.client.post(
            "/api/image/upload",
            {
                "file": file,
                "uploader_type": "api.Guest",
                "uploader_id": self.guest.id,
            },
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Image.objects.filter(original_name="test_image.png").exists())

        # Clean metadata using the same tool as the implementation
        cleaned_io = SyncExifTool().clean(
            BytesIO(self.image_content), filename="test_image.png"
        )

        # Compute hash of the cleaned data
        hasher = blake3.blake3()
        hasher.update(cleaned_io.getvalue())
        checksum = hasher.hexdigest()

        self.assertTrue(Image.objects.filter(resource__checksum=checksum).exists())
