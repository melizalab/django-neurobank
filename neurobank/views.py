from django.shortcuts import render
from rest_framework import generics
from neurobank import models
from neurobank import serializers

class ResourceList(generics.ListCreateAPIView):
    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer


class ResourceDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer


class DomainList(generics.ListCreateAPIView):
    lookup_field = "name"
    queryset = models.Domain.objects.all()
    serializer_class = serializers.DomainSerializer

    def filter_queryset(self, queryset):
        qs = super(DomainList, self).filter_queryset(queryset)
        try:
            qs = qs.filter(resource=self.kwargs["resource_pk"])
        except KeyError:
            pass
        return qs

class DomainDetail(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "name"
    queryset = models.Domain.objects.all()
    serializer_class = serializers.DomainSerializer

    def filter_queryset(self, queryset):
        try:
            queryset = queryset.filter(resource=self.kwargs["resource_pk"])
        except KeyError:
            pass
        return queryset


class DataTypeList(generics.ListCreateAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer


class DataTypeDetail(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer
