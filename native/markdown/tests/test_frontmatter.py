import unittest

from markdown_it_rs_py import MarkdownIt

YAML_FRONTMATTER_INPUT = "---\ntitle: Test\n---\n# heading"
TOML_FRONTMATTER_INPUT = "+++\ntitle = 'Test'\n+++\n# heading"
UNCLOSED_FRONTMATTER_INPUT = "---\ntitle: Test\n# heading"


class FrontmatterTests(unittest.TestCase):
    def test_yaml_frontmatter(self):
        plan = MarkdownIt().prepare(YAML_FRONTMATTER_INPUT, include_frontmatter=True)
        html = plan.finish()

        self.assertIn('<h1 id="heading">heading</h1>', html)
        self.assertNotIn("title", html)
        self.assertEqual(plan.frontmatter, {"title": "Test"})

    def test_toml_frontmatter(self):
        plan = MarkdownIt().prepare(TOML_FRONTMATTER_INPUT, include_frontmatter=True)

        self.assertEqual(plan.frontmatter, {"title": "Test"})

    def test_invalid_frontmatter_uses_stable_value_errors(self):
        cases = {
            "invalid YAML frontmatter": "---\n[unclosed\n---",
            "invalid TOML frontmatter": "+++\ntitle =\n+++",
            "frontmatter must be a mapping": "---\n- invalid\n---",
            "frontmatter mapping keys must be strings": "---\n1: invalid\n---",
            "frontmatter floats must be finite": "+++\nvalue = nan\n+++",
        }

        for message, source in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    MarkdownIt().prepare(source, include_frontmatter=True)

    def test_unclosed_frontmatter(self):
        self.assertEqual(
            MarkdownIt().prepare(UNCLOSED_FRONTMATTER_INPUT).finish(),
            '<hr>\n<p>title: Test</p>\n<h1 id="heading">heading</h1>\n',
        )


if __name__ == "__main__":
    unittest.main()
