from uuid import UUID

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class GuestUUIDMigrationTest(TransactionTestCase):
    def test_preserves_guest_relationships(self):
        executor = MigrationExecutor(connection)
        before = [
            ("api", "0057_apiclientcredential_and_more"),
            (
                "media_service",
                "0003_imageresource_responsive_variants_enabled_and_more",
            ),
        ]
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA guest_uuid_migration_test")
            cursor.execute("SET search_path TO guest_uuid_migration_test, public")
        self.addCleanup(self.cleanup_schema)
        state = executor.loader.project_state(before)
        apps = state.apps
        with connection.schema_editor() as editor:
            for model in apps.get_models():
                editor.create_model(model)
        Guest = apps.get_model("api", "Guest")
        guests = [
            Guest.objects.create(name=name, email=f"{name}@example.com", avatar="")
            for name in ("first", "second")
        ]
        post = apps.get_model("api", "Post").objects.create(
            title="UUID migration",
            slug="uuid-migration",
            content="test",
            content_update_at=timezone.now(),
        )
        provider = apps.get_model("api", "OAuthProvider").objects.create(
            provider_key="test", name="Test"
        )
        guest_type, _ = apps.get_model(
            "contenttypes", "ContentType"
        ).objects.get_or_create(app_label="api", model="guest")
        admin_type, _ = apps.get_model(
            "contenttypes", "ContentType"
        ).objects.get_or_create(app_label="auth", model="user")
        resource = apps.get_model("media_service", "ImageResource").objects.create(
            checksum="migration-test", file="test.png", width=1, height=1, size=1
        )
        Image = apps.get_model("media_service", "Image")
        admin_image = Image.objects.create(
            resource=resource, uploader_type=admin_type, uploader_id=guests[0].pk
        )
        old_admin_id = str(guests[0].pk)
        for guest in guests:
            apps.get_model("api", "Comment").objects.create(
                guest=guest, post=post, content=guest.name
            )
            apps.get_model("api", "OAuthIdentity").objects.create(
                guest=guest, provider=provider, user_id=guest.name
            )
            Image.objects.create(
                resource=resource,
                uploader_type=guest_type,
                uploader_id=guest.pk,
                original_name=guest.name,
                metadata={"uploader_id": guest.pk, "other": "preserved"},
            )

        for key in (
            ("media_service", "0004_alter_uploader_ids"),
            ("api", "0058_alter_guest_id"),
        ):
            with connection.schema_editor() as editor:
                state = executor.loader.get_migration(*key).apply(state, editor)
        apps = state.apps
        Guest = apps.get_model("api", "Guest")
        Image = apps.get_model("media_service", "Image")
        self.assertEqual(Guest.objects.count(), 2)
        for guest in Guest.objects.all():
            self.assertIsInstance(guest.pk, UUID)
            self.assertEqual(guest.pk.version, 4)
            comment = apps.get_model("api", "Comment").objects.get(content=guest.name)
            identity = apps.get_model("api", "OAuthIdentity").objects.get(
                user_id=guest.name
            )
            image = Image.objects.get(original_name=guest.name)
            self.assertEqual(comment.guest_id, guest.pk)
            self.assertEqual(identity.guest_id, guest.pk)
            self.assertEqual(image.uploader_id, str(guest.pk))
            self.assertEqual(
                image.metadata, {"uploader_id": str(guest.pk), "other": "preserved"}
            )
        self.assertEqual(Image.objects.get(pk=admin_image.pk).uploader_id, old_admin_id)
        new_guest = Guest.objects.create(name="new", email="new@example.com", avatar="")
        self.assertIsInstance(new_guest.pk, UUID)
        self.assertEqual(Guest.objects.values("id").distinct().count(), 3)

    def cleanup_schema(self):
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            cursor.execute("DROP SCHEMA guest_uuid_migration_test CASCADE")
