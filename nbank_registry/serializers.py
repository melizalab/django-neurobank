# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

import re

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator, UniqueValidator

from nbank_registry.models import Archive, DataType, Location, Resource

sha1_re = re.compile(r"[0-9a-fA-F]{40}")


class SlugField(serializers.SlugField):
    default_error_messages = {
        "invalid": "can only contain letters, numbers, underscores, and hyphens"
    }


class ResourceSerializer(serializers.ModelSerializer):
    name = SlugField(
        required=False,
        validators=[
            UniqueValidator(
                queryset=Resource.objects.all(),
                message="a resource with this name already exists",
            )
        ],
    )
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
    metadata = serializers.JSONField(required=False)

    def validate_sha1(self, value):
        """If updating, check if user has permission. Check if valid sha1"""
        try:
            is_superuser = self.context["request"].user.is_superuser
        except (AttributeError, KeyError):
            is_superuser = False
        if self.instance is not None:
            if not is_superuser and self.instance.sha1 != value:
                raise serializers.ValidationError(
                    "sha1 value cannot be updated; create a new resource"
                )
        if value is not None and sha1_re.match(value) is None:
            raise serializers.ValidationError("invalid sha1 value")
        return value

    def validate_name(self, value):
        if self.instance is not None and self.instance.name != value:
            raise serializers.ValidationError("name cannot be updated")
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
        for key, value in validated_data.get("metadata", {}).items():
            if value is not None:
                instance.metadata[key] = value
            else:
                instance.metadata.pop(key, None)
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
            "locations",
            "created_by",
            "created_on",
        )


class DataTypeSerializer(serializers.ModelSerializer):
    name = SlugField(
        validators=[
            UniqueValidator(
                queryset=DataType.objects.all(),
                message="a dtype with this name already exists",
            )
        ]
    )

    class Meta:
        model = DataType
        fields = ("name", "content_type", "extension")


class ArchiveSerializer(serializers.ModelSerializer):
    name = SlugField(
        validators=[
            UniqueValidator(
                queryset=Archive.objects.all(),
                message="an archive with this name already exists",
            )
        ]
    )

    class Meta:
        model = Archive
        fields = ("name", "scheme", "root")


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

    class Meta:
        model = Location
        fields = ("archive_name", "scheme", "root", "resource_name")
        validators = [
            UniqueTogetherValidator(
                queryset=Location.objects.all(),
                fields=("resource_name", "archive_name"),
            )
        ]
