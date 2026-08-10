from django.test import SimpleTestCase

from api.markdown import Markdown


class MarkdownFrontmatterTests(SimpleTestCase):
    def test_yaml_frontmatter_uses_json_like_values(self):
        frontmatter, html = Markdown().render_with_frontmatter(
            "---\n"
            "title: Test\n"
            "published: 2025-07-23\n"
            "updated: 2025-07-23 14:34:00+08:00\n"
            "nested:\n"
            "  values: [1, true, null]\n"
            "---\n\n"
            "# body"
        )

        self.assertEqual(
            frontmatter,
            {
                "title": "Test",
                "published": "2025-07-23",
                "updated": "2025-07-23T14:34:00+08:00",
                "nested": {"values": [1, True, None]},
            },
        )
        self.assertEqual(html, '<h1 id="body">body</h1>\n')

    def test_toml_frontmatter_uses_json_like_values(self):
        frontmatter = Markdown().extract_frontmatter(
            "+++\n"
            'title = "Test"\n'
            "published = 2025-07-23\n"
            "updated = 2025-07-23T14:34:00+08:00\n"
            "time = 14:34:00\n"
            "[nested]\n"
            'values = [1, true, false, "value"]\n'
            "+++\n\n"
            "# body"
        )

        self.assertEqual(
            frontmatter,
            {
                "title": "Test",
                "published": "2025-07-23",
                "updated": "2025-07-23T14:34:00+08:00",
                "time": "14:34:00",
                "nested": {"values": [1, True, False, "value"]},
            },
        )

    def test_frontmatter_rejects_invalid_values(self):
        cases = {
            "non_mapping": "---\n- invalid\n---",
            "non_string_key": "---\n1: invalid\n---",
            "non_finite_float": "+++\nvalue = nan\n+++",
            "invalid_yaml": "---\n[unclosed\n---",
            "invalid_toml": "+++\ntitle =\n+++",
        }

        markdown = Markdown()
        for name, source in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    markdown.extract_frontmatter(source)
