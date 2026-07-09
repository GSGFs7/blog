from django.test import TestCase, override_settings
from django.urls import reverse

from api.models import Post


@override_settings(SECURE_SSL_REDIRECT=False)
class BlogPostMarkdownTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.content = "# Published post\n\nOriginal **markdown** body."
        Post.objects.create(
            title="Published post",
            slug="published-post",
            content=cls.content,
            meta_description="post summary",
            keywords="test",
            status="published",
        )
        Post.objects.create(
            title="Draft post",
            slug="draft-post",
            content="# Draft post",
            meta_description="draft summary",
            keywords="draft",
            status="draft",
        )

    def test_published_post_markdown_response(self):
        response = self.client.get(
            reverse("blog_post_markdown", args=["published-post"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/markdown; charset=utf-8")
        self.assertEqual(
            response["Content-Disposition"],
            'inline; filename="published-post.md"',
        )
        self.assertEqual(response.content.decode(), self.content)

    @override_settings(DEBUG=True)
    def test_html_post_links_to_markdown_alternate(self):
        response = self.client.get(reverse("blog_post_slug", args=["published-post"]))

        self.assertContains(
            response,
            (
                '<link rel="alternate" type="text/markdown" '
                'href="https://gsgfs.moe/blog/published-post.md">'
            ),
            html=False,
        )

    def test_draft_post_markdown_returns_404(self):
        response = self.client.get(reverse("blog_post_markdown", args=["draft-post"]))

        self.assertEqual(response.status_code, 404)
