from django.shortcuts import render, get_object_or_404
from rest_framework import generics, mixins, status
from rest_framework.response import Response
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


class LocationList(generics.ListAPIView):
    """List locations for a specific resource """
    serializer_class = serializers.LocationSerializer

    def get_object(self):
        return get_object_or_404(models.Resource, pk=self.kwargs["resource_pk"])

    def get_queryset(self):
        resource = self.get_object()
        return resource.location_set.all()

    def post(self, request, *args, **kwargs):
        request.data["resource_name"] = kwargs["resource_pk"]
        serializer = serializers.LocationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
