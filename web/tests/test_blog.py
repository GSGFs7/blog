import json
import re

from django.test import TestCase, override_settings
from django.urls import reverse

from api.models import Category, Post, Tag


@override_settings(SECURE_SSL_REDIRECT=False)
class BlogListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="技术")
        cls.tag = Tag.objects.create(name="Django")

        for i in range(15):
            post = Post.objects.create(
                title=f"Post {i:02d}",
                slug=f"post-{i:02d}",
                content=f"Content {i}",
                meta_description=f"Desc {i}",
                keywords=f"kw{i}",
                category=cls.category,
                status="published",
            )
            post.tags.add(cls.tag)

        Post.objects.create(
            title="Draft Post",
            slug="draft-post",
            content="Draft content",
            meta_description="Draft desc",
            keywords="draft",
            status="draft",
        )

    def test_blog_list_returns_200(self):
        response = self.client.get(reverse("blog"))
        self.assertEqual(response.status_code, 200)

    def test_blog_list_uses_correct_template(self):
        response = self.client.get(reverse("blog"))
        self.assertTemplateUsed(response, "web/pages/blog.html")

    def test_page_1_shows_10_posts(self):
        response = self.client.get(reverse("blog"))
        self.assertEqual(len(response.context["post_list"]), 10)
        self.assertEqual(response.context["page_number"], 1)
        self.assertTrue(response.context["has_next"])
        self.assertFalse(response.context["has_previous"])

    def test_page_2_shows_remaining_posts(self):
        response = self.client.get(reverse("blog") + "?page=2")
        self.assertEqual(len(response.context["post_list"]), 5)
        self.assertEqual(response.context["page_number"], 2)
        self.assertFalse(response.context["has_next"])
        self.assertTrue(response.context["has_previous"])
        self.assertEqual(response.context["previous_page_number"], 1)

    def test_page_beyond_range_returns_last_page(self):
        response = self.client.get(reverse("blog") + "?page=999")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_number"], 2)

    def test_non_numeric_page_defaults_to_1(self):
        response = self.client.get(reverse("blog") + "?page=abc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_number"], 1)

    def test_negative_page_defaults_to_1(self):
        response = self.client.get(reverse("blog") + "?page=-5")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_number"], 1)

    def test_zero_page_defaults_to_1(self):
        response = self.client.get(reverse("blog") + "?page=0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_number"], 1)

    def test_post_list_contains_titles(self):
        response = self.client.get(reverse("blog"))
        titles = [p.title for p in response.context["post_list"]]
        self.assertIn("Post 14", titles)
        self.assertIn("Post 05", titles)

    def test_draft_posts_excluded_from_list(self):
        response = self.client.get(reverse("blog"))
        titles = [p.title for p in response.context["post_list"]]
        self.assertNotIn("Draft Post", titles)

    def test_all_published_posts_appear_across_pages(self):
        all_titles = set()
        for page in (1, 2):
            response = self.client.get(reverse("blog") + f"?page={page}")
            for post in response.context["post_list"]:
                all_titles.add(post.title)
        self.assertEqual(len(all_titles), 15)
        self.assertNotIn("Draft Post", all_titles)

    def test_canonical_link(self):
        response = self.client.get(reverse("blog"))
        self.assertContains(
            response,
            '<link rel="canonical" href="https://gsgfs.moe/blog">',
            html=False,
        )

    def test_canonical_link_includes_page_number(self):
        response = self.client.get(reverse("blog") + "?page=2")
        self.assertContains(
            response,
            '<link rel="canonical" href="https://gsgfs.moe/blog?page=2">',
            html=False,
        )

    def test_canonical_omits_page_1(self):
        response = self.client.get(reverse("blog") + "?page=1")
        self.assertContains(
            response,
            '<link rel="canonical" href="https://gsgfs.moe/blog">',
            html=False,
        )

    def test_prev_next_links_on_page_1(self):
        response = self.client.get(reverse("blog"))
        self.assertContains(
            response,
            '<link rel="next" href="https://gsgfs.moe/blog?page=2">',
            html=False,
        )
        self.assertNotContains(response, 'rel="prev"', html=False)

    def test_prev_next_links_on_page_2(self):
        response = self.client.get(reverse("blog") + "?page=2")
        self.assertContains(
            response,
            '<link rel="prev" href="https://gsgfs.moe/blog?page=1">',
            html=False,
        )
        self.assertNotContains(response, 'rel="next"', html=False)

    def test_og_tags(self):
        response = self.client.get(reverse("blog"))
        self.assertContains(
            response,
            '<meta property="og:title" content="Blog - GSGFs&#x27;s blog">',
        )
        self.assertContains(
            response,
            '<meta property="og:url" content="https://gsgfs.moe/blog">',
        )
        self.assertContains(response, '<meta property="og:type" content="website">')

    def test_empty_blog_list(self):
        Post.objects.all().delete()
        response = self.client.get(reverse("blog"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["post_list"]), 0)
        self.assertFalse(response.context["has_previous"])
        self.assertFalse(response.context["has_next"])


@override_settings(SECURE_SSL_REDIRECT=False)
class BlogPostSlugViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="技术")
        cls.tag_django = Tag.objects.create(name="Django")
        cls.tag_python = Tag.objects.create(name="Python")

        cls.post = Post.objects.create(
            title="Test Published Post",
            slug="test-published-post",
            content="# Hello\n\nThis is a **test**.",
            meta_description="A test post description",
            keywords="test,django",
            category=cls.category,
            status="published",
            header_image="https://img.example.com/header.jpg",
        )
        cls.post.tags.add(cls.tag_django, cls.tag_python)

        cls.draft_post = Post.objects.create(
            title="Draft Post",
            slug="draft-post-slug",
            content="Secret draft",
            meta_description="Draft desc",
            keywords="draft",
            status="draft",
        )

    def test_published_post_returns_200(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertTemplateUsed(response, "web/pages/blog_post.html")

    def test_draft_post_returns_404(self):
        response = self.client.get(
            reverse("blog_post_slug", args=[self.draft_post.slug])
        )
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_slug_returns_404(self):
        response = self.client.get(reverse("blog_post_slug", args=["nonexistent-slug"]))
        self.assertEqual(response.status_code, 404)

    def test_context_contains_title(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(response.context["title"], "Test Published Post")

    def test_context_contains_slug(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(response.context["slug"], "test-published-post")

    def test_context_contains_content_html(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertIn("content_html", response.context)

    def test_context_contains_meta_description(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(
            response.context["meta_description"], "A test post description"
        )

    def test_context_contains_keywords(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(response.context["keywords"], "test,django")

    def test_context_contains_category(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(response.context["category_name"], "技术")

    def test_context_contains_tag_names(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(set(response.context["tag_names"]), {"Django", "Python"})

    def test_context_og_image_uses_header_image(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertEqual(
            response.context["og_image"],
            "https://img.example.com/header.jpg",
        )

    def test_context_og_image_falls_back_to_cover_image(self):
        post = Post.objects.create(
            title="Cover Only",
            slug="cover-only",
            content="Content",
            meta_description="Desc",
            keywords="test",
            status="published",
            cover_image="https://img.example.com/cover.jpg",
        )
        response = self.client.get(reverse("blog_post_slug", args=[post.slug]))
        self.assertEqual(
            response.context["og_image"],
            "https://img.example.com/cover.jpg",
        )

    def test_context_og_image_empty_when_no_images(self):
        post = Post.objects.create(
            title="No Images",
            slug="no-images",
            content="Content",
            meta_description="Desc",
            keywords="test",
            status="published",
        )
        response = self.client.get(reverse("blog_post_slug", args=[post.slug]))
        self.assertEqual(response.context["og_image"], "")

    def test_context_published_at(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertIsNotNone(response.context["published_at"])

    def test_canonical_link(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<link rel="canonical" href="https://gsgfs.moe/blog/test-published-post">',
            html=False,
        )

    def test_markdown_alternate_link(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<link rel="alternate" type="text/markdown" '
            'href="https://gsgfs.moe/blog/test-published-post.md">',
            html=False,
        )

    def test_meta_description_tag(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<meta name="description" content="A test post description">',
            html=False,
        )

    def test_meta_keywords_tag(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<meta name="keywords" content="test,django">',
            html=False,
        )

    def test_og_tags(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<meta property="og:title" content="Test Published Post">',
        )
        self.assertContains(response, '<meta property="og:type" content="article">')
        self.assertContains(
            response,
            '<meta property="og:image" content="https://img.example.com/header.jpg">',
        )

    def test_article_tags_in_meta(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<meta property="article:tag" content="Django">',
        )
        self.assertContains(
            response,
            '<meta property="article:tag" content="Python">',
        )

    def test_article_published_time(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<meta property="article:published_time"',
        )

    def test_twitter_card_large_image_when_og_image_present(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        self.assertContains(
            response,
            '<meta name="twitter:card" content="summary_large_image">',
        )

    def test_twitter_card_summary_when_no_image(self):
        post = Post.objects.create(
            title="No Image Post",
            slug="no-image-post",
            content="Content",
            meta_description="Desc",
            keywords="test",
            status="published",
        )
        response = self.client.get(reverse("blog_post_slug", args=[post.slug]))
        self.assertContains(
            response,
            '<meta name="twitter:card" content="summary">',
        )

    def _get_json_ld(self, response):
        match = re.search(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
            response.content.decode(),
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        return json.loads(match.group(1))

    def test_json_ld(self):
        response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
        data = self._get_json_ld(response)
        self.assertEqual(data["@type"], "BlogPosting")
        self.assertEqual(data["headline"], "Test Published Post")
        self.assertEqual(data["url"], "https://gsgfs.moe/blog/test-published-post")
        self.assertEqual(data["image"], "https://img.example.com/header.jpg")
        self.assertEqual(data["author"], {"@type": "Person", "name": "GSGFs"})
        self.assertIn("datePublished", data)

    def test_json_ld_preserves_special_characters(self):
        post = Post.objects.create(
            title='Quote "</script><script>x</script>',
            slug="json-ld-special-characters",
            content="Content",
            meta_description='Description & <tag> "quoted"',
            keywords="test",
            status="published",
        )
        response = self.client.get(reverse("blog_post_slug", args=[post.slug]))
        data = self._get_json_ld(response)
        self.assertEqual(data["headline"], post.title)
        self.assertEqual(data["description"], post.meta_description)

    def test_post_detail_query_count(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse("blog_post_slug", args=[self.post.slug]))
            self.assertEqual(response.status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False)
class BlogPostIdViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.post = Post.objects.create(
            title="Redirect Test",
            slug="redirect-test",
            content="Content",
            meta_description="Desc",
            keywords="test",
            status="published",
        )

    def test_published_post_redirects_permanently(self):
        response = self.client.get(reverse("blog_post_id", args=[self.post.pk]))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, f"/blog/{self.post.slug}")

    def test_nonexistent_id_returns_404(self):
        response = self.client.get(reverse("blog_post_id", args=[99999]))
        self.assertEqual(response.status_code, 404)


@override_settings(SECURE_SSL_REDIRECT=False)
class BlogRandomPostViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.post = Post.objects.create(
            title="Random Target",
            slug="random-target",
            content="Content",
            meta_description="Desc",
            keywords="test",
            status="published",
        )

    def test_redirects_to_a_published_post(self):
        response = self.client.get(reverse("blog_random_post"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/blog/{self.post.slug}")

    def test_redirects_to_blog_index_when_no_posts(self):
        Post.objects.all().delete()
        response = self.client.get(reverse("blog_random_post"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("blog"))
