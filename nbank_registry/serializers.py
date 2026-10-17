# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

import re

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator, UniqueValidator

from nbank_registry.models import Archive, DataType, Location, Resource

sha1_re = re.compile(r"[0-9a-fA-F]{40}")

# resource fields that clients before API 1.2 sent and read in metadata. For backwards
# compatibility, these fields are interpolated into the metadata
CORE_FIELDS = ("animal", "experimenter", "protocol")


def metadata_keys() -> dict[str, str]:
    """Returns {metadata key: field} for the core fields and their aliases.

    Aliases come from the NBANK_METADATA_ALIASES setting, e.g. {"bird": "animal"}.
    """
    keys = {field: field for field in CORE_FIELDS}
    for alias, field in getattr(settings, "NBANK_METADATA_ALIASES", {}).items():
        if field not in CORE_FIELDS:
            raise ImproperlyConfigured(
                f"NBANK_METADATA_ALIASES: '{field}' is not one of {CORE_FIELDS}"
            )
        keys[alias] = field
    return keys


def split_metadata(metadata: dict) -> tuple[dict, dict]:
    """Splits out the core fields from metadata. Returns (other metadata, core fields).

    Raises ValueError if two keys for the same field have different values.

    """
    keys = metadata_keys()
    rest, found, found_as = {}, {}, {}
    for key, value in metadata.items():
        field = keys.get(key)
        if field is None:
            rest[key] = value
        elif field in found and found[field] != value:
            raise ValueError(
                f"'{found_as[field]}' and '{key}' have different values for {field}"
            )
        else:
            found[field] = value
            found_as[field] = key
    return rest, found


SLUG_ERROR_MESSAGES = {
    "invalid": "can only contain letters, numbers, underscores, and hyphens"
}


def unique_name_kwargs(model, message):
    """extra_kwargs for a unique slug name with custom messages.

    Keeps the max_length and other settings that ModelSerializer takes from
    the model field.
    """
    return {
        "error_messages": SLUG_ERROR_MESSAGES,
        "validators": [UniqueValidator(queryset=model.objects.all(), message=message)],
    }


class AccessibilityField(serializers.Field):
    def to_representation(self, value):
        return Archive.Accessibility(value).label

    def to_internal_value(self, data):
        try:
            return Archive.Accessibility[data.upper()]
        except (AttributeError, KeyError):
            return Archive.Accessibility(0)


class ResourceSerializer(serializers.ModelSerializer):
    dtype = serializers.SlugRelatedField(
        queryset=DataType.objects.all(),
        slug_field="name",
        error_messages={
            "does_not_exist": "no such dtype '{value}'",
            "invalid": "invalid dtype name",
        },
    )
    locations = serializers.SlugRelatedField(
        queryset=Archive.objects.all(),
        required=False,
        many=True,
        slug_field="name",
        error_messages={
            "does_not_exist": "no such archive '{value}'",
            "invalid": "invalid archive name",
        },
    )
    created_by = serializers.ReadOnlyField(source="created_by.username")
    experimenter = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field="username",
        required=False,
        allow_null=True,
        error_messages={
            "does_not_exist": "no such user '{value}'",
            "invalid": "invalid username",
        },
    )
    metadata = serializers.JSONField(required=False)

    def to_internal_value(self, data):
        """Moves core fields sent in metadata to their own fields."""
        metadata = data.get("metadata") if isinstance(data, dict) else None
        if isinstance(metadata, dict):
            try:
                rest, found = split_metadata(metadata)
            except ValueError as err:
                raise serializers.ValidationError({"metadata": [str(err)]}) from err
            if found:
                data = {**data, "metadata": rest}
                for field, value in found.items():
                    if field in data and data[field] != value:
                        raise serializers.ValidationError(
                            {field: ["differs from the value in metadata"]}
                        )
                    data[field] = value
        return super().to_internal_value(data)

    def to_representation(self, instance):
        """Copies the core fields into metadata, where clients before API 1.2 read them."""
        data = super().to_representation(instance)
        copies = {f: data[f] for f in CORE_FIELDS if data.get(f) is not None}
        if copies:
            data["metadata"] = {**(data.get("metadata") or {}), **copies}
        return data

    def validate_animal(self, value):
        return value or None

    def validate_protocol(self, value):
        return value or None

    def validate_sha1(self, value):
        """If updating, check if user has permission. Check if valid sha1"""
        if value is not None:
            if sha1_re.match(value) is None:
                raise serializers.ValidationError("invalid sha1 value")
            value = value.lower()
        try:
            is_superuser = self.context["request"].user.is_superuser
        except (AttributeError, KeyError):
            is_superuser = False
        if self.instance is not None:
            if not is_superuser and self.instance.sha1 != value:
                raise serializers.ValidationError(
                    "sha1 value cannot be updated; create a new resource"
                )
        if value is not None:
            # done here, after lowercasing, rather than through the default
            # UniqueValidator, which would compare the value as submitted
            qs = Resource.objects.filter(sha1=value)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "a resource with this sha1 already exists"
                )
        return value

    def validate_name(self, value):
        if self.instance is not None and self.instance.name != value:
            raise serializers.ValidationError("name cannot be updated")
        return value

    def validate_metadata(self, value):
        """Ensure that the metadata is a dict"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("metadata must be a dictionary")
        return value

    def create(self, validated_data):
        archives = validated_data.pop("locations", [])
        resource = Resource.objects.create(**validated_data)
        for archive in archives:
            Location.objects.create(resource=resource, archive=archive)
        return resource

    def update(self, instance, validated_data):
        """Update the instance with supplied data.

        For the metadata field, any sub-fields not in the supplied data are
        retained. To delete a subfield, set it to None
        """
        archives = validated_data.pop("locations", [])
        for archive in archives:
            if archive not in instance.locations:
                Location.objects.create(resource=instance, archive=archive)
        instance.dtype = validated_data.get("dtype", instance.dtype)
        instance.sha1 = validated_data.get("sha1", instance.sha1)
        for field in CORE_FIELDS:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        if "metadata" in validated_data:
            metadata = dict(instance.metadata or {})
            for key, value in validated_data["metadata"].items():
                if value is not None:
                    metadata[key] = value
                else:
                    metadata.pop(key, None)
            instance.metadata = metadata
        instance.save()
        return instance

    class Meta:
        model = Resource
        fields = (
            "name",
            "sha1",
            "dtype",
            "filename",
            "metadata",
            "experimenter",
            "animal",
            "protocol",
            "locations",
            "created_by",
            "created_on",
        )
        extra_kwargs = {
            "name": unique_name_kwargs(
                Resource, "a resource with this name already exists"
            ),
            # uniqueness is checked in validate_sha1, after lowercasing
            "sha1": {"validators": []},
            "protocol": {"error_messages": SLUG_ERROR_MESSAGES},
        }


class DataTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataType
        fields = ("name", "content_type", "extension")
        extra_kwargs = {
            "name": unique_name_kwargs(
                DataType, "a dtype with this name already exists"
            )
        }


class ArchiveSerializer(serializers.ModelSerializer):
    accessibility = AccessibilityField(required=False)

    class Meta:
        model = Archive
        fields = ("name", "scheme", "root", "accessibility")
        extra_kwargs = {
            "name": unique_name_kwargs(
                Archive, "an archive with this name already exists"
            )
        }


class LocationSerializer(serializers.ModelSerializer):
    archive_name = serializers.SlugRelatedField(
        source="archive",
        queryset=Archive.objects.all(),
        slug_field="name",
        error_messages={
            "does_not_exist": "no such archive '{value}'",
            "invalid": "invalid archive name",
        },
    )
    resource_name = serializers.SlugRelatedField(
        source="resource",
        queryset=Resource.objects.all(),
        slug_field="name",
        error_messages={
            "does_not_exist": "no such resource '{value}'",
            "invalid": "invalid resource name",
        },
    )
    scheme = serializers.ReadOnlyField(source="archive.scheme")
    root = serializers.ReadOnlyField(source="archive.root")
    key = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=1024
    )

    def validate_key(self, value):
        """Treat an empty string the same as a missing or null key"""
        return value or None

    def validate(self, attrs):
        key = attrs.get("key", getattr(self.instance, "key", None))
        if key:
            archive = attrs.get("archive", getattr(self.instance, "archive", None))
            qs = Location.objects.filter(archive=archive, key=key)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"key": "another resource in this archive already has this key"}
                )
        return attrs

    class Meta:
        model = Location
        fields = ("archive_name", "scheme", "root", "resource_name", "key")
        validators = [
            UniqueTogetherValidator(
                queryset=Location.objects.all(),
                fields=("resource_name", "archive_name"),
            )
        ]
