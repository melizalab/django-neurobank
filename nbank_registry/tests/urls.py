from django.contrib import admin
from django.contrib.auth import views as authviews
from django.urls import include, re_path

urlpatterns = [
    re_path(r"^neurobank/", include("nbank_registry.urls")),
    re_path(r"^accounts/api-auth/", include("rest_framework.urls")),
]
