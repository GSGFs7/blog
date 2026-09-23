import base64
import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from PIL import Image as PILImage
from PIL import ImageFilter

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

    def test_process_image_blurs_placeholder(self):
        file, size = self.build_image_resource_content()
        image_resource = ImageResource.objects.create(
            checksum="e" * 64,
            file=file,
            width=100,
            height=100,
            size=size,
            mime_type="image/png",
        )

        with patch(
            "media_service.tasks.ImageFilter.GaussianBlur",
            wraps=ImageFilter.GaussianBlur,
        ) as blur:
            process_image(image_resource.id)

        blur.assert_called_once_with(radius=2)
        image_resource.refresh_from_db()
        self.assertTrue(image_resource.placeholder)

    @override_settings(MAX_FRAME_PIXELS=9_999)
    def test_tasks_reject_oversized_resource_before_encoding(self):
        file, size = self.build_image_resource_content()
        resource = ImageResource.objects.create(
            checksum="f" * 64,
            file=file,
            width=100,
            height=100,
            size=size,
            mime_type="image/png",
            responsive_variants_enabled=True,
        )

        for task in (process_image, process_responsive_variants):
            with (
                self.subTest(task=task.name),
                patch("media_service.tasks.save_optimized_image") as encode,
                self.assertLogs("media_service.tasks", level="WARNING") as logs,
            ):
                task(resource.pk)
                encode.assert_not_called()
                self.assertIn("Rejected image resource", logs.output[0])

        resource.refresh_from_db()
        self.assertFalse(resource.is_processed)
        self.assertFalse(resource.avif_file)
        self.assertFalse(resource.webp_file)
        self.assertFalse(resource.thumbnail)
        self.assertFalse(resource.placeholder)
        self.assertFalse(resource.variants.exists())

    def test_failed_encoding_does_not_mark_complete_or_reschedule(self):
        file, size = self.build_image_resource_content()
        resource = ImageResource.objects.create(
            checksum="g" * 64,
            file=file,
            width=100,
            height=100,
            size=size,
            mime_type="image/png",
        )

        with (
            patch("media_service.tasks.save_optimized_image", side_effect=OSError),
            patch("media_service.signals.process_image.delay") as enqueue,
            self.captureOnCommitCallbacks(execute=True),
            self.assertLogs("media_service.tasks", level="WARNING"),
        ):
            process_image(resource.pk)

        enqueue.assert_not_called()
        resource.refresh_from_db()
        self.assertFalse(resource.is_processed)
        self.assertFalse(resource.avif_file)
        self.assertFalse(resource.webp_file)

    def test_animated_images_keep_frames_and_timing(self):
        for source_format, default_image in (
            ("GIF", False),
            ("WEBP", False),
            ("PNG", False),
            ("AVIF", False),
            ("PNG", True),
        ):
            with self.subTest(source_format=source_format, default_image=default_image):
                buffer = BytesIO()
                frames = [
                    PILImage.new("RGB", (100, 60), color)
                    for color in ("red", "green", "blue")
                ]
                if default_image:
                    frames.insert(0, PILImage.new("RGB", (100, 60), "darkred"))
                frames[0].save(
                    buffer,
                    format=source_format,
                    save_all=True,
                    append_images=frames[1:],
                    duration=[100, 200, 300],
                    loop=2,
                    default_image=default_image,
                )
                resource = ImageResource.objects.create(
                    checksum=f"{source_format.lower()}{int(default_image)}".ljust(
                        64, "a"
                    ),
                    file=ContentFile(buffer.getvalue(), name=f"test.{source_format}"),
                    width=100,
                    height=60,
                    size=buffer.tell(),
                    mime_type=PILImage.MIME[source_format],
                    responsive_variants_enabled=True,
                )

                process_image(resource.pk)
                resource.refresh_from_db()
                with patch("media_service.tasks.RESPONSIVE_IMAGE_WIDTHS", (50, 100)):
                    process_responsive_variants(resource.pk)

                outputs = [(resource.avif_file, 100), (resource.webp_file, 100)]
                outputs.extend(
                    (variant.file, variant.width) for variant in resource.variants.all()
                )
                self.assertEqual(len(outputs), 6)
                for file, width in outputs:
                    with file.open("rb") as data, PILImage.open(data) as result:
                        self.assertEqual(result.n_frames, 3)
                        self.assertEqual(result.size, (width, round(width * 0.6)))
                        if result.format == "WEBP" and source_format != "AVIF":
                            self.assertEqual(result.info["loop"], 2)
                        for index, duration in enumerate((100, 200, 300)):
                            result.seek(index)
                            result.load()
                            self.assertAlmostEqual(
                                result.info["duration"], duration, delta=1
                            )
                            pixel = result.convert("RGB").getpixel((0, 0))
                            self.assertEqual(pixel.index(max(pixel)), index)

                with (
                    resource.thumbnail.open("rb") as data,
                    PILImage.open(data) as thumbnail,
                ):
                    self.assertEqual(getattr(thumbnail, "n_frames", 1), 1)
                    pixel = thumbnail.convert("RGB").getpixel((0, 0))
                    self.assertEqual(pixel.index(max(pixel)), 0)
                placeholder = BytesIO(
                    base64.b64decode(resource.placeholder.split(",", 1)[1])
                )
                with PILImage.open(placeholder) as result:
                    self.assertEqual(getattr(result, "n_frames", 1), 1)

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
