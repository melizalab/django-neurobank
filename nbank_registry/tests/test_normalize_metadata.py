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


@pytest.fixture
def p50(animal):
    return animal("P50")


@pytest.fixture
def p51(animal):
    return animal("P51")


def animal_of(res):
    res.refresh_from_db()
    return str(res.animal_id) if res.animal_id else None


@pytest.fixture
def make(user):
    dtype = DataType.objects.create(name="ext-arf", content_type="x")

    def make(metadata, **fields):
        return Resource.objects.create(
            dtype=dtype, created_by=user, metadata=metadata, **fields
        )

    return make


def normalize(tmp_path, mappings=None, *args):
    """Runs the command; returns (stdout, stderr)."""
    if mappings is not None:
        path = tmp_path / "mappings.toml"
        path.write_text(mappings)
        args = ("--mappings", str(path), *args)
    out, err = StringIO(), StringIO()
    call_command("normalize_metadata", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_valid_values_are_moved(tmp_path, make, user, p50):
    res = make({"experimenter": "user", "animal": f" {p50.upper()} ", "pen": 1})
    normalize(tmp_path)
    assert animal_of(res) == p50
    assert res.experimenter == user
    assert res.metadata == {"pen": 1}


def test_other_keys_are_left_in_metadata(tmp_path, make):
    res = make({"protocol": "chorus", "experiment": "chorus"})
    _, err = normalize(tmp_path)
    res.refresh_from_db()
    assert res.metadata == {"protocol": "chorus", "experiment": "chorus"}
    assert "changed 0" in err


@pytest.mark.parametrize(
    "metadata",
    [
        {"experimenter": "nobody"},
        {"animal": "P99"},
        {"animal": "15db7d088-f7c5-4bed-b77d-77ac55583174"},
        {"animal": [1]},
    ],
)
def test_invalid_values_are_left_in_metadata(tmp_path, make, metadata):
    res = make(metadata)
    _, err = normalize(tmp_path)
    assert animal_of(res) is None
    assert (res.experimenter, res.metadata) == (None, metadata)
    assert "unresolved 1" in err


def test_dry_run_changes_nothing(tmp_path, make, p50):
    res = make({"animal": p50})
    _, err = normalize(tmp_path, None, "--dry-run")
    assert animal_of(res) is None
    assert res.metadata == {"animal": p50}
    assert "would change 1" in err


def test_aliases_from_mappings_and_settings(tmp_path, make, user, p50, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    res = make({"bird": p50, "experiemtner": "user"})
    normalize(tmp_path, '[aliases]\nexperiemtner = "experimenter"\n')
    assert animal_of(res) == p50
    assert (res.experimenter, res.metadata) == (user, {})


def test_values_are_mapped(tmp_path, make, user, p50):
    res = make({"experimenter": "bbellanger", "animal": "B2"})
    normalize(
        tmp_path, f'[experimenter]\nbbellanger = "user"\n[animal]\nB2 = "{p50}"\n'
    )
    assert animal_of(res) == p50
    assert (res.experimenter, res.metadata) == (user, {})


def test_move_leaves_field_empty_and_renames_key(tmp_path, make):
    res = make({"animal": "synthetic"})
    normalize(tmp_path, '[animal]\nsynthetic = { move = "source" }\n')
    assert animal_of(res) is None
    assert res.metadata == {"source": "synthetic"}


def test_move_onto_a_different_value_is_a_conflict(tmp_path, make):
    res = make({"animal": "synthetic", "source": "other"})
    _, err = normalize(tmp_path, '[animal]\nsynthetic = { move = "source" }\n')
    res.refresh_from_db()
    assert res.metadata == {"animal": "synthetic", "source": "other"}
    assert f"conflict in {res.name}: animal" in err


def test_users_are_created_inactive(tmp_path, make):
    res = make({"experimenter": "bple"})
    normalize(tmp_path, '[users]\ncreate = ["bple"]\n')
    res.refresh_from_db()
    assert res.experimenter.username == "bple"
    assert not res.experimenter.is_active
    assert not res.experimenter.has_usable_password()


def test_dry_run_creates_no_users(tmp_path, make):
    make({"experimenter": "bple"})
    _, err = normalize(tmp_path, '[users]\ncreate = ["bple"]\n', "--dry-run")
    assert not User.objects.filter(username="bple").exists()
    assert "would change 1" in err


def test_keys_that_disagree_are_a_conflict(tmp_path, make, user, p50, p51, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    res = make({"bird": p50, "animal": p51, "experimenter": "user"})
    _, err = normalize(tmp_path)
    assert animal_of(res) is None
    # the other fields are still moved
    assert res.experimenter == user
    assert res.metadata == {"bird": p50, "animal": p51}
    assert f"conflict in {res.name}: animal" in err


def test_keys_that_map_to_the_same_value_agree(tmp_path, make, p50, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    res = make({"bird": "B2", "animal": p50})
    normalize(tmp_path, f'[animal]\nB2 = "{p50}"\n')
    assert animal_of(res) == p50
    assert res.metadata == {}


def test_field_already_set_to_another_value_is_a_conflict(tmp_path, make, p50, p51):
    res = make({"animal": p50}, animal_id=p51)
    _, err = normalize(tmp_path)
    assert animal_of(res) == p51
    assert res.metadata == {"animal": p50}
    assert f"already '{p51}'" in err


def test_blank_values_are_removed(tmp_path, make):
    res = make({"animal": " ", "pen": 1})
    normalize(tmp_path)
    assert animal_of(res) is None
    assert res.metadata == {"pen": 1}


def test_runs_in_batches(tmp_path, make, animal):
    animals = [animal(f"P{i}") for i in range(5)]
    resources = [make({"animal": a}) for a in animals]
    _, err = normalize(tmp_path, None, "--batch-size", "2")
    assert "changed 5" in err
    assert [animal_of(r) for r in resources] == animals


@pytest.mark.parametrize(
    "mappings",
    [
        "[bird]\n",
        '[protocol]\nsong_chorus = "song-chorus"\n',
        "[aliases]\nexperiment = 5\n",
        '[aliases]\nexperiment = "protocol"\nprotocol = "experiment"\n',
        "[metadata.animal]\n",
        "[metadata.protocol]\nchorus = 5\n",
        '[metadata]\nprotocol = "chorus"\n',
        '[aliases]\nexperiment = "protocol"\n[metadata.experiment]\n',
        '[aliases]\nanimal = "experimenter"\n',
        '[users]\ncreate = ["not a name"]\n',
        '[experimenter]\nbbellanger = "nobody"\n',
        '[animal]\nB2 = "P99"\n',
        '[animal]\nB2 = ""\n',
        '[animal]\nsynthetic = { move = "animal" }\n',
        '[animal]\nsynthetic = { rename = "source" }\n',
        "not toml",
    ],
)
def test_bad_mappings_are_refused(tmp_path, make, mappings):
    res = make({"animal": "P50"})
    with pytest.raises(CommandError):
        normalize(tmp_path, mappings)
    res.refresh_from_db()
    assert res.metadata == {"animal": "P50"}


def test_template(tmp_path, make, p50, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    make({"experimenter": "bple", "bird": "B2"})
    make({"experimenter": "user", "bird": p50})
    make({"experimenter": "bple", "bird": "synthetic"})
    out, _ = normalize(
        tmp_path,
        '[aliases]\nexperiemtner = "experimenter"\n'
        '[animal]\nsynthetic = { move = "source" }\n',
        "--dry-run",
    )
    template = tomllib.loads(out)
    # mappings carry over; found values are commented out
    assert template == {
        "aliases": {"experiemtner": "experimenter"},
        "users": {"create": []},
        "experimenter": {},
        "animal": {"synthetic": {"move": "source"}},
    }
    lines = out.splitlines()
    assert '    # "bple",  # 2 resources' in lines
    assert '# "bird" = "animal"  # from NBANK_METADATA_ALIASES' in lines
    assert '"synthetic" = { move = "source" }  # 1 resources' in lines
    assert '# "B2" = ""  # 1 resources: no such animal' in lines
    # values that can't be stored come first
    assert lines.index('# "bple" = ""  # 2 resources: no such user') < lines.index(
        '# "user" = ""  # 1 resources'
    )
    assert lines.index('# "B2" = ""  # 1 resources: no such animal') < lines.index(
        f'# "{p50}" = ""  # 1 resources'
    )


def test_template_round_trips(tmp_path, make, p50):
    make({"experimenter": "bple", "animal": "B2"})
    out, _ = normalize(tmp_path, None, "--dry-run")
    filled = out.replace('    # "bple",', '    "bple",').replace(
        '# "B2" = ""', f'"B2" = "{p50}"'
    )
    out, err = normalize(tmp_path, filled, "--dry-run")
    assert "would change 1" in err
    assert tomllib.loads(out)["users"] == {"create": ["bple"]}
    assert tomllib.loads(out)["animal"] == {"B2": p50}


def test_bad_mappings_with_settings_aliases_are_refused(tmp_path, make, settings):
    settings.NBANK_METADATA_ALIASES = {"bird": "animal"}
    make({"animal": "P50"})
    for mappings in ('[aliases]\nsubject = "bird"\n', "[metadata.bird]\n"):
        with pytest.raises(CommandError):
            normalize(tmp_path, mappings)


def test_metadata_keys_are_renamed(tmp_path, make):
    res = make({"experiment": "chorus", "pen": 1})
    _, err = normalize(tmp_path, '[aliases]\nexperiment = "protocol"\n')
    res.refresh_from_db()
    assert res.metadata == {"protocol": "chorus", "pen": 1}
    assert "metadata.protocol: changed 1" in err


def test_metadata_values_are_mapped_and_trimmed(tmp_path, make):
    a = make({"experiment": "song_chorus"})
    b = make({"protocol": " chorus "})
    c = make({"protocol": "synthetic"})
    normalize(
        tmp_path,
        '[aliases]\nexperiment = "protocol"\n'
        '[metadata.protocol]\nsong_chorus = "song-chorus"\n'
        'synthetic = { move = "source" }\n',
    )
    for res in (a, b, c):
        res.refresh_from_db()
    assert a.metadata == {"protocol": "song-chorus"}
    assert b.metadata == {"protocol": "chorus"}
    assert c.metadata == {"source": "synthetic"}


def test_metadata_values_that_arent_strings_are_kept(tmp_path, make):
    res = make({"protocol": 3, "experiment": 3})
    normalize(
        tmp_path, '[aliases]\nexperiment = "protocol"\n[metadata.protocol]\n"3" = "x"\n'
    )
    res.refresh_from_db()
    assert res.metadata == {"protocol": 3}


def test_unchanged_metadata_is_not_counted(tmp_path, make):
    make({"protocol": "chorus"})
    _, err = normalize(tmp_path, "[metadata.protocol]\n")
    assert "changed 0" in err
    assert "metadata.protocol: unchanged 1" in err


def test_metadata_keys_that_disagree_are_a_conflict(tmp_path, make):
    metadata = {"experiment": "arc6", "protocol": "chorus"}
    res = make(metadata)
    _, err = normalize(tmp_path, '[aliases]\nexperiment = "protocol"\n')
    res.refresh_from_db()
    assert res.metadata == metadata
    assert f"conflict in {res.name}: metadata.protocol" in err


def test_metadata_keys_that_agree_are_merged(tmp_path, make):
    res = make({"experiment": "song_chorus", "protocol": "song-chorus"})
    normalize(
        tmp_path,
        '[aliases]\nexperiment = "protocol"\n'
        '[metadata.protocol]\nsong_chorus = "song-chorus"\n',
    )
    res.refresh_from_db()
    assert res.metadata == {"protocol": "song-chorus"}


def test_template_lists_metadata_values(tmp_path, make):
    make({"experiment": "song_chorus"})
    make({"protocol": "chorus"})
    make({"protocol": "chorus", "pen": 3})
    out, _ = normalize(
        tmp_path, '[aliases]\nexperiment = "protocol"\n[metadata.pen]\n', "--dry-run"
    )
    template = tomllib.loads(out)
    assert template["aliases"] == {"experiment": "protocol"}
    assert template["metadata"] == {"protocol": {}, "pen": {}}
    lines = out.splitlines()
    assert lines.index("[metadata.protocol]") < lines.index(
        '# "chorus" = ""  # 2 resources'
    )
    assert '# "song_chorus" = ""  # 1 resources' in lines
    # values that aren't strings aren't listed
    assert lines[lines.index("[metadata.pen]") + 1 :] == []
    filled = out.replace('# "song_chorus" = ""', '"song_chorus" = "song-chorus"')
    out, _ = normalize(tmp_path, filled, "--dry-run")
    assert tomllib.loads(out)["metadata"]["protocol"] == {"song_chorus": "song-chorus"}


def test_metadata_move_onto_a_different_value_is_a_conflict(tmp_path, make):
    metadata = {"protocol": "synthetic", "source": "other"}
    res = make(metadata)
    _, err = normalize(
        tmp_path, '[metadata.protocol]\nsynthetic = { move = "source" }\n'
    )
    res.refresh_from_db()
    assert res.metadata == metadata
    assert f"conflict in {res.name}: metadata.protocol" in err
