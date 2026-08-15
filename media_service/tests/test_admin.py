import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice
from PIL import Image as PILImage

from media_service.models import Image


@override_settings(SECURE_SSL_REDIRECT=False)
class ImageAdminTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)

        user_model = get_user_model()
        self.admin_user = user_model.objects.create_superuser(
            username="admin",
            email="admin@gsgfs.moe",
            password="passwd114",
        )
        self.client.force_login(self.admin_user)
        self.otp_device = TOTPDevice.objects.create(
            user=self.admin_user,
            name="default",
            confirmed=True,
        )
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = self.otp_device.persistent_id
        session.save()

    @staticmethod
    def generate_test_image(name="admin-test.png", size=(100, 100), color="red"):
        file = BytesIO()
        image = PILImage.new("RGB", size, color)
        image.save(file, format="PNG")
        file.seek(0)
        return SimpleUploadedFile(name, file.read(), content_type="image/png")

    def test_admin_upload_binds_current_user_as_uploader(self):
        response = self.client.post(
            # the Django admin panel endpoint
            reverse("admin:media_service_image_add"),
            {
                "file": self.generate_test_image(),
                "original_name": "admin-test.png",
                "alt_text": "admin upload",
                "description": "uploaded from admin",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)

        image = Image.objects.get(original_name="admin-test.png")
        self.assertEqual(image.uploader, self.admin_user)

    def test_admin_upload_can_enable_responsive_variants(self):
        with (
            patch("media_service.signals.process_image.delay"),
            patch("media_service.admin.process_responsive_variants.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                reverse("admin:media_service_image_add"),
                {
                    "file": self.generate_test_image(name="responsive.png"),
                    "original_name": "responsive.png",
                    "alt_text": "responsive admin upload",
                    "description": "",
                    "responsive_variants_enabled": "on",
                    "_save": "Save",
                },
            )

        self.assertEqual(response.status_code, 302)
        image = Image.objects.get(original_name="responsive.png")
        self.assertTrue(image.resource.responsive_variants_enabled)
        delay.assert_called_once_with(image.resource_id)

    def test_admin_change_can_enable_responsive_variants(self):
        self.client.post(
            reverse("admin:media_service_image_add"),
            {
                "file": self.generate_test_image(name="change-responsive.png"),
                "original_name": "change-responsive.png",
                "alt_text": "before change",
                "description": "",
                "_save": "Save",
            },
        )
        image = Image.objects.get(original_name="change-responsive.png")

        with (
            patch("media_service.admin.process_responsive_variants.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                reverse("admin:media_service_image_change", args=[image.pk]),
                {
                    "original_name": image.original_name,
                    "alt_text": image.alt_text,
                    "description": image.description,
                    "responsive_variants_enabled": "on",
                    "_save": "Save",
                },
            )

        self.assertEqual(response.status_code, 302)
        image.resource.refresh_from_db()
        self.assertTrue(image.resource.responsive_variants_enabled)
        delay.assert_called_once_with(image.resource_id)

    def test_admin_change_retries_missing_responsive_variants(self):
        self.client.post(
            reverse("admin:media_service_image_add"),
            {
                "file": self.generate_test_image(name="retry-responsive.png"),
                "original_name": "retry-responsive.png",
                "alt_text": "retry variants",
                "description": "",
                "_save": "Save",
            },
        )
        image = Image.objects.get(original_name="retry-responsive.png")
        image.resource.responsive_variants_enabled = True
        image.resource.save(update_fields=["responsive_variants_enabled"])

        with (
            patch("media_service.admin.process_responsive_variants.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                reverse("admin:media_service_image_change", args=[image.pk]),
                {
                    "original_name": image.original_name,
                    "alt_text": image.alt_text,
                    "description": image.description,
                    "responsive_variants_enabled": "on",
                    "_save": "Save",
                },
            )

        self.assertEqual(response.status_code, 302)
        delay.assert_called_once_with(image.resource_id)
