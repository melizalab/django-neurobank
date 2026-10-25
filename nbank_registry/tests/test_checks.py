# -*- mode: python -*-
"""Django's system checks and the migrations, which the other tests skip (they
build the database from the models)."""

import pytest
from django.core.management import call_command


def test_system_checks_pass():
    call_command("check", fail_level="WARNING")


@pytest.mark.django_db
def test_migrations_match_the_models(settings):
    # --no-migrations turns off every app's migrations, which makemigrations
    # would then skip
    settings.MIGRATION_MODULES = {}
    # exits with status 1 if a migration is missing
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_metadata_aliases_setting_is_an_error(settings):
    from django.core.management.base import SystemCheckError

    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    with pytest.raises(SystemCheckError, match="NBANK_METADATA_ALIASES"):
        call_command("check")


@pytest.fixture
def keyed_locations(user):
    """Returns a function that runs the migration setting keys from file names, and
    the locations it was given."""
    import importlib

    from django.apps import apps

    from nbank_registry.models import Archive, DataType, Location, Resource

    migration = importlib.import_module(
        "nbank_registry.migrations.0014_location_keys_from_filenames"
    )
    wav = DataType.objects.create(name="wav", extension="wav")
    plain = DataType.objects.create(name="plain", extension="")
    archives = {
        scheme: Archive.objects.create(name=scheme, scheme=scheme, root=f"/{scheme}")
        for scheme in ("neurobank", "tape", "https")
    }

    def locate(name, dtype, scheme="neurobank", key=None):
        resource = Resource.objects.create(name=name, dtype=dtype, created_by=user)
        return Location.objects.create(
            resource=resource, archive=archives[scheme], key=key
        )

    def run():
        migration.set_keys(apps, None)
        return {
            (loc.archive.scheme, loc.resource.name): loc.key
            for loc in Location.objects.select_related("archive", "resource")
        }

    return locate, wav, plain, run


@pytest.mark.django_db
def test_migration_sets_keys_from_file_names(keyed_locations):
    locate, wav, plain, run = keyed_locations
    locate("res_1", wav)
    locate("res_2.json", wav)
    locate("res_3", plain)
    locate("res_4", wav, key="res_4.flac")
    locate("res_5", wav, scheme="tape")
    locate("res_6", wav, scheme="https")
    assert run() == {
        ("neurobank", "res_1"): "res_1.wav",
        ("neurobank", "res_2.json"): "res_2.json",
        ("neurobank", "res_3"): "res_3",
        # a key is never replaced
        ("neurobank", "res_4"): "res_4.flac",
        # only neurobank archives' keys are file names
        ("tape", "res_5"): None,
        ("https", "res_6"): None,
    }


@pytest.mark.django_db
def test_migration_leaves_a_taken_key_unset(keyed_locations):
    locate, wav, plain, run = keyed_locations
    # both would be res_7.wav
    locate("res_7", wav)
    locate("res_7.wav", plain)
    locate("res_8", wav, key="res_9.wav")
    locate("res_9", wav)
    keys = run()
    assert {keys[("neurobank", "res_7")], keys[("neurobank", "res_7.wav")]} == {
        "res_7.wav",
        None,
    }
    assert keys[("neurobank", "res_9")] is None


@pytest.mark.django_db
def test_migration_updates_in_batches(keyed_locations, monkeypatch):
    import importlib

    locate, wav, plain, run = keyed_locations
    migration = importlib.import_module(
        "nbank_registry.migrations.0014_location_keys_from_filenames"
    )
    monkeypatch.setattr(migration, "_batch_size", 2)
    for i in range(5):
        locate(f"res_{i}", wav)
    assert all(key == f"{name}.wav" for (_, name), key in run().items())
