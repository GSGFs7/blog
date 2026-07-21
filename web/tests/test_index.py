import re

from django.test import TestCase


class IndexViewTestCase(TestCase):
    def test_hero_image_uses_format_variants(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        rendered_html = re.sub(
            r"<!--.*?-->", "", response.content.decode(), flags=re.DOTALL
        )
        pictures = re.findall(r"<picture\b.*?</picture>", rendered_html, re.DOTALL)
        hero_pictures = [
            picture for picture in pictures if 'fetchpriority="high"' in picture
        ]

        self.assertEqual(len(hero_pictures), 1)
        self.assertIn('type="image/avif"', hero_pictures[0])
        self.assertIn('type="image/webp"', hero_pictures[0])
        self.assertIn('loading="eager"', hero_pictures[0])
