from django.test import SimpleTestCase
from markdown_it_rs_py import MarkdownIt

from api.markdown import Markdown


class MarkdownTextTests(SimpleTestCase):
    def test_native_binding_extracts_text(self):
        self.assertEqual(
            MarkdownIt().strip_markdown(
                "---\ntitle: Test\n---\n"
                "# 标题\n\n[**正文**](https://example.com) `a < b`\n\n"
                "![图片](/image.png)\n\n```python\nprint('code')\n```\n\n"
                "$x + y$\n\n<p>HTML &amp; 文本</p>"
            ),
            "标题\n正文 a < b\nHTML & 文本",
        )

    def test_wrapper_can_strip_and_render_repeatedly(self):
        markdown = Markdown()
        for _ in range(2):
            self.assertEqual(markdown.strip_markdown("**正文**"), "正文")
            self.assertEqual(
                markdown.render("**正文**"), "<p><strong>正文</strong></p>\n"
            )

    def test_literal_markup_survives_html_extraction(self):
        self.assertEqual(
            Markdown().strip_markdown(
                "`<script>literal</script>` &lt;b&gt; "
                "<script>hidden</script><!-- hidden -->"
            ),
            "<script>literal</script> <b>",
        )

    def test_html_attributes_and_block_boundaries_are_respected(self):
        markdown = Markdown()
        self.assertEqual(
            markdown.strip_markdown('正文 <span title="<script>">可见</span> 后文'),
            "正文 可见 后文",
        )
        self.assertEqual(
            markdown.strip_markdown("前文 <script>\n\n</script>\n\n后文"),
            "前文\n后文",
        )
        self.assertEqual(
            markdown.strip_markdown("<table><tr><td>甲</td><td>乙</td></tr></table>"),
            "甲\t乙",
        )
