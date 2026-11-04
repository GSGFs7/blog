from unittest.mock import patch

from django.db.backends.utils import CursorWrapper
from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import Category, Post, Tag


@override_settings(SECURE_SSL_REDIRECT=False)
class PostListQueryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Query category")
        cls.tag = Tag.objects.create(name="Query tag")
        cls.posts = Post.objects.bulk_create(
            [
                Post(
                    title=f"Query post {i}",
                    slug=f"query-post-{i}",
                    content="Large body " * 10000,
                    content_html="<p>Large HTML</p>" * 10000,
                    tokenized_content="Large tokens " * 10000,
                    toc=[{"title": "Heading", "id": "heading"}],
                    category=cls.category,
                    status="published",
                    content_update_at=timezone.now(),
                )
                for i in range(2)
            ]
        )
        for post in cls.posts:
            post.tags.add(cls.tag)

    def test_cards_serialize_relations_without_loading_large_fields(self):
        queries = []
        execute = CursorWrapper.execute

        def record(cursor, sql, params=None):
            queries.append(sql)
            return execute(cursor, sql, params)

        with patch.object(CursorWrapper, "execute", record):
            response = self.client.get("/api/post?page=1&size=10")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pagination"]["total"], 2)
        self.assertEqual(len(data["posts"]), 2)
        for card in data["posts"]:
            self.assertEqual(
                card["category"],
                {"id": self.category.id, "name": self.category.name},
            )
            self.assertEqual(card["tags"], [{"id": self.tag.id, "name": self.tag.name}])
            self.assertNotIn("content", card)
            self.assertNotIn("content_html", card)

        post_queries = [
            sql
            for sql in queries
            if sql.lstrip().upper().startswith("SELECT") and '"api_post"."id"' in sql
        ]
        self.assertEqual(len(post_queries), 1)
        for field in (
            "content",
            "content_html",
            "toc",
            "tokenized_content",
            "pg_gin_search_vector",
        ):
            self.assertNotIn(f'"api_post"."{field}"', post_queries[0])
