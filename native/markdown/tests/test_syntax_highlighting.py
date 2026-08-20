import unittest

from markdown_it_rs_py import MarkdownIt


class SyntaxHighlightingTests(unittest.TestCase):
    def test_syntax_highlighting(self):
        html = MarkdownIt().prepare("```rust\nfn main() {}\n```").finish()

        self.assertIn('<code class="syntect-code language-rust">', html)
        self.assertIn('class="syntect-line"', html)
        self.assertIn("<span", html)


if __name__ == "__main__":
    unittest.main()
