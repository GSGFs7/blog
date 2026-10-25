import unittest

from markdown_it_rs_py import MarkdownIt


class HeadingAnchorTests(unittest.TestCase):
    def test_heading_anchors(self):
        html = MarkdownIt().prepare("## Ciallo ～(∠・ω< )⌒★!").finish()

        self.assertIn('<h2 id="ciallo', html)
        self.assertIn("Ciallo ～(∠・ω&lt; )⌒★!", html)

    def test_toc_preserves_inline_text_semantics(self):
        plan = MarkdownIt().prepare(
            "# 中文 *强调* &amp; `code` ![alt](image.png) $x$ <b>raw</b>",
            include_toc=True,
        )

        self.assertEqual(
            plan.toc,
            [
                {
                    "level": 1,
                    "slug": "中文-强调-code-alt-raw",
                    "text": "中文 强调 & code alt  raw",
                }
            ],
        )

    def test_toc_preserves_setext_softbreaks(self):
        plan = MarkdownIt().prepare(
            "第一行\n第二行 *末尾* &amp;\n====", include_toc=True
        )

        self.assertEqual(
            plan.toc,
            [
                {
                    "level": 1,
                    "slug": "第一行-第二行-末尾",
                    "text": "第一行\n第二行 末尾 &",
                }
            ],
        )

    def test_toc_only_includes_top_level_headings(self):
        plan = MarkdownIt().prepare(
            "# Root\n\n> ## Quote\n\n- ### List\n\n"
            ":::spoiler\n## Hidden\n:::\n\n## Visible",
            include_toc=True,
        )

        self.assertEqual(
            plan.toc,
            [
                {"level": 1, "slug": "root", "text": "Root"},
                {"level": 2, "slug": "visible", "text": "Visible"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
