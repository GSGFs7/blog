import shutil
import tempfile
from unittest.mock import patch

from django.core.cache import caches
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from media_service.image_cache import (
    IMAGE_METADATA_TTL,
    _metadata_cache_key,
    get_image_render_metadata,
    invalidate_image_render_metadata,
)
from media_service.models import ImageResource, ImageVariant
from media_service.templatetags.media_tags import to_thumbnail

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "image-cache-tests-default",
    },
    "image_metadata": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "image-cache-tests-metadata",
    },
}


@override_settings(CACHES=TEST_CACHES, SECURE_SSL_REDIRECT=False)
class ImageMetadataCacheTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        caches["image_metadata"].clear()
        self.resource = self.create_resource("a" * 64)

    def create_resource(self, checksum: str) -> ImageResource:
        return ImageResource.objects.create(
            checksum=checksum,
            file=ContentFile(b"raw", name="test.jpg"),
            avif_file=ContentFile(b"avif", name="test.avif"),
            webp_file=ContentFile(b"webp", name="test.webp"),
            thumbnail=ContentFile(b"thumbnail", name="test-thumb.avif"),
            placeholder="data:image/webp;base64,placeholder",
            width=100,
            height=100,
            size=1000,
            mime_type="image/jpeg",
            is_processed=True,
        )

    def test_metadata_cache_hit_avoids_database_queries(self):
        with self.assertNumQueries(2):
            first = get_image_render_metadata(self.resource.checksum)

        with self.assertNumQueries(0):
            second = get_image_render_metadata(self.resource.checksum)

        self.assertEqual(first, second)

    def test_negative_cache_avoids_repeated_database_queries(self):
        checksum = "b" * 64

        with self.assertNumQueries(1):
            self.assertIsNone(get_image_render_metadata(checksum))

        with self.assertNumQueries(0):
            self.assertIsNone(get_image_render_metadata(checksum))

    def test_resource_save_invalidates_metadata_cache(self):
        get_image_render_metadata(self.resource.checksum)
        self.resource.placeholder = "data:image/webp;base64,updated"

        with self.captureOnCommitCallbacks(execute=True):
            self.resource.save(update_fields=["placeholder"])

        with self.assertNumQueries(2):
            metadata = get_image_render_metadata(self.resource.checksum)

        self.assertEqual(metadata["placeholder"], self.resource.placeholder)

    def test_variant_changes_invalidate_metadata_cache(self):
        get_image_render_metadata(self.resource.checksum)

        with self.captureOnCommitCallbacks(execute=True):
            variant = ImageVariant.objects.create(
                resource=self.resource,
                file=ContentFile(b"variant", name="test-320.avif"),
                format=ImageVariant.Format.AVIF,
                width=320,
                height=180,
                size=8,
            )

        with self.assertNumQueries(2):
            metadata = get_image_render_metadata(self.resource.checksum)

        self.assertIn("avif", metadata["responsive_srcsets"])

        with self.captureOnCommitCallbacks(execute=True):
            variant.delete()

        with self.assertNumQueries(2):
            metadata = get_image_render_metadata(self.resource.checksum)

        self.assertNotIn("avif", metadata["responsive_srcsets"])

    def test_resource_creation_invalidates_negative_cache(self):
        checksum = "c" * 64
        self.assertIsNone(get_image_render_metadata(checksum))

        with (
            patch("media_service.signals.process_image.delay"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            resource = self.create_resource(checksum)

        with self.assertNumQueries(2):
            metadata = get_image_render_metadata(resource.checksum)

        self.assertEqual(metadata["file_url"], resource.file.url)

    def test_thumbnail_checksum_reuses_metadata_cache(self):
        with self.assertNumQueries(2):
            first = to_thumbnail(self.resource.checksum)

        with self.assertNumQueries(0):
            second = to_thumbnail(self.resource.checksum)

        self.assertEqual(first, self.resource.thumbnail.url)
        self.assertEqual(second, first)

    def test_stale_generation_is_not_returned(self):
        get_image_render_metadata(self.resource.checksum)
        cache = caches["image_metadata"]
        stale = cache.get(_metadata_cache_key(self.resource.checksum))
        self.assertIsNotNone(stale)
        invalidate_image_render_metadata(self.resource.checksum)
        cache.set(
            _metadata_cache_key(self.resource.checksum),
            stale,
            timeout=IMAGE_METADATA_TTL,
        )

        with self.assertNumQueries(2):
            metadata = get_image_render_metadata(self.resource.checksum)

        self.assertEqual(metadata["file_url"], self.resource.file.url)
