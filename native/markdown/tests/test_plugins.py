import unittest

from markdown_it_rs_py import MarkdownIt


class PluginTests(unittest.TestCase):
    def test_mark_plugin(self):
        md = MarkdownIt()
        self.assertEqual(
            md.prepare("==highlighted==").finish(),
            "<p><mark>highlighted</mark></p>\n",
        )

    def test_tasklist_plugin(self):
        html = MarkdownIt().prepare("- [x] done").finish()

        self.assertIn('class="contains-task-list"', html)
        self.assertIn('class="task-list-item"', html)
        self.assertIn('type="checkbox" checked=""', html)
        self.assertNotIn("[x]", html)

    def test_footnote_plugin(self):
        html = (
            MarkdownIt()
            .prepare("Here is a footnote.[^a]\n\n[^a]: Footnote text.")
            .finish()
        )

        self.assertIn('class="footnote-ref"', html)
        self.assertIn('href="#fn1"', html)
        self.assertIn('id="fn1"', html)
        self.assertIn("Footnote text.", html)
        self.assertNotIn("[^a]:", html)

    def test_directives_plugin(self):
        md = MarkdownIt()

        self.assertEqual(
            md.prepare('hello :name{a="b"} world').finish(),
            '<p>hello <span class="directive name"></span> world</p>\n',
        )
        self.assertEqual(
            md.prepare('::name{cia="llo"}').finish(),
            '<div class="directive name"></div>\n',
        )
        self.assertEqual(
            md.prepare(':::name{cia="llo"}\nworld\n:::').finish(),
            '<div class="directive name">\n<p>world</p>\n</div>\n',
        )

    def test_directive_attributes_are_sanitized(self):
        self.assertEqual(
            MarkdownIt().prepare(':name{onclick="alert(1)"}').finish(),
            '<p><span class="directive name"></span></p>\n',
        )


if __name__ == "__main__":
    unittest.main()
