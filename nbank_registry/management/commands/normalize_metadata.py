# -*- mode: python -*-
"""Normalizes resource metadata: renames keys and maps values."""

import json
import re
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nbank_registry.models import Resource
from nbank_registry.serializers import CORE_FIELDS

TEMPLATE_HEADER = """\
# Mappings for normalize_metadata. Values are matched after trimming whitespace.
#
#   [aliases]          other names for a metadata key (renamed to the key)
#   [metadata.<key>]   values for a metadata key; add a table to list them
#
#   "old" = "new"             use "new" instead
#   "old" = { move = "key" }  keep "old" under "key" instead
#
# A value with no entry is kept as it is. Commented entries list the values
# found, with the number of resources.
"""

bare_key = re.compile(r"[A-Za-z0-9_-]+")


def toml_str(value: str) -> str:
    # JSON string escapes are valid in TOML basic strings
    return json.dumps(value)


def toml_key(value: str) -> str:
    return value if bare_key.fullmatch(value) else toml_str(value)


def not_a_key(name: str) -> str | None:
    """Returns why name can't be a metadata key, or None if it can."""
    if name in CORE_FIELDS:
        return f"'{name}' is a field of the resource, not metadata"
    return None


class Mappings:
    """The contents of a mappings file.

    A target is a metadata key being normalized. keys maps each metadata key read
    to its target, and values maps each target to its value mappings.
    """

    def __init__(self, data: dict):
        unknown = set(data) - {"aliases", "metadata"}
        if unknown:
            raise CommandError(f"unknown tables in mappings: {sorted(unknown)}")
        tables = dict(data.get("metadata", {}))
        self.aliases = dict(data.get("aliases", {}))
        for alias, target in self.aliases.items():
            if not isinstance(target, str) or not target:
                raise CommandError(f"aliases: '{alias}': expected a key")
            if reason := not_a_key(alias) or not_a_key(target):
                raise CommandError(f"aliases: '{alias}': {reason}")
            if target in self.aliases:
                raise CommandError(f"aliases: '{target}' is itself an alias")
        self.targets = list(dict.fromkeys([*self.aliases.values(), *tables]))
        for target in self.targets:
            if reason := not_a_key(target):
                raise CommandError(f"metadata.{target}: {reason}")
            if target in self.aliases:
                raise CommandError(f"metadata.{target}: '{target}' is an alias")
        self.keys = {**{t: t for t in self.targets}, **self.aliases}

        self.values = {}
        for target in self.targets:
            if not isinstance(tables.get(target, {}), dict):
                raise CommandError(f"metadata.{target}: expected a table of values")
            self.values[target] = dict(tables.get(target, {}))
        for target, mapping in self.values.items():
            for old, new in mapping.items():
                label = f"metadata.{target}: '{old}'"
                if isinstance(new, dict):
                    if set(new) != {"move"} or not isinstance(new["move"], str):
                        raise CommandError(f'{label}: expected {{ move = "key" }}')
                    if reason := not_a_key(new["move"]):
                        raise CommandError(f"{label}: {reason}")
                    if new["move"] in self.keys:
                        raise CommandError(
                            f"{label}: can't move to '{new['move']}', "
                            "which is being normalized"
                        )
                elif not isinstance(new, str) or not new:
                    raise CommandError(f"{label}: expected a value or a table")

    def resolve(self, target: str, raw) -> tuple[str | None, tuple]:
        """Returns (label, result) for a metadata value of a target.

        The label is the value as matched, or None for a value that isn't a string
        (which is kept as it is). The result is ("set", value) or ("move", key,
        value).
        """
        if not isinstance(raw, str):
            return None, ("set", raw)
        value = raw.strip()
        new = self.values[target].get(value, value)
        if isinstance(new, dict):
            return value, ("move", new["move"], value)
        return value, ("set", new)


class Command(BaseCommand):
    help = (
        "Renames keys and maps values of resource metadata. Resources whose values "
        "conflict are left as they are and reported."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mappings",
            type=Path,
            help="TOML file of key aliases and value mappings",
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
        self.mappings = Mappings(data)

        self.seen = {target: Counter() for target in self.mappings.targets}
        self.outcomes = {target: Counter() for target in self.mappings.targets}
        self.conflicts = []
        scanned = changed = 0
        # an empty has_any_keys is a syntax error in sqlite
        qs = (
            Resource.objects.filter(metadata__has_any_keys=list(self.mappings.keys))
            if self.mappings.keys
            else Resource.objects.none()
        ).order_by("id")
        last = 0
        while batch := list(qs.filter(id__gt=last)[:batch_size]):
            last = batch[-1].id
            scanned += len(batch)
            updates = [resource for resource in batch if self.normalize(resource)]
            changed += len(updates)
            if updates and not dry_run:
                with transaction.atomic():
                    Resource.objects.bulk_update(
                        updates, ["metadata"], batch_size=batch_size
                    )

        verb = "would change" if dry_run else "changed"
        self.stderr.write(
            f"{scanned} resources with keys to normalize; {verb} {changed}"
        )
        for target in self.mappings.targets:
            outcomes = ", ".join(
                f"{k} {v}" for k, v in sorted(self.outcomes[target].items())
            )
            self.stderr.write(f"  metadata.{target}: {outcomes or 'none found'}")
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
            results = []
            for raw in found.values():
                label, result = self.mappings.resolve(target, raw)
                if label is not None:
                    self.seen[target][label] += 1
                results.append(result)
            # compared as JSON, since metadata values can be lists or dicts
            distinct = {json.dumps(r, sort_keys=True): r for r in results}
            if len(distinct) > 1:
                self.conflict(
                    resource, target, f"{', '.join(found)} have different values"
                )
                continue
            kind, *args = distinct.popitem()[1]
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
        resource.metadata = metadata
        return changed

    def conflict(self, resource: Resource, target: str, message: str):
        self.outcomes[target]["conflict"] += 1
        self.conflicts.append((resource.name, f"metadata.{target}: {message}"))

    def template(self) -> str:
        """Returns the mappings, with the values found as commented entries."""
        m = self.mappings
        lines = [TEMPLATE_HEADER, "[aliases]"]
        lines += [
            f"{toml_str(alias)} = {toml_str(target)}"
            for alias, target in m.aliases.items()
        ]
        for target in m.targets:
            mapping = m.values[target]
            lines += ["", f"[metadata.{toml_key(target)}]"]
            for old, new in mapping.items():
                value = (
                    f"{{ move = {toml_str(new['move'])} }}"
                    if isinstance(new, dict)
                    else toml_str(new)
                )
                lines.append(
                    f"{toml_str(old)} = {value}  # {self.seen[target][old]} resources"
                )
            found = sorted(
                (value for value in self.seen[target] if value not in mapping),
                key=lambda v: (-self.seen[target][v], v),
            )
            for value in found:
                lines.append(
                    f'# {toml_str(value)} = ""  # {self.seen[target][value]} resources'
                )
        return "\n".join(lines) + "\n"
