from django.test import TestCase

from api.text_chunking import chunk_text


class TextChunkingTest(TestCase):
    def test_chunk_text(self):
        text = "Sentence one. Sentence two. Sentence three. Sentence four."
        # chunk_size=30 should split it roughly every 2 sentences
        chunks = chunk_text(text, chunk_size=30, overlap=5)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 30)

        # Test empty text
        self.assertEqual(chunk_text(""), [])

        # Test large chunk size
        self.assertEqual(chunk_text(text, chunk_size=1000), [text])

    def test_chunk_text_rejects_invalid_options(self):
        with self.assertRaises(ValueError):
            chunk_text("ciallo", chunk_size=0)

        with self.assertRaises(ValueError):
            chunk_text("ciallo", chunk_size=10, overlap=-1)

        with self.assertRaises(ValueError):
            chunk_text("ciallo", chunk_size=10, overlap=10)

        with self.assertRaises(ValueError):
            chunk_text("caillo", chunk_size=10, overlap=20)

    def test_chunk_text_returns_empty(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("  \n\n   "), [])
        self.assertEqual(chunk_text('```python\nprint("ciallo")\n```'), [])
        self.assertEqual(chunk_text("![cover](cover.png)"), [])

    def test_chunk_text_cleans_markdown_and_code(self):
        text = """
---
title: title
---

# heading

<p>some content here</p>

```python
print("ciallo")
```

some [link](https://example.com) and **mark**
"""

        chunks = chunk_text(text, chunk_size=1000, overlap=0)
        result = "\n".join(chunks)

        self.assertIn("heading", result)
        self.assertIn("some content here", result)
        self.assertIn("some link and mark", result)
        self.assertNotIn("title", result)
        self.assertNotIn("print", result)
        self.assertNotIn("python", result)
        self.assertNotIn("<p>", result)
        self.assertNotIn("</p>", result)
        self.assertNotIn("**", result)
        self.assertNotIn("https://example.com", result)

    def test_prefers_sentence_boundaries(self):
        text = (
            "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
            "句子一。句子二。句子三。句子四？句子五！"
        )

        chunks = chunk_text(text, chunk_size=20, overlap=0)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertRegex(chunk, r"[.!?。！？]$")
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)

    def test_keeps_cjk_closing_punctuation_with_sentence(self):
        text = "「第一句。」第二句。『第三句！』第四句？"
        chunks = chunk_text(text, chunk_size=8, overlap=0)

        self.assertEqual(
            chunks,
            ["「第一句。」", "第二句。", "『第三句！』", "第四句？"],
        )

    def test_preserves_paragraph_boundaries_when_merging_units(self):
        text = "第一段第一句。\n\n第二段第一句。\n\n第三段第一句。"
        chunks = chunk_text(text, chunk_size=20, overlap=0)

        self.assertEqual(chunks, ["第一段第一句。\n\n第二段第一句。", "第三段第一句。"])

    def test_preserves_paragraph_boundaries_with_overlap(self):
        text = "第一段第一句。\n\n第二段第一句。\n\n第三段第一句。"
        chunks = chunk_text(text, chunk_size=20, overlap=10)

        self.assertEqual(
            chunks,
            [
                "第一段第一句。\n\n第二段第一句。",
                "第二段第一句。\n\n第三段第一句。",
            ],
        )

    def test_split_long_paragraph_with_fallback(self):
        text = "这是一段没有标点的超长文本" * 20
        chunks = chunk_text(text, chunk_size=50, overlap=0)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 50)

    def test_does_not_emit_sentence_tail_fragments(self):
        text = "Sentence one. Sentence two. Sentence three. Sentence four."
        chunks = chunk_text(text, chunk_size=30, overlap=0)

        self.assertEqual(
            chunks,
            [
                "Sentence one. Sentence two.",
                "Sentence three. Sentence four.",
            ],
        )

    def test_supports_overlap(self):
        text = (
            "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
            "句子一。句子二。句子三。句子四？句子五！"
        )
        chunks = chunk_text(text, chunk_size=20, overlap=5)

        self.assertGreater(len(chunks), 1)
        self.assertLess(len(chunks), 20)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)
