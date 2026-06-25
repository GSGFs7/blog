from xml.etree import ElementTree

from django.test import TestCase, override_settings
from django.urls import reverse

from api.models import Category, Post, Tag

ATOM_NS = "http://www.w3.org/2005/Atom"


def atom(name):
    return f"{{{ATOM_NS}}}{name}"


@override_settings(SECURE_SSL_REDIRECT=False)
class BlogPostFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="技术")
        tag = Tag.objects.create(name="Django")

        cls.post = Post.objects.create(
            title="Published post",
            slug="published-post",
            content="# Post content",
            meta_description="post summary",
            keywords="test",
            category=category,
            status="published",
        )
        cls.post.tags.add(tag)
        Post.objects.filter(pk=cls.post.pk).update(content_html="<p>Rendered body</p>")

        Post.objects.create(
            title="Draft post",
            slug="draft-post",
            content="Draft content",
            meta_description="Draft summary",
            keywords="draft",
            status="draft",
        )

    def get_feed(self):
        response = self.client.get(reverse("blog_feed"), secure=True)
        self.assertEqual(response.status_code, 200)
        return response, ElementTree.fromstring(response.content)

    def test_response_metadata(self):
        response, root = self.get_feed()

        self.assertEqual(
            response["Content-Type"],
            "application/atom+xml; charset=utf-8",
        )
        self.assertEqual(root.tag, atom("feed"))
        self.assertEqual(root.findtext(atom("id")), "tag:gsgfs.moe,2024:blog")
        self.assertEqual(root.findtext(atom("subtitle")), "GSGFs's blog")

    def test_entry_content_and_guid(self):
        _, root = self.get_feed()
        entry = root.find(atom("entry"))
        content = entry.find(atom("content"))

        self.assertEqual(content.attrib["type"], "html")
        self.assertEqual(content.text, "<p>Rendered body</p>")
        self.assertEqual(
            entry.findtext(atom("id")),
            f"tag:gsgfs.moe,{self.post.created_at:%Y-%m-%d}:blog#post-{self.post.pk}",
        )

    def test_contains_only_published_posts(self):
        _, root = self.get_feed()
        entries = root.findall(atom("entry"))

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].findtext(atom("title")), self.post.title)

    def test_entry_categories(self):
        _, root = self.get_feed()
        entry = root.find(atom("entry"))
        categories = {
            element.attrib["term"] for element in entry.findall(atom("category"))
        }

        self.assertEqual(categories, {"技术", "Django"})

    def test_feed_entries_limit(self):
        for index in range(10):
            Post.objects.create(
                title=f"Post {index}",
                slug=f"post-{index}",
                content=f"Content-{index}",
                content_html=f"<p>Rendered content {index}</p>",
                meta_description=f"Summary {index}",
                keywords="test",
                status="published",
            )

        _, root = self.get_feed()
        self.assertEqual(len(root.findall(atom("entry"))), 10)

    def test_feed_query_count(self):
        # N+1 query
        with self.assertNumQueries(2):
            response = self.client.get(reverse("blog_feed"))
            self.assertEqual(response.status_code, 200)
