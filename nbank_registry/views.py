# -*- coding: utf-8 -*-
# -*- mode: python -*-
import itertools
from urllib.parse import urlparse

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from django_sendfile import sendfile
from drf_link_header_pagination import LinkHeaderPagination
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

from nbank_registry import (
    __version__,
    api_version,
    errors,
    models,
    resource_download,
    serializers,
)

DOWNLOAD_ARCHIVE_NAME = "registry"


def all_locations(resource, request):
    """Helper function returns a list of all the locations associated with
    resource. If the resource dtype is marked as downloadable, a fake loction
    that points to the registry is also included.

    """
    location_set = resource.location_set.all()
    if not resource.dtype.downloadable:
        return location_set
    base = reverse("neurobank:resource-download-base")
    url = urlparse(request.build_absolute_uri(base))
    registry_archive = models.Archive(
        name=DOWNLOAD_ARCHIVE_NAME,
        scheme=request.scheme,
        root=f"{url.netloc}{url.path}",
    )
    registry_location = models.Location(archive=registry_archive, resource=resource)
    return itertools.chain(location_set, [registry_location])


@api_view(["GET"])
def api_root(request, format=None):
    return Response(
        {
            "info": reverse("neurobank:api-info", request=request, format=format),
            "resources": reverse(
                "neurobank:resource-list", request=request, format=format
            ),
            "datatypes": reverse(
                "neurobank:datatype-list", request=request, format=format
            ),
            "archives": reverse(
                "neurobank:archive-list", request=request, format=format
            ),
        }
    )


@api_view(["GET"])
def notfound(request):
    return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def api_info(request):
    return Response(
        {"name": "django-neurobank", "version": __version__, "api_version": api_version}
    )


class ArchiveFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="istartswith")
    scheme = filters.CharFilter(field_name="scheme", lookup_expr="istartswith")
    root = filters.CharFilter(field_name="root", lookup_expr="iexact")

    class Meta:
        model = models.Archive
        fields = ["name", "scheme", "root"]


class ResourceFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    sha1 = filters.CharFilter(field_name="sha1", lookup_expr="icontains")
    dtype = filters.CharFilter(field_name="dtype__name", lookup_expr="icontains")
    location = filters.CharFilter(field_name="locations__name", lookup_expr="icontains")
    created_by = filters.CharFilter(
        field_name="created_by__username", lookup_expr="icontains"
    )
    scheme = filters.CharFilter(
        field_name="locations__scheme", lookup_expr="istartswith"
    )

    class Meta:
        model = models.Resource
        fields = {
            "created_on": ["exact", "year", "range"],
        }


class ResourceList(generics.ListCreateAPIView):
    """This view is a list of resources in the registry.

    Results can be filtered using query params on name, dtype, location, sha1, etc (see OPTIONS).

    Results can be flexibly filtered on metadata by prefixing the query parameter
    with `metadata__`. Use django suffixes for other kinds of matches and
    `__neq` for exclusions. For example, `?metadata__experimenter=dmeliza` will
    return all resources with experimenter set to dmeliza,
    `?metadata__experimenter_neq=dmeliza` will return all resources with
    experimenter set to something else, and
    `?metadata__experimenter__isnull=True` will return all resources without a
    value set for `experimenter`.

    """

    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ResourceFilter
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    pagination_class = LinkHeaderPagination

    def filter_queryset(self, queryset):
        qs = super(ResourceList, self).filter_queryset(queryset)
        # this could be a little dangerous b/c we're letting the user design
        # queries
        mf = {}
        me = {}
        for k, v in self.request.GET.items():
            if k.startswith("metadata__"):
                if k.endswith("__neq"):
                    me[k[:-5]] = v
                else:
                    mf[k] = v
        return qs.exclude(**me).filter(**mf).order_by("name")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ResourceDetail(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "name"
    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)


@api_view(["GET"])
def download_resource(request, name):
    try:
        resource = models.Resource.objects.get(name=name)
        path = resource_download.local_resource_path(resource)
    except models.Resource.DoesNotExist:
        return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
    except errors.NotAvailableForDownloadError as err:
        return Response(
            {"detail": str(err)}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
    return sendfile(request, path, attachment=True)


class ArchiveList(generics.ListCreateAPIView):
    lookup_field = "name"
    queryset = models.Archive.objects.all()
    serializer_class = serializers.ArchiveSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ArchiveFilter


class ArchiveDetail(generics.RetrieveUpdateAPIView):
    lookup_field = "name"
    queryset = models.Archive.objects.all()
    serializer_class = serializers.ArchiveSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)


class DataTypeList(generics.ListCreateAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)


class DataTypeDetail(generics.RetrieveAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)


class LocationList(generics.ListAPIView):
    """List locations for a specific resource"""

    serializer_class = serializers.LocationSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

    def get_object(self):
        return get_object_or_404(models.Resource, name=self.kwargs["resource_name"])

    def get_queryset(self):
        resource = self.get_object()
        return resource.location_set.all()

    def list(self, request, *args, **kwargs):
        resource = self.get_object()
        queryset = all_locations(resource, request)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        data = {
            "archive_name": request.data["archive_name"],
            "resource_name": kwargs["resource_name"],
        }
        serializer = serializers.LocationSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LocationDetail(generics.RetrieveDestroyAPIView):
    queryset = models.Location.objects.all()
    serializer_class = serializers.LocationSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

    def get_object(self):
        return get_object_or_404(
            models.Location,
            resource__name=self.kwargs["resource_name"],
            archive__name=self.kwargs["archive_pk"],
        )


def check_bulk_args(request):
    try:
        names = request.data["names"]
    except KeyError:
        return Response(
            {"detail": "usage: {'names': ['id1', 'id2', ...]}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(names) == 0:
        return Response(
            {"detail": "must supply at least one name"},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["POST"])
def bulk_resource_list(request, format=None):
    """Retrieve metadata for multiple resources by name. POST {'names': ['name1', 'name2',...]}"""
    if (resp := check_bulk_args(request)) is not None:
        return resp
    query = Q()
    for name in request.data["names"]:
        query |= Q(name=name)
    resources = models.Resource.objects.filter(query)
    serializer = serializers.ResourceSerializer(resources, many=True)
    return Response(serializer.data)


@api_view(["POST"])
def bulk_location_list(request, format=None):
    """Retrieve locations for multiple resources by name. POST {'names': ['name1', 'name2',...]}"""
    if (resp := check_bulk_args(request)) is not None:
        return resp
    query = Q()
    for name in request.data["names"]:
        query |= Q(name=name)
    output = []
    for resource in models.Resource.objects.filter(query):
        locations = all_locations(resource, request)
        serializer = serializers.LocationSerializer(locations, many=True)
        output.append({"name": resource.name, "locations": serializer.data})
    return Response(output)
