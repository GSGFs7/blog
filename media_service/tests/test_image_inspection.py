from io import BytesIO
from unittest.mock import AsyncMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from PIL import ExifTags, UnidentifiedImageError
from PIL import Image as PILImage

from media_service.models import Image


class ImageInspectionTest(SimpleTestCase):
    @staticmethod
    def build_jpeg(orientation: int | None = None) -> BytesIO:
        content = BytesIO()
        image = PILImage.new("RGB", (8, 4), "red")

        # set orientation
        exif = image.getexif()
        if orientation is not None:
            exif[ExifTags.Base.Orientation] = orientation

        image.save(content, format="JPEG", exif=exif)
        content.seek(0)
        return content

    @staticmethod
    def build_animated_gif() -> BytesIO:
        content = BytesIO()
        first = PILImage.new("RGB", (8, 4), "red")
        second = PILImage.new("RGB", (8, 4), "blue")

        # merge to a GIF
        first.save(
            content,
            format="GIF",
            save_all=True,
            append_images=[second],
            duration=[100, 200],
            loop=0,
        )
        content.seek(0)
        return content

    def test_inspects_all_exif_orientations(self):
        for orientation in range(1, 9):
            with self.subTest(orirntation=orientation):
                content = self.build_jpeg(orientation)

                inspection = Image._inspect_image(content)

                self.assertEqual(inspection.image_format, "JPEG")
                self.assertEqual(inspection.mime_type, "image/jpeg")
                self.assertEqual(inspection.width, 8)
                self.assertEqual(inspection.height, 4)
                self.assertEqual(inspection.orientation, orientation)
                self.assertEqual(inspection.frame_count, 1)
                self.assertFalse(inspection.is_animated)

                expected_size = (4, 8) if orientation in {5, 6, 7, 8} else (8, 4)
                self.assertEqual(inspection.normalized_size, expected_size)
                self.assertEqual(content.tell(), 0)

    def test_default_to_orientation_one(self):
        content = self.build_jpeg()

        inspection = Image._inspect_image(content)

        self.assertEqual(inspection.orientation, 1)
        self.assertEqual(inspection.normalized_size, (8, 4))

    def test_detects_animated_image(self):
        content = self.build_animated_gif()

        inspection = Image._inspect_image(content)

        self.assertEqual(inspection.image_format, "GIF")
        self.assertEqual(inspection.mime_type, "image/gif")
        self.assertEqual(inspection.frame_count, 2)
        self.assertEqual(inspection.orientation, 1)
        self.assertEqual(content.tell(), 0)
        self.assertTrue(inspection.is_animated)

    def test_rejects_disallowed_format(self):
        content = BytesIO()
        PILImage.new("RGBA", (16, 16), "red").save(content, format="ICO")
        content.seek(0)

        with self.assertRaisesMessage(ValidationError, "Not allowed image types"):
            Image._inspect_image(content)

        self.assertEqual(content.tell(), 0)

    def test_reject_invalid_image_and_resets_position(self):
        content = BytesIO(b"this not a image")

        with self.assertRaises(UnidentifiedImageError):
            Image._inspect_image(content)

        self.assertEqual(content.tell(), 0)


class ImageMetadataCleaningTest(SimpleTestCase):
    @staticmethod
    def build_oriented_png(orientation: int = 6) -> BytesIO:
        colors = (
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (0, 255, 255),
            (255, 0, 255),
            (255, 255, 0),
        )
        image = PILImage.new("RGB", (3, 2))
        for index, color in enumerate(colors):
            image.putpixel((index % 3, index // 3), color)

        exif = image.getexif()
        exif[ExifTags.Base.Orientation] = orientation

        content = BytesIO()
        image.save(content, format="PNG", exif=exif)
        content.seek(0)
        return content

    def test_reuses_pillow_cleaned_buffer_without_exiftool(self):
        content = self.build_oriented_png()
        inspection = Image._inspect_image(content)
        normalized_io = Image._normalize_static_orientation(content, inspection)
        self.assertIsNotNone(normalized_io)
        self.addCleanup(normalized_io.close)
        normalized_io.seek(0, 2)

        with (
            patch(
                "media_service.models.image.SyncExifTool.is_available",
                return_value=False,
            ) as is_available,
            patch.object(Image, "_process_clean_metadata_fallback") as fallback,
        ):
            cleaned_io = Image._process_clean_metadata(
                normalized_io,
                "oriented.png",
                pillow_cleaned=True,
            )

        self.assertIs(cleaned_io, normalized_io)
        self.assertEqual(cleaned_io.tell(), 0)
        is_available.assert_called_once_with()
        fallback.assert_not_called()

    def test_uses_pillow_fallback_once_for_untouched_content(self):
        content = self.build_oriented_png(orientation=1)
        fallback_output = BytesIO(b"cleaned")
        fallback_output.seek(0, 2)
        self.addCleanup(fallback_output.close)

        with (
            patch(
                "media_service.models.image.SyncExifTool.is_available",
                return_value=False,
            ) as is_available,
            patch.object(
                Image,
                "_process_clean_metadata_fallback",
                return_value=fallback_output,
            ) as fallback,
        ):
            cleaned_io = Image._process_clean_metadata(content, "plain.png")

        self.assertIs(cleaned_io, fallback_output)
        self.assertEqual(cleaned_io.tell(), 0)
        is_available.assert_called_once_with()
        fallback.assert_called_once_with(content)

    async def test_async_reuses_pillow_cleaned_buffer_without_exiftool(self):
        content = self.build_oriented_png()
        inspection = Image._inspect_image(content)
        normalized_io = Image._normalize_static_orientation(content, inspection)
        self.assertIsNotNone(normalized_io)
        self.addCleanup(normalized_io.close)
        normalized_io.seek(0, 2)

        with (
            patch(
                "media_service.models.image.AsyncExifTool.is_available",
                new_callable=AsyncMock,
                return_value=False,
            ) as is_available,
            patch.object(Image, "_process_clean_metadata_fallback") as fallback,
        ):
            cleaned_io = await Image._aprocess_clean_metadata(
                normalized_io,
                "oriented.png",
                pillow_cleaned=True,
            )

        self.assertIs(cleaned_io, normalized_io)
        self.assertEqual(cleaned_io.tell(), 0)
        is_available.assert_awaited_once_with()
        fallback.assert_not_called()

    async def test_async_uses_pillow_fallback_once_for_untouched_content(self):
        content = self.build_oriented_png(orientation=1)
        fallback_output = BytesIO(b"cleaned")
        fallback_output.seek(0, 2)
        self.addCleanup(fallback_output.close)

        with (
            patch(
                "media_service.models.image.AsyncExifTool.is_available",
                new_callable=AsyncMock,
                return_value=False,
            ) as is_available,
            patch.object(
                Image,
                "_process_clean_metadata_fallback",
                return_value=fallback_output,
            ) as fallback,
        ):
            cleaned_io = await Image._aprocess_clean_metadata(content, "plain.png")

        self.assertIs(cleaned_io, fallback_output)
        self.assertEqual(cleaned_io.tell(), 0)
        is_available.assert_awaited_once_with()
        fallback.assert_called_once_with(content)

    def test_sync_flow_skips_second_pillow_save_after_normalization(self):
        content = self.build_oriented_png()

        with (
            patch(
                "media_service.models.image.SyncExifTool.is_available",
                return_value=False,
            ),
            patch.object(Image, "_process_clean_metadata_fallback") as fallback,
            patch.object(
                Image,
                "_create_from_file__write_db",
                return_value=None,
            ) as write_db,
        ):
            Image.create_from_file(content, "oriented.png")

        fallback.assert_not_called()
        cleaned_io = write_db.call_args.kwargs["cleaned_io"]
        self.addCleanup(cleaned_io.close)
        res_meta = write_db.call_args.kwargs["res_meta"]

        with PILImage.open(cleaned_io) as result:
            self.assertEqual(result.size, (2, 3))
            self.assertEqual(result.getexif().get(ExifTags.Base.Orientation, 1), 1)
            self.assertEqual(
                [
                    result.getpixel((x, y))
                    for y in range(result.height)
                    for x in range(result.width)
                ],
                [
                    (0, 255, 255),
                    (255, 0, 0),
                    (255, 0, 255),
                    (0, 255, 0),
                    (255, 255, 0),
                    (0, 0, 255),
                ],
            )

        self.assertEqual((res_meta.width, res_meta.height), (2, 3))
        self.assertEqual(res_meta.mime_type, "image/png")

    async def test_async_flow_skips_second_pillow_save_after_normalization(self):
        content = self.build_oriented_png()

        with (
            patch(
                "media_service.models.image.AsyncExifTool.is_available",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(Image, "_process_clean_metadata_fallback") as fallback,
            patch.object(
                Image,
                "_acreate_from_file__write_db",
                new_callable=AsyncMock,
                return_value=None,
            ) as write_db,
        ):
            await Image.acreate_from_file(content, "oriented.png")

        fallback.assert_not_called()
        cleaned_io = write_db.await_args.kwargs["cleaned_io"]
        self.addCleanup(cleaned_io.close)
        res_meta = write_db.await_args.kwargs["res_meta"]

        with PILImage.open(cleaned_io) as result:
            self.assertEqual(result.size, (2, 3))
            self.assertEqual(result.getexif().get(ExifTags.Base.Orientation, 1), 1)

        self.assertEqual((res_meta.width, res_meta.height), (2, 3))
        self.assertEqual(res_meta.mime_type, "image/png")
