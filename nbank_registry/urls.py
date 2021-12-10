# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.conf.urls import re_path

from nbank_registry import views

app_name = "neurobank"
urlpatterns = [
    re_path(r'^$', views.api_root, name='index'),
    re_path(r'^info/$', views.api_info, name='api-info'),
    re_path(r"^datatypes/$", views.DataTypeList.as_view(), name="datatype-list"),
    re_path(r"^datatypes/(?P<name>[\w-]+)/$", views.DataTypeDetail.as_view(),
        name='datatype'),
    re_path(r"^archives/$", views.ArchiveList.as_view(), name="archive-list"),
    re_path(r"^archives/(?P<name>[\w-]+)/$", views.ArchiveDetail.as_view(),
        name='archive'),
    re_path(r"^resources/$", views.ResourceList.as_view(), name="resource-list"),
    re_path(r"^resources/(?P<name>[\w-]+)/$", views.ResourceDetail.as_view(),
        name='resource'),
    re_path(r"^resources/(?P<name>[\w-]+)/download", views.ResourceDownload.as_view(),
        name='resource-download'),
    re_path(r"^resources/(?P<resource_name>[\w-]+)/locations/$",
        views.LocationList.as_view(), name="location-list"),
    re_path(r"^resources/(?P<resource_name>[\w-]+)/locations/(?P<archive_pk>[\w-]+)/$",
        views.LocationDetail.as_view(), name="location"),
    # fallthrough to 404
    re_path(r"^.*/$", views.notfound, name='notfound')
]
