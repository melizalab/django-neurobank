# -*- mode: python -*-

import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator, UniqueValidator

from nbank_registry.models import (
    Archive,
    DataType,
    Location,
    Resource,
    get_animal_model,
)

sha1_re = re.compile(r"[0-9a-fA-F]{40}")

# resource fields that refer to other records, which can't also be metadata
CORE_FIELDS = ("animal", "experimenter")


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


class AnimalField(serializers.PrimaryKeyRelatedField):
    """An animal, by the primary key of the animal model, as a string."""

    default_error_messages = {
        "does_not_exist": "no such animal '{pk_value}'",
        "incorrect_type": "invalid animal identifier",
    }

    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except ValidationError:
            # a value the primary key can't hold, such as a malformed UUID
            self.fail("does_not_exist", pk_value=data)

    def to_representation(self, value):
        return str(super().to_representation(value))


class LocationField(serializers.Field):
    """A location given as an archive name, or as {"archive": name, "key": key} to
    record where the resource is in the archive. Shown as the archive name."""

    default_error_messages = {
        "invalid": 'invalid location: give an archive name or {{"archive", "key"}}',
        "does_not_exist": "no such archive '{value}'",
    }

    def to_internal_value(self, data) -> tuple[Archive, str | None]:
        if isinstance(data, str):
            name, key = data, None
        elif (
            isinstance(data, dict)
            and "archive" in data
            and set(data) <= {"archive", "key"}
            and isinstance(data["archive"], str)
            and isinstance(data.get("key"), str | None)
        ):
            name, key = data["archive"], data.get("key")
        else:
            self.fail("invalid")
        try:
            return Archive.objects.get(name=name), key
        except Archive.DoesNotExist:
            self.fail("does_not_exist", value=name)

    def to_representation(self, value):
        return value.name


class LocationsField(serializers.ListField):
    child = LocationField()

    def get_attribute(self, instance):
        return instance.locations.all()

    def to_internal_value(self, data):
        locations = super().to_internal_value(data)
        archives = [archive for archive, _ in locations]
        if len(set(archives)) < len(archives):
            raise serializers.ValidationError("an archive is given more than once")
        for archive, key in locations:
            if key and Location.objects.filter(archive=archive, key=key).exists():
                raise serializers.ValidationError(
                    f"key '{key}' is already used in archive '{archive.name}'"
                )
        return locations


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
    locations = LocationsField(required=False)
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
    animal = AnimalField(
        queryset=get_animal_model().objects.all(), required=False, allow_null=True
    )
    metadata = serializers.JSONField(required=False, allow_null=True)
    superseded_by = serializers.SlugRelatedField(
        queryset=Resource.objects.all(),
        slug_field="name",
        required=False,
        allow_null=True,
        error_messages={
            "does_not_exist": "no such resource '{value}'",
            "invalid": "invalid resource name",
        },
    )
    superseded_note = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    def is_superuser(self) -> bool:
        try:
            return self.context["request"].user.is_superuser
        except (AttributeError, KeyError):
            return False

    def validate_sha1(self, value):
        """If updating, check if user has permission. Check if valid sha1"""
        if value is not None:
            if sha1_re.match(value) is None:
                raise serializers.ValidationError("invalid sha1 value")
            value = value.lower()
        if self.instance is not None:
            if not self.is_superuser() and self.instance.sha1 != value:
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
        """Ensure that the metadata is a dict without the core fields. Null, as
        a resource without metadata is read, is no metadata."""
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("metadata must be a dictionary")
        for field in CORE_FIELDS:
            if field in value:
                raise serializers.ValidationError(
                    f"'{field}' is a field of the resource, not metadata; send it as "
                    f"'{field}'"
                )
        return value

    def validate_superseded_note(self, value):
        # null clears the note, like an empty string
        return value or ""

    def validate(self, attrs):
        """Only superusers can mark a resource as superseded or unmark it, and a
        resource can't be superseded by itself or by one it supersedes.

        superseded_on says whether the resource is superseded: superseded_by and
        superseded_note need it, and setting it to null clears them.
        """
        details = ("superseded_by", "superseded_note")
        for field in ("superseded_on", *details):
            if field not in attrs:
                continue
            current = getattr(self.instance, field, None) or None
            if (attrs[field] or None) != current and not self.is_superuser():
                raise serializers.ValidationError(
                    {field: ["only a superuser can mark a resource as superseded"]}
                )
        if "superseded_on" in attrs:
            superseded_on = attrs["superseded_on"]
        else:
            superseded_on = getattr(self.instance, "superseded_on", None)
        if superseded_on is None:
            for field in details:
                if attrs.get(field):
                    raise serializers.ValidationError(
                        {field: ["needs superseded_on to mark the resource"]}
                    )
            if self.instance is not None:
                attrs.update(superseded_by=None, superseded_note="")
        replacement = attrs.get("superseded_by")
        if replacement is not None and self.instance is not None:
            seen = set()
            while replacement is not None and replacement.pk not in seen:
                if replacement.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        {"superseded_by": ["a resource can't supersede itself"]}
                    )
                seen.add(replacement.pk)
                replacement = replacement.superseded_by
        return attrs

    def create(self, validated_data):
        locations = validated_data.pop("locations", [])
        resource = Resource.objects.create(**validated_data)
        for archive, key in locations:
            Location.objects.create(resource=resource, archive=archive, key=key)
        return resource

    def update(self, instance, validated_data):
        """Update the instance with supplied data.

        For the metadata field, any sub-fields not in the supplied data are
        retained. To delete a subfield, set it to None
        """
        existing = set(instance.locations.all())
        for archive, key in validated_data.pop("locations", []):
            if archive not in existing:
                Location.objects.create(resource=instance, archive=archive, key=key)
        instance.dtype = validated_data.get("dtype", instance.dtype)
        instance.sha1 = validated_data.get("sha1", instance.sha1)
        for field in (
            *CORE_FIELDS,
            "superseded_on",
            "superseded_by",
            "superseded_note",
        ):
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
            "locations",
            "created_by",
            "created_on",
            "superseded_on",
            "superseded_by",
            "superseded_note",
        )
        extra_kwargs = {
            "name": unique_name_kwargs(
                Resource, "a resource with this name already exists"
            ),
            # uniqueness is checked in validate_sha1, after lowercasing
            "sha1": {"validators": []},
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


class LocationRecordSerializer(LocationSerializer):
    """A location with its resource's file name, hash and dtype, for listing
    locations."""

    filename = serializers.SerializerMethodField()
    sha1 = serializers.ReadOnlyField(source="resource.sha1")
    dtype = serializers.ReadOnlyField(source="resource.dtype.name")

    def get_filename(self, location) -> str:
        return location.resource.filename()

    class Meta(LocationSerializer.Meta):
        fields = (*LocationSerializer.Meta.fields, "filename", "sha1", "dtype")
