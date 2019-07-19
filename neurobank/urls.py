# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.conf.urls import url

from neurobank import views

app_name = "neurobank"
urlpatterns = [
    url(r'^$', views.api_root, name='index'),
    url(r'^info/$', views.api_info, name='api-info'),
    url(r"^datatypes/$", views.DataTypeList.as_view(), name="datatype-list"),
    url(r"^datatypes/(?P<name>[\w-]+)/$", views.DataTypeDetail.as_view(),
        name='datatype'),
    url(r"^archives/$", views.ArchiveList.as_view(), name="archive-list"),
    url(r"^archives/(?P<name>[\w-]+)/$", views.ArchiveDetail.as_view(),
        name='archive'),
    url(r"^resources/$", views.ResourceList.as_view(), name="resource-list"),
    url(r"^resources/(?P<name>[\w-]+)/$", views.ResourceDetail.as_view(),
        name='resource'),
    url(r"^resources/(?P<resource_name>[\w-]+)/locations/$",
        views.LocationList.as_view(), name="location-list"),
    url(r"^resources/(?P<resource_name>[\w-]+)/locations/(?P<archive_pk>[\w-]+)/$",
        views.LocationDetail.as_view(), name="location"),
    # fallthrough to 404
    url(r"^.*/$", views.notfound, name='notfound')
]
