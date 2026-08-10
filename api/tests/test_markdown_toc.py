import json
from pathlib import Path

from django.test import SimpleTestCase

from api.markdown import Markdown

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "markdown" / "toc"
FIXTURE_NAMES = {
    "atx",
    "chinese",
    "duplicate_slug",
    "empty_slug",
    "inline_markup",
    "setext",
}


class MarkdownTocTests(SimpleTestCase):
    def test_render_with_toc_matches_golden_fixtures(self):
        fixture_paths = sorted(FIXTURE_DIRECTORY.glob("*.json"))

        self.assertEqual({path.stem for path in fixture_paths}, FIXTURE_NAMES)

        markdown = Markdown()
        for fixture_path in fixture_paths:
            with self.subTest(fixture=fixture_path.stem):
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                html, toc = markdown.render_with_toc(fixture["markdown"])
                self.assertEqual(html, fixture["html"])
                self.assertEqual(toc, fixture["toc"])
