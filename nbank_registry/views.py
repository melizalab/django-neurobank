# -*- mode: python -*-
import json
from urllib.parse import urlparse

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError, Q
from django.db.utils import IntegrityError
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from django_sendfile import sendfile
from drf_link_header_pagination import LinkHeaderPagination
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.versioning import AcceptHeaderVersioning

from nbank_registry import (
    __version__,
    api_version,
    errors,
    models,
    resource_download,
    serializers,
)

DOWNLOAD_ARCHIVE_NAME = "registry"
# the most records the resource list streams from the database at a time
STREAM_CHUNK_SIZE = 1000


class JSONLRenderer(JSONRenderer):
    """Renders data as one line of JSON. Streamed responses are a series of these."""

    media_type = "application/x-ndjson"
    format = "jsonl"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        out = super().render(data, accepted_media_type=None, renderer_context=None)
        return out + b"\n"


def stream_jsonl(records) -> StreamingHttpResponse:
    """Returns a response that streams each of records as a line of JSON."""
    renderer = JSONLRenderer()
    return StreamingHttpResponse(
        (renderer.render(record) for record in records),
        content_type=JSONLRenderer.media_type,
    )


class StreamedListMixin:
    """For list views: paginated JSON by default, or every result in one response,
    streamed as line-delimited JSON, to a request that asks for
    `application/x-ndjson`. A stream needs a search parameter, so that a mistake
    doesn't send the whole table."""

    pagination_class = LinkHeaderPagination
    # the default renderer comes first, so only a request that asks gets the stream
    renderer_classes = (*api_settings.DEFAULT_RENDERER_CLASSES, JSONLRenderer)

    def list(self, request, *args, **kwargs):
        if not isinstance(request.accepted_renderer, JSONLRenderer):
            return super().list(request, *args, **kwargs)
        if not self.is_filtered(request):
            return Response(
                {
                    "detail": "a stream needs a search parameter (see OPTIONS); "
                    "ask for application/json to get every result in pages"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = self.filter_queryset(self.get_queryset())
        return stream_jsonl(
            self.get_serializer(item).data
            for item in qs.iterator(chunk_size=STREAM_CHUNK_SIZE)
        )

    def is_filtered(self, request) -> bool:
        """Whether the request has a parameter the view searches with. Unknown
        parameters are ignored, so they don't count."""
        return any(p in self.filterset_class.base_filters for p in request.query_params)


# the most resources check/resources/ checks in one request
MAX_RESOURCE_CHECKS = 1000


class ApiVersioning(AcceptHeaderVersioning):
    """The API version a request asks for in its Accept header, e.g.
    `application/json; version=2.0`. Clients before neurobank 1.0 don't ask, so
    their requests have no version; asking for another version is a 406."""

    allowed_versions = (api_version,)

    def is_allowed_version(self, version):
        # DRF allows no version only as the default version, which would make
        # every old client's request look like a current one
        return version is None or version in self.allowed_versions


class ChangesNeedVersion(permissions.BasePermission):
    """Refuses requests that change the registry unless they ask for the
    current API version, so clients before neurobank 1.0 can read but not
    write. The refusal is a 400 rather than a 403 because old clients print a
    400's messages, and only a generic message for a 403."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS or request.version is not None:
            return True
        raise ValidationError(
            {
                "neurobank": [
                    "this version can no longer change the registry; upgrade to "
                    "neurobank 1.0 or later"
                ]
            }
        )


# for views that change the registry
CHANGE_PERMISSIONS = (
    permissions.DjangoModelPermissionsOrAnonReadOnly,
    ChangesNeedVersion,
)


def add_virtual_registry_location(request, resource, qs):
    """Add a virtual (non-persisted) location for registry downloads.

    This creates in-memory Archive and Location instances that represent the registry's
    download endpoint. These objects are never saved to the database but work seamlessly
    with our serializers. This does not check whether the file actually exists; this is
    deferred until the user tries to retrieve it. qs is sorted by accessibility, and the
    new location goes after the remote ones, before any offline.

    """
    base = reverse("neurobank:resource-download-base")
    url = urlparse(request.build_absolute_uri(base))
    registry_archive = models.Archive(
        name=DOWNLOAD_ARCHIVE_NAME,
        scheme=request.scheme,
        root=f"{url.netloc}{url.path}",
        accessibility=models.Archive.Accessibility.REMOTE,
    )
    registry_location = models.Location(archive=registry_archive, resource=resource)
    locations = list(qs)
    i = next(
        (
            i
            for i, location in enumerate(locations)
            if location.archive.accessibility > registry_archive.accessibility
        ),
        len(locations),
    )
    return [*locations[:i], registry_location, *locations[i:]]


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
            "locations": reverse(
                "neurobank:all-location-list", request=request, format=format
            ),
            "check": reverse(
                "neurobank:resource-check", request=request, format=format
            ),
        }
    )


@api_view(["GET"])
def notfound(request):
    return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)


def user_info(user) -> dict | None:
    """Who a request is from and what they can change in the registry, or None
    if it's anonymous"""
    if not user.is_authenticated:
        return None
    prefix = f"{models.Resource._meta.app_label}."
    permissions = sorted(
        p.removeprefix(prefix)
        for p in user.get_all_permissions()
        if p.startswith(prefix)
    )
    return {
        "username": user.username,
        "superuser": user.is_superuser,
        "permissions": permissions,
    }


@api_view(["GET"])
def api_info(request):
    return Response(
        {
            "name": "django-neurobank",
            "version": __version__,
            "api_version": api_version,
            "user": user_info(request.user),
        }
    )


class ArchiveFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="istartswith")
    scheme = filters.CharFilter(field_name="scheme", lookup_expr="istartswith")
    root = filters.CharFilter(field_name="root", lookup_expr="iexact")

    class Meta:
        model = models.Archive
        fields = ["name", "scheme", "root", "accessibility"]


class LocationFilter(filters.FilterSet):
    archive = filters.CharFilter(field_name="archive__name", lookup_expr="exact")
    scheme = filters.CharFilter(field_name="archive__scheme", lookup_expr="iexact")

    class Meta:
        model = models.Location
        fields = ["archive", "scheme"]


class AllLocationFilter(LocationFilter):
    has_key = filters.BooleanFilter(method="filter_has_key")

    def filter_has_key(self, queryset, name, value):
        return queryset.filter(key__isnull=not value)


def animal_pk(value):
    """Returns value as a primary key of the animal model, or None if it can't be one
    (such as a malformed UUID)."""
    try:
        return models.get_animal_model()._meta.pk.to_python(value)
    except DjangoValidationError:
        return None


class ResourceFilter(filters.FilterSet):
    # TODO: consider changing some of these to exact by default
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    sha1 = filters.CharFilter(method="filter_sha1")
    sha1_contains = filters.CharFilter(field_name="sha1", lookup_expr="icontains")
    dtype = filters.CharFilter(field_name="dtype__name", lookup_expr="icontains")
    location = filters.CharFilter(
        field_name="locations__name", lookup_expr="icontains", distinct=True
    )
    archive = filters.CharFilter(
        field_name="locations__name", lookup_expr="exact", distinct=True
    )
    has_location = filters.BooleanFilter(
        field_name="locations", lookup_expr="isnull", exclude=True, distinct=True
    )
    created_by = filters.CharFilter(
        field_name="created_by__username", lookup_expr="icontains"
    )
    scheme = filters.CharFilter(
        field_name="locations__scheme", lookup_expr="istartswith", distinct=True
    )
    experimenter = filters.CharFilter(field_name="experimenter__username")
    animal = filters.CharFilter(method="filter_animal")
    # exclusions keep resources with no value for the field
    experimenter__neq = filters.CharFilter(
        field_name="experimenter__username", exclude=True
    )
    animal__neq = filters.CharFilter(method="exclude_animal")
    experimenter__isnull = filters.BooleanFilter(
        field_name="experimenter", lookup_expr="isnull"
    )
    animal__isnull = filters.BooleanFilter(field_name="animal", lookup_expr="isnull")
    # e.g. the first part of a UUID, as people type it
    animal__istartswith = filters.CharFilter(
        field_name="animal__pk", lookup_expr="istartswith"
    )
    superseded = filters.BooleanFilter(
        field_name="superseded_on", lookup_expr="isnull", exclude=True
    )
    superseded_by = filters.CharFilter(field_name="superseded_by__name")

    def filter_sha1(self, queryset, name, value):
        return queryset.filter(sha1=value.lower())

    def filter_animal(self, queryset, name, value):
        pk = animal_pk(value)
        return queryset.none() if pk is None else queryset.filter(animal=pk)

    def exclude_animal(self, queryset, name, value):
        pk = animal_pk(value)
        return queryset if pk is None else queryset.exclude(animal=pk)

    class Meta:
        model = models.Resource
        fields = {
            "created_on": ["exact", "year", "range"],
        }


# values accepted for metadata__<key>__isnull, case-insensitively
ISNULL_VALUES = {"true": True, "1": True, "false": False, "0": False}


class ResourceList(StreamedListMixin, generics.ListCreateAPIView):
    """This view is a list of resources in the registry.

    Results can be filtered using query params on name, dtype, location, sha1,
    experimenter, animal, etc (see OPTIONS). The last two also take `__neq` and
    `__isnull`, and animal takes `__istartswith`.

    Results can be flexibly filtered on metadata by prefixing the query parameter
    with `metadata__`. Use django suffixes for other kinds of matches and
    `__neq` for exclusions. For example, `?metadata__site=3` will return all
    resources with site set to 3, `?metadata__site__neq=3` will return all
    resources with site set to something else, and `?metadata__site__isnull=True`
    will return all resources without a value set for `site`. The core fields
    (experimenter, animal) aren't metadata: search them with their own params.

    Results are paginated JSON, with links to the other pages in the Link header.
    A request that asks for `application/x-ndjson` and searches with at least one
    parameter gets every result in one response instead, streamed as line-delimited
    JSON. Ask for it alone: JSON wins if both are accepted, as DRF doesn't weigh q
    values.

    """

    queryset = models.Resource.objects.select_related(
        "dtype", "created_by", "experimenter", "superseded_by"
    ).prefetch_related("locations")
    serializer_class = serializers.ResourceSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ResourceFilter
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning

    def is_filtered(self, request) -> bool:
        return super().is_filtered(request) or any(
            p.startswith("metadata__") for p in request.query_params
        )

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        # this could be a little dangerous b/c we're letting the user design
        # queries
        mf = {}
        me = {}
        for param, v in self.request.GET.items():
            if param.startswith("metadata__"):
                k = param
                exclude = k.endswith("__neq")
                if exclude:
                    k = k[:-5]
                key = k.removeprefix("metadata__").partition("__")[0]
                if key in serializers.CORE_FIELDS:
                    raise ValidationError(
                        {
                            param: [
                                f"'{key}' is a field of the resource, not metadata; "
                                f"search it with ?{key}="
                            ]
                        }
                    )
                if k.endswith("__isnull"):
                    try:
                        v = ISNULL_VALUES[v.lower()]
                    except KeyError:
                        raise ValidationError(
                            {param: ["must be true or false"]}
                        ) from None
                else:
                    # try to parse the value as json, which will convert numeric
                    # values
                    try:
                        v = json.loads(v)
                    except json.decoder.JSONDecodeError:
                        pass
                (me if exclude else mf)[k] = v
        return qs.exclude(**me).filter(**mf).order_by("name")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ResourceDetail(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "name"
    queryset = models.Resource.objects.select_related(
        "dtype", "created_by", "experimenter", "superseded_by"
    ).prefetch_related("locations")
    serializer_class = serializers.ResourceSerializer
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            names = ", ".join(
                r.name for r in self.get_object().supersedes.order_by("name")
            )
            return Response(
                {"detail": f"can't delete a resource that supersedes others ({names})"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class ResourceCheck(generics.GenericAPIView):
    """Checks a resource as it would be created (POST the same body as to
    resources/), without creating it: that its name and sha1 aren't taken, and
    that its dtype, archives, experimenter, animal, and metadata are valid.

    Returns 200 if the resource could be created, or 400 with the errors that
    creating it would give. Another deposit can still take the name or sha1
    before the resource is created.

    POST a list of bodies to check several resources: the response is 200 with
    a list of the errors for each one, in order ({} if it could be created). A
    name or sha1 that an earlier resource in the list has is an error, as it
    would be if they were created in order.
    """

    queryset = models.Resource.objects.all()
    serializer_class = serializers.ResourceSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    versioning_class = ApiVersioning

    def post(self, request, *args, **kwargs):
        if isinstance(request.data, list):
            return self.check_many(request.data)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": "the resource can be created"})

    def check_many(self, bodies: list) -> Response:
        if not bodies:
            detail = "give at least one resource"
        elif len(bodies) > MAX_RESOURCE_CHECKS:
            detail = f"give at most {MAX_RESOURCE_CHECKS} resources"
        elif not all(isinstance(body, dict) for body in bodies):
            detail = "each resource must be an object"
        else:
            detail = None
        if detail is not None:
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        results = []
        earlier = {"name": {}, "sha1": {}}
        for i, body in enumerate(bodies):
            serializer = self.get_serializer(data=body)
            if serializer.is_valid():
                errors = {}
            else:
                errors = {k: list(v) for k, v in serializer.errors.items()}
            for field, seen in earlier.items():
                value = body.get(field)
                if not isinstance(value, str) or not value:
                    continue
                if field == "sha1":
                    value = value.lower()
                if value in seen:
                    errors.setdefault(field, []).append(
                        f"the same as resource {seen[value]} in this request"
                    )
                else:
                    seen[value] = i
            results.append(errors)
        return Response(results)


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
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ArchiveFilter


class ArchiveDetail(generics.RetrieveUpdateAPIView):
    lookup_field = "name"
    queryset = models.Archive.objects.all()
    serializer_class = serializers.ArchiveSerializer
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning


class DataTypeList(generics.ListCreateAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning


class DataTypeDetail(generics.RetrieveAPIView):
    lookup_field = "name"
    queryset = models.DataType.objects.all()
    serializer_class = serializers.DataTypeSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    versioning_class = ApiVersioning


class AllLocationList(StreamedListMixin, generics.ListAPIView):
    """This view is a list of every location in the registry, with its resource's
    file name and hash, ordered by resource name.

    Filter with `archive` (the archive's name), `scheme`, and `has_key`. Results are
    paginated JSON, with links to the other pages in the Link header; a request that
    asks for `application/x-ndjson` and searches with at least one parameter gets
    every result in one response instead, streamed as line-delimited JSON. The
    registry's download locations aren't listed.

    """

    queryset = models.Location.objects.select_related(
        "archive", "resource__dtype"
    ).order_by("resource__name", "archive__name")
    serializer_class = serializers.LocationRecordSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = AllLocationFilter
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning


class LocationList(generics.ListAPIView):
    """List locations for a specific resource"""

    serializer_class = serializers.LocationSerializer
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = LocationFilter

    def get_object(self):
        if not hasattr(self, "_resource"):
            self._resource = get_object_or_404(
                models.Resource.objects.select_related("dtype"),
                name=self.kwargs["resource_name"],
            )
        return self._resource

    def get_queryset(self):
        resource = self.get_object()
        return resource.location_set.select_related("archive")

    def list(self, request, *args, **kwargs):
        resource = self.get_object()
        f = LocationFilter(
            request.GET,
            resource.location_set.select_related("archive").order_by(
                "archive__accessibility"
            ),
        )
        qs = f.qs
        if resource.dtype.downloadable and len(request.query_params) == 0:
            qs = add_virtual_registry_location(request, resource, qs)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        data = {"resource_name": kwargs["resource_name"]}
        if "archive_name" in request.data:
            data["archive_name"] = request.data["archive_name"]
        if "key" in request.data:
            data["key"] = request.data["key"]
        serializer = serializers.LocationSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            serializer.save()
        except IntegrityError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class LocationDetail(generics.RetrieveDestroyAPIView):
    queryset = models.Location.objects.all()
    serializer_class = serializers.LocationSerializer
    permission_classes = CHANGE_PERMISSIONS
    versioning_class = ApiVersioning

    def get_object(self):
        return get_object_or_404(
            models.Location,
            resource__name=self.kwargs["resource_name"],
            archive__name=self.kwargs["archive_pk"],
        )

    def patch(self, request, *args, **kwargs):
        if set(request.data) - {"key"}:
            return Response(
                {"detail": "only the key of a location can be changed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        location = self.get_object()
        serializer = serializers.LocationSerializer(
            location, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            serializer.save()
        except IntegrityError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.data)


def check_bulk_args(request):
    """Parse bulk arguments.

    Returns a list of names or raises ValueError with a detailed error message for the
    response.

    """
    try:
        names = request.data["names"]
    except KeyError:
        raise ValueError("usage: {'names': ['id1', 'id2', ...]}") from None
    if not isinstance(names, list):
        raise ValueError("'names' must be a list of names")
    if len(names) == 0:
        raise ValueError("must supply at least one name")
    return names


@api_view(["POST"])
def bulk_resource_list(request, format=None):
    """Retrieve metadata for multiple resources by name. POST {'names': ['name1', 'name2',...]}.
    Streams results as line-delimited JSON records.

    """
    try:
        names = check_bulk_args(request)
    except ValueError as err:
        return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
    query = Q()
    for name in names:
        query |= Q(name=name)
    qs = models.Resource.objects.filter(query).select_related(
        "experimenter", "superseded_by"
    )
    return stream_jsonl(serializers.ResourceSerializer(obj).data for obj in qs)


@api_view(["POST"])
def bulk_location_list(request, format=None):
    """Retrieve locations for multiple resources by name. POST {'names': ['name1', 'name2',...]}
    Streams results as line-delimited JSON records.

    """
    try:
        names = check_bulk_args(request)
    except ValueError as err:
        return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
    request.data.pop("names")
    query = Q()
    for name in names:
        query |= Q(name=name)
    qs = models.Resource.objects.filter(query).select_related("dtype")

    def gen(qs):
        for resource in qs:
            lqs = list(
                LocationFilter(
                    request.data,
                    resource.location_set.select_related("archive").order_by(
                        "archive__accessibility"
                    ),
                ).qs
            )
            if not lqs:
                continue
            if resource.dtype.downloadable and len(request.data) == 0:
                lqs = add_virtual_registry_location(request, resource, lqs)
            yield {
                "name": resource.name,
                "sha1": resource.sha1,
                "filename": resource.filename(),
                "locations": serializers.LocationSerializer(lqs, many=True).data,
            }

    return stream_jsonl(gen(qs))
