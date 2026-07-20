import re
from posixpath import splitext
from urllib.parse import urlsplit

from django import template
from django.conf import settings
from django.utils.html import format_html, format_html_join

from media_service.models import Image, ImageResource

register = template.Library()


# make sure the URL prefix has img variant
def _render_known_variant_image(
    src: str,
    alt: str,
    class_name: str,
    img_class: str,
    loading: str,
    sizes: str,
    fetch_priority: str,
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

        return format_html(
            '<picture class="{}"><source srcset="{}/{}.avif" type="image/avif">'
            '<source srcset="{}/{}.webp" type="image/webp"><img src="{}" '
            'alt="{}" class="{}" loading="{}" decoding="async" sizes="{}" '
            'fetchpriority="{}"></picture>',
            class_name,
            avif_prefix.rstrip("/"),
            stem,
            webp_prefix.rstrip("/"),
            stem,
            src,
            alt,
            img_class,
            loading,
            sizes,
            fetch_priority,
        )

    return None


@register.simple_tag
def render_image(
    image_input: Image | ImageResource | str | None,
    alt: str = "",
    class_name: str = "",
    img_class: str = "",
    loading: str = "lazy",
    sizes: str = "100vw",
    fetch_priority: str = "auto",
):
    if not image_input:
        return ""

    # find image resource
    resource: ImageResource | None = None
    alt_text = alt
    if isinstance(image_input, Image):
        resource = image_input.resource
        alt_text = alt or image_input.alt_text
    elif isinstance(image_input, ImageResource):
        resource = image_input
    elif isinstance(image_input, str):
        match = re.search(r"([a-f0-9]{64})", image_input)
        if match:
            checksum = match.group(1)
            resource = ImageResource.objects.filter(checksum=checksum).first()

    # if not found
    if not resource:
        src = image_input if isinstance(image_input, str) else ""
        if not src:
            return ""
        # try match the prefix
        # it's safe to generate variant url if matched
        if picture := _render_known_variant_image(
            src,
            alt,
            class_name,
            img_class,
            loading,
            sizes,
            fetch_priority,
        ):
            return picture
        return format_html(
            '<img src="{}" alt="{}" class="{}" loading="{}" fetchpriority="{}">',
            src,
            alt,
            img_class or class_name,
            loading,
            fetch_priority,
        )

    # picture source
    sources = []
    responsive_srcsets = resource.responsive_srcsets()

    # avif source
    avif_srcset = responsive_srcsets.get("avif")
    if avif_srcset:
        sources.append(
            format_html(
                '<source srcset="{}" sizes="{}" type="image/avif">',
                avif_srcset,
                sizes,
            )
        )
    elif resource.avif_file:
        sources.append(
            format_html('<source srcset="{}" type="image/avif">', resource.avif_url)
        )

    # webp source
    webp_srcset = responsive_srcsets.get("webp")
    if webp_srcset:
        sources.append(
            format_html(
                '<source srcset="{}" sizes="{}" type="image/webp">',
                webp_srcset,
                sizes,
            )
        )
    elif resource.webp_file:
        sources.append(
            format_html('<source srcset="{}" type="image/webp">', resource.webp_url)
        )

    # build styles
    style = ""
    if resource.placeholder:
        style = (
            f"background-image: url({resource.placeholder}); background-size: cover;"
        )

    dimensions = ""
    if resource.width and resource.height:
        dimensions = format_html(
            ' width="{}" height="{}"', resource.width, resource.height
        )

    # render <picture>
    source_html = format_html_join("", "{}", ((source,) for source in sources))
    return format_html(
        '<picture class="{}">{}<img src="{}" alt="{}" style="{}" class="{}" '
        'loading="{}" decoding="async" sizes="{}" fetchpriority="{}"{}></picture>',
        class_name,
        source_html,
        resource.file.url,
        alt_text,
        style,
        img_class,
        loading,
        sizes,
        fetch_priority,
        dimensions,
    )


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
            resource = ImageResource.objects.filter(checksum=checksum).first()
            if resource:
                return resource.thumbnail_url or resource.file.url
        return image_input
    return ""
