# -*- mode: python -*-
"""Normalizes resource metadata: moves experimenter and animal into their fields,
and renames keys and maps values of other metadata."""

import json
import re
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nbank_registry.models import ANIMAL_MODEL, Resource, get_animal_model
from nbank_registry.serializers import CORE_FIELDS, metadata_keys

TEMPLATE_HEADER = """\
# Mappings for normalize_metadata. Values are matched after trimming whitespace.
#
#   [aliases]                  other names for a field (moved into the field) or
#                              for a metadata key (renamed in metadata)
#   [experimenter], [animal]   values for the fields
#   [metadata.<key>]           values for a metadata key; add a table to list them
#
#   "old" = "new"             use "new" instead
#   "old" = { move = "key" }  leave the field or key empty, and keep "old" in
#                             metadata as "key"
#
# A value with no entry is kept as it is. For a field, it's stored if it's valid
# and otherwise left in metadata. Commented entries list the values found, with
# the number of resources and, for a value that can't be stored, the reason.
"""

bare_key = re.compile(r"[A-Za-z0-9_-]+")


def animal_pk(value: str):
    """Returns value as a primary key of the animal model, or None if it can't be one."""
    try:
        return get_animal_model()._meta.pk.to_python(value)
    except ValidationError:
        return None


def normalize(value) -> str | None:
    """Returns a metadata value as a trimmed string, or None if it's not a string or number."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    return str(value).strip()


def toml_str(value: str) -> str:
    # JSON string escapes are valid in TOML basic strings
    return json.dumps(value)


def toml_key(value: str) -> str:
    return value if bare_key.fullmatch(value) else toml_str(value)


class Mappings:
    """The contents of a mappings file, checked against the registry's users and
    animals (as strings of their primary keys).

    A target is a field or a metadata key being normalized. keys maps each metadata
    key read to its target, and values maps each target to its value mappings.
    """

    def __init__(self, data: dict, users: set[str], animals: set[str]):
        unknown = set(data) - {"aliases", "users", "metadata", *CORE_FIELDS}
        if unknown:
            raise CommandError(f"unknown tables in mappings: {sorted(unknown)}")
        tables = dict(data.get("metadata", {}))
        self.aliases = dict(data.get("aliases", {}))
        for alias, target in self.aliases.items():
            if not isinstance(target, str) or not target:
                raise CommandError(f"aliases: '{alias}': expected a key or field")
            if alias in CORE_FIELDS:
                raise CommandError(f"aliases: '{alias}' is a field name")
            if target in self.aliases:
                raise CommandError(f"aliases: '{target}' is itself an alias")
        field_keys = metadata_keys()
        self.metadata_targets = list(
            dict.fromkeys(
                [t for t in self.aliases.values() if t not in CORE_FIELDS]
                + list(tables)
            )
        )
        for target in self.metadata_targets:
            if target in field_keys:
                raise CommandError(f"metadata.{target}: '{target}' is read as a field")
            if target in self.aliases:
                raise CommandError(f"metadata.{target}: '{target}' is an alias")
        self.keys = {
            **field_keys,
            **{t: t for t in self.metadata_targets},
            **self.aliases,
        }

        self.create = list(data.get("users", {}).get("create", []))
        for name in self.create:
            if not isinstance(name, str) or not is_username(name):
                raise CommandError(f"users.create: '{name}' is not a valid username")
        self.users = users | set(self.create)
        self.animals = animals

        self.values = {field: dict(data.get(field, {})) for field in CORE_FIELDS}
        for target in self.metadata_targets:
            if not isinstance(tables.get(target, {}), dict):
                raise CommandError(f"metadata.{target}: expected a table of values")
            self.values[target] = dict(tables.get(target, {}))
        for target, mapping in self.values.items():
            label = target if target in CORE_FIELDS else f"metadata.{target}"
            for old, new in mapping.items():
                if isinstance(new, dict):
                    if set(new) != {"move"} or not isinstance(new["move"], str):
                        raise CommandError(
                            f"{label}: '{old}': expected {{ move = \"key\" }}"
                        )
                    if new["move"] in self.keys:
                        raise CommandError(
                            f"{label}: '{old}': can't move to '{new['move']}', "
                            "which is being normalized"
                        )
                elif not isinstance(new, str) or not new:
                    raise CommandError(f"{label}: '{old}': expected a value or a table")
                elif target in CORE_FIELDS and (reason := self.check(target, new)[1]):
                    raise CommandError(f"{label}: '{old}' = '{new}': {reason}")

    def check(self, field: str, value: str) -> tuple[str | None, str | None]:
        """Returns (value as stored, None) if value can be stored in field, or
        (None, why not)."""
        if field == "experimenter":
            return (value, None) if value in self.users else (None, "no such user")
        # animals are compared by primary key, so a UUID in capitals still matches
        pk = animal_pk(value)
        if pk is None or str(pk) not in self.animals:
            # naming the model shows when NBANK_ANIMAL_MODEL isn't the one expected
            return None, f"no such animal in {ANIMAL_MODEL}"
        return str(pk), None

    def resolve(self, target: str, raw) -> tuple[str | None, tuple | None, str | None]:
        """Returns (label, result, reason) for a metadata value of a target.

        The label is the value as matched, or None for a metadata value that isn't a
        string or number (which is kept as it is). The result is ("set", value),
        ("move", key, value), or for a field ("drop",) for a blank value; it's None
        if the value can't be stored in a field, and reason says why.
        """
        value = normalize(raw)
        if target not in CORE_FIELDS and not isinstance(raw, str):
            return None, ("set", raw), None
        if value is None:
            return json.dumps(raw), None, "not a string"
        if value == "" and target in CORE_FIELDS:
            return value, ("drop",), None
        new = self.values[target].get(value, value)
        if isinstance(new, dict):
            return value, ("move", new["move"], value), None
        if target not in CORE_FIELDS:
            return value, ("set", new), None
        stored, reason = self.check(target, new)
        return value, (None if reason else ("set", stored)), reason


class Command(BaseCommand):
    help = (
        "Moves experimenter and animal values out of resource metadata into the "
        "fields, and renames keys and maps values of other metadata. Values that "
        "can't be stored in a field, and resources whose values conflict, are left "
        "as they are and reported."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mappings",
            type=Path,
            help="TOML file of aliases, users to create, and value mappings",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="change nothing, and write a mappings template to stdout",
        )
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, mappings=None, dry_run=False, batch_size=1000, **options):
        data = {}
        if mappings is not None:
            try:
                with open(mappings, "rb") as fp:
                    data = tomllib.load(fp)
            except (OSError, tomllib.TOMLDecodeError) as err:
                raise CommandError(f"can't read mappings: {err}") from err
        users = set(User.objects.values_list("username", flat=True))
        animals = {
            str(pk) for pk in get_animal_model().objects.values_list("pk", flat=True)
        }
        self.mappings = Mappings(data, users, animals)
        if not dry_run:
            for name in self.mappings.create:
                if name not in users:
                    user = User(username=name, is_active=False)
                    user.set_unusable_password()
                    user.save()
                    self.stderr.write(f"created inactive user '{name}'")
        self.user_ids = dict(User.objects.values_list("username", "id"))

        targets = [*CORE_FIELDS, *self.mappings.metadata_targets]
        self.seen = {target: Counter() for target in targets}
        self.reasons = {}
        self.outcomes = {target: Counter() for target in targets}
        self.conflicts = []
        scanned = changed = 0
        qs = (
            Resource.objects.filter(metadata__has_any_keys=list(self.mappings.keys))
            .select_related("experimenter")
            .order_by("id")
        )
        last = 0
        while batch := list(qs.filter(id__gt=last)[:batch_size]):
            last = batch[-1].id
            scanned += len(batch)
            updates = [resource for resource in batch if self.normalize(resource)]
            changed += len(updates)
            if updates and not dry_run:
                with transaction.atomic():
                    Resource.objects.bulk_update(
                        updates, ["metadata", *CORE_FIELDS], batch_size=batch_size
                    )

        verb = "would change" if dry_run else "changed"
        self.stderr.write(
            f"{scanned} resources with keys to normalize; {verb} {changed}"
        )
        for target in targets:
            outcomes = ", ".join(
                f"{k} {v}" for k, v in sorted(self.outcomes[target].items())
            )
            label = target if target in CORE_FIELDS else f"metadata.{target}"
            self.stderr.write(f"  {label}: {outcomes or 'none found'}")
        for name, message in self.conflicts:
            self.stderr.write(f"  conflict in {name}: {message}")
        if dry_run:
            self.stdout.write(self.template(), ending="")

    def normalize(self, resource: Resource) -> bool:
        """Normalizes a resource's metadata. Returns True if anything changed."""
        metadata = dict(resource.metadata)
        by_target = defaultdict(dict)
        for key, value in metadata.items():
            if (target := self.mappings.keys.get(key)) is not None:
                by_target[target][key] = value
        changed = False
        for target, found in by_target.items():
            results = {}
            for key, raw in found.items():
                label, result, reason = self.mappings.resolve(target, raw)
                if label is not None:
                    self.seen[target][label] += 1
                if reason:
                    self.reasons[target, label] = reason
                results[key] = result
            if None in results.values():
                self.outcomes[target]["unresolved"] += 1
                continue
            # compared as JSON, since metadata values can be lists or dicts
            distinct = {json.dumps(r, sort_keys=True): r for r in results.values()}
            if len(distinct) > 1:
                self.conflict(
                    resource, target, f"{', '.join(found)} have different values"
                )
                continue
            kind, *args = distinct.popitem()[1]
            if target not in CORE_FIELDS:
                if kind == "move":
                    key, value = args
                else:
                    key, (value,) = target, args
                if key not in found and metadata.get(key, value) != value:
                    self.conflict(
                        resource, target, f"'{key}' already has a different value"
                    )
                    continue
                before = dict(metadata)
                for k in found:
                    del metadata[k]
                metadata[key] = value
                if metadata != before:
                    self.outcomes[target]["moved" if kind == "move" else "changed"] += 1
                    changed = True
                else:
                    self.outcomes[target]["unchanged"] += 1
                continue
            if kind == "set":
                (value,) = args
                if target == "experimenter":
                    current = (
                        resource.experimenter.username
                        if resource.experimenter_id
                        else None
                    )
                else:
                    current = str(resource.animal_id) if resource.animal_id else None
                if current not in (None, value):
                    self.conflict(resource, target, f"the field is already '{current}'")
                    continue
                if target == "experimenter":
                    # a user to be created has no id in a dry run
                    resource.experimenter_id = self.user_ids.get(value)
                else:
                    resource.animal_id = animal_pk(value)
            elif kind == "move":
                key, value = args
                if metadata.get(key, value) != value:
                    self.conflict(
                        resource, target, f"'{key}' already has a different value"
                    )
                    continue
                metadata[key] = value
            for key in found:
                del metadata[key]
            self.outcomes[target][kind] += 1
            changed = True
        resource.metadata = metadata
        return changed

    def conflict(self, resource: Resource, target: str, message: str):
        self.outcomes[target]["conflict"] += 1
        label = target if target in CORE_FIELDS else f"metadata.{target}"
        self.conflicts.append((resource.name, f"{label}: {message}"))

    def template(self) -> str:
        """Returns the mappings, with the values found as commented entries."""
        m = self.mappings
        lines = [TEMPLATE_HEADER, "[aliases]"]
        lines += [
            f"# {toml_str(alias)} = {toml_str(field)}  # from NBANK_METADATA_ALIASES"
            for alias, field in metadata_keys().items()
            if alias != field and alias not in m.aliases
        ]
        lines += [
            f"{toml_str(alias)} = {toml_str(target)}"
            for alias, target in m.aliases.items()
        ]

        candidates = [
            value
            for value, _ in self.seen["experimenter"].most_common()
            if self.reasons.get(("experimenter", value)) == "no such user"
            and value not in m.values["experimenter"]
            and is_username(value)
        ]
        lines += [
            "",
            "[users]",
            "# usernames to create as inactive users",
            "create = [",
        ]
        lines += [f"    {toml_str(name)}," for name in m.create]
        lines += [
            f"    # {toml_str(name)},  # {self.seen['experimenter'][name]} resources"
            for name in candidates
        ]
        lines.append("]")

        for target in [*CORE_FIELDS, *m.metadata_targets]:
            mapping = m.values[target]
            table = target if target in CORE_FIELDS else f"metadata.{toml_key(target)}"
            lines += ["", f"[{table}]"]
            for old, new in mapping.items():
                value = (
                    f"{{ move = {toml_str(new['move'])} }}"
                    if isinstance(new, dict)
                    else toml_str(new)
                )
                lines.append(
                    f"{toml_str(old)} = {value}  # {self.seen[target][old]} resources"
                )
            # values that can't be stored first, then the rest by frequency
            found = sorted(
                (value for value in self.seen[target] if value not in mapping),
                key=lambda v: (
                    (target, v) not in self.reasons,
                    -self.seen[target][v],
                    v,
                ),
            )
            for value in found:
                note = f"{self.seen[target][value]} resources"
                if reason := self.reasons.get((target, value)):
                    note += f": {reason}"
                lines.append(f'# {toml_str(value)} = ""  # {note}')
        return "\n".join(lines) + "\n"


def is_username(value: str) -> bool:
    try:
        User.username_validator(value)
    except ValidationError:
        return False
    return len(value) <= User._meta.get_field("username").max_length
