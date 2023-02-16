# -*- coding: utf-8 -*-
# -*- mode: python -*-
from http import HTTPStatus

from collections import OrderedDict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic.detail import BaseDetailView
from django_filters import rest_framework as filters
from django_sendfile import sendfile
from drf_link_header_pagination import LinkHeaderPagination
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from urllib.parse import urlparse

from nbank_registry import __version__, api_version, errors, models, serializers


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
def notfound(request, format=None):
    return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def api_info(request, format=None):
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


class LocationFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="archive__name", lookup_expr="icontains")
    scheme = filters.CharFilter(field_name="archive__scheme", lookup_expr="istartswith")

    class Meta:
        model = models.Location
        fields = ["name", "scheme"]


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
        for (k, v) in self.request.GET.items():
            if k.startswith("metadata__"):
                if k.endswith("__neq"):
                    me[k[:-5]] = v
                else:
                    mf[k] = v
        return qs.exclude(**me).filter(**mf).order_by("name")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ResourceDetail(generics.RetrieveUpdateAPIView):
    lookup_field = "name"
    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)


class ResourceDownload(BaseDetailView):
    slug_url_kwarg = "name"
    slug_field = "name"
    model = models.Resource
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

    def render_to_response(self, context):
        try:
            path = self.object.resolve_to_path()
            return sendfile(self.request, path, attachment=True)
        except errors.SchemeNotImplementedError:
            return HttpResponse(
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                reason=(
                    f"None of the archives in which resource"
                    f" '{self.object}' is stored support resolution"
                    " to a path"
                ),
            )
        except errors.NonDownloadableDtypeError:
            return HttpResponse(
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                reason=(
                    f"Resource '{self.object}' is of type"
                    f" '{self.object.dtype}', which does not support"
                    " direct downloading."
                ),
            )


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
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = LocationFilter
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

    def get_object(self):
        return get_object_or_404(models.Resource, name=self.kwargs["resource_name"])

    def get_queryset(self):
        resource = self.get_object()
        return resource.location_set.all()

    def list(self, request, *args, **kwargs):
        resource = self.get_object()
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        # add the registry location
        try:
            resource.resolve_to_path()
            base = reverse("neurobank:resource-download-base")
            url = urlparse(request.build_absolute_uri(base))
            data.append(
                OrderedDict(
                    archive_name="registry",
                    scheme=request.scheme,
                    root=f"{url.netloc}{url.path}",
                    resource_name=resource.name,
                )
            )
        except errors.NotAvailableForDownloadError:
            pass
        return Response(data)

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
