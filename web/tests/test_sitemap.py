from django.test import TestCase
from django.urls import reverse

from api.models import Post


class SitemapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.post = Post.objects.create(
            title="Published post",
            slug="published-post",
            content="# Post content",
            status="published",
        )
        Post.objects.create(
            title="Draft post",
            slug="draft-post",
            content="Draft content",
            status="draft",
        )

    def test_sitemap_xml(self):
        response = self.client.get(reverse("django.contrib.sitemaps.views.sitemap"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")

        content = response.content.decode("utf-8")
        self.assertIn("/blog/published-post", content)
        self.assertIn("/about", content)
        self.assertIn("/blog", content)
        self.assertNotIn("/blog/draft-post", content)
