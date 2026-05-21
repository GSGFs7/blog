import re

from django import template
from django.utils.safestring import mark_safe

from media_service.models import Image, ImageResource

register = template.Library()


@register.simple_tag
def render_image(
    image_input: Image | ImageResource | str | None,
    alt: str = "",
    class_name: str = "",
    img_class: str = "",
    loading: str = "lazy",
):
    if not image_input:
        return ""

    # find image resource
    resource: ImageResource | None = None
    alt_text = ""
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
        return mark_safe(
            f"<img"
            f' src="{src}"'
            f' alt="{alt}"'
            f' class="{img_class or class_name}"'
            f' loading="{loading}"'
            f">"
        )

    # picture source
    sources = []
    if resource.avif_file:
        sources.append(f'<source srcset="{resource.avif_url}" type="image/avif">')
    if resource.webp_file:
        sources.append(f'<source srcset="{resource.webp_url}" type="image/webp">')

    # build styles
    style = ""
    if resource.placeholder:
        style = (
            f"background-image: url(data:image/svg+xml;base64,{resource.placeholder});"
            f"background-size: cover;"
        )

    # render <picture>
    picture_html = f'<picture class="{class_name}">'
    for s in sources:
        picture_html += s
    picture_html += (
        f"<img"
        f' src="{resource.file.url}"'
        f' alt="{alt_text}"'
        f' style="{style}"'
        f' class="{img_class}"'
        f' loading="{loading}"'
        f' decoding="async"'
        f" {f'width="{resource.width}"' if resource else ''}"
        f" {f'height="{resource.height}"' if resource.height else ''}"
        f">"
    )
    picture_html += "</picture>"

    return mark_safe(picture_html)


@register.filter
def to_thumbnail(image_input):
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
