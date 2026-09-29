# -*- coding: utf-8 -*-
# -*- mode: python -*-
import hashlib
import json
import os
import posixpath as ppath
import tempfile
import uuid

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from rest_framework import status

from nbank_registry.models import Archive, DataType, Location, Resource
from nbank_registry.views import DOWNLOAD_ARCHIVE_NAME

pytestmark = pytest.mark.django_db

# DataType and Archive names are both 32-character SlugFields
INVALID_SLUG_NAMES = [
    pytest.param("a" * 33, id="too-long"),
    pytest.param("bad name", id="contains-space"),
    pytest.param("bad!name", id="contains-punctuation"),
    pytest.param("bad.name", id="contains-period"),
]
# Bulk access requires a list of names
INVALID_BULK_NAMES = [[], "bare string", 5]


class TestResource:
    @pytest.fixture(autouse=True)
    def setup(self, user):
        self.user = user
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pprox+json; version=1.0",
        )
        self.archive = Archive.objects.create(
            name="local", scheme="neurobank", root="/home/data/intracellular"
        )
        self.archive_2 = Archive.objects.create(
            name="other", scheme="neurobank", root="/home/data/other"
        )
        self.resource = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"},
        )
        self.location = Location.objects.create(
            resource=self.resource, archive=self.archive
        )

    def test_can_access_resource_list(self, client):
        response = client.get(reverse("neurobank:resource-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_can_create_resource(self, auth_client):
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {
                "dtype": self.dtype.name,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        response2 = auth_client.get(
            reverse("neurobank:resource", args=[response.data["name"]])
        )
        assert response2.status_code == status.HTTP_200_OK

    def test_can_create_resource_with_own_name(self, auth_client):
        myuuid = str(uuid.uuid4())
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {"dtype": self.dtype.name, "name": myuuid},
        )
        assert response.status_code == status.HTTP_201_CREATED
        response2 = auth_client.get(reverse("neurobank:resource", args=[myuuid]))
        assert response2.status_code == status.HTTP_200_OK

    def test_cannot_create_resource_with_invalid_name(self, auth_client):
        bad_name = "blah/blah"
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {"dtype": self.dtype.name, "name": bad_name},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_create_resource_with_duplicate_name(self, auth_client):
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {
                "dtype": self.dtype.name,
                "name": self.resource.name,
                "locations": [self.archive_2.name],
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # check that the location was not created (database should roll back on error)
        response = auth_client.get(
            reverse("neurobank:location-list", args=[self.resource])
        )
        assert response.status_code == status.HTTP_200_OK
        assert self.archive_2.name not in [loc["archive_name"] for loc in response.data]

    def test_can_create_resource_with_metadata(self, auth_client):
        myuuid = str(uuid.uuid4())
        mdata = {"blah": "1234"}
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {"dtype": self.dtype.name, "name": myuuid, "metadata": mdata},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        response2 = auth_client.get(reverse("neurobank:resource", args=[myuuid]))
        assert response2.status_code == status.HTTP_200_OK
        assert response2.data["metadata"] == mdata

    @pytest.mark.parametrize("bad_meta", ["bare_string", 5])
    def test_cannot_create_resource_with_nonobject_metadata(
        self, auth_client, bad_meta
    ):
        myuuid = str(uuid.uuid4())
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {"dtype": self.dtype.name, "name": myuuid, "metadata": bad_meta},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_can_create_resource_with_location(self, auth_client):
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {"dtype": self.dtype.name, "locations": [self.archive.name]},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == response.data | {"locations": [self.archive.name]}

    def test_cannot_create_resource_with_invalid_location(self, auth_client):
        myuuid = str(uuid.uuid4())
        response = auth_client.post(
            reverse("neurobank:resource-list"),
            {"dtype": self.dtype.name, "name": myuuid, "locations": ["bad-location"]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # check that resource was not created
        response = auth_client.get(reverse("neurobank:resource", args=[myuuid]))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_can_access_resource_detail(self, client):
        response = client.get(reverse("neurobank:resource", args=[self.resource.name]))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == response.data | {
            "name": str(self.resource),
            "sha1": self.resource.sha1,
            "dtype": self.dtype.name,
            "filename": self.resource.filename(),
            "created_by": self.user.username,
            "metadata": self.resource.metadata,
            "locations": [self.archive.name],
        }

    def test_cannot_access_nonexistent_resource_detail(self, client):
        response = client.get(reverse("neurobank:resource", args=[uuid.uuid4()]))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_access_invalid_resource_detail(self, client):
        url = ppath.join(reverse("neurobank:resource-list"), "not.a.slug") + "/"
        response = client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_can_bulk_access_resource_detail(self, client):
        query = {"names": [self.resource.name]}
        response = client.post(
            reverse("neurobank:bulk-resource-list"), query, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        data = [json.loads(record) for record in response]
        assert len(data) == 1
        assert data[0] == data[0] | {
            "name": str(self.resource),
            "sha1": self.resource.sha1,
            "dtype": self.dtype.name,
            "filename": self.resource.filename(),
            "created_by": self.user.username,
            "metadata": self.resource.metadata,
            "locations": [self.archive.name],
        }

    @pytest.mark.parametrize("bad_names", INVALID_BULK_NAMES)
    def test_cannot_bulk_access_resource_with_bad_names(self, client, bad_names):
        query = {"names": bad_names}
        response = client.post(
            reverse("neurobank:bulk-resource-list"), query, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_access_resource_with_bad_request(self, client):
        query = {"something_wrong": [self.resource.name]}
        response = client.post(
            reverse("neurobank:bulk-resource-list"), query, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_can_access_resource_locations(self, client):
        response = client.get(
            reverse("neurobank:location-list", args=[self.resource.name])
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0] == response.data[0] | {
            "archive_name": self.archive.name,
            "resource_name": self.resource.name,
            "root": self.archive.root,
            "scheme": self.archive.scheme,
        }

    def test_can_filter_resource_locations(self, client):
        response = client.get(
            reverse("neurobank:location-list", args=[self.resource.name]),
            {"archive": self.archive.name},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        response = client.get(
            reverse("neurobank:location-list", args=[self.resource.name]),
            {"archive": "no-such-archive"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0

    def test_cannot_access_nonexistent_resource_locations(self, client):
        response = client.get(reverse("neurobank:location-list", args=["argle-bargle"]))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_bulk_access_resource_locations(self, client):
        query = {"names": [self.resource.name]}
        response = client.post(
            reverse("neurobank:bulk-location-list"), query, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        data = [json.loads(record) for record in response]
        assert len(data) == 1
        res_loc = data[0]
        assert res_loc["name"] == self.resource.name
        assert res_loc["filename"] == self.resource.filename()
        assert len(res_loc["locations"]) == 1
        assert res_loc["locations"][0] == res_loc["locations"][0] | {
            "archive_name": self.archive.name,
            "resource_name": self.resource.name,
            "root": self.archive.root,
            "scheme": self.archive.scheme,
        }

    @pytest.mark.parametrize("bad_names", INVALID_BULK_NAMES)
    def test_cannot_bulk_access_resource_locations_with_bad_names(
        self, client, bad_names
    ):
        query = {"names": bad_names}
        response = client.post(
            reverse("neurobank:bulk-location-list"), query, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bulk_access_resource_locations_with_bad_request(self, client):
        query = {"something_wrong": [self.resource.name]}
        response = client.post(
            reverse("neurobank:bulk-location-list"), query, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_anonymously_delete_resource(self, client):
        response = client.delete(reverse("neurobank:resource", args=[self.resource]))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_can_delete_resource(self, auth_client):
        response = auth_client.delete(
            reverse("neurobank:resource", args=[self.resource])
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        response2 = auth_client.get(
            reverse("neurobank:resource", args=[self.resource.name])
        )
        assert response2.status_code == status.HTTP_404_NOT_FOUND
        assert self.location not in Location.objects.all()

    def test_cannot_modify_name(self, auth_client):
        response = auth_client.patch(
            reverse("neurobank:resource", args=[self.resource]),
            {"name": str(uuid.uuid4())},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_superuser_can_modify_sha1(self, auth_client):
        my_sha = hashlib.sha1(b"blah").hexdigest()
        response = auth_client.patch(
            reverse("neurobank:resource", args=[self.resource]),
            {"sha1": my_sha},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["sha1"] == my_sha

    def test_nonsuperuser_cannot_modify_sha1(self, client, user_password):
        normal_user = User.objects.create_user(
            username="normal_user",
            password=user_password,
            email="normal-user@domain.com",
        )
        normal_user.user_permissions.add(
            Permission.objects.get(codename="change_resource")
        )
        client.login(username="normal_user", password=user_password)
        response = client.patch(
            reverse("neurobank:resource", args=[self.resource]),
            {"sha1": hashlib.sha1(b"blah").hexdigest()},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_can_update_metadata(self, auth_client):
        response = auth_client.patch(
            reverse("neurobank:resource", args=[self.resource]),
            {"metadata": {"test_field": "value"}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["metadata"] == response.data["metadata"] | {
            "test_field": "value"
        }

    @pytest.mark.skip(reason="not implemented")
    def test_can_dry_run_create_resource(self, auth_client):
        response = auth_client.post(
            reverse("neurobank:resource-test-create"),
            {
                "dtype": self.dtype.name,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        response2 = auth_client.get(
            reverse("neurobank:resource", args=[response.data["name"]])
        )
        assert response2.status_code == status.HTTP_404_NOT_FOUND


class TestLocation:
    @pytest.fixture(autouse=True)
    def setup(self, user):
        self.user = user
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0",
        )
        self.archive = Archive.objects.create(
            name="local", scheme="neurobank", root="/home/data/intracellular"
        )
        self.resource = Resource.objects.create(
            name="a_boring_file",
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"},
        )
        self.location = Location.objects.create(
            resource=self.resource, archive=self.archive
        )

    def test_location_list(self, client):
        response = client.get(reverse("neurobank:location-list", args=[self.resource]))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_location_list_sorted_by_accessbility(self, client):
        offline_archive = Archive.objects.create(
            name="tape",
            scheme="tape",
            root="tape_a:1",
            accessibility=Archive.Accessibility.OFFLINE,
        )
        resource = Resource.objects.create(
            name="an_important_file",
            sha1=hashlib.sha1(b"12345").hexdigest(),
            dtype=self.dtype,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"},
        )
        Location.objects.create(
            resource=resource,
            archive=offline_archive,
        )
        Location.objects.create(
            resource=resource,
            archive=self.archive,
        )
        response = client.get(reverse("neurobank:location-list", args=[resource]))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        assert response.data[0]["archive_name"] == self.archive.name
        assert response.data[1]["archive_name"] == offline_archive.name

    def test_location_list_404_invalid_resource(self, client):
        response = client.get(reverse("neurobank:location-list", args=["adsadf"]))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_location_404_invalid_archive(self, client):
        dummy_location = "adsfadf"
        response = client.get(
            reverse("neurobank:location", args=[self.resource, dummy_location])
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_location_detail(self, client):
        response = client.get(
            reverse("neurobank:location", args=[self.resource, self.archive])
        )
        assert response.status_code == status.HTTP_200_OK
        ret = response.data
        assert ret == ret | {
            "archive_name": self.archive.name,
            "resource_name": self.resource.name,
            "scheme": self.archive.scheme,
        }

    def test_cannot_add_duplicate_location(self, auth_client):
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": self.archive.name},
        )
        assert (
            response.status_code == status.HTTP_400_BAD_REQUEST
        ), "should not be able to add duplicate archive to resource locations"

    def test_can_delete_location(self, auth_client):
        response = auth_client.delete(
            reverse("neurobank:location", args=[self.resource.name, self.archive])
        )
        assert (
            response.status_code == status.HTTP_204_NO_CONTENT
        ), "unable to delete a location"

        response = auth_client.get(
            reverse("neurobank:location-list", args=[self.resource])
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_can_add_location(self, auth_client):
        new_archive = Archive.objects.create(
            name="secret", scheme="neurobank", root="/home/data/secret"
        )
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": new_archive.name},
            format="json",
        )
        assert (
            response.status_code == status.HTTP_201_CREATED
        ), "unable to add location to resource"
        assert self.resource.locations.count() == 2

    def test_post_location_without_archive_name_is_bad_request(self, auth_client):
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["archive_name"] == ["This field is required."]

    def test_location_key_defaults_to_null(self, client):
        response = client.get(
            reverse("neurobank:location", args=[self.resource, self.archive])
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["key"] is None

    def test_can_add_location_with_key(self, auth_client):
        new_archive = Archive.objects.create(
            name="dataverse", scheme="dataverse", root="dataverse.example.edu/doi:1"
        )
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": new_archive.name, "key": "123456"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["key"] == "123456"

        list_response = auth_client.get(
            reverse("neurobank:location-list", args=[self.resource])
        )
        by_archive = {loc["archive_name"]: loc for loc in list_response.data}
        assert by_archive[new_archive.name]["key"] == "123456"

        detail_response = auth_client.get(
            reverse("neurobank:location", args=[self.resource, new_archive])
        )
        assert detail_response.data["key"] == "123456"

        bulk_response = auth_client.post(
            reverse("neurobank:bulk-location-list"),
            {"names": [self.resource.name]},
            format="json",
        )
        data = [json.loads(record) for record in bulk_response]
        bulk_by_archive = {loc["archive_name"]: loc for loc in data[0]["locations"]}
        assert bulk_by_archive[new_archive.name]["key"] == "123456"

    def test_can_add_location_with_empty_string_key_stores_null(self, auth_client):
        new_archive = Archive.objects.create(
            name="secret", scheme="neurobank", root="/home/data/secret"
        )
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": new_archive.name, "key": ""},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["key"] is None

    def test_can_add_location_with_numeric_key_stores_as_string(self, auth_client):
        new_archive = Archive.objects.create(
            name="dataverse", scheme="dataverse", root="dataverse.example.edu/doi:1"
        )
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": new_archive.name, "key": 123456},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["key"] == "123456"

    def test_cannot_add_location_with_too_long_key(self, auth_client):
        new_archive = Archive.objects.create(
            name="secret", scheme="neurobank", root="/home/data/secret"
        )
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": new_archive.name, "key": "a" * 1025},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["key"] == [
            "Ensure this field has no more than 1024 characters."
        ]

    def test_cannot_add_duplicate_key_in_same_archive(self, auth_client):
        new_archive = Archive.objects.create(
            name="dataverse", scheme="dataverse", root="dataverse.example.edu/doi:1"
        )
        other_resource = Resource.objects.create(dtype=self.dtype, created_by=self.user)
        Location.objects.create(
            resource=other_resource, archive=new_archive, key="123456"
        )
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": new_archive.name, "key": "123456"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["key"] == [
            "another resource in this archive already has this key"
        ]

    def test_can_reuse_key_in_different_archive(self, auth_client):
        archive_a = Archive.objects.create(
            name="dataverse-a", scheme="dataverse", root="dataverse.example.edu/a"
        )
        archive_b = Archive.objects.create(
            name="dataverse-b", scheme="dataverse", root="dataverse.example.edu/b"
        )
        other_resource = Resource.objects.create(dtype=self.dtype, created_by=self.user)
        Location.objects.create(resource=other_resource, archive=archive_a, key="123456")
        response = auth_client.post(
            reverse("neurobank:location-list", args=[self.resource]),
            {"archive_name": archive_b.name, "key": "123456"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_can_have_multiple_null_keys_in_same_archive(self):
        other_resource = Resource.objects.create(dtype=self.dtype, created_by=self.user)
        Location.objects.create(resource=other_resource, archive=self.archive)
        # self.location already has a null key in self.archive from setup
        assert (
            Location.objects.filter(archive=self.archive, key__isnull=True).count() == 2
        )

    def test_can_patch_key(self, auth_client):
        url = reverse("neurobank:location", args=[self.resource, self.archive])
        response = auth_client.patch(url, {"key": "abc"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["key"] == "abc"

        response = auth_client.patch(url, {"key": "def"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["key"] == "def"
        get_response = auth_client.get(url)
        assert get_response.data["key"] == "def"

        response = auth_client.patch(url, {"key": None}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["key"] is None
        get_response = auth_client.get(url)
        assert get_response.data["key"] is None

    def test_cannot_patch_other_fields(self, auth_client):
        url = reverse("neurobank:location", args=[self.resource, self.archive])
        response = auth_client.patch(
            url, {"archive_name": "somewhere-else"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"detail": "only the key of a location can be changed"}
        self.location.refresh_from_db()
        assert self.location.archive == self.archive

    def test_cannot_patch_key_without_authentication(self, client):
        url = reverse("neurobank:location", args=[self.resource, self.archive])
        response = client.patch(url, {"key": "abc"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_patch_key_without_permission(self, client, user_password):
        normal_user = User.objects.create_user(
            username="normal_user",
            password=user_password,
            email="normal-user@domain.com",
        )
        normal_user.user_permissions.add(Permission.objects.get(codename="add_location"))
        normal_user.user_permissions.add(
            Permission.objects.get(codename="delete_location")
        )
        client.login(username="normal_user", password=user_password)
        url = reverse("neurobank:location", args=[self.resource, self.archive])
        response = client.patch(url, {"key": "abc"}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_patch_nonexistent_location_returns_404(self, auth_client):
        url = reverse("neurobank:location", args=[self.resource, "no-such-archive"])
        response = auth_client.patch(url, {"key": "abc"}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDataType:
    @pytest.fixture(autouse=True)
    def setup(self, user):
        self.user = user
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0",
            extension="pprox",
        )

    def test_can_access_datatype_list(self, client):
        response = client.get(reverse("neurobank:datatype-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_can_access_datatype_detail(self, client):
        response = client.get(reverse("neurobank:datatype", args=[self.dtype]))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "name": self.dtype.name,
            "content_type": self.dtype.content_type,
            "extension": "pprox",
        }

    def test_cannot_access_nonexistent_datatype_detail(self, client):
        response = client.get(reverse("neurobank:datatype", args=["blarg"]))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_can_create_datatype(self, auth_client):
        data = {
            "name": "acoustic_waveform",
            "content_type": "audio/wav",
            "extension": "wav",
        }
        response = auth_client.post(reverse("neurobank:datatype-list"), data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == data

        response2 = auth_client.get(reverse("neurobank:datatype", args=[data["name"]]))
        assert response2.status_code == status.HTTP_200_OK
        assert response2.data == data

    @pytest.mark.parametrize("bad_name", INVALID_SLUG_NAMES)
    def test_cannot_create_datatype_with_invalid_name(self, auth_client, bad_name):
        data = {
            "name": bad_name,
            "content_type": "audio/wav",
            "extension": "wav",
        }
        response = auth_client.post(reverse("neurobank:datatype-list"), data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_create_duplicate_datatype(self, auth_client):
        data = {
            "name": self.dtype.name,
            "content_type": self.dtype.content_type,
            "extension": "pprox",
        }
        response = auth_client.post(reverse("neurobank:datatype-list"), data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_delete_datatype(self, auth_client):
        response = auth_client.delete(reverse("neurobank:datatype", args=[self.dtype]))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_cannot_modify_datatype(self, auth_client):
        response = auth_client.patch(
            reverse("neurobank:datatype", args=[self.dtype]), {"name": "blahblahblah"}
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestArchive:
    @pytest.fixture(autouse=True)
    def setup(self, user):
        self.user = user
        self.archive = Archive.objects.create(
            name="local", scheme="neurobank", root="/home/data/intracellular"
        )

    def test_can_access_archive_list(self, client):
        response = client.get(reverse("neurobank:archive-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_can_access_archive_detail(self, client):
        response = client.get(reverse("neurobank:archive", args=[self.archive]))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "name": self.archive.name,
            "scheme": self.archive.scheme,
            "root": self.archive.root,
            "accessibility": "local",  # default
        }

    def test_cannot_access_nonexistent_archive_detail(self, client):
        response = client.get(reverse("neurobank:archive", args=["blarg"]))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_can_create_archive(self, auth_client):
        data = {
            "name": "remote",
            "scheme": "http",
            "root": "/meliza.org/spike_times/",
            "accessibility": "remote",
        }
        response = auth_client.post(reverse("neurobank:archive-list"), data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data == data

        response2 = auth_client.get(reverse("neurobank:archive", args=[data["name"]]))
        assert response2.status_code == status.HTTP_200_OK
        assert response2.data == data

    def test_cannot_create_duplicate_archive(self, auth_client):
        data = {
            "name": self.archive.name,
            "scheme": "http",
            "root": "/meliza.org/spike_times/",
        }
        response = auth_client.post(reverse("neurobank:archive-list"), data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.parametrize("bad_name", INVALID_SLUG_NAMES)
    def test_cannot_create_archive_with_invalid_name(self, auth_client, bad_name):
        data = {
            "name": bad_name,
            "scheme": "http",
            "root": "/meliza.org/spike_times/",
        }
        response = auth_client.post(reverse("neurobank:archive-list"), data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_delete_archive(self, auth_client):
        response = auth_client.delete(reverse("neurobank:archive", args=[self.archive]))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_can_modify_archive(self, auth_client):
        response = auth_client.patch(
            reverse("neurobank:archive", args=[self.archive]),
            {"name": "local_intrac"},
        )
        assert response.status_code == status.HTTP_200_OK


class TestArchiveFilter:
    @pytest.fixture(autouse=True)
    def setup(self, user):
        self.user = user
        self.archive_1 = Archive.objects.create(
            name="intracellular", scheme="neurobank", root="/home/data/intracellular"
        )
        self.archive_2 = Archive.objects.create(
            name="extracellular", scheme="http", root="/meliza.org/data/extracellular"
        )

    def test_can_filter_by_scheme(self, client):
        url = reverse("neurobank:archive-list")
        response = client.get(url, {"scheme": self.archive_1.scheme})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_can_filter_by_root(self, client):
        url = reverse("neurobank:archive-list")
        response = client.get(url, {"root": self.archive_1.root})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1


class TestResourceFilter:
    @pytest.fixture(autouse=True)
    def setup(self, user):
        self.user = user
        self.dtype1 = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0",
        )
        self.dtype2 = DataType.objects.create(
            name="acoustic_waveform", content_type="audio/wav"
        )
        self.archive_local = Archive.objects.create(
            name="local", scheme="neurobank", root="/home/data/intracellular"
        )
        self.archive_remote = Archive.objects.create(
            name="remote", scheme="http", root="/meliza.org/data/intracellular"
        )
        self.resource1 = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype1,
            created_by=self.user,
            metadata={
                "experimenter": "dmeliza",
                "int_val": 5,
                "float_val": 3.12,
                "strint_val": "10",
            },
        )
        Location.objects.create(resource=self.resource1, archive=self.archive_local)
        Location.objects.create(resource=self.resource1, archive=self.archive_remote)
        self.resource2 = Resource.objects.create(
            dtype=self.dtype2,
            created_by=self.user,
            metadata={"experimenter": "mcb2x", "int_val": 7, "float_val": -0.123},
        )
        Location.objects.create(resource=self.resource2, archive=self.archive_local)

    def test_can_filter_by_name(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"name": str(self.resource1)[:6]}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource1)

    def test_can_filter_by_sha1(self, client):
        response = client.get(
            reverse("neurobank:resource-list"),
            {"sha1": str(self.resource1.sha1)[:6]},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource1)

    def test_can_filter_by_dtype(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"dtype": self.dtype1.name}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource1)

    def test_can_filter_by_user(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"created_by": self.user.username}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_can_filter_by_location(self, client):
        response = client.get(
            reverse("neurobank:resource-list"),
            {"location": self.archive_local.name},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_can_filter_by_no_location(self, client):
        response = client.get(
            reverse("neurobank:resource-list"),
            {"has_location": False},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0

    def test_can_filter_by_scheme(self, client):
        response = client.get(
            reverse("neurobank:resource-list"),
            {"scheme": self.archive_remote.scheme},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_can_filter_by_metadata(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"metadata__experimenter": "mcb2x"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource2)

    def test_can_exclude_by_metadata(self, client):
        response = client.get(
            reverse("neurobank:resource-list"),
            {"metadata__experimenter__neq": "mcb2x"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource1)

    def test_can_filter_by_numeric_value(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"metadata__int_val": 5}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource1)

    def test_can_filter_int_by_nonequality(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"metadata__int_val__gt": 5}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource2)

    def test_can_filter_float_by_nonequality(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"metadata__float_val__lte": 0}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource2)

    def test_can_filter_string_encoded_numeric_value(self, client):
        response = client.get(
            reverse("neurobank:resource-list"), {"metadata__strint_val": r'"10"'}
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == str(self.resource1)


class TestDownload:
    @pytest.fixture(autouse=True)
    def _sendfile_settings(self, settings):
        settings.SENDFILE_BACKEND = "django_sendfile.backends.nginx"
        settings.SENDFILE_ROOT = "/"
        settings.SENDFILE_URL = "/"

    @pytest.fixture(autouse=True)
    def setup(self, user, tmp_path):
        self.user = user
        self.directory = tmp_path
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pprox+json; version=1.0",
            downloadable=True,
        )
        self.archive = Archive.objects.create(
            name="local", scheme="neurobank", root=str(self.directory)
        )
        self.resource, self.fs_path = self._create_file()

    def _create_file(
        self,
        content=b"",
        skip_file_creation=False,
        dtype=None,
        archive=None,
    ):
        if dtype is None:
            dtype = self.dtype
        if archive is None:
            archive = self.archive
        file = tempfile.NamedTemporaryFile()
        file.write(content)
        resource = Resource.objects.create(
            sha1=hashlib.sha1(content).hexdigest(),
            dtype=dtype,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"},
        )
        Location.objects.create(resource=resource, archive=archive)
        fs_path = (
            self.directory / "resources" / resource.name[0:2] / (resource.name + ".bin")
        )
        if not skip_file_creation:
            fs_path.parent.mkdir(parents=True, exist_ok=True)
            fs_path.write_bytes(file.read())
        return resource, str(fs_path)

    def test_locations_include_remote(self, client):
        url = reverse("neurobank:location-list", args=[self.resource])
        response = client.get(url)
        assert response.status_code == 200
        assert {self.archive.name, DOWNLOAD_ARCHIVE_NAME} == {
            loc["archive_name"] for loc in response.data
        }

    def test_virtual_registry_location_has_null_key(self, client):
        url = reverse("neurobank:location-list", args=[self.resource])
        response = client.get(url)
        registry_loc = next(
            loc for loc in response.data if loc["archive_name"] == DOWNLOAD_ARCHIVE_NAME
        )
        assert registry_loc["key"] is None

    def test_bulk_locations_include_remote(self, client):
        query = {"names": [self.resource.name]}
        url = reverse("neurobank:bulk-location-list")
        response = client.post(url, query, format="json")
        assert response.status_code == 200
        data = [json.loads(record) for record in response]
        assert len(data) == 1
        res_loc = data[0]["locations"]
        assert {self.archive.name, DOWNLOAD_ARCHIVE_NAME} == {
            loc["archive_name"] for loc in res_loc
        }

    def test_bulk_locations_multiple_resources(self, client):
        resource, _path = self._create_file(content=b"something different")
        query = {"names": [self.resource.name, resource.name]}
        url = reverse("neurobank:bulk-location-list")
        response = client.post(url, query, format="json")
        assert response.status_code == 200
        data = [json.loads(record) for record in response]
        assert len(data) == 2

    def test_bulk_locations_filter_by_archive(self, client):
        archive = Archive.objects.create(
            name="other-local", scheme="neurobank", root=""
        )
        resource, _path = self._create_file(
            content=b"something different", skip_file_creation=True, archive=archive
        )
        query = {
            "names": [self.resource.name, resource.name],
            "archive": archive.name,
        }
        url = reverse("neurobank:bulk-location-list")
        response = client.post(url, query, format="json")
        assert response.status_code == 200
        data = [json.loads(record) for record in response]
        assert len(data) == 1
        res_loc = data[0]["locations"]
        assert (
            {archive.name} == {loc["archive_name"] for loc in res_loc}
        ), "bulk locations should omit registry when filtering by archive name or scheme"

    def test_nginx_header(self, client):
        url = reverse("neurobank:resource-download", args=[self.resource])
        response = client.get(url)
        assert response.status_code == 200
        assert ppath.samefile(response["X-Accel-Redirect"], self.fs_path)

    def test_missing_file(self, client):
        missing_resource, _ = self._create_file(b"missing", skip_file_creation=True)
        url = reverse("neurobank:resource-download", args=[missing_resource])
        response = client.get(url)
        assert response.status_code == 415
        url = reverse("neurobank:resource", args=[missing_resource])
        response = client.get(url)
        assert "download_url" not in response.data

    def test_non_downloadable_dtype(self, client):
        non_downloadable_dtype = DataType.objects.create(
            name="folder",
        )
        non_downloadable_resource, _ = self._create_file(
            b"non-donwloadable", dtype=non_downloadable_dtype
        )

        url = reverse("neurobank:resource-download", args=[non_downloadable_resource])
        response = client.get(url)
        assert response.status_code == 415
        url = reverse("neurobank:resource", args=[non_downloadable_resource])
        response = client.get(url)
        assert "download_url" not in response.data

    def test_folder_instead_of_file(self, client):
        missing_resource, path = self._create_file(b"missing", skip_file_creation=True)
        os.makedirs(path)
        url = reverse("neurobank:resource-download", args=[missing_resource])
        response = client.get(url)
        assert response.status_code == 415
        url = reverse("neurobank:resource", args=[missing_resource])
        response = client.get(url)
        assert "download_url" not in response.data

    def test_non_neurobank_archive_scheme(self, client):
        archive = Archive.objects.create(
            name="ipfs", scheme="ipfs", root=str(self.directory)
        )
        resource, _ = self._create_file(b"bad archive", archive=archive)
        url = reverse("neurobank:resource-download", args=[resource])
        response = client.get(url)
        assert response.status_code == 415
        url = reverse("neurobank:resource", args=[resource])
        response = client.get(url)
        assert "download_url" not in response.data


def test_api_info_reports_version_1_1(client):
    response = client.get(reverse("neurobank:api-info"))
    assert response.status_code == status.HTTP_200_OK
    assert response.data["api_version"] == "1.1"
