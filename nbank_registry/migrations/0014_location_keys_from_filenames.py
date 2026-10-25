"""Sets the key of each location in a neurobank archive that has none to the
resource's file name, which is what neurobank 1.0 records for new deposits. The
file in the archive almost always has that name; neurobank's `check archive
--fix` corrects the few that don't."""

from pathlib import PurePosixPath

from django.db import migrations

_batch_size = 2000


def filename(name: str, extension: str) -> str:
    """The resource's file name, as Resource.filename gives it (historical models
    don't have its methods)."""
    path = PurePosixPath(name)
    if not path.suffix and extension:
        return str(path.with_suffix(f".{extension.lstrip('.')}"))
    return name


def set_keys(apps, schema_editor):
    """A key another location in the archive holds is left unset: keys are unique
    within an archive."""
    Location = apps.get_model("nbank_registry", "Location")
    taken = set(
        Location.objects.filter(key__isnull=False).values_list("archive_id", "key")
    )
    locations = (
        Location.objects.filter(archive__scheme="neurobank", key__isnull=True)
        .select_related("resource__dtype")
        .order_by("id")
    )
    batch = []
    for location in locations.iterator(chunk_size=_batch_size):
        resource = location.resource
        key = filename(resource.name, resource.dtype.extension)
        if (location.archive_id, key) in taken:
            continue
        taken.add((location.archive_id, key))
        location.key = key
        batch.append(location)
        if len(batch) == _batch_size:
            Location.objects.bulk_update(batch, ["key"])
            batch = []
    Location.objects.bulk_update(batch, ["key"])


class Migration(migrations.Migration):
    dependencies = [
        ("nbank_registry", "0013_resource_superseded"),
    ]

    operations = [
        # keys set by the migration can't be told apart from others, so they stay
        migrations.RunPython(set_keys, migrations.RunPython.noop),
    ]
