from typing import Any

from markdown_it_rs_py import MarkdownIt

from .images import _image_picture_source_prefixes, _resolve_images


class Markdown:
    md = MarkdownIt()

    def render(self, markdown: str) -> str:
        """markdown -> HTML"""
        plan = self.md.prepare(
            markdown,
            image_picture_source_prefixes=_image_picture_source_prefixes(),
        )
        return plan.finish(_resolve_images(plan.image_checksums))

    def render_with_toc(self, markdown: str) -> tuple[str, list[dict[str, Any]]]:
        """markdown -> (HTML, TOC)"""
        plan = self.md.prepare(
            markdown,
            include_toc=True,
            image_picture_source_prefixes=_image_picture_source_prefixes(),
        )
        html = plan.finish(_resolve_images(plan.image_checksums))
        return html, plan.toc

    def render_with_frontmatter(self, markdown: str) -> tuple[dict[str, Any], str]:
        """markdown -> frontmatter + HTML"""
        plan = self.md.prepare(
            markdown,
            include_frontmatter=True,
            image_picture_source_prefixes=_image_picture_source_prefixes(),
        )
        html = plan.finish(_resolve_images(plan.image_checksums))
        return plan.frontmatter or {}, html

    def extract_frontmatter(self, markdown: str) -> dict[str, Any]:
        """extract frontmatter"""
        plan = self.md.prepare(
            markdown,
            include_frontmatter=True,
            image_picture_source_prefixes=_image_picture_source_prefixes(),
        )
        return plan.frontmatter or {}
