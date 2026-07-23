import base64
import logging
from io import BytesIO

from celery import shared_task
from django.core.files.base import ContentFile
from PIL import Image as PILImage
from PIL import ImageFilter

from media_service.constants import RESPONSIVE_IMAGE_WIDTHS
from media_service.models import ImageResource, ImageVariant

logger = logging.getLogger(__name__)


@shared_task
def process_image(image_resource_id: int, force: bool = False):
    """Generate optimized versions (WebP, AVIF) and thumbnail for an image."""
    try:
        image_res_obj = ImageResource.objects.get(id=image_resource_id)

        if not force and image_res_obj.is_processed:
            return

        with PILImage.open(image_res_obj.file) as img:
            # AVIF
            if force or not image_res_obj.avif_file:
                try:
                    buffer = BytesIO()  # in memory
                    img.save(buffer, format="AVIF", quality=80)

                    data = buffer.getvalue()
                    # filename also use raw image check sum
                    filename = f"{image_res_obj.checksum}.avif"

                    image_res_obj.avif_file.save(
                        filename, ContentFile(data), save=False
                    )

                    logger.info(f"Successfully generated AVIF for {image_resource_id}")
                except Exception as e:
                    logger.warning(
                        f"Could not generate AVIF for {image_resource_id}: {e}"
                    )

            # WebP
            if force or not image_res_obj.webp_file:
                try:
                    buffer = BytesIO()
                    img.save(buffer, format="WEBP", quality=80)

                    data = buffer.getvalue()
                    filename = f"{image_res_obj.checksum}.webp"

                    image_res_obj.webp_file.save(
                        filename, ContentFile(data), save=False
                    )

                    logger.info(f"Successfully generated WebP for {image_resource_id}")
                except Exception as e:
                    logger.warning(
                        f"Could not generate WebP for {image_resource_id}: {e}"
                    )

            # Thumbnail, AVIF default
            if force or not image_res_obj.thumbnail:
                try:
                    thumb_img = img.copy()
                    thumb_img.thumbnail((300, 300))

                    buffer = BytesIO()
                    thumb_img.save(buffer, format="AVIF", quality=60)
                    data = buffer.getvalue()
                    filename = f"{image_res_obj.checksum}_thumb.avif"

                    image_res_obj.thumbnail.save(
                        filename, ContentFile(data), save=False
                    )

                    logger.info(
                        f"Successfully generated thumbnail for {image_resource_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to generate thumbnail for {image_resource_id}: {e}"
                    )

            if force or not image_res_obj.placeholder:
                try:
                    placeholder = img.copy()
                    placeholder.thumbnail((32, 32))
                    placeholder = placeholder.filter(ImageFilter.GaussianBlur(radius=2))

                    buffer = BytesIO()
                    placeholder.save(buffer, format="WEBP", quality=30)

                    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                    encoded_img = f"data:image/webp;base64,{encoded}"
                    image_res_obj.placeholder = encoded_img
                except Exception as e:
                    logger.warning(
                        f"Failed to generate placeholder for {image_resource_id}: {e}"
                    )

            image_res_obj.is_processed = True
            # save updated fields only
            # avoid race conditions
            image_res_obj.save(
                update_fields=[
                    "avif_file",
                    "webp_file",
                    "thumbnail",
                    "placeholder",
                    "is_processed",
                    "updated_at",
                ]
            )
    except ImageResource.DoesNotExist:
        logger.error(f"Image not found: {image_resource_id}")
    except Exception as e:
        logger.error(f"Error processing image {image_resource_id}: {e}")


@shared_task
def process_responsive_variants(image_resource_id: int):
    try:
        resource = ImageResource.objects.get(id=image_resource_id)
        if not resource.responsive_variants_enabled:
            return

        with PILImage.open(resource.file) as img:
            for width in target_widths(img.width):
                generate_variant(
                    resource,
                    img,
                    width,
                    ImageVariant.Format.AVIF,
                    "AVIF",
                    50,
                )
                generate_variant(
                    resource,
                    img,
                    width,
                    ImageVariant.Format.WEBP,
                    "WEBP",
                    80,
                )
    except ImageResource.DoesNotExist:
        logger.error(f"Image not found: {image_resource_id}")
    except Exception as e:
        logger.error(
            f"Error processing responsive variants for {image_resource_id}: {e}"
        )


def target_widths(original_width: int) -> list[int]:
    return sorted({min(width, original_width) for width in RESPONSIVE_IMAGE_WIDTHS})


def generate_variant(
    resource: ImageResource,
    source: PILImage.Image,
    width: int,
    image_format: str,
    pil_format: str,
    quality: int,
):
    height = round(source.height * width / source.width)
    variant, _ = ImageVariant.objects.get_or_create(
        resource=resource,
        format=image_format,
        width=width,
        defaults={"height": height, "size": 0},
    )
    if variant.file:
        return

    if width == source.width:
        resized = source.copy()
    else:
        resized = source.resize((width, height), PILImage.Resampling.LANCZOS)

    buffer = BytesIO()
    resized.save(buffer, format=pil_format, quality=quality)

    variant.height = height
    variant.size = buffer.tell()
    variant.file.save(
        f"{resource.checksum}-{width}.{image_format}",
        ContentFile(buffer.getvalue()),
        save=False,
    )
    variant.save()
