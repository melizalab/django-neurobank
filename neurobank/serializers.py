# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

import re

from rest_framework import serializers
from neurobank.models import Resource, DataType, Domain, Location

sha1_re = re.compile(r"[0-9a-fA-F]{40}")

class ResourceSerializer(serializers.ModelSerializer):
    dtype = serializers.SlugRelatedField(queryset=DataType.objects.all(), slug_field='name')
    locations = serializers.SlugRelatedField(
                                             read_only=True, many=True, slug_field='name')

    def validate_sha1(self, value):
        if self.instance is not None and self.instance.sha1 != value:
            raise serializers.ValidationError("sha1 value cannot be updated; create a new resource")
        if sha1_re.match(value) is None:
            raise serializers.ValidationError("invalid sha1 value")
        return value

    def validate_name(self, value):
        if self.instance is not None and self.instance.name != value:
            raise serializers.ValidationError("name cannot be updated")
        return value

    class Meta:
        model = Resource
        fields = ('name', 'sha1', 'dtype', 'registered', 'metadata', 'locations')
        read_only_fields = ('registered',)


class DataTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataType
        fields = ('name', 'content_type')


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ('name', 'scheme', 'root')


class LocationSerializer(serializers.ModelSerializer):
    domain_name = serializers.SlugRelatedField(source="domain",
                                               queryset=Domain.objects.all(), slug_field="name")
    resource_name = serializers.SlugRelatedField(source="resource",
                                                 queryset=Resource.objects.all(), slug_field="name")
    scheme = serializers.ReadOnlyField(source="domain.scheme")
    root = serializers.ReadOnlyField(source="domain.root")

    class Meta:
        model = Location
        fields = ('domain_name', 'scheme', 'root', 'resource_name')
