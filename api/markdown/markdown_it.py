from typing import Any

from markdown_it_rs_py import MarkdownIt

from .post_processors import post_process_html
from .utils import parse_frontmatter


class Markdown:
    md = MarkdownIt()

    def render(self, markdown: str) -> str:
        """markdown -> HTML"""
        plan = self.md.prepare(markdown)
        return post_process_html(plan.finish())

    def render_with_toc(self, markdown: str) -> tuple[str, list[dict[str, Any]]]:
        """markdown -> (HTML, TOC)"""
        plan = self.md.prepare(markdown, include_toc=True)
        html = post_process_html(plan.finish())
        return html, plan.toc

    def render_with_frontmatter(self, markdown: str) -> tuple[dict[str, Any], str]:
        """markdown -> frontmatter + HTML"""
        plan = self.md.prepare(markdown, include_frontmatter=True)
        html = post_process_html(plan.finish())
        if frontmatter := plan.frontmatter:
            return parse_frontmatter(frontmatter), html
        return {}, html

    def extract_frontmatter(self, markdown: str) -> dict[str, Any]:
        """extract frontmatter"""
        plan = self.md.prepare(markdown, include_frontmatter=True)
        if fm := plan.frontmatter:
            return parse_frontmatter(fm)
        return {}
