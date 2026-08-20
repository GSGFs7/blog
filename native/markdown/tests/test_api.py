import unittest

from markdown_it_rs_py import MarkdownIt, RenderPlan


class MarkdownItTests(unittest.TestCase):
    def test_fixed_pipeline(self):
        html = MarkdownIt().prepare("hello<br>world\n\n$E=mc^2$").finish()

        self.assertIn("hello<br>world", html)
        self.assertIn('<span class="math-inline">', html)

    def test_prepare_returns_render_plan(self):
        plan = MarkdownIt().prepare("# heading", include_toc=True)

        self.assertIsInstance(plan, RenderPlan)
        self.assertEqual(plan.image_checksums, [])
        self.assertEqual(
            plan.toc,
            [{"level": 1, "slug": "heading", "text": "heading"}],
        )
        self.assertIsNone(plan.frontmatter)
        self.assertEqual(plan.finish(), '<h1 id="heading">heading</h1>\n')
        self.assertEqual(plan.finish({"checksum": {"src": "image.jpg"}}), plan.finish())
        self.assertEqual(plan.finish(None), plan.finish())


if __name__ == "__main__":
    unittest.main()
