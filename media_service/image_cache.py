from typing import TypedDict

from django.core.cache import caches

from media_service.models import ImageResource

IMAGE_METADATA_TTL = 24 * 60 * 60  # 1d
INCOMPLETE_METADATA_TTL = 5 * 60  # 5min
NEGATIVE_METADATA_TTL = 30 * 60  # 30 min
METADATA_GENERATION_TTL = IMAGE_METADATA_TTL + NEGATIVE_METADATA_TTL


class ImageRenderMetadata(TypedDict):
    file_url: str
    avif_url: str | None
    webp_url: str | None
    thumbnail_url: str | None
    placeholder: str
    width: int
    height: int
    responsive_srcsets: dict[str, str]


class CachedImageLookup(TypedDict):
    generation: int
    metadata: ImageRenderMetadata | None


def _metadata_cache_key(checksum: str) -> str:
    return f"media:image-meta:v1:{checksum}"


def _generation_cache_key(checksum: str) -> str:
    return f"media:image-meta:generation:v1:{checksum}"


def _metadata_cache():
    return caches["image_metadata"]


# add a generation prevent concurrent issues
# update cache only in generation match
def _get_generation(cache, checksum: str) -> int:
    generation = cache.get(_generation_cache_key(checksum), 0)
    return generation if isinstance(generation, int) else 0


def _set_metadata(
    cache,
    checksum: str,
    generation: int,
    metadata: ImageRenderMetadata | None,
    timeout: int,
) -> None:
    if _get_generation(cache, checksum) != generation:
        # it meaning has updated if not match
        # do not set the old data to cache
        return

    cache.set(
        _metadata_cache_key(checksum),
        {"generation": generation, "metadata": metadata},
        timeout=timeout,
    )


def build_image_render_metadata(
    resource: ImageResource,
) -> ImageRenderMetadata:
    return {
        "file_url": resource.file.url,
        "avif_url": resource.avif_url,
        "webp_url": resource.webp_url,
        "thumbnail_url": resource.thumbnail_url,
        "placeholder": resource.placeholder,
        "width": resource.width,
        "height": resource.height,
        "responsive_srcsets": resource.responsive_srcsets(),
    }


def get_image_render_metadata(
    checksum: str,
) -> ImageRenderMetadata | None:
    cache = _metadata_cache()
    generation = _get_generation(cache, checksum)
    key = _metadata_cache_key(checksum)
    cached: CachedImageLookup | None = cache.get(key)
    if isinstance(cached, dict) and cached.get("generation") == generation:
        return cached["metadata"]
    if cached is not None:
        cache.delete(key)

    resource = (
        ImageResource.objects.prefetch_related("variants")
        .filter(checksum=checksum)
        .first()
    )
    if resource is None:
        _set_metadata(cache, checksum, generation, None, NEGATIVE_METADATA_TTL)
        return None

    metadata = build_image_render_metadata(resource)
    timeout = IMAGE_METADATA_TTL if resource.is_processed else INCOMPLETE_METADATA_TTL
    _set_metadata(cache, checksum, generation, metadata, timeout)
    return metadata


def invalidate_image_render_metadata(checksum: str) -> None:
    cache = _metadata_cache()
    generation_key = _generation_cache_key(checksum)
    # update generation
    if not cache.add(generation_key, 1, timeout=METADATA_GENERATION_TTL):
        try:
            cache.incr(generation_key)
        except ValueError:
            cache.add(generation_key, 1, timeout=METADATA_GENERATION_TTL)
        else:
            cache.touch(generation_key, timeout=METADATA_GENERATION_TTL)
    cache.delete(_metadata_cache_key(checksum))
