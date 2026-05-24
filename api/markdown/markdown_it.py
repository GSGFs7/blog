import json
from typing import Any

from markdown_it_rs_py import MarkdownIt

from .post_processors import post_process_html
from .utils import extract_toc, parse_frontmatter


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
        heading_anchors: bool = True,
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

    def render(self, markdown: str) -> str:
        """markdown -> HTML"""
        result = self.md.render(markdown)
        return post_process_html(result)

    def render_with_toc(self, markdown: str) -> tuple[str, list[dict[str, Any]]]:
        """markdown -> (HTML, TOC)"""
        ast = self.md.parse(markdown)
        toc = extract_toc(ast.root.children)
        html = post_process_html(ast.root.render())
        return html, toc

    def render_with_frontmatter(self, markdown: str) -> tuple[dict[str, Any], str]:
        """markdown -> frontmatter + HTML"""
        res = self.md.render_with_frontmatter(markdown)
        html = post_process_html(res.html)
        if frontmatter := res.frontmatter:
            return parse_frontmatter(frontmatter), html
        return {}, html

    def extract_frontmatter(self, markdown: str) -> dict[str, Any]:
        """extract frontmatter"""
        frontmatter = self.md.parse_frontmatter(markdown)
        if frontmatter:
            return parse_frontmatter(frontmatter)
        return {}


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
