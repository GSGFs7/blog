from django.db import migrations, models


def backfill_published_at(apps, schema_editor):
    Post = apps.get_model("api", "Post")
    Post.objects.filter(status="published", published_at__isnull=True).update(
        published_at=models.F("created_at")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0053_post_published_at"),
    ]

    operations = [
        migrations.RunPython(backfill_published_at, migrations.RunPython.noop)
    ]
