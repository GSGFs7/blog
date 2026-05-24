import re
from collections.abc import Callable
from urllib.parse import urlparse

__all__ = [
    "post_process_html",
]

HtmlPostProcessor = Callable[[str], str]


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
        img_tag = match.group(1)
        alt_match = re.search(r'alt="([^"]*)"', img_tag)
        title_match = re.search(r'title="([^"]*)"', img_tag)

        alt = alt_match.group(1) if alt_match else ""
        title = title_match.group(1) if title_match else ""
        caption = title if title else alt

        return (
            f'<span class="md-img-container" data-caption="{caption}">{img_tag}</span>'
        )

    return re.sub(r"(<img[^>]*>)", wrap_img, html)


def add_pre_language_attributes(html: str) -> str:
    return re.sub(
        r'(<pre)([^>]*>)\s*<code class="([^"]*\blanguage-(\w+))"',
        r'\1 data-language="\4"\2<code class="\3"',
        html,
    )


POST_PROCESSORS: tuple[HtmlPostProcessor, ...] = (
    inject_link_domains,
    wrap_images,
    add_pre_language_attributes,
)


def post_process_html(html: str) -> str:
    for processor in POST_PROCESSORS:
        html = processor(html)
    return html
