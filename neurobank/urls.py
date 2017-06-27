# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.conf.urls import url

from neurobank import views

urlpatterns = [
    url(r"^resources/$", views.ResourceList.as_view(), name="resource-list"),
    url(r"^resources/(?P<pk>[a-f0-9\-]{36})/$", views.ResourceDetail.as_view(),
        name='resource'),
]
