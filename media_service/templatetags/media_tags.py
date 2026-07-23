import re
from dataclasses import dataclass
from posixpath import splitext
from urllib.parse import urlsplit

from django import template
from django.conf import settings
from django.forms.utils import flatatt
from django.utils.html import format_html, format_html_join

from media_service.image_cache import (
    ImageRenderMetadata,
    build_image_render_metadata,
    get_image_render_metadata,
)
from media_service.models import Image, ImageResource

__all__ = ("render_image", "to_thumbnail")

register = template.Library()


@dataclass(frozen=True)
class _ImageRenderOptions:
    alt: str
    class_name: str
    img_class: str
    loading: str
    sizes: str
    fetch_priority: str
    style: str
    data_attributes: dict[str, object]


def _render_img_attributes(style: str, data_attributes: dict[str, object]):
    attributes = {
        name.replace("_", "-"): value for name, value in data_attributes.items()
    }
    if style:
        attributes["style"] = style
    return flatatt(attributes)


def _validate_data_attributes(data_attributes: dict[str, object]) -> None:
    unexpected_attributes = [
        name for name in data_attributes if not re.fullmatch(r"data_[a-z0-9_]+", name)
    ]
    if unexpected_attributes:
        unexpected = ", ".join(sorted(unexpected_attributes))
        raise TypeError(
            f"render_image() got unexpected keyword arguments: {unexpected}"
        )


def _resolve_image_input(
    image_input: Image | ImageResource | str,
    alt: str,
) -> tuple[ImageRenderMetadata | None, str, str]:
    # find image resource
    if isinstance(image_input, Image):
        return (
            build_image_render_metadata(image_input.resource),
            "",
            alt or image_input.alt_text,
        )
    if isinstance(image_input, ImageResource):
        return build_image_render_metadata(image_input), "", alt
    if isinstance(image_input, str):
        match = re.search(r"([a-f0-9]{64})", image_input)
        metadata = get_image_render_metadata(match.group(1)) if match else None
        return metadata, image_input, alt
    return None, "", alt


# it make sure the URL prefix has img variant
def _render_known_variant_image(
    src: str,
    options: _ImageRenderOptions,
):
    for source_prefix, variant_prefixes in getattr(
        settings, "IMAGE_PICTURE_URL_PREFIXES", {}
    ).items():
        if not src.startswith(source_prefix):
            continue

        relative_path = urlsplit(src).path.removeprefix(urlsplit(source_prefix).path)
        # stem: ab/cd/abcd... (img hash)
        # extension: .jpeg
        stem, extension = splitext(relative_path)
        avif_prefix = variant_prefixes.get("avif")
        webp_prefix = variant_prefixes.get("webp")
        if not stem or not extension or not avif_prefix or not webp_prefix:
            return None

        img_attributes = _render_img_attributes(options.style, options.data_attributes)
        return format_html(
            '<picture class="{}"><source srcset="{}/{}.avif" type="image/avif">'
            '<source srcset="{}/{}.webp" type="image/webp"><img src="{}" '
            'alt="{}" class="{}" loading="{}" decoding="async" sizes="{}" '
            'fetchpriority="{}"{}></picture>',
            options.class_name,
            avif_prefix.rstrip("/"),
            stem,
            webp_prefix.rstrip("/"),
            stem,
            src,
            options.alt,
            options.img_class,
            options.loading,
            options.sizes,
            options.fetch_priority,
            img_attributes,
        )

    return None


def _render_fallback_image(src: str, options: _ImageRenderOptions):
    # if not found
    # try match the prefix
    # it's safe to generate variant url if matched
    if picture := _render_known_variant_image(src, options):
        return picture
    img_attributes = _render_img_attributes(options.style, options.data_attributes)
    return format_html(
        '<img src="{}" alt="{}" class="{}" loading="{}" fetchpriority="{}"{}>',
        src,
        options.alt,
        options.img_class or options.class_name,
        options.loading,
        options.fetch_priority,
        img_attributes,
    )


def _render_picture_source(
    srcset: str | None,
    fallback_url: str | None,
    image_format: str,
    sizes: str,
):
    if srcset:
        return format_html(
            '<source srcset="{}" sizes="{}" type="image/{}">',
            srcset,
            sizes,
            image_format,
        )
    if fallback_url:
        return format_html(
            '<source srcset="{}" type="image/{}">', fallback_url, image_format
        )
    return None


def _render_picture_sources(metadata: ImageRenderMetadata, sizes: str):
    # picture source
    responsive_srcsets = metadata["responsive_srcsets"]
    sources = []

    # avif source
    if source := _render_picture_source(
        responsive_srcsets.get("avif"), metadata["avif_url"], "avif", sizes
    ):
        sources.append(source)

    # webp source
    if source := _render_picture_source(
        responsive_srcsets.get("webp"), metadata["webp_url"], "webp", sizes
    ):
        sources.append(source)

    return format_html_join("", "{}", ((source,) for source in sources))


def _build_image_style(metadata: ImageRenderMetadata, style: str) -> str:
    # build styles
    placeholder = metadata["placeholder"]
    if placeholder:
        placeholder_style = (
            f"background-image: url({placeholder}); background-size: cover;"
        )
        return f"{placeholder_style} {style}" if style else placeholder_style
    return style


def _render_metadata_image(
    metadata: ImageRenderMetadata,
    alt_text: str,
    options: _ImageRenderOptions,
):
    source_html = _render_picture_sources(metadata, options.sizes)
    img_attributes = _render_img_attributes(
        _build_image_style(metadata, options.style), options.data_attributes
    )

    dimensions = ""
    if metadata["width"] and metadata["height"]:
        dimensions = format_html(
            ' width="{}" height="{}"', metadata["width"], metadata["height"]
        )

    # render <picture>
    return format_html(
        '<picture class="{}">{}<img src="{}" alt="{}"{} class="{}" '
        'loading="{}" decoding="async" sizes="{}" fetchpriority="{}"{}></picture>',
        options.class_name,
        source_html,
        metadata["file_url"],
        alt_text,
        img_attributes,
        options.img_class,
        options.loading,
        options.sizes,
        options.fetch_priority,
        dimensions,
    )


@register.simple_tag
def render_image(
    image_input: Image | ImageResource | str | None,
    alt: str = "",
    class_name: str = "",
    img_class: str = "",
    loading: str = "lazy",
    sizes: str = "100vw",
    fetch_priority: str = "auto",
    style: str = "",
    **data_attributes: object,
):
    _validate_data_attributes(data_attributes)
    if not image_input:
        return ""

    options = _ImageRenderOptions(
        alt=alt,
        class_name=class_name,
        img_class=img_class,
        loading=loading,
        sizes=sizes,
        fetch_priority=fetch_priority,
        style=style,
        data_attributes=data_attributes,
    )
    metadata, src, alt_text = _resolve_image_input(image_input, alt)
    if metadata:
        return _render_metadata_image(metadata, alt_text, options)
    if src:
        return _render_fallback_image(src, options)
    return ""


@register.filter
def to_thumbnail(image_input: Image | ImageResource | str | None):
    if not image_input:
        return ""

    if isinstance(image_input, Image):
        return image_input.resource.thumbnail_url or image_input.url
    elif isinstance(image_input, ImageResource):
        return image_input.thumbnail_url or image_input.file.url
    elif isinstance(image_input, str):
        match = re.search("([a-f0-9]{64})", image_input)
        if match:
            checksum = match.group(1)
            metadata = get_image_render_metadata(checksum)
            if metadata:
                return metadata["thumbnail_url"] or metadata["file_url"]
        return image_input
    return ""
