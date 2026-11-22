from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("media_service", "0003_imageresource_responsive_variants_enabled_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="image",
            name="uploader_id",
            field=models.CharField(max_length=36),
        ),
    ]
