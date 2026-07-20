import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from media_service.image_cache import invalidate_image_render_metadata
from media_service.models import ImageResource, ImageVariant
from media_service.tasks import process_image

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ImageResource)
def trigger_image_processing(sender, instance: ImageResource, created, **kwargs):
    """
    Trigger image processing (compression, format conversion) after upload.

    sync function, it will running in the thead pool
    """
    if (
        created
        or not instance.webp_file
        or not instance.avif_file
        or not instance.thumbnail
    ):
        try:

            def task():
                process_image.delay(instance.pk)
                logger.info(f"Triggered image processing for Image ID {instance.pk}")

            transaction.on_commit(task)
        except Exception as e:
            logger.error(
                f"Failed to trigger image processing for Image ID {instance.pk}: {e}"
            )


# NOTE: QuerySet.update() will not trigger signal
def _invalidate_metadata_on_commit(checksum: str, using: str) -> None:
    transaction.on_commit(
        lambda checksum=checksum: invalidate_image_render_metadata(checksum),
        using=using,
    )


@receiver([post_save, pre_delete], sender=ImageResource)
def invalidate_resource_metadata(sender, instance: ImageResource, using, **kwargs):
    _invalidate_metadata_on_commit(instance.checksum, using)


@receiver([post_save, pre_delete], sender=ImageVariant)
def invalidate_variant_metadata(sender, instance: ImageVariant, using, **kwargs):
    _invalidate_metadata_on_commit(instance.resource.checksum, using)
