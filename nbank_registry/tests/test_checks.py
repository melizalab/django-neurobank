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
