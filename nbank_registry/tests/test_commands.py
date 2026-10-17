# -*- mode: python -*-
import sys
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from nbank_registry.models import DataType, Resource

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

pytestmark = pytest.mark.django_db

UUID = "6d6ba7c4-3ea6-4bfa-a1d0-0f0a76d8bd3b"


@pytest.fixture
def make(user):
    dtype = DataType.objects.create(name="ext-arf", content_type="x")

    def make(metadata, **fields):
        return Resource.objects.create(
            dtype=dtype, created_by=user, metadata=metadata, **fields
        )

    return make


def promote(tmp_path, mappings=None, *args):
    """Runs the command; returns (stdout, stderr)."""
    if mappings is not None:
        path = tmp_path / "mappings.toml"
        path.write_text(mappings)
        args = ("--mappings", str(path), *args)
    out, err = StringIO(), StringIO()
    call_command("promote_metadata", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_valid_values_are_moved(tmp_path, make, user):
    res = make(
        {"experimenter": "user", "animal": f" {UUID} ", "protocol": "chorus", "pen": 1}
    )
    promote(tmp_path)
    res.refresh_from_db()
    assert res.experimenter == user
    assert (res.animal, res.protocol) == (UUID, "chorus")
    assert res.metadata == {"pen": 1}


def test_invalid_values_are_left_in_metadata(tmp_path, make):
    metadata = {"experimenter": "nobody", "protocol": "not a slug", "animal": [1]}
    res = make(metadata)
    _, err = promote(tmp_path)
    res.refresh_from_db()
    assert res.metadata == metadata
    assert (res.experimenter, res.animal, res.protocol) == (None, None, None)
    assert "unresolved 1" in err


def test_dry_run_changes_nothing(tmp_path, make):
    res = make({"protocol": "chorus"})
    _, err = promote(tmp_path, None, "--dry-run")
    res.refresh_from_db()
    assert res.protocol is None
    assert res.metadata == {"protocol": "chorus"}
    assert "would change 1" in err


def test_aliases_from_mappings_and_settings(tmp_path, make, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    res = make({"bird": "P50", "experiment": "chorus"})
    promote(tmp_path, '[aliases]\nexperiment = "protocol"\n')
    res.refresh_from_db()
    assert (res.animal, res.protocol) == ("P50", "chorus")
    assert res.metadata == {}


def test_values_are_mapped(tmp_path, make):
    res = make({"protocol": "song_chorus", "animal": "B2"})
    promote(
        tmp_path, f'[protocol]\nsong_chorus = "song-chorus"\n[animal]\nB2 = "{UUID}"\n'
    )
    res.refresh_from_db()
    assert (res.animal, res.protocol) == (UUID, "song-chorus")


def test_mapping_makes_an_invalid_value_valid(tmp_path, make, user):
    res = make({"experimenter": "bbellanger"})
    promote(tmp_path, '[experimenter]\nbbellanger = "user"\n')
    res.refresh_from_db()
    assert res.experimenter == user
    assert res.metadata == {}


def test_move_leaves_field_empty_and_renames_key(tmp_path, make):
    res = make({"animal": "synthetic"})
    promote(tmp_path, '[animal]\nsynthetic = { move = "source" }\n')
    res.refresh_from_db()
    assert res.animal is None
    assert res.metadata == {"source": "synthetic"}


def test_move_onto_a_different_value_is_a_conflict(tmp_path, make):
    res = make({"animal": "synthetic", "source": "other"})
    _, err = promote(tmp_path, '[animal]\nsynthetic = { move = "source" }\n')
    res.refresh_from_db()
    assert res.metadata == {"animal": "synthetic", "source": "other"}
    assert f"conflict in {res.name}: animal" in err


def test_users_are_created_inactive(tmp_path, make):
    res = make({"experimenter": "bple"})
    promote(tmp_path, '[users]\ncreate = ["bple"]\n')
    res.refresh_from_db()
    assert res.experimenter.username == "bple"
    assert not res.experimenter.is_active
    assert not res.experimenter.has_usable_password()


def test_dry_run_creates_no_users(tmp_path, make):
    make({"experimenter": "bple"})
    _, err = promote(tmp_path, '[users]\ncreate = ["bple"]\n', "--dry-run")
    assert not User.objects.filter(username="bple").exists()
    assert "would change 1" in err


def test_keys_that_disagree_are_a_conflict(tmp_path, make, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    metadata = {"bird": "P50", "animal": "P51", "protocol": "chorus"}
    res = make(metadata)
    _, err = promote(tmp_path)
    res.refresh_from_db()
    # the other fields are still moved
    assert res.protocol == "chorus"
    assert res.metadata == {"bird": "P50", "animal": "P51"}
    assert f"conflict in {res.name}: animal" in err


def test_keys_that_map_to_the_same_value_agree(tmp_path, make, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    res = make({"bird": "B2", "animal": UUID})
    promote(tmp_path, f'[animal]\nB2 = "{UUID}"\n')
    res.refresh_from_db()
    assert res.animal == UUID
    assert res.metadata == {}


def test_field_already_set_to_another_value_is_a_conflict(tmp_path, make):
    res = make({"protocol": "chorus"}, protocol="other")
    _, err = promote(tmp_path)
    res.refresh_from_db()
    assert res.protocol == "other"
    assert res.metadata == {"protocol": "chorus"}
    assert "already 'other'" in err


def test_blank_values_are_removed(tmp_path, make):
    res = make({"animal": " ", "pen": 1})
    promote(tmp_path)
    res.refresh_from_db()
    assert res.animal is None
    assert res.metadata == {"pen": 1}


def test_runs_in_batches(tmp_path, make):
    resources = [make({"protocol": f"p{i}"}) for i in range(5)]
    _, err = promote(tmp_path, None, "--batch-size", "2")
    assert "changed 5" in err
    assert [Resource.objects.get(pk=r.pk).protocol for r in resources] == [
        f"p{i}" for i in range(5)
    ]


@pytest.mark.parametrize(
    "mappings",
    [
        "[bird]\n",
        '[aliases]\nbird = "species"\n',
        '[aliases]\nanimal = "protocol"\n',
        '[users]\ncreate = ["not a name"]\n',
        '[experimenter]\nbbellanger = "nobody"\n',
        '[protocol]\nsong_chorus = "song chorus"\n',
        '[protocol]\nsong_chorus = ""\n',
        '[animal]\nsynthetic = { move = "animal" }\n',
        '[animal]\nsynthetic = { rename = "source" }\n',
        "not toml",
    ],
)
def test_bad_mappings_are_refused(tmp_path, make, mappings):
    res = make({"protocol": "chorus"})
    with pytest.raises(CommandError):
        promote(tmp_path, mappings)
    res.refresh_from_db()
    assert res.metadata == {"protocol": "chorus"}


def test_template(tmp_path, make, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    make({"experimenter": "bple", "bird": "B2", "protocol": "song chorus"})
    make({"experimenter": "user", "bird": UUID, "protocol": "chorus"})
    make({"experimenter": "bple", "bird": "synthetic"})
    out, _ = promote(
        tmp_path,
        '[aliases]\nexperiment = "protocol"\n[animal]\nsynthetic = { move = "source" }\n',
        "--dry-run",
    )
    template = tomllib.loads(out)
    # mappings carry over; found values are commented out
    assert template == {
        "aliases": {"experiment": "protocol"},
        "users": {"create": []},
        "experimenter": {},
        "animal": {"synthetic": {"move": "source"}},
        "protocol": {},
    }
    lines = out.splitlines()
    assert '    # "bple",  # 2 resources' in lines
    assert '# "bird" = "animal"  # from NBANK_METADATA_ALIASES' in lines
    assert '"synthetic" = { move = "source" }  # 1 resources' in lines
    assert '# "song chorus" = ""  # 1 resources: not a slug' in lines
    # values that can't be stored come first
    assert lines.index('# "bple" = ""  # 2 resources: no such user') < lines.index(
        '# "user" = ""  # 1 resources'
    )


def test_template_round_trips(tmp_path, make):
    make({"experimenter": "bple", "protocol": "song_chorus"})
    out, _ = promote(tmp_path, None, "--dry-run")
    filled = out.replace('    # "bple",', '    "bple",').replace(
        '# "song_chorus" = ""', '"song_chorus" = "song-chorus"'
    )
    out, err = promote(tmp_path, filled, "--dry-run")
    assert "would change 1" in err
    assert tomllib.loads(out)["users"] == {"create": ["bple"]}
    assert tomllib.loads(out)["protocol"] == {"song_chorus": "song-chorus"}


def test_value_too_long_for_field_is_left(tmp_path, make):
    res = make({"protocol": "p" * 65})
    out, _ = promote(tmp_path, None, "--dry-run")
    res.refresh_from_db()
    assert res.protocol is None
    assert "longer than 64 characters" in out
