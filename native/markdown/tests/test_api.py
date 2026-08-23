import unittest
from collections import UserDict

from markdown_it_rs_py import ImageMetadata, MarkdownIt, RenderPlan


class MarkdownItTests(unittest.TestCase):
    def test_image_metadata_is_public(self):
        metadata: ImageMetadata = {"src": "image.jpg"}

        self.assertEqual(metadata, {"src": "image.jpg"})

    def test_fixed_pipeline(self):
        html = MarkdownIt().prepare("hello<br>world\n\n$E=mc^2$").finish()

        self.assertIn("hello<br>world", html)
        self.assertIn('<span class="math-inline">', html)

    def test_prepare_returns_render_plan_metadata(self):
        plan = MarkdownIt().prepare("# heading", include_toc=True)

        self.assertIsInstance(plan, RenderPlan)
        self.assertEqual(plan.image_checksums, ())
        self.assertEqual(
            plan.toc,
            [{"level": 1, "slug": "heading", "text": "heading"}],
        )
        self.assertIsNone(plan.frontmatter)

    def test_finish_renders_and_consumes_plan(self):
        plan = MarkdownIt().prepare("# heading")

        self.assertEqual(
            plan.finish(),
            '<h1 id="heading">heading</h1>\n',
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "render plan already finished",
        ):
            plan.finish()

    def test_finish_accepts_image_data(self):
        expected = '<h1 id="heading">heading</h1>\n'

        cases = (
            None,
            {},
            UserDict(),
            {"checksum": {"src": "image.jpg"}},
        )

        for images in cases:
            with self.subTest(images=images):
                plan = MarkdownIt().prepare("# heading")
                self.assertEqual(plan.finish(images), expected)

    def test_finish_argument_error_does_not_consume_plan(self):
        plan = MarkdownIt().prepare("# heading")

        with self.assertRaises(TypeError):
            plan.finish([])

        self.assertEqual(plan.finish({}), '<h1 id="heading">heading</h1>\n')


if __name__ == "__main__":
    unittest.main()
