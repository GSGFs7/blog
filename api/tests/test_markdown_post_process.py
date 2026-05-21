from django.test import SimpleTestCase
from api.markdown.markdown_it import Markdown

class TestMarkdownPostProcess(SimpleTestCase):
    def setUp(self):
        self.md = Markdown()

    def test_image_wrapping_and_centering(self):
        """Test that images are wrapped in a span with md-img-container class."""
        markdown_text = "![alt](test.png)"
        html = self.md.render(markdown_text)
        self.assertIn('<span class="md-img-container"', html)
        self.assertIn('<img src="test.png" alt="alt">', html)
        self.assertIn('</span>', html)

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
        """Test that images inside paragraphs are correctly wrapped without breaking text."""
        markdown_text = "Text before ![alt](img.png) text after."
        html = self.md.render(markdown_text)
        self.assertIn('<p>Text before <span class="md-img-container"', html)
        self.assertIn('</span> text after.</p>', html)

    def test_pre_data_language(self):
        markdown_text = "```python\nprint('hello')\n```"
        html = self.md.render(markdown_text)
        self.assertIn('<pre data-language="python"', html)

    def test_pre_without_language_class(self):
        markdown_text = "```\nno language\n```"
        html = self.md.render(markdown_text)
        self.assertNotIn('data-language=', html)

    def test_pre_data_language_multiple_blocks(self):
        markdown_text = "```python\na = 1\n```\n\n```rust\nlet x = 1;\n```"
        html = self.md.render(markdown_text)
        self.assertIn('data-language="python"', html)
        self.assertIn('data-language="rust"', html)
