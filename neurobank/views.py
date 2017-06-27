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
