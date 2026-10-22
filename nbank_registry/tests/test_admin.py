# -*- mode: python -*-
"""The resource admin's autocomplete for animals, which depends on the animal
model having an admin with search_fields."""

import pytest
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, ForeignKeyRawIdWidget
from django.test import RequestFactory

from nbank_registry.admin import ResourceAdmin
from nbank_registry.models import Animal, Resource, get_animal_model

pytestmark = pytest.mark.django_db


@pytest.fixture
def request_(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


def resource_admin(animal_search_fields=None):
    """A ResourceAdmin on its own site, with an admin for the animal model if
    animal_search_fields is given"""
    site = admin.AdminSite()
    if animal_search_fields is not None:
        site.register(get_animal_model(), search_fields=animal_search_fields)
    site.register(Resource, ResourceAdmin)
    return site._registry[Resource]


def animal_widget(model_admin, request):
    field = Resource._meta.get_field("animal")
    return model_admin.formfield_for_dbfield(field, request).widget


def test_animal_autocomplete_with_a_searchable_admin(request_):
    model_admin = resource_admin(animal_search_fields=("pk",))
    assert "animal" in model_admin.get_autocomplete_fields(request_)
    assert isinstance(animal_widget(model_admin, request_), AutocompleteSelect)


@pytest.mark.parametrize("search_fields", [None, ()], ids=["no-admin", "no-search"])
def test_animal_raw_id_otherwise(request_, search_fields):
    model_admin = resource_admin(animal_search_fields=search_fields)
    assert model_admin.get_autocomplete_fields(request_) == ("superseded_by",)
    widget = animal_widget(model_admin, request_)
    assert isinstance(widget, ForeignKeyRawIdWidget)


def test_default_site(request_):
    """The registry's own animal model has a searchable admin; a site's own
    model (the tests' UUID model) has none."""
    model_admin = admin.site._registry[Resource]
    autocomplete = "animal" in model_admin.get_autocomplete_fields(request_)
    assert autocomplete == (not Animal._meta.swapped)


def test_autocomplete_finds_animals(auth_client, animal):
    """The view the widget calls finds animals with the default model, and
    refuses with a model that has no admin."""
    name = animal("P50")
    response = auth_client.get(
        "/admin/autocomplete/",
        {
            "app_label": "nbank_registry",
            "model_name": "resource",
            "field_name": "animal",
            "term": "P5" if not Animal._meta.swapped else name[:8],
        },
    )
    if Animal._meta.swapped:
        assert response.status_code in (403, 404)
    else:
        assert response.status_code == 200
        assert [r["id"] for r in response.json()["results"]] == [name]
