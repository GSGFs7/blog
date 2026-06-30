import json

from django.test import TestCase, override_settings

from api.auth import TimeBaseAuth
from api.models import Comment, Guest, OAuthIdentity, OAuthProvider, Post


@override_settings(SECURE_SSL_REDIRECT=False)
class TestComment(TestCase):
    def setUp(self) -> None:
        Post.objects.create(
            title="comment test", content="comment test", slug="comment_test"
        )
        self.guest = Guest.objects.create(
            name="test-user",
            email="test-user@example.com",
            avatar="https://example.com/avatar.png",
        )
        provider = OAuthProvider.objects.create(
            provider_key="myself",
            name="Myself",
            client_id="test-client",
            client_secret="test-secret",
            authorization_url="https://example.com/authorize",
            token_url="https://example.com/token",
            userinfo_url="https://example.com/userinfo",
        )
        OAuthIdentity.objects.create(
            guest=self.guest,
            provider=provider,
            user_id="114514",
        )

    def test_new_comment_endpoint(self) -> None:
        data = {
            "provider_key": "myself",
            "user_id": "114514",
            "content": "test comment",
            "post_id": Post.objects.get(title="comment test").pk,
            "metadata": {
                "user_agent": "UA",
                "platform": "Linux",
                "browser": "firefox",
                "browser_version": "114",
                "OS": "ArchLinux",
            },
        }

        # unauthed test
        response = self.client.post(
            "/api/comment/new",
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

        # authed test
        token = TimeBaseAuth.create_token("test comment")
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.post(
            "/api/comment/new",
            data=json.dumps(data),
            headers=headers,
            content_type="application/json",
            # or use this replace 'headers=headers'
            # HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(response.status_code, 200)
        created_comment = Comment.objects.latest("id")
        response_data = json.loads(response.content)
        self.assertEqual(response_data["id"], created_comment.pk)

    def test_get_all_comment_from_post_performance(self):
        post = Post.objects.get(title="comment test")
        # Create multiple comments
        for i in range(5):
            Comment.objects.create(
                content=f"test comment {i}",
                post=post,
                guest=self.guest,
            )

        # The number of queries should be constant regardless of the number of comments
        with self.assertNumQueries(2):
            response = self.client.get(f"/api/comment/post/{post.pk}/all")
            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            self.assertEqual(len(response_data["comments"]), 5)

    def test_get_all_comment_from_non_existent_post(self):
        response = self.client.get("/api/comment/post/99999/all")
        self.assertEqual(response.status_code, 404)

        response = self.client.get("/api/comment/post/99999/ids")
        self.assertEqual(response.status_code, 404)
