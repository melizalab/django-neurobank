from django.urls import include, path

urlpatterns = [
    path("^neurobank/", include("nbank_registry.urls")),
    path("^accounts/api-auth/", include("rest_framework.urls")),
]
