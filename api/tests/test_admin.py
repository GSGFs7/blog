from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from api.admin import (
    ApiClientAdmin,
    ApiClientCredentialInline,
    ApiClientCredentialInlineForm,
    PostAdmin,
)
from api.models import ApiClient, ApiClientCredential, Post


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


class TestApiClientAdmin(TestCase):
    def test_credential_is_managed_only_through_client(self):
        self.assertNotIn(ApiClientCredential, admin.site._registry)
        self.assertEqual(ApiClientAdmin.inlines, [ApiClientCredentialInline])

    def test_add_client_creates_credential_and_shows_it_on_change(self):
        request = RequestFactory().post("/not-admin/api/apiclient/add/")
        client_admin = ApiClientAdmin(ApiClient, admin.site)
        client_form = client_admin.get_form(request)(
            data={"client_id": "new-client", "scopes": "[]"}
        )
        self.assertTrue(client_form.is_valid(), client_form.errors)
        client = client_admin.save_form(request, client_form, change=False)
        with patch.object(client_admin, "message_user") as message_user:
            client_admin.save_model(request, client, client_form, change=False)

        credential = client.credentials.get()
        self.assertTrue(credential.kid)
        self.assertTrue(credential.secret)
        self.assertIn(credential.kid, message_user.call_args.args[1])
        self.assertIn(credential.secret, message_user.call_args.args[1])
        fields = client_admin.get_fieldsets(request, client)[0][1]["fields"]
        self.assertNotIn("masked_secret", fields)
        self.assertEqual(len(client_admin.get_inlines(request, client)), 1)
        self.assertEqual(client_admin.get_inlines(request, None), [])

        client_admin.save_model(request, client, client_form, change=True)
        self.assertEqual(client.credentials.count(), 1)

    def test_inline_creates_updates_and_revokes_credentials(self):
        client = ApiClient.objects.create(client_id="inline-client")
        credential = ApiClientCredential.objects.create(
            client=client, kid="existing-key", secret="existing-secret"
        )
        self.assertFalse(
            ApiClientCredentialInlineForm(instance=credential).fields["revoke"].disabled
        )
        request = RequestFactory().post("/not-admin/api/apiclient/1/change/")
        request.user = SimpleNamespace(has_perm=lambda permission: True)
        client_admin = ApiClientAdmin(ApiClient, admin.site)
        inline = ApiClientCredentialInline(ApiClient, admin.site)
        formset_class = inline.get_formset(request, client)
        self.assertEqual(formset_class(instance=client).total_form_count(), 1)
        prefix = formset_class.get_default_prefix()
        expires_at = timezone.now() + timedelta(days=7)
        formset = formset_class(
            data={
                f"{prefix}-TOTAL_FORMS": "2",
                f"{prefix}-INITIAL_FORMS": "1",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
                f"{prefix}-0-id": str(credential.pk),
                f"{prefix}-0-description": "old integration",
                f"{prefix}-0-expires_at_0": expires_at.date().isoformat(),
                f"{prefix}-0-expires_at_1": expires_at.time().strftime("%H:%M:%S"),
                f"{prefix}-0-revoke": "on",
                f"{prefix}-1-description": "new integration",
                f"{prefix}-1-expires_at_0": expires_at.date().isoformat(),
                f"{prefix}-1-expires_at_1": expires_at.time().strftime("%H:%M:%S"),
            },
            instance=client,
            prefix=prefix,
        )
        self.assertTrue(formset.is_valid(), formset.errors)

        with patch.object(client_admin, "message_user") as message_user:
            client_admin.save_formset(request, None, formset, change=True)

        credential.refresh_from_db()
        self.assertEqual(credential.description, "old integration")
        self.assertIsNotNone(credential.revoked_at)
        self.assertIsNotNone(credential.expires_at)
        revoked_form = ApiClientCredentialInlineForm(instance=credential)
        self.assertTrue(revoked_form.fields["revoke"].disabled)
        self.assertTrue(revoked_form.fields["revoke"].initial)
        new_credential = client.credentials.exclude(pk=credential.pk).get()
        self.assertEqual(new_credential.description, "new integration")
        self.assertTrue(new_credential.kid)
        self.assertTrue(new_credential.secret)
        self.assertIn(new_credential.secret, message_user.call_args.args[1])

    def test_inline_creates_credential_without_expiration(self):
        client = ApiClient.objects.create(client_id="blank-inline-client")
        request = RequestFactory().post("/not-admin/api/apiclient/1/change/")
        request.user = SimpleNamespace(has_perm=lambda permission: True)
        client_admin = ApiClientAdmin(ApiClient, admin.site)
        inline = ApiClientCredentialInline(ApiClient, admin.site)
        formset_class = inline.get_formset(request, client)
        prefix = formset_class.get_default_prefix()
        self.assertEqual(formset_class(instance=client).total_form_count(), 0)
        formset = formset_class(
            data={
                f"{prefix}-TOTAL_FORMS": "2",
                f"{prefix}-INITIAL_FORMS": "0",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
            },
            instance=client,
            prefix=prefix,
        )
        self.assertTrue(formset.is_valid(), formset.errors)

        with patch.object(client_admin, "message_user") as message_user:
            client_admin.save_formset(request, None, formset, change=True)

        self.assertEqual(client.credentials.count(), 2)
        self.assertEqual(message_user.call_count, 2)
        self.assertTrue(all(item.secret for item in client.credentials.all()))
        self.assertTrue(all(not item.description for item in client.credentials.all()))

        unchanged_formset = formset_class(
            data={
                f"{prefix}-TOTAL_FORMS": "2",
                f"{prefix}-INITIAL_FORMS": "2",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
                **{
                    f"{prefix}-{index}-id": str(credential.pk)
                    for index, credential in enumerate(client.credentials.all())
                },
            },
            instance=client,
            prefix=prefix,
        )
        self.assertTrue(unchanged_formset.is_valid(), unchanged_formset.errors)
        client_admin.save_formset(request, None, unchanged_formset, change=True)
        self.assertEqual(client.credentials.count(), 2)
