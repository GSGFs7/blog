import uuid

import django.db.models.deletion
from django.db import migrations, models


def populate_guest_uuids(apps, schema_editor):
    alias = schema_editor.connection.alias
    Guest = apps.get_model("api", "Guest")
    Comment = apps.get_model("api", "Comment")
    OAuthIdentity = apps.get_model("api", "OAuthIdentity")
    ContentType = apps.get_model("contenttypes", "ContentType")
    guest_type = (
        ContentType.objects.using(alias).filter(app_label="api", model="guest").first()
    )
    for guest in Guest.objects.using(alias).all().iterator():
        guest_uuid = uuid.uuid4()
        Guest.objects.using(alias).filter(pk=guest.pk).update(uuid=guest_uuid)
        Comment.objects.using(alias).filter(guest_id=guest.pk).update(
            guest_uuid=guest_uuid
        )
        OAuthIdentity.objects.using(alias).filter(guest_id=guest.pk).update(
            guest_uuid=guest_uuid
        )
        if guest_type is not None:
            Image = apps.get_model("media_service", "Image")
            uploads = Image.objects.using(alias).filter(
                uploader_type_id=guest_type.pk, uploader_id=str(guest.pk)
            )
            for upload in uploads.iterator():
                metadata = upload.metadata
                if isinstance(metadata, dict) and "uploader_id" in metadata:
                    metadata = {**metadata, "uploader_id": str(guest_uuid)}
                uploads.filter(pk=upload.pk).update(
                    uploader_id=str(guest_uuid), metadata=metadata
                )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0057_apiclientcredential_and_more"),
        ("media_service", "0004_alter_uploader_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="guest",
            name="uuid",
            field=models.UUIDField(null=True, unique=True),
        ),
        migrations.AddField(
            model_name="comment",
            name="guest_uuid",
            field=models.UUIDField(null=True),
        ),
        migrations.AddField(
            model_name="oauthidentity",
            name="guest_uuid",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(populate_guest_uuids),
        migrations.RemoveField(model_name="comment", name="guest"),
        migrations.RemoveField(model_name="oauthidentity", name="guest"),
        migrations.RemoveField(model_name="guest", name="id"),
        migrations.RenameField(model_name="guest", old_name="uuid", new_name="id"),
        migrations.AlterField(
            model_name="guest",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, primary_key=True, serialize=False
            ),
        ),
        migrations.RenameField(
            model_name="comment", old_name="guest_uuid", new_name="guest"
        ),
        migrations.RenameField(
            model_name="oauthidentity", old_name="guest_uuid", new_name="guest"
        ),
        migrations.AlterField(
            model_name="comment",
            name="guest",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="comments",
                to="api.guest",
            ),
        ),
        migrations.AlterField(
            model_name="oauthidentity",
            name="guest",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="oauth_identities",
                to="api.guest",
            ),
        ),
    ]
