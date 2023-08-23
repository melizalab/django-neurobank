# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.urls import re_path, path

from nbank_registry import views

app_name = "neurobank"
urlpatterns = [
    re_path(r"^$", views.api_root, name="index"),
    re_path(r"^info/$", views.api_info, name="api-info"),
    re_path(r"^datatypes/$", views.DataTypeList.as_view(), name="datatype-list"),
    re_path(
        r"^datatypes/(?P<name>[\w-]+)/$",
        views.DataTypeDetail.as_view(),
        name="datatype",
    ),
    re_path(r"^archives/$", views.ArchiveList.as_view(), name="archive-list"),
    re_path(
        r"^archives/(?P<name>[\w-]+)/$", views.ArchiveDetail.as_view(), name="archive"
    ),
    re_path(r"^resources/$", views.ResourceList.as_view(), name="resource-list"),
    re_path(
        r"^resources/(?P<name>[\w-]+)/$",
        views.ResourceDetail.as_view(),
        name="resource",
    ),
    path(
        "resources/<slug:name>/download",
        views.download_resource,
        name="resource-download-old",
    ),
    re_path(
        r"^resources/(?P<resource_name>[\w-]+)/locations/$",
        views.LocationList.as_view(),
        name="location-list",
    ),
    re_path(
        r"^bulk/resources/$",
        views.bulk_resource_list,
        name="bulk-resource-list",
    ),
    re_path(
        r"^bulk/locations/$",
        views.bulk_location_list,
        name="bulk-location-list",
    ),
    path(
        "download/<slug:name>/",
        views.download_resource,
        name="resource-download",
    ),
    # used to construct locations for the registry
    re_path(r"^download/$", views.notfound, name="resource-download-base"),
    # fallthrough to 404
    re_path(r"^.*/$", views.notfound, name="notfound"),
]
