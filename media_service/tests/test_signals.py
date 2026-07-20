import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image as PILImage

from media_service.models import ImageResource


@override_settings(SECURE_SSL_REDIRECT=False)
class MediaSignalsTest(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)

    @staticmethod
    def build_image_resource_content():
        buffer = BytesIO()
        image = PILImage.new("RGB", (100, 100), "red")
        image.save(buffer, format="PNG")
        content = buffer.getvalue()
        return ContentFile(content, name="signal-test.png"), len(content)

    def test_create_image_resource_triggers_processing_task(self):
        with (
            patch("media_service.signals.transaction.on_commit") as on_commit,
            patch("media_service.signals.process_image.delay") as delay,
        ):
            on_commit.side_effect = lambda callback, **kwargs: callback()
            file, size = self.build_image_resource_content()

            ImageResource.objects.create(
                checksum="a" * 64,
                file=file,
                width=100,
                height=100,
                size=size,
                mime_type="image/png",
            )

        delay.assert_called_once()
