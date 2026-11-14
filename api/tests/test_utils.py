from django.test import TestCase

from api.utils import (
    chinese_slugify,
    convert_openapi,
    extract_first_image,
    extract_front_matter,
    extract_metadata,
    normalize_slug,
)


class TestUtils(TestCase):
    def test_extract_front_matter(self):
        test_cases = [
            (
                "---\ntitle: Test Post\ntags: [python, django]\n---\ncontent",
                {"title": "Test Post", "tags": ["python", "django"]},
            ),
            (
                "---\ntitle: Simple\n---\ncontent",
                {"title": "Simple"},
            ),
            (
                "---\nkey: value\nlist: [a, b, c]\n---\ncontent",
                {"key": "value", "list": ["a", "b", "c"]},
            ),
            ("No front matter", {}),
            (
                "---\n---\ncontent",
                {},
            ),
            (
                "---\nmultiline: |\n  line1\n  line2\n---\ncontent",
                {"multiline": "line1\nline2"},
            ),
            (
                "---\nnum: 42\nbool: true\nempty: null\n---\ncontent",
                {"num": 42, "bool": True, "empty": None},
            ),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text[:50]):
                result = extract_front_matter(input_text)
                self.assertEqual(result, expected)

    def test_extract_front_matter_invalid_yaml(self):
        # Test that invalid YAML returns empty dict
        test_cases = [
            "---\ninvalid: yaml: here\n---\ncontent",
            "---\n  indented wrong\n---\ncontent",
            "---\nunclosed: [list\n---\ncontent",
            "---\ninvalid & characters\n---\ncontent",
        ]

        for input_text in test_cases:
            with self.subTest(input_text=input_text[:50]):
                result = extract_front_matter(input_text)
                self.assertEqual(result, {})

    def test_extract_first_image(self):
        test_cases = [
            ("![alt](image.jpg)", "image.jpg"),
            (
                "![alt text](https://example.com/image.png)",
                "https://example.com/image.png",
            ),
            ("<img src='local.jpg'>", "local.jpg"),
            ('<img src="https://test.com/img.jpg">', "https://test.com/img.jpg"),
            ("Text ![first](first.jpg) ![second](second.jpg)", "first.jpg"),
            ("<img src='first.jpg'> <img src='second.jpg'>", "first.jpg"),
            ("No image here", None),
            ("![markdown](img.png) and <img src='html.jpg'>", "img.png"),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text[:50]):
                result = extract_first_image(input_text)
                self.assertEqual(result, expected)

    def test_extract_metadata_basic(self):
        text = """---
title: Test Post
tags: [python, django]
category: Programming
cover_image: cover.jpg
og_image: header.jpg
---
# This is a test post

This is the content of the test post with some **bold** text and `code`.

![First Image](first.jpg)

More content here.
"""

        result = extract_metadata(text)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["title"], "Test Post")
        self.assertEqual(result["tags"], ["python", "django"])
        self.assertEqual(result["category"], "Programming")
        self.assertEqual(result["cover_image"], "cover.jpg")
        self.assertEqual(result["header_image"], "header.jpg")
        self.assertIn("keywords", result)
        self.assertIn("description", result)
        self.assertIsInstance(result["keywords"], str)
        self.assertIsInstance(result["description"], str)

    def test_extract_metadata_no_front_matter(self):
        text = """# Simple Post

This is a simple post without front matter.

![Only Image](only.jpg)

Some content here.
"""

        result = extract_metadata(text)

        self.assertIsInstance(result, dict)
        self.assertIsNone(result["title"])
        self.assertIsNone(result["slug"])
        self.assertIsNone(result["category"])
        self.assertIsNone(result["cover_image"])
        self.assertEqual(result["header_image"], "only.jpg")
        self.assertEqual(result["tags"], [])
        self.assertIn("keywords", result)
        self.assertIn("description", result)

    def test_extract_metadata_various_tag_formats(self):
        test_cases = [
            ("---\ntags: python\n---\ncontent", ["python"]),
            ("---\ntags: [python, django]\n---\ncontent", ["python", "django"]),
            ("---\ntag: python\n---\ncontent", ["python"]),
            ("---\ntag: [python, django]\n---\ncontent", ["python", "django"]),
            ("---\ntags: python\ntag: django\n---\ncontent", ["python", "django"]),
        ]

        for input_text, expected_tags in test_cases:
            with self.subTest(input_text=input_text[:50]):
                result = extract_metadata(input_text)
                self.assertEqual(result["tags"], expected_tags)

    def test_extract_metadata_category_variations(self):
        test_cases = [
            ("---\ncategory: Tech\n---\ncontent", "Tech"),
            ("---\ncategories: Tech\n---\ncontent", "Tech"),
            ("---\ncategories: [Tech, Blog]\n---\ncontent", "Tech"),
            ("---\ncategory: [Tech, Blog]\n---\ncontent", "Tech"),
            ("---\n---\ncontent", None),
        ]

        for input_text, expected_category in test_cases:
            with self.subTest(input_text=input_text[:50]):
                result = extract_metadata(input_text)
                self.assertEqual(result["category"], expected_category)

    def test_extract_metadata_image_variations(self):
        test_cases = [
            ("---\ncover_image: cover.jpg\n---\ncontent", "cover.jpg"),
            ("---\ncover-image: cover.jpg\n---\ncontent", "cover.jpg"),
            ("---\ncover_img: cover.jpg\n---\ncontent", "cover.jpg"),
            ("---\ncover-img: cover.jpg\n---\ncontent", "cover.jpg"),
            ("---\ncover: cover.jpg\n---\ncontent", "cover.jpg"),
            ("---\nheader_image: header.jpg\n---\ncontent", "header.jpg"),
            ("---\nheader-image: header.jpg\n---\ncontent", "header.jpg"),
            ("---\nog_image: og.jpg\n---\ncontent", "og.jpg"),
            ("---\nog-image: og.jpg\n---\ncontent", "og.jpg"),
        ]

        for input_text, expected_image in test_cases:
            with self.subTest(input_text=input_text[:50]):
                result = extract_metadata(input_text)
                if "cover" in input_text:
                    self.assertEqual(result["cover_image"], expected_image)
                else:
                    self.assertEqual(result["header_image"], expected_image)

    def test_chinese_slugify(self):
        test_cases = [
            ("测试标题", "ce-shi-biao-ti"),
            ("Hello World", "hello-world"),
            ("测试 Title 混合", "ce-shi-title-hun-he"),
            ("Python编程指南", "python-bian-cheng-zhi-nan"),
            ("", "untitled"),
            ("   ", "untitled"),
            ("Special!@#$%^&*()Chars", "special-chars"),
            ("中文和English混合", "zhong-wen-he-english-hun-he"),
            ("测试-已经-有-连字符", "ce-shi-yi-jing-you-lian-zi-fu"),
            ("测试   多个   空格", "ce-shi-duo-ge-kong-ge"),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                result = chinese_slugify(input_text)
                self.assertEqual(result, expected)

    def test_normalize_slug(self):
        test_cases = [
            ("Hello World", "Hello-World"),
            ("  Leading and trailing  ", "Leading-and-trailing"),
            ("Multiple   spaces", "Multiple-spaces"),
            ("under_score", "under-score"),
            ("already-slugged", "already-slugged"),
            ("a---b", "a-b"),
            ("Special!@#$%^&*()Chars", "Special-Chars"),
            ("中文 标题", "中文-标题"),
            ("!!!", ""),
        ]

        for input_text, expected in test_cases:
            with self.subTest(input_text=input_text):
                self.assertEqual(normalize_slug(input_text), expected)

    def test_chinese_slugify_max_length(self):
        long_title = "这是一个非常长的中文标题需要被截断" * 10
        result = chinese_slugify(long_title, max_length=50)

        self.assertLessEqual(len(result), 50)
        self.assertIn("-", result)  # Should have hash suffix

        # Test that truncation works for English text too
        english_long = (
            "Very Long Title That Should Be Truncated Because It Exceeds Maximum Length"
        )
        result2 = chinese_slugify(english_long, max_length=50)
        self.assertLessEqual(len(result2), 50)
        self.assertIn("-", result2)

    def test_openapi_convert_decorator(self):
        def sample_openapi_func():
            return {
                "openapi": "3.1.0",
                "components": {
                    "schemas": {
                        "Test": {"type": ["string", "null"], "examples": ["test"]}
                    }
                },
            }

        decorated_func = convert_openapi(sample_openapi_func)
        result = decorated_func()

        self.assertEqual(result["openapi"], "3.0.3")
        self.assertEqual(result["components"]["schemas"]["Test"]["type"], "string")
        self.assertEqual(result["components"]["schemas"]["Test"]["nullable"], True)
        self.assertEqual(result["components"]["schemas"]["Test"]["example"], "test")
        self.assertNotIn("examples", result["components"]["schemas"]["Test"])

    def test_metadata_result_structure(self):
        text = """---
title: Test
tags: [tag1]
---
Content"""

        result = extract_metadata(text)

        self.assertIsInstance(result, dict)
        required_keys = [
            "keywords",
            "tags",
            "description",
            "title",
            "slug",
            "category",
            "cover_image",
            "header_image",
        ]
        for key in required_keys:
            self.assertIn(key, result)

        self.assertIsInstance(result["tags"], list)
        self.assertIsInstance(result["keywords"], str)
        self.assertIsInstance(result["description"], str)

    def test_extract_metadata_with_keywords(self):
        text = """---
title: Test
keywords: [kw1, kw2]
tags: [tag1]
---
Content with python and django"""

        result = extract_metadata(text, num_keywords=3)

        self.assertIn("kw1", result["keywords"])
        self.assertIn("kw2", result["keywords"])
        self.assertIn("tag1", result["keywords"])
        self.assertEqual(len(result["keywords"].split(",")), 3)

    def test_extract_metadata_description_truncation(self):
        long_content = "A" * 200
        text = f"---\ntitle: Test\n---\n{long_content}"

        result = extract_metadata(text)

        self.assertLessEqual(len(result["description"]), 150)
        self.assertTrue(result["description"].startswith("A"))

    def test_description_uses_prose_without_markdown_structure(self):
        source = """---
title: Example
---
# Example
## Why change?
The first **real** paragraph explains the article.
It continues on the next line with a [link](https://example.com).

| Name | Value |
| --- | --- |
| A | B |

::music{src="https://example.com/song.flac"}
"""
        self.assertEqual(
            extract_metadata(source)["description"],
            "The first real paragraph explains the article. "
            "It continues on the next line with a link.",
        )

    def test_description_skips_directives_and_uses_list_as_fallback(self):
        source = """# Music
::music{src="https://example.com/song.flac"}
:::terminal{shell="zsh"}:::
![cover](cover.jpg)

- A useful item
- Another item
"""
        self.assertEqual(
            extract_metadata(source)["description"], "A useful item Another item"
        )

    def test_front_matter_description_takes_priority(self):
        source = """---
description: A hand-written summary of the post.
---
Body text that should not replace it.
"""
        self.assertEqual(
            extract_metadata(source)["description"],
            "A hand-written summary of the post.",
        )
