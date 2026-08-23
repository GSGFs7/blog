from collections.abc import Iterable
from functools import lru_cache

from django.conf import settings
from markdown_it_rs_py import ImageMetadata

from media_service.models import ImageResource


@lru_cache(1)
def _image_picture_source_prefixes() -> tuple[str, ...]:
    return tuple(getattr(settings, "IMAGE_PICTURE_URL_PREFIXES", {}))


def _resolve_images(checksums: Iterable[str]) -> dict[str, ImageMetadata]:
    checksums = tuple(checksums)
    if not checksums:
        return {}

    resources = ImageResource.objects.in_bulk(checksums, field_name="checksum")
    return {
        checksum: ImageMetadata(
            src=resource.file.url,
            avif_src=resource.avif_url,
            webp_src=resource.webp_url,
            width=resource.width,
            height=resource.height,
            placeholder=resource.placeholder or None,
        )
        for checksum, resource in resources.items()
    }
