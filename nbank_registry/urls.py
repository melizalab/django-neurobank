# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.urls import path, re_path

from nbank_registry import views

app_name = "neurobank"
urlpatterns = [
    path("", views.api_root, name="index"),
    path("info/", views.api_info, name="api-info"),
    path("datatypes/", views.DataTypeList.as_view(), name="datatype-list"),
    path(
        "datatypes/<slug:name>/",
        views.DataTypeDetail.as_view(),
        name="datatype",
    ),
    path("archives/", views.ArchiveList.as_view(), name="archive-list"),
    path("archives/<slug:name>/", views.ArchiveDetail.as_view(), name="archive"),
    path("resources/", views.ResourceList.as_view(), name="resource-list"),
    path(
        "resources/<slug:name>/",
        views.ResourceDetail.as_view(),
        name="resource",
    ),
    path(
        "resources/<slug:name>/download",
        views.download_resource,
        name="resource-download-old",
    ),
    path(
        "resources/<slug:resource_name>/locations/",
        views.LocationList.as_view(),
        name="location-list",
    ),
    path(
        "resources/<slug:resource_name>/locations/<slug:archive_pk>/",
        views.LocationDetail.as_view(),
        name="location",
    ),
    path(
        "bulk/resources/",
        views.bulk_resource_list,
        name="bulk-resource-list",
    ),
    path(
        "bulk/locations/",
        views.bulk_location_list,
        name="bulk-location-list",
    ),
    path(
        "download/<slug:name>/",
        views.download_resource,
        name="resource-download",
    ),
    # used to construct locations for the registry
    path("download/", views.notfound, name="resource-download-base"),
    # fallthrough to 404
    re_path(r"^.*/$", views.notfound, name="notfound"),
]
