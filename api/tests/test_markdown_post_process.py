from django.test import SimpleTestCase, TestCase, override_settings

from api.markdown.markdown_it import Markdown
from media_service.models import ImageResource


class TestMarkdownPostProcess(SimpleTestCase):
    def setUp(self):
        self.md = Markdown()

    def test_image_wrapping_and_centering(self):
        """Test that images are wrapped in a span with md-img-container class."""
        markdown_text = "![alt](test.png)"
        html = self.md.render(markdown_text)
        self.assertIn('<span class="md-img-container"', html)
        self.assertIn('<img src="test.png" alt="alt">', html)
        self.assertIn("</span>", html)

    def test_caption_priority_alt_only(self):
        """Test that data-caption uses alt when title is missing."""
        markdown_text = "![alt text](test.png)"
        html = self.md.render(markdown_text)
        self.assertIn('data-caption="alt text"', html)

    def test_caption_priority_title_wins(self):
        """Test that data-caption prioritizes title over alt."""
        markdown_text = '![alt text](test.png "title text")'
        html = self.md.render(markdown_text)
        self.assertIn('data-caption="title text"', html)
        self.assertIn('alt="alt text"', html)
        self.assertIn('title="title text"', html)

    def test_caption_only_title(self):
        """Test that data-caption works when only title is provided."""
        markdown_text = '![](test.png "only title")'
        html = self.md.render(markdown_text)
        self.assertIn('data-caption="only title"', html)

    def test_no_caption_if_both_missing(self):
        """Test that data-caption is empty if both alt and title are missing."""
        markdown_text = "![](test.png)"
        html = self.md.render(markdown_text)
        self.assertIn('data-caption=""', html)

    def test_multiple_images(self):
        """Test that multiple images in one document are all correctly processed."""
        markdown_text = "![img1](1.png)\n\n![img2](2.png)"
        html = self.md.render(markdown_text)
        self.assertEqual(html.count('class="md-img-container"'), 2)
        self.assertIn('data-caption="img1"', html)
        self.assertIn('data-caption="img2"', html)

    def test_image_inside_other_text(self):
        """
        Test that images inside paragraphs are correctly
        wrapped without breaking text.
        """
        markdown_text = "Text before ![alt](img.png) text after."
        html = self.md.render(markdown_text)
        self.assertIn('<p>Text before <span class="md-img-container"', html)
        self.assertIn("</span> text after.</p>", html)

    def test_pre_data_language(self):
        markdown_text = "```python\nprint('hello')\n```"
        html = self.md.render(markdown_text)
        self.assertIn('<pre data-language="python"', html)

    def test_pre_without_language_class(self):
        markdown_text = "```\nno language\n```"
        html = self.md.render(markdown_text)
        self.assertNotIn("data-language=", html)

    def test_pre_data_language_multiple_blocks(self):
        markdown_text = "```python\na = 1\n```\n\n```rust\nlet x = 1;\n```"
        html = self.md.render(markdown_text)
        self.assertIn('data-language="python"', html)
        self.assertIn('data-language="rust"', html)

    def test_domain_injection(self):
        """Test that data-domain is injected only into the <span> tag."""
        markdown_text = "[google](https://google.com)"
        html = self.md.render(markdown_text)
        self.assertIn('<span data-domain="google.com">google</span>', html)
        self.assertNotIn('<a data-domain="google.com"', html)

    def test_sanitizes_dangerous_html(self):
        markdown_text = """
<span class="heimu" onclick="alert(1)">secret</span>
<script>alert(1)</script>
<a href="javascript:alert(1)">bad</a>
<img src="x" onerror="alert(1)">
"""
        html = self.md.render(markdown_text)

        self.assertIn('<span class="heimu">secret</span>', html)
        self.assertIn('<a rel="noopener noreferrer">bad</a>', html)
        self.assertNotIn("alert(1)", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("onclick", html)
        self.assertNotIn("onerror", html)
        self.assertNotIn("<script", html)

    def test_task_list_survives_sanitizer(self):
        html = self.md.render("- [x] done\n- [ ] todo")

        self.assertIn('class="contains-task-list"', html)
        self.assertIn('class="task-list-item"', html)
        self.assertIn('class="task-list-item-checkbox"', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn('disabled=""', html)
        self.assertIn('checked=""', html)

    def test_footnotes_survive_sanitizer(self):
        html = self.md.render("hello[^1]\n\n[^1]: note")

        self.assertIn('<section class="footnotes">', html)
        self.assertIn('class="footnote-ref"', html)
        self.assertIn('id="fnref1"', html)
        self.assertIn('href="#fn1"', html)
        self.assertIn('class="footnote-backref"', html)

    def test_math_survives_sanitizer(self):
        html = self.md.render("$$\nE = mc^2\n$$")

        self.assertIn('class="math-block"', html)
        self.assertIn('class="katex"', html)
        self.assertIn('xmlns="http://www.w3.org/1998/Math/MathML"', html)
        self.assertIn('encoding="application/x-tex"', html)
        self.assertIn('style="height:', html)

    def test_python_wasm_directive_mounts_repl_island(self):
        html = self.md.render('<div class="directive python-wasm"></div>')

        self.assertIn('data-solid-island="PythonREPL"', html)


@override_settings(MEDIA_URL="/media/")
class TestMarkdownImageOptimization(TestCase):
    def test_image_resource_is_rendered_as_wrapped_picture(self):
        checksum = "d45c3754209b10b7c7ecab223d712ddbc21dde4e58cd819f05381c92d3327aa3"
        ImageResource.objects.create(
            checksum=checksum,
            file=f"images/raw/d4/5c/{checksum}.jpg",
            avif_file=f"images/avif/d4/5c/{checksum}.avif",
            webp_file=f"images/webp/d4/5c/{checksum}.webp",
            width=916,
            height=916,
            size=1,
            mime_type="image/jpeg",
            placeholder="data:image/webp;base64,test+value",
        )

        html = Markdown().render(f"![caption]({checksum})")

        self.assertIn('<span class="md-img-container" data-caption="caption">', html)
        self.assertIn("<picture>", html)
        self.assertIn('type="image/avif"', html)
        self.assertIn('type="image/webp"', html)
        self.assertIn(f'src="/media/images/raw/d4/5c/{checksum}.jpg"', html)
        self.assertIn("background-image:url(data:image/webp;base64,test+value)", html)
        self.assertIn("background-size:cover", html)
        self.assertNotIn("</picture?", html)
        self.assertNotIn("\\+", html)
