# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

import re

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from neurobank.models import Resource, DataType, Domain, Location

sha1_re = re.compile(r"[0-9a-fA-F]{40}")

class SlugField(serializers.SlugField):
    default_error_messages = {"invalid":
                              "can only contain letters, numbers, underscores, and hyphens"}


class ResourceSerializer(serializers.ModelSerializer):
    name = SlugField(required=False,
                     validators=[UniqueValidator(queryset=Resource.objects.all(),
                                                 message="a resource with this name already exists")])
    dtype = serializers.SlugRelatedField(
        queryset=DataType.objects.all(), slug_field='name',
        error_messages={
            'does_not_exist': 'dtype with name {value} does not exist.',
            'invalid': 'invalid dtype'})
    locations = serializers.SlugRelatedField(
        queryset=Domain.objects.all(), required=False,
        many=True, slug_field='name',
        error_messages={
            'does_not_exist': 'domain with name {value} does not exist.',
            'invalid': 'invalid domain'})
    created_by = serializers.ReadOnlyField(source='created_by.username')

    def validate_sha1(self, value):
        if self.instance is not None and self.instance.sha1 != value:
            raise serializers.ValidationError("sha1 value cannot be updated; create a new resource")
        if value is not None and sha1_re.match(value) is None:
            raise serializers.ValidationError("invalid sha1 value")
        return value

    def validate_name(self, value):
        if self.instance is not None and self.instance.name != value:
            raise serializers.ValidationError("name cannot be updated")
        return value

    class Meta:
        model = Resource
        fields = ('name', 'sha1', 'dtype','metadata', 'locations',
                  'created_by', 'created_on')

    def create(self, validated_data):
        domains = validated_data.pop('locations', [])
        resource = Resource.objects.create(**validated_data)
        for domain in domains:
            Location.objects.create(resource=resource, domain=domain)
        return resource


class DataTypeSerializer(serializers.ModelSerializer):
    name = SlugField(validators=[UniqueValidator(queryset=DataType.objects.all(),
                                                 message="a dtype with this name already exists")])

    class Meta:
        model = DataType
        fields = ('name', 'content_type')


class DomainSerializer(serializers.ModelSerializer):
    name = SlugField(validators=[UniqueValidator(queryset=Domain.objects.all(),
                                                 message="a domain with this name already exists")])

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
