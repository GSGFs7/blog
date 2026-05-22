import json
import re
import tomllib
from typing import Any
from urllib.parse import urlparse

import yaml
from markdown_it_rs_py import FrontMatter, MarkdownIt


class Markdown:
    # rust render engine instance cache (it useless i think)
    _mds: dict[tuple, MarkdownIt] = {}

    def __init__(
        self,
        *,
        html: bool = False,
        linkify: bool = True,
        math: bool = True,
        frontmatter: bool = True,
        footnote: bool = True,
        tasklist: bool = True,
        typographer: bool = False,
        sourcepos: bool = False,
        heading_anchors: bool = False,
        syntax_highlighting: bool = True,
        syntax_theme: str | None = None,
        syntax_classed: bool = True,
        directives: bool = False,
    ):
        # tuple native support hash
        idx_key = (
            html,
            linkify,
            math,
            frontmatter,
            footnote,
            tasklist,
            typographer,
            sourcepos,
            heading_anchors,
            syntax_highlighting,
            syntax_theme,
            syntax_classed,
            directives,
        )

        if md := self._mds.get(idx_key):
            self.md = md
        else:
            self.md = MarkdownIt(
                html=html,
                linkify=linkify,
                math=math,
                frontmatter=frontmatter,
                footnote=footnote,
                tasklist=tasklist,
                typographer=typographer,
                sourcepos=sourcepos,
                heading_anchors=heading_anchors,
                syntax_highlighting=syntax_highlighting,
                syntax_theme=syntax_theme,
                syntax_classed=syntax_classed,
                directives=directives,
            )
            self._mds[idx_key] = self.md

    @staticmethod
    def _parse_frontmatter(frontmatter: FrontMatter) -> dict[str, Any]:
        if frontmatter.kind == "yaml":
            return yaml.safe_load(frontmatter.raw)
        elif frontmatter.kind == "toml":
            return tomllib.loads(frontmatter.raw)
        else:
            return {}

    @staticmethod
    def _post_process(result: str) -> str:
        """Post-process rendered HTML"""

        def inject_domain(match: re.Match) -> str:
            full_tag = match.group(0)
            href = match.group(1)
            try:
                parsed = urlparse(href)
                # Only add for http/https and if it has a netloc (domain)
                if parsed.scheme in ("http", "https") and parsed.netloc:
                    domain = parsed.netloc
                    if "data-domain=" not in full_tag:
                        # Extract the tag content to wrap it in a span
                        # This regex finds the closing </a> and captures content
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

        def wrap_img(match: re.Match) -> str:
            img_tag = match.group(1)
            # Extract alt and title attributes
            alt_match = re.search(r'alt="([^"]*)"', img_tag)
            title_match = re.search(r'title="([^"]*)"', img_tag)

            alt = alt_match.group(1) if alt_match else ""
            title = title_match.group(1) if title_match else ""

            # Prioritize title for display, fallback to alt
            caption = title if title else alt

            return (
                f'<span class="md-img-container" data-caption="{caption}">'
                f"{img_tag}"
                f"</span>"
            )

        # Inject data-domain into <a> tags
        result = re.sub(
            r'<a\s+[^>]*href="([^"]*)"[^>]*>.*?</a>',
            inject_domain,
            result,
            flags=re.DOTALL,
        )

        # Wrap <img> tags in a span for centering (span is valid inside <p>)
        result = re.sub(r"(<img[^>]*>)", wrap_img, result)

        # Extract language from <code class="...language-xxx..."> and put it on <pre>
        result = re.sub(
            r'(<pre)([^>]*>)\s*<code class="([^"]*\blanguage-(\w+))"',
            r'\1 data-language="\4"\2<code class="\3"',
            result,
        )

        return result

    def render(self, markdown: str) -> str:
        """markdown -> HTML"""
        result = self.md.render(markdown)
        return self._post_process(result)

    def frontmatter(self, markdown: str) -> dict[str, Any]:
        """extract frontmatter"""
        frontmatter = self.md.parse_frontmatter(markdown)
        if frontmatter:
            return self._parse_frontmatter(frontmatter)
        return {}

    def render_with_frontmatter(self, markdown: str) -> tuple[dict[str, Any], str]:
        """markdown -> frontmatter + HTML"""
        res = self.md.render_with_frontmatter(markdown)
        html = self._post_process(res.html)
        if frontmatter := res.frontmatter:
            return self._parse_frontmatter(frontmatter), html
        return {}, html


if __name__ == "__main__":
    test_md = """---
title: Test Markdown
description: This is a test markdown file.
tags: [test, markdown]
datetime: 2025-07-23 14:34:00
math: true
keywords: 
  - test
  - markdown
---

# heading

content

$$
E = mc^2
$$

<a href="https://a.com">inline html</a>

```python
print("你好")
```
"""

    fm, html = Markdown().render_with_frontmatter(test_md)
    print(json.dumps(fm, default=str))
    print(html)
