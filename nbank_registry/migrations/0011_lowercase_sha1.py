from django.db import migrations


def lowercase_sha1(apps, schema_editor):
    Resource = apps.get_model("nbank_registry", "Resource")
    for resource in Resource.objects.exclude(sha1__isnull=True).exclude(sha1=""):
        lowered = resource.sha1.lower()
        if lowered != resource.sha1:
            resource.sha1 = lowered
            resource.save(update_fields=["sha1"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("nbank_registry", "0010_location_key"),
    ]

    operations = [
        migrations.RunPython(lowercase_sha1, noop),
    ]
