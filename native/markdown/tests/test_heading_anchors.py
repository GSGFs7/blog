import unittest

from markdown_it_rs_py import MarkdownIt


class HeadingAnchorTests(unittest.TestCase):
    def test_heading_anchors(self):
        html = MarkdownIt().prepare("## Ciallo ～(∠・ω< )⌒★!").finish()

        self.assertIn('<h2 id="ciallo', html)
        self.assertIn("Ciallo ～(∠・ω&lt; )⌒★!", html)


if __name__ == "__main__":
    unittest.main()
