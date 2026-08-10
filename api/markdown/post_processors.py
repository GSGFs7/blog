import json
import re
from collections.abc import Callable
from copy import deepcopy
from html import unescape
from urllib.parse import urlparse, urlsplit

from django.utils.html import escape
from nh3 import nh3

from media_service.models import ImageResource

__all__ = ("post_process_html",)


HtmlPostProcessor = Callable[[str], str]


IMG_RE = re.compile(r"<img\b(?P<attrs>[^>]*)>", re.IGNORECASE)
ATTR_RE = re.compile(r'(?P<name>[\w:-]+)="(?P<value>[^"]*)"')
CHECKSUM_RE = re.compile(r"^[a-f0-9]{64}$")
CHECKSUM_PATH_RE = re.compile(r"(?:^|/)([a-f0-9]{64})\.[A-Za-z0-9]+$")

DIRECTIVE_TAG_RE = re.compile(r"<(?P<tag>span|div)\b(?P<attrs>[^>]*)>", re.IGNORECASE)
MARKDOWN_DIRECTIVE_ISLANDS = {
    "counter": "Counter",
    "python-wasm": "PythonREPL",
    "python-repl": "PythonREPL",
    "chart": "Chart",
    "charts": "Chart",
}
MARKDOWN_DIRECTIVE_PROPS = {
    "Counter": {"initial"},
    "PythonREPL": set(),
    "Chart": {"formula", "x-min", "x-max", "y-min", "y-max"},
}

HTML_TAGS = nh3.ALLOWED_TAGS | {
    "annotation",
    "maction",
    "math",
    "menclose",
    "merror",
    "mfrac",
    "mi",
    "mmultiscripts",
    "mn",
    "mo",
    "mover",
    "mpadded",
    "mphantom",
    "mprescripts",
    "mroot",
    "mrow",
    "ms",
    "mspace",
    "msqrt",
    "mstyle",
    "msub",
    "msubsup",
    "msup",
    "mtable",
    "mtd",
    "mtext",
    "mtr",
    "munder",
    "munderover",
    "none",
    "picture",
    "section",
    "semantics",
    "source",
    "input",
}

HTML_ATTRIBUTES = deepcopy(nh3.ALLOWED_ATTRIBUTES)
HTML_ATTRIBUTES["*"] = {"aria-hidden", "class", "id", "title"}
HTML_ATTRIBUTES.setdefault("a", set()).update({"href", "target"})
HTML_ATTRIBUTES.setdefault("annotation", set()).add("encoding")
HTML_ATTRIBUTES.setdefault("code", set()).add("class")
HTML_ATTRIBUTES.setdefault("img", set()).update(
    {"decoding", "loading", "style", "title"}
)
HTML_ATTRIBUTES.setdefault("input", set()).update({"checked", "disabled"})
HTML_ATTRIBUTES.setdefault("math", set()).update({"display", "xmlns"})
HTML_ATTRIBUTES.setdefault("pre", set()).add("data-language")
HTML_ATTRIBUTES.setdefault("source", set()).update({"media", "sizes", "srcset", "type"})
HTML_ATTRIBUTES.setdefault("span", set()).update(
    {"data-caption", "data-domain", "style", "data-solid-island", "data-props"}
)
HTML_ATTRIBUTES.setdefault("div", set()).update(
    {
        "data-solid-island",
        "data-props",
        "aria-label",
        # terminal
        "data-shell",
        "style",
    }
)
HTML_ATTRIBUTES.setdefault("td", set()).update({"colspan", "rowspan"})
HTML_ATTRIBUTES.setdefault("th", set()).update({"colspan", "rowspan"})
HTML_ATTRIBUTES.setdefault("time", set()).add("datetime")

HTML_STYLE_PROPERTIES = {
    "background-image",
    "background-size",
    "height",
    "left",
    "margin-left",
    "margin-right",
    "min-width",
    "right",
    "top",
    "vertical-align",
    "width",
    # terminal
    "--terminal-prompt",
}

HTML_URL_SCHEMES = {"http", "https", "mailto", "tel"}

DEFAULT_PROMPTS = {
    "bash": "$",
    "fish": ">",
    "powershell": "PS>",
    "pwsh": "PS>",
    "sh": "$",
    "zsh": "$",
    "python": ">>>",
}
TERMINAL_SHELL_RE = re.compile(r"^[a-z0-9][a-z0-9_+-]{0,31}$")
TERMINAL_PROMPT_RE = re.compile(r"^[\w@:/~.+#>$%?❯-]{1,16}$")
# '❯' is the default prompt in my terminal
TERMINAL_PROMPT_STYLE_RE = re.compile(r'^--terminal-prompt:"[\w@:/~.+#>$%?❯-]{1,16} "$')


def inject_link_domains(html: str) -> str:
    def inject_domain(match: re.Match[str]) -> str:
        full_tag = match.group(0)
        href = match.group(1)
        try:
            parsed = urlparse(href)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                domain = parsed.hostname
                if not domain:
                    return full_tag
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
        caption = unescape(title if title else alt)

        return (
            f'<span class="md-img-container" data-caption="{escape(caption)}">'
            f"{media_tag}"
            f"</span>"
        )

    return re.sub(r"(<picture\b.*?</picture>|<img\b[^>]*>)", wrap_img, html)


def add_pre_language_attributes(html: str) -> str:
    return re.sub(
        r'(<pre)([^>]*>)\s*<code class="([^"]*\blanguage-([^\s"]+))"',
        r'\1 data-language="\4"\2<code class="\3"',
        html,
    )


def _parse_attrs(raw_attrs: str) -> dict[str, str]:
    return {m.group("name"): m.group("value") for m in ATTR_RE.finditer(raw_attrs)}


def _render_attrs(attrs: dict[str, str]) -> str:
    return " ".join(f'{name}="{escape(value)}"' for name, value in attrs.items())


def _extract_image_checksum(src: str) -> str | None:
    if CHECKSUM_RE.fullmatch(src):
        return src

    match = CHECKSUM_PATH_RE.search(urlsplit(src).path)
    return match.group(1) if match else None


def _matches_image_resource(src: str, checksum: str, resource: ImageResource) -> bool:
    return src == checksum or src == resource.file.url


def optimize_images(html: str) -> str:
    matches = list(IMG_RE.finditer(html))
    if not matches:
        return html

    checksum_by_match = {}
    for match in matches:
        attrs = _parse_attrs(match.group("attrs"))
        src = attrs.get("src", "")
        if checksum := _extract_image_checksum(src):
            checksum_by_match[match] = checksum

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
        attrs = _parse_attrs(match.group("attrs"))
        src = attrs.get("src", "")
        if not resource or not _matches_image_resource(src, checksum, resource):
            parts.append(match.group(0))
            last_end = match.end()
            continue

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


def mount_solid_directives(html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        attrs = _parse_attrs(match.group("attrs"))
        classes = attrs.get("class", "").split()
        if "directive" not in classes:
            return match.group(0)

        directive_name = next((name for name in classes if name != "directive"), "")
        component_name = MARKDOWN_DIRECTIVE_ISLANDS.get(directive_name)
        if not component_name:
            return match.group(0)

        props = {
            key: value
            for key, value in attrs.items()
            if key in MARKDOWN_DIRECTIVE_PROPS[component_name]
        }
        props_json = escape(json.dumps(props, separators=(",", ":")))
        tag = match.group("tag").lower()
        return (
            f'<{tag} data-solid-island="{escape(component_name)}" '
            f'data-props="{props_json}">'
        )

    return DIRECTIVE_TAG_RE.sub(replace, html)


def render_terminal_directives(html: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group("tag").lower() != "div":
            return match.group(0)

        # find the directive node
        attrs = _parse_attrs(match.group("attrs"))
        classes = set(attrs.get("class", "").split())
        if not {"directive", "terminal"}.issubset(classes):
            return match.group(0)

        # :::terminal{shell="bash"}
        shell = unescape(attrs.get("shell", "bash")).strip().lower()
        if not TERMINAL_SHELL_RE.fullmatch(shell):
            shell = "bash"

        # :::terminal{prompt="$"}
        default_prompt = DEFAULT_PROMPTS.get(shell, "$")
        prompt = unescape(attrs.get("prompt", default_prompt)).strip()
        if not TERMINAL_PROMPT_RE.fullmatch(prompt):
            prompt = default_prompt

        # :::terminal{title="Terminal"}
        title = unescape(attrs.get("title", "Terminal"))
        title = " ".join(title.splitlines()).strip()[:100] or "Terminal"
        wrapper_attrs = _render_attrs(
            {
                "class": "terminal",
                "data-shell": shell,
                "role": "group",
                "aria-label": title,
                "style": f'--terminal-prompt:"{prompt} "',
            }
        )
        return (
            f"<div {wrapper_attrs}>"
            f'<div class="terminal-title" aria-hidden="true">{escape(title)}</div>'
        )

    return DIRECTIVE_TAG_RE.sub(replace, html)


def filter_html_attribute(tag: str, attr: str, value: str) -> str | None:
    if tag == "div" and attr == "style":
        if not TERMINAL_PROMPT_STYLE_RE.fullmatch(value):
            return None
    return value


def sanitize_html(html: str) -> str:
    return nh3.clean(
        html,
        tags=HTML_TAGS,
        clean_content_tags={"script", "style"},
        attributes=HTML_ATTRIBUTES,
        attribute_filter=filter_html_attribute,
        tag_attribute_values={
            "input": {"type": {"checkbox"}},
            # terminal
            "div": {"role": {"group"}},
        },
        set_tag_attribute_values={"input": {"disabled": ""}},
        filter_style_properties=HTML_STYLE_PROPERTIES,
        url_schemes=HTML_URL_SCHEMES,
    )


POST_PROCESSORS: tuple[HtmlPostProcessor, ...] = (
    inject_link_domains,
    optimize_images,
    wrap_images,
    add_pre_language_attributes,
    render_terminal_directives,
    mount_solid_directives,
    sanitize_html,
)


def post_process_html(html: str) -> str:
    for processor in POST_PROCESSORS:
        html = processor(html)
    return html
