import re
from collections.abc import Callable
from urllib.parse import urlparse

from django.utils.html import escape

from media_service.models import ImageResource

__all__ = ("post_process_html",)


HtmlPostProcessor = Callable[[str], str]


IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)>", re.IGNORECASE)
ATTR_RE = re.compile(r'(?P<name>[\w:-]+)="(?P<value>[^"]*)"')
CHECKSUM_RE = re.compile(r"([a-f0-9]{64})")


def inject_link_domains(html: str) -> str:
    def inject_domain(match: re.Match[str]) -> str:
        full_tag = match.group(0)
        href = match.group(1)
        try:
            parsed = urlparse(href)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                domain = parsed.netloc
                if "data-domain=" not in full_tag:
                    tag_pattern = re.compile(
                        r'(<a\s+[^>]*href="[^"]*"[^>]*>)(.*?)(</a>)', re.DOTALL
                    )
                    tag_match = tag_pattern.search(full_tag)
                    if tag_match:
                        start_tag, content, end_tag = tag_match.groups()
                        return (
                            f'{start_tag}<span data-domain="{domain}">'
                            f"{content}"
                            f"</span>{end_tag}"
                        )
        except Exception:
            pass
        return full_tag

    return re.sub(
        r'<a\s+[^>]*href="([^"]*)"[^>]*>.*?</a>',
        inject_domain,
        html,
        flags=re.DOTALL,
    )


def wrap_images(html: str) -> str:
    def wrap_img(match: re.Match[str]) -> str:
        media_tag = match.group(1)
        img_match = re.search(r"<img\b[^>]*>", media_tag)
        img_tag = img_match.group(0) if img_match else media_tag

        alt_match = re.search(r'alt="([^"]*)"', img_tag)
        title_match = re.search(r'title="([^"]*)"', img_tag)

        alt = alt_match.group(1) if alt_match else ""
        title = title_match.group(1) if title_match else ""
        caption = title if title else alt

        return (
            f'<span class="md-img-container" data-caption="{escape(caption)}">'
            f"{media_tag}"
            f"</span>"
        )

    return re.sub(r"(<picture\b.*?</picture>|<img\b[^>]*>)", wrap_img, html)


def add_pre_language_attributes(html: str) -> str:
    return re.sub(
        r'(<pre)([^>]*>)\s*<code class="([^"]*\blanguage-(\w+))"',
        r'\1 data-language="\4"\2<code class="\3"',
        html,
    )


def _parse_attrs(raw_attrs: str) -> dict[str, str]:
    return {m.group("name"): m.group("value") for m in ATTR_RE.finditer(raw_attrs)}


def _render_attrs(attrs: dict[str, str]) -> str:
    return " ".join(f'{name}="{escape(value)}"' for name, value in attrs.items())


def optimize_images(html: str) -> str:
    matches = list(IMG_RE.finditer(html))
    if not matches:
        return html

    checksum_by_match = {}
    for match in matches:
        attrs = _parse_attrs(match.group("attrs"))
        src = attrs.get("src", "")
        checksum_match = CHECKSUM_RE.search(src)
        if checksum_match:
            checksum_by_match[match] = checksum_match.group(1)

    if not checksum_by_match:
        return html

    resources = ImageResource.objects.in_bulk(
        set(checksum_by_match.values()), field_name="checksum"
    )

    parts = []
    last_end = 0
    for match in matches:
        parts.append(html[last_end : match.start()])
        checksum = checksum_by_match.get(match)
        resource = resources.get(checksum) if checksum else None
        if not resource:
            parts.append(match.group(0))
            last_end = match.end()
            continue

        attrs = _parse_attrs(match.group("attrs"))
        attrs["src"] = resource.file.url
        attrs.setdefault("loading", "lazy")
        attrs.setdefault("decoding", "async")
        if resource.width:
            attrs.setdefault("width", str(resource.width))
        if resource.height:
            attrs.setdefault("height", str(resource.height))
        if resource.placeholder:
            attrs["style"] = (
                attrs.get("style", "")
                + f" background-image: url({resource.placeholder});"
                " background-size: cover;"
            ).strip()

        source = []
        if resource.avif_file:
            source.append(f'<source srcset="{resource.avif_url}" type="image/avif">')
        if resource.webp_url:
            source.append(f'<source srcset="{resource.webp_url}" type="image/webp">')

        parts.append(
            f"<picture>{''.join(source)}<img {_render_attrs(attrs)}></picture>"
        )
        last_end = match.end()

    parts.append(html[last_end:])
    return "".join(parts)


POST_PROCESSORS: tuple[HtmlPostProcessor, ...] = (
    inject_link_domains,
    optimize_images,
    wrap_images,
    add_pre_language_attributes,
)


def post_process_html(html: str) -> str:
    for processor in POST_PROCESSORS:
        html = processor(html)
    return html
