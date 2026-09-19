from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import Post


@override_settings(SECURE_SSL_REDIRECT=False, DEBUG=True)
class MarkdownIndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for index in range(12):
            post = Post.objects.create(
                title=f"Article {index}",
                slug=f"article-{index}",
                content="Body",
                meta_description="Summary",
                keywords="test",
                status="published",
            )
            Post.objects.filter(pk=post.pk).update(
                published_at=timezone.now() - timedelta(days=index),
                order=index,
            )
        Post.objects.create(
            title="Private draft",
            slug="private-draft",
            content="Secret",
            meta_description="Secret summary",
            keywords="test",
            status="draft",
        )

    def test_markdown_matches_html_pagination(self):
        for page in ("1", "2", "999", "abc", "0", "-1"):
            with self.subTest(page=page):
                html = self.client.get(reverse("blog"), {"page": page})
                response = self.client.get(reverse("blog_markdown"), {"page": page})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response["Content-Type"], "text/markdown; charset=utf-8"
                )
                self.assertEqual(
                    list(html.context["post_list"]),
                    list(response.context["post_list"]),
                )
                self.assertEqual(response.context["total_posts"], 12)
                self.assertEqual(response.context["total_pages"], 2)
                self.assertNotContains(response, "private-draft")
                for post in response.context["post_list"]:
                    self.assertContains(response, f"/blog/{post.slug}.md")

    def test_navigation_and_html_alternate(self):
        for page in (1, 2):
            with self.subTest(page=page):
                suffix = f"?page={page}" if page > 1 else ""
                html = self.client.get(reverse("blog"), {"page": page})
                self.assertContains(
                    html,
                    '<link rel="alternate" type="text/markdown" '
                    f'href="https://gsgfs.moe/blog.md{suffix}">',
                )
                response = self.client.get(reverse("blog_markdown"), {"page": page})
                self.assertContains(response, f"https://gsgfs.moe/blog?page={page}")
                self.assertContains(response, "https://gsgfs.moe/llms.txt")
                if page == 1:
                    self.assertContains(
                        response, "[Next page](https://gsgfs.moe/blog.md?page=2)"
                    )
                    self.assertNotContains(response, "[Previous page]")
                else:
                    self.assertContains(
                        response, "[Previous page](https://gsgfs.moe/blog.md?page=1)"
                    )
                    self.assertNotContains(response, "[Next page]")

    def test_llms_lists_five_recent_published_posts(self):
        response = self.client.get(reverse("llms"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(response, "https://gsgfs.moe/blog.md")
        self.assertEqual(
            [post.slug for post in response.context["recent_posts"]],
            [f"article-{index}" for index in range(5)],
        )
        self.assertNotContains(response, "private-draft")
        self.assertNotContains(response, "/blog/article-5.md")
        Post.objects.filter(slug="article-0").update(status="draft")
        updated = self.client.get(reverse("llms"))
        self.assertNotContains(updated, "/blog/article-0.md")
        self.assertContains(updated, "/blog/article-5.md")

    def test_inline_markdown_is_escaped_in_both_templates(self):
        Post.objects.filter(slug="article-0").update(
            title='A ] [link](url) <b> & "quote"',
            meta_description="First\nsecond *bold* `code` \\ path",
            order=100,
        )
        for name in ("blog_markdown", "llms"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, r'A \] \[link\]\(url\) \<b\> \& "quote"')
                self.assertContains(response, r"First second \*bold\* \`code\` \\ path")
                self.assertNotContains(response, "&quot;")

    def test_empty_indexes_and_markdown_head(self):
        Post.objects.filter(status="published").update(status="draft")
        for name in ("blog_markdown", "llms"):
            response = self.client.get(reverse(name))
            self.assertContains(response, "No published articles yet.")
        response = self.client.head(reverse("blog_markdown"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["Content-Type"], "text/markdown; charset=utf-8")
