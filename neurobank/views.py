# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.shortcuts import render, get_object_or_404
from rest_framework import generics, mixins, status
from rest_framework.response import Response
from django_filters import rest_framework as filters

from neurobank import models
from neurobank import serializers


# class ResourceFilter(filters.FilterSet):
#     name = filters.CharFilter(name="name", lookup_expr="istartswith")
#     sha1 = filters.CharFilter(name="sha1", lookup_expr="istartswith")
#     dtype = filters.CharFilter(name="dtype__name", lookup_expr="icontains")
#     location = filters.CharFilter(name="locations__name", lookup_expr="icontains")

#     class Meta:
#         model = models.Resource
#         fields = {
#             'registered': ['exact', 'year', 'range'],
#         }


# class DomainFilter(filters.FilterSet):
#     name = filters.CharFilter(name="name", lookup_expr = "icontains")
#     scheme = filters.CharFilter(name="scheme", lookup_expr = "istartswith")
#     class Meta:
#         model = models.Domain


class ResourceList(generics.ListCreateAPIView):
    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer


class ResourceDetail(generics.RetrieveUpdateAPIView):
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

class DomainDetail(generics.RetrieveUpdateAPIView):
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


class DataTypeDetail(generics.RetrieveAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer


class LocationList(generics.ListAPIView):
    """List locations for a specific resource """
    serializer_class = serializers.LocationSerializer

    def get_object(self):
        return get_object_or_404(models.Resource, pk=self.kwargs["resource_pk"])

    def get_queryset(self):
        resource = self.get_object()
        return resource.location_set.all()

    def post(self, request, *args, **kwargs):
        data = {"domain_name": request.data["domain_name"],
                "resource_name": kwargs["resource_pk"]}
        serializer = serializers.LocationSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LocationDetail(generics.RetrieveDestroyAPIView):
    serializer_class = serializers.LocationSerializer

    def get_object(self):
        return get_object_or_404(models.Location,
                                 resource=self.kwargs["resource_pk"],
                                 domain__name=self.kwargs["domain_pk"]
        )
