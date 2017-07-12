# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.shortcuts import render, get_object_or_404
from rest_framework import generics, mixins, status, permissions
from rest_framework.response import Response
from django_filters import rest_framework as filters

from neurobank import models
from neurobank import serializers


class ResourceFilter(filters.FilterSet):
    name = filters.CharFilter(name="name", lookup_expr="istartswith")
    sha1 = filters.CharFilter(name="sha1", lookup_expr="istartswith")
    dtype = filters.CharFilter(name="dtype__name", lookup_expr="icontains")
    location = filters.CharFilter(name="locations__name", lookup_expr="icontains")
    created_by = filters.CharFilter(name="created_by__username", lookup_expr="icontains")
    scheme = filters.CharFilter(name="locations__scheme", lookup_expr="istartswith")

    class Meta:
        model = models.Resource
        fields = {
            'created_on': ['exact', 'year', 'range'],
        }


class LocationFilter(filters.FilterSet):
    name = filters.CharFilter(name="domain__name", lookup_expr = "icontains")
    scheme = filters.CharFilter(name="domain__scheme", lookup_expr = "istartswith")
    class Meta:
        model = models.Location
        fields = ["name", "scheme"]


class ResourceList(generics.ListCreateAPIView):
    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = ResourceFilter
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)

    def filter_queryset(self, queryset):
        qs = super(ResourceList, self).filter_queryset(queryset)
        # this could be a little dangerous b/c we're letting the user design queries
        mq = {k: v for k,v in self.request.GET.items() if k.startswith("metadata__")}
        return qs.filter(**mq)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ResourceDetail(generics.RetrieveUpdateAPIView):
    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)


class DomainList(generics.ListCreateAPIView):
    lookup_field = "name"
    queryset = models.Domain.objects.all()
    serializer_class = serializers.DomainSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)


class DomainDetail(generics.RetrieveUpdateAPIView):
    lookup_field = "name"
    queryset = models.Domain.objects.all()
    serializer_class = serializers.DomainSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)


class DataTypeList(generics.ListCreateAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)


class DataTypeDetail(generics.RetrieveAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)


class LocationList(generics.ListAPIView):
    """List locations for a specific resource """
    serializer_class = serializers.LocationSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = LocationFilter

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
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)

    def get_object(self):
        return get_object_or_404(models.Location,
                                 resource=self.kwargs["resource_pk"],
                                 domain__name=self.kwargs["domain_pk"]
        )
