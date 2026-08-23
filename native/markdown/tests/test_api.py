import unittest
from collections import UserDict
from concurrent.futures import ThreadPoolExecutor

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

    def test_prepare_collects_image_checksums_in_first_seen_order(self):
        first = "a" * 64
        second = "b" * 64
        plan = MarkdownIt().prepare(
            f"![first]({first})\n\n"
            f"![second](https://example.com/{second}.jpg?size=1)\n\n"
            f"![duplicate]({first})"
        )

        self.assertEqual(plan.image_checksums, (first, second))

    def test_prepare_ignores_images_in_raw_html_nodes(self):
        checksum = "a" * 64

        plan = MarkdownIt().prepare(f'<img src="/media/{checksum}.jpg">')

        self.assertEqual(plan.image_checksums, ())

    def test_prepare_accepts_picture_source_prefixes(self):
        plan = MarkdownIt().prepare(
            "hello",
            image_picture_source_prefixes=("https://uploads.example/raw/",),
        )

        self.assertEqual(plan.finish(), "<p>hello</p>\n")

    def test_prepare_rejects_invalid_picture_source_prefixes(self):
        with self.assertRaises(TypeError):
            MarkdownIt().prepare("hello", image_picture_source_prefixes=(1,))

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

    def test_finish_optimizes_resolved_markdown_images(self):
        checksum = "a" * 64
        plan = MarkdownIt().prepare(f"![caption]({checksum})")

        html = plan.finish(
            {
                checksum: {
                    "src": "/media/image.jpg",
                    "webp_src": "/media/image.webp",
                    "width": 640,
                    "height": 480,
                }
            }
        )

        self.assertIn('<span class="md-img-container" data-caption="caption">', html)
        self.assertIn('<source srcset="/media/image.webp" type="image/webp">', html)
        self.assertIn(
            '<img src="/media/image.jpg" alt="caption" loading="lazy" '
            'decoding="async" width="640" height="480">',
            html,
        )

    def test_finish_argument_error_does_not_consume_plan(self):
        plan = MarkdownIt().prepare("# heading")

        with self.assertRaises(TypeError):
            plan.finish([])

        self.assertEqual(plan.finish({}), '<h1 id="heading">heading</h1>\n')

    def test_shared_parser_supports_concurrent_rendering(self):
        source = "# Heading\n\n```rust\nfn main() {}\n```\n\n" * 64
        expected = MarkdownIt().prepare(source).finish()

        for workers in (1, 4, 16):
            with self.subTest(workers=workers):
                markdown = MarkdownIt()
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    results = list(
                        executor.map(
                            lambda _: markdown.prepare(source).finish(),
                            range(workers * 2),
                        )
                    )

                self.assertEqual(results, [expected] * (workers * 2))

    def test_render_plan_can_finish_on_another_thread(self):
        plan = MarkdownIt().prepare("# Heading")

        with ThreadPoolExecutor(max_workers=1) as executor:
            html = executor.submit(plan.finish).result()

        self.assertEqual(html, '<h1 id="heading">Heading</h1>\n')


if __name__ == "__main__":
    unittest.main()
