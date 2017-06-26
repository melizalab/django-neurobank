# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

from rest_framework import serializers
from neurobank.models import Resource, DataType, Domain, Location



class ResourceSerializer(serializers.ModelSerializer):
    dtype = serializers.SlugRelatedField(queryset=DataType.objects.all(), slug_field='name')
    locations = serializers.SlugRelatedField(queryset=Location.objects.all(),
                                             many=True, slug_field='name')
    #locations = LocationSerializer(source="location_set", many=True, read_only=True)
    # domains = serializers.PrimaryKeyRelatedField(source="locations",
    #                                              queryset=Location.objects.all(),
    #                                              required=False,
    #                                              many=True, write_only=True)

    class Meta:
        model = Resource
        fields = ('name', 'sha1', 'dtype', 'registered', 'metadata', 'locations')


class DataTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataType
        fields = ('name', 'content_type')


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ('pk', 'name', 'scheme', 'root')


class LocationSerializer(serializers.ModelSerializer):
    url = serializers.CharField()

    class Meta:
        model = DataType
        fields = ('url',)
