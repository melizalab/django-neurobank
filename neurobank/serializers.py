# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

import re

from rest_framework import serializers
from neurobank.models import Resource, DataType, Domain, Location

sha1_re = re.compile(r"[0-9a-fA-F]{40}")

class ResourceSerializer(serializers.ModelSerializer):
    dtype = serializers.SlugRelatedField(queryset=DataType.objects.all(), slug_field='name')
    locations = serializers.SlugRelatedField(queryset=Domain.objects.all(),
                                             required=False, many=True, slug_field='name')

    def validate_sha1(self, value):
        if self.instance is not None and self.instance.sha1 != value:
            raise serializers.ValidationError("sha1 value cannot be updated; create a new resource")
        if sha1_re.match(value) is None:
            raise serializers.ValidationError("invalid sha1 value")

    class Meta:
        model = Resource
        fields = ('name', 'sha1', 'dtype', 'registered', 'metadata', 'locations')
        read_only_fields = ('name', 'registered')


class DataTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataType
        fields = ('name', 'content_type')


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ('name', 'scheme', 'root')


# class LocationSerializer(serializers.ModelSerializer):
#     url = serializers.CharField()

#     class Meta:
#         model = DataType
#         fields = ('url',)
