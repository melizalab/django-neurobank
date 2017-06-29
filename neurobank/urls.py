# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.conf.urls import url

from neurobank import views

urlpatterns = [
    url(r"^datatypes/$", views.DataTypeList.as_view(), name="datatype-list"),
    url(r"^datatypes/(?P<name>[\w-]+)/$", views.DataTypeDetail.as_view(),
        name='datatype'),
    url(r"^domains/$", views.DomainList.as_view(), name="domain-list"),
    url(r"^domains/(?P<name>[\w-]+)/$", views.DomainDetail.as_view(),
        name='domain'),
    url(r"^resources/$", views.ResourceList.as_view(), name="resource-list"),
    url(r"^resources/(?P<pk>[a-f0-9\-]{36})/$", views.ResourceDetail.as_view(),
        name='resource'),
    url(r"^resources/(?P<resource_pk>[a-f0-9\-]{36})/locations/$",
        views.LocationList.as_view(), name="location-list"),
    url(r"^resources/(?P<resource_pk>[a-f0-9\-]{36})/locations/(?P<domain_pk>[\w-]+)/$",
        views.LocationDetail.as_view(), name="location")
]
