# -*- mode: python -*-
import tomllib
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from nbank_registry.models import DataType, Resource

pytestmark = pytest.mark.django_db


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


def test_without_mappings_nothing_changes(tmp_path, make):
    res = make({"protocol": "chorus", "experiment": "chorus"})
    out, err = normalize(tmp_path, None, "--dry-run")
    res.refresh_from_db()
    assert res.metadata == {"protocol": "chorus", "experiment": "chorus"}
    assert "0 resources with keys to normalize" in err
    assert tomllib.loads(out) == {"aliases": {}}


def test_metadata_keys_are_renamed(tmp_path, make):
    res = make({"experiment": "chorus", "pen": 1})
    _, err = normalize(tmp_path, '[aliases]\nexperiment = "protocol"\n')
    res.refresh_from_db()
    assert res.metadata == {"protocol": "chorus", "pen": 1}
    assert "metadata.protocol: changed 1" in err


def test_dry_run_changes_nothing(tmp_path, make):
    res = make({"experiment": "chorus"})
    _, err = normalize(tmp_path, '[aliases]\nexperiment = "protocol"\n', "--dry-run")
    res.refresh_from_db()
    assert res.metadata == {"experiment": "chorus"}
    assert "would change 1" in err


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


def test_metadata_move_onto_a_different_value_is_a_conflict(tmp_path, make):
    metadata = {"protocol": "synthetic", "source": "other"}
    res = make(metadata)
    _, err = normalize(
        tmp_path, '[metadata.protocol]\nsynthetic = { move = "source" }\n'
    )
    res.refresh_from_db()
    assert res.metadata == metadata
    assert f"conflict in {res.name}: metadata.protocol" in err


def test_runs_in_batches(tmp_path, make):
    resources = [make({"experiment": f"e{i}"}) for i in range(5)]
    _, err = normalize(
        tmp_path, '[aliases]\nexperiment = "protocol"\n', "--batch-size", "2"
    )
    assert "changed 5" in err
    for i, res in enumerate(resources):
        res.refresh_from_db()
        assert res.metadata == {"protocol": f"e{i}"}


@pytest.mark.parametrize(
    "mappings",
    [
        "[bird]\n",
        '[protocol]\nsong_chorus = "song-chorus"\n',
        "[aliases]\nexperiment = 5\n",
        '[aliases]\nexperiment = "protocol"\nprotocol = "experiment"\n',
        "[metadata.protocol]\nchorus = 5\n",
        '[metadata]\nprotocol = "chorus"\n',
        '[aliases]\nexperiment = "protocol"\n[metadata.experiment]\n',
        '[metadata.protocol]\nsynthetic = { move = "protocol" }\n',
        '[metadata.protocol]\nsynthetic = { rename = "source" }\n',
        # experimenter and animal are fields, not metadata
        '[aliases]\nbird = "animal"\n',
        '[aliases]\nexperimenter = "person"\n',
        "[metadata.animal]\n",
        '[metadata.protocol]\nsynthetic = { move = "animal" }\n',
        '[experimenter]\nbbellanger = "user"\n',
        '[users]\ncreate = ["bple"]\n',
        "not toml",
    ],
)
def test_bad_mappings_are_refused(tmp_path, make, mappings):
    res = make({"protocol": "synthetic"})
    with pytest.raises(CommandError):
        normalize(tmp_path, mappings)
    res.refresh_from_db()
    assert res.metadata == {"protocol": "synthetic"}


def test_template_lists_metadata_values(tmp_path, make):
    make({"experiment": "song_chorus"})
    make({"protocol": "chorus"})
    make({"protocol": "chorus", "pen": 3})
    make({"protocol": "synthetic"})
    out, _ = normalize(
        tmp_path,
        '[aliases]\nexperiment = "protocol"\n[metadata.pen]\n'
        '[metadata.protocol]\nsynthetic = { move = "source" }\n',
        "--dry-run",
    )
    template = tomllib.loads(out)
    # mappings carry over; found values are commented out
    assert template["aliases"] == {"experiment": "protocol"}
    assert template["metadata"] == {
        "protocol": {"synthetic": {"move": "source"}},
        "pen": {},
    }
    lines = out.splitlines()
    assert '"synthetic" = { move = "source" }  # 1 resources' in lines
    # values by frequency
    assert lines.index('# "chorus" = ""  # 2 resources') < lines.index(
        '# "song_chorus" = ""  # 1 resources'
    )
    # values that aren't strings aren't listed
    assert lines[lines.index("[metadata.pen]") + 1 :] == []
    filled = out.replace('# "song_chorus" = ""', '"song_chorus" = "song-chorus"')
    out, err = normalize(tmp_path, filled, "--dry-run")
    assert tomllib.loads(out)["metadata"]["protocol"] == {
        "synthetic": {"move": "source"},
        "song_chorus": "song-chorus",
    }
    assert "would change 2" in err
