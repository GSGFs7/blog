from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from api.admin import PostAdmin
from api.models import Post


class TestPostAdmin(TestCase):
    def test_make_published_preserves_existing_publication_time(self):
        original_published_at = timezone.now() - timedelta(days=30)
        published_post = Post.objects.create(
            title="published post",
            content="published content",
            slug="published-post",
            status="published",
            published_at=original_published_at,
        )
        draft_post = Post.objects.create(
            title="draft post",
            content="draft content",
            slug="draft-post",
        )
        new_published_at = timezone.now()
        model_admin = PostAdmin(Post, admin.site)
        request = RequestFactory().post("/admin/api/post/")

        with (
            patch("api.admin.timezone.now", return_value=new_published_at),
            patch.object(model_admin, "message_user") as message_user,
        ):
            model_admin.make_published(
                request,
                Post.objects.filter(pk__in=[published_post.pk, draft_post.pk]),
            )

        published_post.refresh_from_db()
        draft_post.refresh_from_db()
        self.assertEqual(published_post.published_at, original_published_at)
        self.assertEqual(draft_post.status, "published")
        self.assertEqual(draft_post.published_at, new_published_at)
        message_user.assert_called_once_with(request, "已成功发布 1 篇文章")
