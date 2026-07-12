import asyncio
import logging
import os
from dataclasses import dataclass
from io import BytesIO
from typing import IO

from asgiref.sync import sync_to_async
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models, transaction
from PIL import ExifTags, ImageOps
from PIL import Image as PILImage

from core.hash import calculate_blake3_hash
from media_service.constants import IMAGE_ALLOWED_FORMAT, RESPONSIVE_IMAGE_WIDTHS
from media_service.exiftool import AsyncExifTool, SyncExifTool

from .base import BaseModel

# Create your models here.

logger = logging.getLogger(__name__)


# image resource upload path. do not make any changes.
# Django ORM may break (because 0047 migration hardcode the function path)
# or, move there functions into 0047 migration?
def image_raw_upload_path(instance: "ImageResource", filename: str) -> str:
    """
    Generate upload path for images using checksum-based directory structure.
    Prevent too many files in a single directory by sharding into sub dirs.
    """
    ext = os.path.splitext(filename)[-1].lower()
    return (
        f"images/raw/"
        f"{instance.checksum[:2]}/"
        f"{instance.checksum[2:4]}/"
        f"{instance.checksum}{ext}"
    )


def image_thumbnail_upload_path(instance: "ImageResource", filename: str) -> str:
    ext = os.path.splitext(filename)[-1].lower()
    return (
        f"images/thumbnails/"
        f"{instance.checksum[:2]}/"
        f"{instance.checksum[2:4]}/"
        f"{instance.checksum}{ext}"
    )


def image_avif_upload_path(instance: "ImageResource", filename: str) -> str:
    return (
        f"images/avif/"
        f"{instance.checksum[:2]}/"
        f"{instance.checksum[2:4]}/"
        f"{instance.checksum}.avif"
    )


def image_webp_upload_path(instance: "ImageResource", filename: str) -> str:
    return (
        f"images/webp/"
        f"{instance.checksum[:2]}/"
        f"{instance.checksum[2:4]}/"
        f"{instance.checksum}.webp"
    )


# TODO: add a very fast image tool to check if image size is too large
#       & generate a suitable size image (writen in Rust?)
class ImageResource(BaseModel):
    """single physical file"""

    # checksum
    checksum = models.CharField(max_length=64, unique=True)

    # files
    file = models.ImageField(upload_to=image_raw_upload_path, null=False, blank=False)
    # other files auto generate by django signal & celery task
    avif_file = models.ImageField(
        upload_to=image_avif_upload_path, null=True, blank=True
    )
    webp_file = models.ImageField(
        upload_to=image_webp_upload_path, null=True, blank=True
    )
    thumbnail = models.ImageField(
        upload_to=image_thumbnail_upload_path, null=True, blank=True
    )

    # low quality image placeholder, base64 encoded text
    placeholder = models.TextField(blank=True, default="")

    # attribute
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    size = models.PositiveIntegerField()
    mime_type = models.CharField(max_length=50)

    is_processed = models.BooleanField(default=False)
    responsive_variants_enabled = models.BooleanField(default=False)

    @property
    def avif_url(self) -> str | None:
        return self.avif_file.url if self.avif_file else None

    @property
    def webp_url(self) -> str | None:
        return self.webp_file.url if self.webp_file else None

    @property
    def thumbnail_url(self) -> str | None:
        return self.thumbnail.url if self.thumbnail else None

    class Meta:
        indexes = [models.Index(fields=["checksum"])]

    @dataclass
    class ImageResourceMeta:
        width: int
        height: int
        size: int
        mime_type: str

    def responsive_srcsets(self) -> dict[str, str]:
        grouped: dict[str, list[str]] = {
            ImageVariant.Format.AVIF: [],
            ImageVariant.Format.WEBP: [],
        }

        for variant in self.variants.all():
            if variant.file:
                grouped[variant.format].append(f"{variant.file.url} {variant.width}w")

        return {
            image_format: ", ".join(values)
            for image_format, values in grouped.items()
            if values
        }

    def has_complete_responsive_variants(self) -> bool:
        widths = {min(width, self.width) for width in RESPONSIVE_IMAGE_WIDTHS}
        expected = {
            (image_format, width)
            for image_format in (ImageVariant.Format.AVIF, ImageVariant.Format.WEBP)
            for width in widths
        }
        existing = set(self.variants.exclude(file="").values_list("format", "width"))
        return expected.issubset(existing)


def image_variant_update_path(instance: "ImageVariant", filename: str) -> str:
    checksum = instance.resource.checksum
    return (
        f"images/responsive/{instance.format}/"
        f"{checksum[:2]}/{checksum[2:4]}/"
        f"{checksum}-{instance.width}.{instance.format}"
    )


# INFO: about the image variant
#       this variant used for generate website UI image.
#       DO NOT use it for those used in blog post. (it maybe unclear)
class ImageVariant(BaseModel):
    class Format(models.TextChoices):
        AVIF = "avif", "AVIF"
        WEBP = "webp", "WEBP"

    resource = models.ForeignKey(
        ImageResource, on_delete=models.CASCADE, related_name="variants"
    )
    file = models.ImageField(upload_to=image_variant_update_path)

    format = models.CharField(max_length=8, choices=Format)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    size = models.PositiveIntegerField()

    class Meta:
        ordering = ["format", "width"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "format", "width"],
                name="unique_image_responsive_variant",
            )
        ]


@dataclass(frozen=True, slots=True)
class ImageInspection:
    image_format: str
    mime_type: str
    width: int
    height: int
    orientation: int
    frame_count: int

    @property
    def is_animated(self) -> bool:
        return self.frame_count > 1

    @property
    def normalized_size(self) -> tuple[int, int]:
        if self.orientation in {5, 6, 7, 8}:
            return self.height, self.width
        return self.width, self.height


# Create your models here.
class Image(BaseModel):
    """logical image file"""

    resource = models.ForeignKey(
        ImageResource, on_delete=models.CASCADE, related_name="references"
    )

    # image file info
    original_name = models.CharField(max_length=255, blank=True)

    # uploader (use django contenttype framework)
    # doc: https://docs.djangoproject.com/en/6.0/ref/contrib/contenttypes/
    # why polymorphic?
    #  an image may uploaded by guest who upload an image on the post comment
    #  or, an admin who want to add an image on django admin panel
    uploader_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
    )
    uploader_id = models.PositiveIntegerField()
    uploader = GenericForeignKey("uploader_type", "uploader_id")

    # Markdown meta info
    alt_text = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    # image metadata
    metadata = models.JSONField(default=dict, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name or f"Image {self.id}"

    @property
    def url(self) -> str:
        return self.resource.file.url

    # DRY principle
    # read: https://docs.djangoproject.com/en/6.0/misc/design-philosophies/#don-t-repeat-yourself-dry
    @classmethod
    def create_from_file(
        cls,
        content: IO[bytes],
        filename: str,
        alt_text: str = "",
        description: str = "",
        uploader: models.Model | None = None,
        metadata: dict | None = None,
    ) -> tuple["Image", ImageResource, bool]:

        # NOTE: There are some problem here
        #  1. image workflow is too long & complex, sync blocking in front, reduce QPS.
        #  2. if calculate hash only, EXIF clean and duplicates removing will invalid,
        #     and hash remap is too unelegant.
        #  Feature-rich & High-concurrency can't have it both ways?
        #  just like CAP theorem?

        # 0. extract basic info and verify file integrity
        try:
            inspection = cls._inspect_image(content)
        except Exception:
            raise ValidationError("Unrecognizable image file or file is corrupted")

        # 0.5. normalize orientation
        try:
            normalized_io = cls._normalize_static_orientation(content, inspection)
            content_for_cleaning = normalized_io or content
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(f"Could not process image: {e}")
            raise ValidationError("Cloud not normalize image orientation")

        # TODO: some photography may needs keep some EXIF
        # 1. clean metadata
        cleaned_io: BytesIO = None
        try:
            cleaned_io = cls._process_clean_metadata(
                content_for_cleaning,
                filename,
                pillow_cleaned=normalized_io is not None,
            )
            del content
        except Exception as e:
            logger.warning(f"Could not process image: {e}")
            raise ValidationError("Could not clean image metadata")
        finally:
            # close this to reduce peak memory usage
            if normalized_io is not None and cleaned_io is not normalized_io:
                normalized_io.close()

        # 2. checksum
        checksum = cls._calculate_file_checksum(cleaned_io)

        # 3. write to db
        final_inspection = cls._inspect_image(cleaned_io)
        res_meta = ImageResource.ImageResourceMeta(
            final_inspection.width,
            final_inspection.height,
            cleaned_io.getbuffer().nbytes,
            final_inspection.mime_type,
        )
        return cls._create_from_file__write_db(
            cleaned_io=cleaned_io,
            checksum=checksum,
            filename=filename,
            res_meta=res_meta,
            alt_text=alt_text,
            description=description,
            uploader=uploader,
            metadata=metadata,
        )

    @classmethod
    async def acreate_from_file(
        cls,
        content: IO[bytes],
        filename: str,
        alt_text: str = "",
        description: str = "",
        uploader: models.Model | None = None,
        metadata: dict | None = None,
    ) -> tuple["Image", ImageResource, bool]:
        # 0. verify
        try:
            inspection = await cls._ainspect_image(content)
        except Exception:
            raise ValidationError("Unrecognizable image file or file is corrupted")

        # 0.5. normalize orientation
        try:
            normalized_io = await cls._anormalize_static_orientation(
                content, inspection
            )
            content_for_cleaning = normalized_io or content
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(f"Could not process image: {e}")
            raise ValidationError("Could not clean image metadata")

        # 1. clean EXIF data
        cleaned_io: BytesIO = None
        try:
            cleaned_io = await cls._aprocess_clean_metadata(
                content_for_cleaning,
                filename,
                pillow_cleaned=normalized_io is not None,
            )
            del content
        except Exception as e:
            logger.warning(f"Could not process image (async): {e}")
            raise ValidationError("Could not clean image metadata")
        finally:
            if normalized_io is not None and cleaned_io is not normalized_io:
                normalized_io.close()

        # 2. checksum
        checksum = await cls._acalculate_file_checksum(cleaned_io)

        # 3. write to db
        final_inspection = await cls._ainspect_image(cleaned_io)
        res_meta = ImageResource.ImageResourceMeta(
            final_inspection.width,
            final_inspection.height,
            cleaned_io.getbuffer().nbytes,
            final_inspection.mime_type,
        )
        return await cls._acreate_from_file__write_db(
            cleaned_io=cleaned_io,
            checksum=checksum,
            filename=filename,
            res_meta=res_meta,
            alt_text=alt_text,
            description=description,
            uploader=uploader,
            metadata=metadata,
        )

    # --- verify & normalize ---

    @staticmethod
    def _inspect_image(content: IO[bytes]) -> ImageInspection:
        content.seek(0)

        try:
            with PILImage.open(content) as source:
                image_format = source.format
                mime_type = PILImage.MIME.get(image_format)
                if image_format is None or mime_type not in IMAGE_ALLOWED_FORMAT:
                    raise ValidationError("Not allowed image types")

                orientation = source.getexif().get(ExifTags.Base.Orientation, 1)
                if not isinstance(orientation, int) or orientation not in range(1, 9):
                    orientation = 1

                inspection = ImageInspection(
                    image_format=image_format,
                    mime_type=mime_type,
                    width=source.width,
                    height=source.height,
                    orientation=orientation,
                    frame_count=getattr(source, "n_frames", 1),
                )

            # verify
            content.seek(0)
            with PILImage.open(content) as source:
                source.verify()

            return inspection
        # not catch it
        finally:
            content.seek(0)

    @classmethod
    async def _ainspect_image(cls, content: IO[bytes]) -> ImageInspection:
        return await asyncio.to_thread(cls._inspect_image, content)

    @staticmethod
    def _normalize_static_orientation(content: IO[bytes], inspection: ImageInspection):
        if inspection.is_animated:
            if inspection.orientation != 1:
                # too complex
                raise ValidationError(
                    "Animated images with EXIF orientation are not supported"
                )
            return None

        if inspection.orientation == 1:
            return None

        content.seek(0)

        try:
            with PILImage.open(content) as source:
                normalized = ImageOps.exif_transpose(source)
                normalized_io = BytesIO()

                # the options
                save_options = {}
                if inspection.image_format == "JPEG":
                    save_options = {
                        "quality": 95,
                        "subsampling": 0,
                    }
                elif inspection.image_format in {"AVIF", "WEBP", "HEIF"}:
                    save_options = {"quality": 95}

                # normalized orientation
                try:
                    normalized.save(
                        normalized_io,
                        format=inspection.image_format,
                        **save_options,
                    )
                except Exception:
                    normalized_io.close()
                    raise
                finally:
                    normalized.close()

                normalized_io.seek(0)
                return normalized_io
        finally:
            content.seek(0)

    @classmethod
    async def _anormalize_static_orientation(
        cls, content: IO[bytes], inspection: ImageInspection
    ):
        return await asyncio.to_thread(
            cls._normalize_static_orientation, content, inspection
        )

    # --- clean metadata ---

    @staticmethod
    def _process_clean_metadata_fallback(content: IO[bytes]) -> BytesIO:
        content.seek(0)

        with PILImage.open(content) as img:
            cleaned_io = BytesIO()
            img.save(cleaned_io, quality=100, save_all=True, format=img.format)

        cleaned_io.seek(0)
        return cleaned_io

    @classmethod
    def _process_clean_metadata(
        cls,
        content: IO[bytes],
        filename: str,
        *,
        pillow_cleaned: bool = False,
    ) -> BytesIO:
        content.seek(0)

        if SyncExifTool.is_available():
            # SyncExifTool, no PIL re-encoding, more efficient
            cleaned_io = SyncExifTool().clean(content, filename=filename)
        elif pillow_cleaned:
            # reuse pillow cleaned data
            if not isinstance(content, BytesIO):
                raise TypeError("Pillow-cleaned content must be BytesIO")
            cleaned_io = content
        else:
            # fallback
            cleaned_io = cls._process_clean_metadata_fallback(content)

        cleaned_io.seek(0)
        return cleaned_io

    @classmethod
    async def _aprocess_clean_metadata(
        cls,
        content: IO[bytes],
        filename: str,
        *,
        pillow_cleaned: bool = False,
    ) -> BytesIO:
        content.seek(0)

        if await AsyncExifTool().is_available():
            cleaned_io = await AsyncExifTool().clean(content, filename)
        elif pillow_cleaned:
            if not isinstance(content, BytesIO):
                raise TypeError("Pillow-cleaned content must be BytesIO")
            cleaned_io = content
        else:
            cleaned_io = await asyncio.to_thread(
                cls._process_clean_metadata_fallback,
                content,
            )

        cleaned_io.seek(0)
        return cleaned_io

    # --- checksum ---

    @staticmethod
    def _calculate_file_checksum(cleaned_io: IO) -> str:
        return calculate_blake3_hash(cleaned_io)

    @staticmethod
    async def _acalculate_file_checksum(cleaned_io: IO) -> str:
        return await asyncio.to_thread(calculate_blake3_hash, cleaned_io)

    # --- db ---

    @classmethod
    @transaction.atomic
    def _create_from_file__write_db(
        cls,
        *,
        cleaned_io: BytesIO,
        checksum: str,
        filename: str,
        res_meta: ImageResource.ImageResourceMeta,
        alt_text: str,
        description: str,
        uploader: models.Model | None,
        metadata: dict | None,
    ) -> tuple["Image", ImageResource, bool]:
        if uploader is not None:
            content_type = ContentType.objects.get_for_model(uploader)
        else:
            content_type = None

        cleaned_io.seek(0)
        img_res, created = ImageResource.objects.get_or_create(
            checksum=checksum,
            defaults={
                "file": File(cleaned_io, name=filename),
                "width": res_meta.width,
                "height": res_meta.height,
                "size": res_meta.size,
                "mime_type": res_meta.mime_type,
            },
        )
        img = cls.objects.create(
            resource=img_res,
            original_name=filename,
            uploader_type=content_type,
            uploader_id=uploader.pk if uploader else None,
            alt_text=alt_text,
            description=description,
            metadata=metadata or {},
        )
        return img, img_res, created

    @classmethod
    async def _acreate_from_file__write_db(
        cls,
        *,
        cleaned_io: BytesIO,
        checksum: str,
        filename: str,
        res_meta: ImageResource.ImageResourceMeta,
        alt_text: str,
        description: str,
        uploader: models.Model | None,
        metadata: dict | None,
    ) -> tuple["Image", ImageResource, bool]:
        return await sync_to_async(cls._create_from_file__write_db)(
            cleaned_io=cleaned_io,
            checksum=checksum,
            filename=filename,
            res_meta=res_meta,
            alt_text=alt_text,
            description=description,
            uploader=uploader,
            metadata=metadata,
        )
