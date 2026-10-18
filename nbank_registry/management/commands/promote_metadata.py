# -*- mode: python -*-
"""Moves experimenter and animal out of resource metadata into their fields."""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nbank_registry.models import Resource, get_animal_model
from nbank_registry.serializers import CORE_FIELDS, metadata_keys

TEMPLATE_HEADER = """\
# Mappings for promote_metadata. Values are matched after trimming whitespace.
#
#   "old" = "new"             store "new" in the field
#   "old" = { move = "key" }  leave the field empty and keep "old" in metadata as "key"
#
# A value with no entry is stored as it is if it's valid for the field, and is
# otherwise left in metadata. Commented entries list the values found, with the
# number of resources and, for a value that can't be stored, the reason.
"""


def animal_pk(value: str):
    """Returns value as a primary key of the animal model, or None if it can't be one."""
    try:
        return get_animal_model()._meta.pk.to_python(value)
    except ValidationError:
        return None


def normalize(value) -> str | None:
    """Returns a metadata value as a trimmed string, or None if it's not a string or number."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return str(value).strip()


def toml_str(value: str) -> str:
    # JSON string escapes are valid in TOML basic strings
    return json.dumps(value)


class Mappings:
    """The contents of a mappings file, checked against the registry's users and
    animals (as strings of their primary keys)."""

    def __init__(self, data: dict, users: set[str], animals: set[str]):
        unknown = set(data) - {"aliases", "users", *CORE_FIELDS}
        if unknown:
            raise CommandError(f"unknown tables in mappings: {sorted(unknown)}")
        self.aliases = dict(data.get("aliases", {}))
        for alias, field in self.aliases.items():
            if field not in CORE_FIELDS:
                raise CommandError(f"aliases: '{field}' is not one of {CORE_FIELDS}")
            if alias in CORE_FIELDS:
                raise CommandError(f"aliases: '{alias}' is a field name")
        self.keys = {**metadata_keys(), **self.aliases}

        self.create = list(data.get("users", {}).get("create", []))
        for name in self.create:
            if not isinstance(name, str) or not is_username(name):
                raise CommandError(f"users.create: '{name}' is not a valid username")
        self.users = users | set(self.create)
        self.animals = animals

        self.values = {field: dict(data.get(field, {})) for field in CORE_FIELDS}
        for field, mapping in self.values.items():
            for old, new in mapping.items():
                if isinstance(new, dict):
                    if set(new) != {"move"} or not isinstance(new["move"], str):
                        raise CommandError(
                            f"{field}: '{old}': expected {{ move = \"key\" }}"
                        )
                    if new["move"] in self.keys:
                        raise CommandError(
                            f"{field}: '{old}': can't move to '{new['move']}', "
                            "which is read as a field"
                        )
                elif not isinstance(new, str) or not new:
                    raise CommandError(f"{field}: '{old}': expected a value or a table")
                elif reason := self.check(field, new)[1]:
                    raise CommandError(f"{field}: '{old}' = '{new}': {reason}")

    def check(self, field: str, value: str) -> tuple[str | None, str | None]:
        """Returns (value as stored, None) if value can be stored in field, or
        (None, why not)."""
        if field == "experimenter":
            return (value, None) if value in self.users else (None, "no such user")
        # animals are compared by primary key, so a UUID in capitals still matches
        pk = animal_pk(value)
        if pk is None or str(pk) not in self.animals:
            return None, "no such animal"
        return str(pk), None

    def resolve(self, field: str, raw) -> tuple[str, tuple | None, str | None]:
        """Returns (label, result, reason) for a metadata value of a field.

        The label is the value as matched (or its JSON for a value that can't be
        matched). The result is ("set", value), ("move", key, value), or ("drop",)
        for a blank value; it's None if the value can't be stored, and reason says why.
        """
        value = normalize(raw)
        if value is None:
            return json.dumps(raw), None, "not a string"
        if value == "":
            return value, ("drop",), None
        new = self.values[field].get(value, value)
        if isinstance(new, dict):
            return value, ("move", new["move"], value), None
        stored, reason = self.check(field, new)
        return value, (None if reason else ("set", stored)), reason


class Command(BaseCommand):
    help = (
        "Moves experimenter and animal values out of resource metadata "
        "into the fields. Values that can't be stored, and resources whose values "
        "conflict, are left as they are and reported."
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

        self.seen = {field: Counter() for field in CORE_FIELDS}
        self.reasons = {}
        self.outcomes = {field: Counter() for field in CORE_FIELDS}
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
            updates = [resource for resource in batch if self.promote(resource)]
            changed += len(updates)
            if updates and not dry_run:
                with transaction.atomic():
                    Resource.objects.bulk_update(
                        updates, ["metadata", *CORE_FIELDS], batch_size=batch_size
                    )

        verb = "would change" if dry_run else "changed"
        self.stderr.write(
            f"{scanned} resources with fields in metadata; {verb} {changed}"
        )
        for field in CORE_FIELDS:
            outcomes = ", ".join(
                f"{k} {v}" for k, v in sorted(self.outcomes[field].items())
            )
            self.stderr.write(f"  {field}: {outcomes or 'none found'}")
        for name, message in self.conflicts:
            self.stderr.write(f"  conflict in {name}: {message}")
        if dry_run:
            self.stdout.write(self.template(), ending="")

    def promote(self, resource: Resource) -> bool:
        """Moves the fields out of a resource's metadata. Returns True if anything changed."""
        metadata = dict(resource.metadata)
        by_field = defaultdict(dict)
        for key, value in metadata.items():
            if (field := self.mappings.keys.get(key)) is not None:
                by_field[field][key] = value
        changed = False
        for field, found in by_field.items():
            results = {}
            for key, raw in found.items():
                label, result, reason = self.mappings.resolve(field, raw)
                self.seen[field][label] += 1
                if reason:
                    self.reasons[field, label] = reason
                results[key] = result
            if None in results.values():
                self.outcomes[field]["unresolved"] += 1
                continue
            distinct = set(results.values())
            if len(distinct) > 1:
                self.conflict(
                    resource, field, f"{', '.join(found)} have different values"
                )
                continue
            kind, *args = distinct.pop()
            if kind == "set":
                (value,) = args
                if field == "experimenter":
                    current = (
                        resource.experimenter.username
                        if resource.experimenter_id
                        else None
                    )
                else:
                    current = str(resource.animal_id) if resource.animal_id else None
                if current not in (None, value):
                    self.conflict(resource, field, f"the field is already '{current}'")
                    continue
                if field == "experimenter":
                    # a user to be created has no id in a dry run
                    resource.experimenter_id = self.user_ids.get(value)
                else:
                    resource.animal_id = animal_pk(value)
            elif kind == "move":
                key, value = args
                if metadata.get(key, value) != value:
                    self.conflict(
                        resource, field, f"'{key}' already has a different value"
                    )
                    continue
                metadata[key] = value
            for key in found:
                del metadata[key]
            self.outcomes[field][kind] += 1
            changed = True
        resource.metadata = metadata
        return changed

    def conflict(self, resource: Resource, field: str, message: str):
        self.outcomes[field]["conflict"] += 1
        self.conflicts.append((resource.name, f"{field}: {message}"))

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
            f"{toml_str(alias)} = {toml_str(field)}"
            for alias, field in m.aliases.items()
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

        for field in CORE_FIELDS:
            mapping = m.values[field]
            lines += ["", f"[{field}]"]
            for old, new in mapping.items():
                target = (
                    f"{{ move = {toml_str(new['move'])} }}"
                    if isinstance(new, dict)
                    else toml_str(new)
                )
                lines.append(
                    f"{toml_str(old)} = {target}  # {self.seen[field][old]} resources"
                )
            # values that can't be stored first, then the rest by frequency
            found = sorted(
                (value for value in self.seen[field] if value not in mapping),
                key=lambda v: ((field, v) not in self.reasons, -self.seen[field][v], v),
            )
            for value in found:
                note = f"{self.seen[field][value]} resources"
                if reason := self.reasons.get((field, value)):
                    note += f": {reason}"
                lines.append(f'# {toml_str(value)} = ""  # {note}')
        return "\n".join(lines) + "\n"


def is_username(value: str) -> bool:
    try:
        User.username_validator(value)
    except ValidationError:
        return False
    return len(value) <= User._meta.get_field("username").max_length
