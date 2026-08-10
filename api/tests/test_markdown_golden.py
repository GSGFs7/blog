import json
from pathlib import Path

from django.test import SimpleTestCase

from api.markdown import Markdown

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "markdown"
FIXTURE_NAMES = {
    "commonmark",
    "footnote",
    "heading_anchors",
    "math",
    "raw_html",
    "syntax_highlighting",
    "table",
    "tasklist",
}


class MarkdownGoldenFixtureTests(SimpleTestCase):
    def test_legacy_renderer_matches_golden_fixtures(self):
        fixture_paths = sorted(FIXTURE_DIRECTORY.glob("*.json"))

        self.assertEqual({path.stem for path in fixture_paths}, FIXTURE_NAMES)

        markdown = Markdown()
        for fixture_path in fixture_paths:
            with self.subTest(fixture=fixture_path.stem):
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                self.assertEqual(markdown.render(fixture["markdown"]), fixture["html"])
