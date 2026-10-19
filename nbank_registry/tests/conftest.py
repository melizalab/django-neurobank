# -*- mode: python -*-
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

USERNAME = "user"
PASSWORD = "password1"


@pytest.fixture
def client():
    """An unauthenticated DRF APIClient (overrides pytest-django's plain Client)."""
    return APIClient()


@pytest.fixture
def user_password():
    return PASSWORD


@pytest.fixture
def user(db):
    return User.objects.create_superuser(
        username=USERNAME, password=PASSWORD, email="user@domain.com"
    )


@pytest.fixture
def auth_client(client, user):
    client.login(username=USERNAME, password=PASSWORD)
    return client


@pytest.fixture
def animal(db):
    """Returns a function that creates an animal and returns its identifier.

    The identifier is the name with the default animal model, and a UUID with
    NBANK_TEST_ANIMAL_MODEL=uuid.
    """
    from nbank_registry.models import get_animal_model

    def make(name: str) -> str:
        return str(get_animal_model().objects.create(name=name).pk)

    return make
