# -*- coding: utf-8 -*-
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
