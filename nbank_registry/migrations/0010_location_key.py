from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nbank_registry", "0009_archive_accessibility"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="key",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=1024,
                help_text="address of the resource within the archive, if it "
                "can't be derived from the resource name",
            ),
        ),
        migrations.AddConstraint(
            model_name="location",
            constraint=models.UniqueConstraint(
                condition=models.Q(("key__isnull", False)),
                fields=("archive", "key"),
                name="location_unique_key_per_archive",
            ),
        ),
    ]
