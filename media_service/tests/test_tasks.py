import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image as PILImage

from media_service.models import ImageResource
from media_service.tasks import process_image, process_responsive_variants


@override_settings(SECURE_SSL_REDIRECT=False)
class MediaTasksTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)

    @staticmethod
    def build_image_resource_content():
        buffer = BytesIO()
        image = PILImage.new("RGB", (100, 100), "blue")
        image.save(buffer, format="PNG")
        content = buffer.getvalue()
        return ContentFile(content, name="task-test.png"), len(content)

    def test_process_image_marks_resource_as_processed(self):
        file, size = self.build_image_resource_content()
        image_resource = ImageResource.objects.create(
            checksum="b" * 64,
            file=file,
            width=100,
            height=100,
            size=size,
            mime_type="image/png",
        )

        process_image(image_resource.id)
        image_resource.refresh_from_db()

        self.assertTrue(image_resource.is_processed)
        self.assertFalse(image_resource.variants.exists())

    def test_responsive_variants_are_only_generated_when_enabled(self):
        file, size = self.build_image_resource_content()
        image_resource = ImageResource.objects.create(
            checksum="c" * 64,
            file=file,
            width=100,
            height=100,
            size=size,
            mime_type="image/png",
        )

        process_responsive_variants(image_resource.id)
        self.assertFalse(image_resource.variants.exists())

        image_resource.responsive_variants_enabled = True
        image_resource.save(update_fields=["responsive_variants_enabled"])
        process_responsive_variants(image_resource.id)

        self.assertEqual(
            set(image_resource.variants.values_list("format", "width")),
            {("avif", 100), ("webp", 100)},
        )

    def test_processing_does_not_overwrite_responsive_variant_setting(self):
        file, size = self.build_image_resource_content()
        image_resource = ImageResource.objects.create(
            checksum="d" * 64,
            file=file,
            width=100,
            height=100,
            size=size,
            mime_type="image/png",
        )
        stale_resource = ImageResource.objects.get(pk=image_resource.pk)
        ImageResource.objects.filter(pk=image_resource.pk).update(
            responsive_variants_enabled=True
        )

        with patch(
            "media_service.tasks.ImageResource.objects.get",
            return_value=stale_resource,
        ):
            process_image(image_resource.id, force=True)

        image_resource.refresh_from_db()
        self.assertTrue(image_resource.responsive_variants_enabled)
