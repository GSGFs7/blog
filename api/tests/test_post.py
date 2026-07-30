from django.contrib.postgres.search import SearchQuery
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from api.models import Post
from api.tasks import generate_post_chunks_embedding_task as generate_post_embedding


@override_settings(
    SECURE_SSL_REDIRECT=False,
    # make celery sync run the function
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class TestPost(TestCase):
    def setUp(self):
        post = Post.objects.create(
            title="test", content="test content", slug="test", status="published"
        )
        # generate post embedding again
        # it may fail to auto sync generate
        generate_post_embedding(post.id)

    def test_post_embedding_generation(self):
        post = Post.objects.get(title="test")
        self.assertTrue(post.chunks.exists())

    def test_post_api(self):
        post = Post.objects.get(title="test")
        self.assertEqual(post.content, "test content")

        # test API is available
        response = self.client.get("/api/post/")
        self.assertContains(response, post.pk, status_code=200)

        response = self.client.get("/api/post/ids")
        self.assertContains(response, post.pk, status_code=200)

        response = self.client.get(f"/api/post/{post.pk}")
        self.assertContains(response, "test content", status_code=200)

        response = self.client.get(f"/api/post/{post.slug}")
        self.assertContains(response, "test content", status_code=200)

        response = self.client.get("/api/post/sitemap")
        self.assertContains(response, post.pk, status_code=200)

        response = self.client.get("/api/post/search?q=test")
        self.assertContains(response, "test content", status_code=200)

    def test_post_list_structure(self):
        response = self.client.get("/api/post/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("posts", data)
        self.assertIn("pagination", data)
        self.assertIsInstance(data["posts"], list)
        self.assertGreater(len(data["posts"]), 0)
        post = data["posts"][0]
        for field in ("id", "title", "slug", "meta_description", "created_at"):
            self.assertIn(field, post)
        pagination = data["pagination"]
        for field in ("page", "size", "total"):
            self.assertIn(field, pagination)

    def test_post_ids_structure(self):
        response = self.client.get("/api/post/ids")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("ids", data)
        self.assertIsInstance(data["ids"], list)
        self.assertGreater(len(data["ids"]), 0)

    def test_post_detail_structure(self):
        post = Post.objects.get(title="test")
        response = self.client.get(f"/api/post/{post.pk}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for field in (
            "id",
            "title",
            "slug",
            "content",
            "meta_description",
            "status",
            "view_count",
            "created_at",
            "updated_at",
            "content_update_at",
        ):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_post_detail_by_slug_structure(self):
        response = self.client.get("/api/post/test")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["slug"], "test")
        for field in ("id", "title", "content", "created_at"):
            self.assertIn(field, data)

    def test_post_sitemap_structure(self):
        response = self.client.get("/api/post/sitemap")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        item = data[0]
        for field in ("id", "slug", "updated_at"):
            self.assertIn(field, item, f"Missing field: {field}")

    def test_reserve_slug(self):
        # ORM methods, 'api/admin.py' not work
        error_post = None
        try:
            error_post = Post.objects.create(
                title="reserve slug test", content="reserve slug test", slug="posts"
            )
        except Exception as e:
            if isinstance(e, ValidationError):
                pass
            else:
                raise
        if error_post is not None:
            raise

    def test_numeric_slug_rejected(self):
        with self.assertRaises(ValidationError):
            Post.objects.create(
                title="numeric slug test",
                content="numeric slug content",
                slug="123",
            )

    def test_unpublished_post_not_in_api(self):
        draft = Post.objects.create(
            title="draft post",
            content="draft content",
            slug="draft-post",
            status="draft",
        )
        generate_post_embedding(draft.id)

        response = self.client.get("/api/post/")
        data = response.json()
        self.assertFalse(any(p["id"] == draft.id for p in data["posts"]))

        response = self.client.get("/api/post/ids")
        data = response.json()
        self.assertNotIn(draft.id, data["ids"])

        response = self.client.get(f"/api/post/{draft.id}")
        self.assertEqual(response.status_code, 404)

        response = self.client.get(f"/api/post/{draft.slug}")
        self.assertEqual(response.status_code, 404)

        response = self.client.get("/api/post/sitemap")
        data = response.json()
        self.assertFalse(any(item["id"] == draft.id for item in data))

        response = self.client.get("/api/post/search?q=draft")
        data = response.json()
        self.assertFalse(
            any(
                item["post"]["id"] == draft.id for item in data["posts_with_similarity"]
            )
        )


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class TestPostFullTextSearch(TestCase):
    def setUp(self):
        self.post1 = Post.objects.create(
            title="中文测试文章",
            content="这是一篇关于Python和Django的测试文章，包含中文内容。",
            slug="test-fts-1",
            status="published",
        )
        self.post2 = Post.objects.create(
            title="English Test Post",
            content="This is a test post about PostgreSQL full-text search.",
            slug="test-fts-2",
            status="published",
        )
        self.post3 = Post.objects.create(
            title="混合语言文章 Mixed Language",
            content="This post contains both English 中文 and 混合内容 mixed content.",
            slug="test-fts-3",
            status="published",
        )

    def test_application_level_tokenization(self):
        """Test that jieba tokenization works correctly in the save method."""
        post = Post.objects.get(slug="test-fts-1")
        self.assertIsNotNone(post.tokenized_content)
        self.assertIsInstance(post.tokenized_content, str)

        tokens = post.tokenized_content.split()
        self.assertGreater(len(tokens), 0)

        post2 = Post.objects.get(slug="test-fts-2")
        self.assertIsNotNone(post2.tokenized_content)

        post3 = Post.objects.get(slug="test-fts-3")
        self.assertIsNotNone(post3.tokenized_content)

    def test_tokenization_content_preservation(self):
        """Test that tokenized content preserves the original meaning."""
        post = Post.objects.get(slug="test-fts-1")

        self.assertIsNotNone(post.tokenized_content)
        self.assertGreater(len(post.tokenized_content), 0)

    def test_search_vector_generation(self):
        """Test that SearchVector is properly generated and stored."""
        post = Post.objects.get(slug="test-fts-1")
        self.assertIsNotNone(post.pg_gin_search_vector)

        post2 = Post.objects.get(slug="test-fts-2")
        self.assertIsNotNone(post2.pg_gin_search_vector)

        post3 = Post.objects.get(slug="test-fts-3")
        self.assertIsNotNone(post3.pg_gin_search_vector)

    def test_basic_gin_query_single_term(self):
        """Test basic GIN query with a single search term."""
        search_query = SearchQuery("Python")
        results = Post.objects.filter(pg_gin_search_vector=search_query)

        self.assertGreaterEqual(results.count(), 1)

    def test_basic_gin_query_multiple_terms(self):
        """Test basic GIN query with multiple search terms."""
        search_query = SearchQuery("Django")
        results = Post.objects.filter(pg_gin_search_vector=search_query)

        self.assertGreaterEqual(results.count(), 1)

    def test_gin_query_no_match(self):
        """Test GIN query with no matching results."""
        search_query = SearchQuery("nonexistentword123456")
        results = Post.objects.filter(pg_gin_search_vector=search_query)

        self.assertEqual(results.count(), 0)

    def test_gin_query_title_match(self):
        """Test GIN query matching title field."""
        search_query = SearchQuery("中文")
        results = Post.objects.filter(pg_gin_search_vector=search_query)

        self.assertGreaterEqual(results.count(), 1)

    def test_gin_query_content_match(self):
        """Test GIN query matching tokenized_content field."""
        search_query = SearchQuery("PostgreSQL")
        results = Post.objects.filter(pg_gin_search_vector=search_query)

        self.assertGreaterEqual(results.count(), 1)

    def test_fts_integration_full_workflow(self):
        """Test the full workflow from save to search."""
        new_post = Post.objects.create(
            title="全流程测试",
            content="测试完整的全文搜索流程，从保存到查询。",
            slug="full-workflow-test",
            status="published",
        )

        self.assertIsNotNone(new_post.tokenized_content)

        new_post.refresh_from_db()
        self.assertIsNotNone(new_post.pg_gin_search_vector)

        search_query = SearchQuery("流程")
        results = Post.objects.filter(pg_gin_search_vector=search_query)

        self.assertIn(new_post, results)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class TestHybridSearch(TestCase):
    def setUp(self):
        self.post1 = Post.objects.create(
            title="Django入门教程",
            content="Django是一个强大的Python Web框架，用于快速开发网站。",
            slug="hybrid-search-1",
            status="published",
        )
        self.post2 = Post.objects.create(
            title="Python编程基础",
            content="Python是一种流行的编程语言，广泛用于数据分析和机器学习。",
            slug="hybrid-search-2",
            status="published",
        )
        self.post3 = Post.objects.create(
            title="数据库优化技巧",
            content="PostgreSQL是一个强大的关系型数据库，支持全文搜索和向量搜索。",
            slug="hybrid-search-3",
            status="published",
        )
        self.post1.save()
        self.post2.save()
        self.post3.save()
        self.post1.refresh_from_db()
        self.post2.refresh_from_db()
        self.post3.refresh_from_db()

    def tearDown(self):
        cache.clear()

    def test_search_endpoint_basic(self):
        """Test that search endpoint returns correct structure."""
        response = self.client.get("/api/post/search?q=Django")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("posts_with_similarity", data)
        self.assertIn("pagination", data)

    def test_search_pagination(self):
        """Test pagination in search results."""
        response = self.client.get("/api/post/search?q=编程&page=1&size=2")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertLessEqual(len(data["posts_with_similarity"]), 2)
        self.assertEqual(data["pagination"]["page"], 1)
        self.assertEqual(data["pagination"]["size"], 2)
        self.assertGreater(data["pagination"]["total"], 0)

    def test_query_too_long(self):
        """Test that long queries return 400 error."""
        long_query = "a" * 201
        response = self.client.get(f"/api/post/search?q={long_query}")
        self.assertEqual(response.status_code, 400)
        self.assertIn("too long", response.json()["message"].lower())

    def test_search_returns_posts(self):
        """Test that search returns actual Post objects."""
        response = self.client.get("/api/post/search?q=Django")
        data = response.json()

        self.assertGreater(len(data["posts_with_similarity"]), 0)

        result = data["posts_with_similarity"][0]
        self.assertIn("post", result)
        self.assertIn("similarity", result)

        self.assertEqual(result["post"]["id"], self.post1.id)

    def test_empty_search_result(self):
        """Test search with no matching results."""
        response = self.client.get("/api/post/search?q=nonexistent123456")
        data = response.json()

        self.assertEqual(len(data["posts_with_similarity"]), 0)
        self.assertEqual(data["pagination"]["total"], 0)
