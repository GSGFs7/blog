from django.test import TestCase


class IndexViewTestCase(TestCase):
    def test_hero_image_uses_format_variants(self):
        response = self.client.get("/")

        self.assertContains(
            response,
            'srcset="https://img.gsgfs.moe/images/avif/6a/d5/'
            '6ad5852d8f1048c49a862e400a133d10da1fdb302bf3116fd74b0289b002731e.avif"',
        )
        self.assertContains(
            response,
            'srcset="https://img.gsgfs.moe/images/webp/6a/d5/'
            '6ad5852d8f1048c49a862e400a133d10da1fdb302bf3116fd74b0289b002731e.webp"',
        )
        self.assertContains(response, 'fetchpriority="high"')
