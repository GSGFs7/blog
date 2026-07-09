import base64
import logging
from io import BytesIO

from celery import shared_task
from django.core.files.base import ContentFile
from PIL import Image as PILImage

from media_service.models import ImageResource

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
            image_res_obj.save()
    except ImageResource.DoesNotExist:
        logger.error(f"Image not found: {image_resource_id}")
    except Exception as e:
        logger.error(f"Error processing image {image_resource_id}: {e}")
