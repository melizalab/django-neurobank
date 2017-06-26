# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

from rest_framework import serializers
from neurobank.models import Resource, DataType, Domain, Location



class ResourceSerializer(serializers.ModelSerializer):
    dtype = serializers.SlugRelatedField(queryset=DataType.objects.all(), slug_field='name')
    locations = serializers.SlugRelatedField(queryset=Location.objects.all(),
                                             many=True, slug_field='name')

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
        fields = ('name', 'scheme', 'root')


class LocationSerializer(serializers.ModelSerializer):
    url = serializers.CharField()

    class Meta:
        model = DataType
        fields = ('url',)
