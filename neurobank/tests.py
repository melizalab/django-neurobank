# -*- coding: utf-8 -*-
# -*- mode: python -*-
import hashlib
import uuid
import posixpath as ppath

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth.models import User
from neurobank.models import Resource, DataType, Archive, Location


class APIAuthTestCase(APITestCase):
    username = "user"
    password = "password1"

    def login(self):
        self.client.login(username=self.username, password=self.password)

    def logout(self):
        self.client.logout()

    def setUp(self):
        self.user = User.objects.create_superuser(username=self.username,
                                                  password=self.password,
                                                  email="user@domain.com")


class ResourceTests(APIAuthTestCase):

    def setUp(self):
        super(ResourceTests, self).setUp()
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pprox+json; version=1.0")
        self.archive = Archive.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.resource = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"})
        self.location = Location.objects.create(
            resource=self.resource,
            archive=self.archive)

    def test_can_access_resource_list(self):
        response = self.client.get(reverse('neurobank:resource-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_create_resource(self):
        self.login()
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name,})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response2 = self.client.get(reverse('neurobank:resource',
                                            args=[response.data["name"]]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_can_create_resource_with_own_name(self):
        self.login()
        myuuid = str(uuid.uuid4())
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name, "name": myuuid})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response2 = self.client.get(reverse('neurobank:resource',
                                            args=[myuuid]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_cannot_create_resource_with_invalid_name(self):
        self.login()
        bad_name = "blah/blah"
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name, "name": bad_name})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_create_resource_with_metadata(self):
        self.login()
        myuuid = str(uuid.uuid4())
        mdata = {"blah": "1234"}
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name, "name": myuuid, "metadata": mdata},
                                    format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response2 = self.client.get(reverse('neurobank:resource',
                                            args=[myuuid]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertDictEqual(response2.data["metadata"], mdata)

    def test_can_create_resource_with_location(self):
        self.login()
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name, "locations": [self.archive.name]},
                                    format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertDictContainsSubset({
            "locations": [self.archive.name]}, response.data)

    def test_cannot_create_resource_with_invalid_location(self):
        self.login()
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name, "locations": ["bad-location"]},
                                    format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_access_resource_detail(self):
        response = self.client.get(reverse('neurobank:resource', args=[self.resource.name]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset({
            "name": str(self.resource.name),
            "sha1": self.resource.sha1,
            "dtype": self.dtype.name,
            "created_by": self.user.username,
            "metadata": self.resource.metadata,
            "locations": [self.archive.name]}, response.data)

    def test_cannot_access_nonexistent_resource_detail(self):
        response = self.client.get(reverse('neurobank:resource', args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_access_invalid_resource_detail(self):
        url = ppath.join(reverse('neurobank:resource-list'), "not.a.slug") + "/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_delete_resource(self):
        self.login()
        response = self.client.delete(reverse('neurobank:resource', args=[self.resource.name]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_cannot_modify_name(self):
        self.login()
        response = self.client.patch(reverse('neurobank:resource', args=[self.resource.name]),
                                     {"name": str(uuid.uuid4())})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_modify_sha1(self):
        self.login()
        response = self.client.patch(reverse('neurobank:resource', args=[self.resource.name]),
                                     {"sha1": hashlib.sha1(b"blah").hexdigest()})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_update_metadata(self):
        self.login()
        response = self.client.patch(reverse('neurobank:resource', args=[self.resource.name]),
                                     {"metadata": {"test_field": "value"}}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset({"test_field": "value"}, response.data["metadata"])


class LocationTests(APIAuthTestCase):

    def setUp(self):
        super(LocationTests, self).setUp()
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")
        self.archive = Archive.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.resource = Resource.objects.create(
            name="a_boring_file",
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"})

    def test_can_add_and_delete_location(self):
        url = reverse('neurobank:location-list', args=[self.resource.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

        self.login()
        response = self.client.post(url, {"archive_name": self.archive.name}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        response = self.client.post(url, {"archive_name": self.archive.name})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.delete(reverse("neurobank:location",
                                              args=[self.resource.name, self.archive.name]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class DataTypeTests(APIAuthTestCase):

    def setUp(self):
        super(DataTypeTests, self).setUp()
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")

    def test_can_access_datatype_list(self):
        response = self.client.get(reverse("neurobank:datatype-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_access_datatype_detail(self):
        response = self.client.get(reverse("neurobank:datatype", args=[self.dtype.name]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data,
                         {"name": self.dtype.name,
                          "content_type": self.dtype.content_type})

    def test_cannot_access_nonexistent_datatype_detail(self):
        response = self.client.get(reverse('neurobank:datatype', args=["blarg"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_create_datatype(self):
        self.login()
        data = {"name": "acoustic_waveform",
                "content_type": "audio/wav"}
        response = self.client.post(reverse("neurobank:datatype-list"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data, data)

        response2 = self.client.get(reverse("neurobank:datatype", args=[data["name"]]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data, data)

    def test_cannot_delete_datatype(self):
        self.login()
        response = self.client.delete(reverse("neurobank:datatype", args=[self.dtype.name]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_cannot_modify_datatype(self):
        self.login()
        response = self.client.patch(reverse("neurobank:datatype", args=[self.dtype.name]),
                                     {"name": "blahblahblah"})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ArchiveTests(APIAuthTestCase):

    def setUp(self):
        super(ArchiveTests, self).setUp()
        self.archive = Archive.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")

    def test_can_access_archive_list(self):
        response = self.client.get(reverse("neurobank:archive-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_access_archive_detail(self):
        response = self.client.get(reverse("neurobank:archive", args=[self.archive.name]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data,
                         {"name": self.archive.name,
                          "scheme": self.archive.scheme,
                          "root": self.archive.root})

    def test_cannot_access_nonexistent_archive_detail(self):
        response = self.client.get(reverse('neurobank:archive', args=["blarg"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_create_archive(self):
        self.login()
        data = {"name": "remote",
                "scheme": "http",
                "root": "/meliza.org/spike_times/"}
        response = self.client.post(reverse("neurobank:archive-list"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data, data)

        response2 = self.client.get(reverse("neurobank:archive", args=[data["name"]]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data, data)

    def test_cannot_create_duplicate_archive(self):
        self.login()
        data = {"name": self.archive.name,
                "scheme": "http",
                "root": "/meliza.org/spike_times/"}
        response = self.client.post(reverse("neurobank:archive-list"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_create_badly_named_archive(self):
        self.login()
        data = {"name": "blargh!!@!#",
                "scheme": "http",
                "root": "/meliza.org/spike_times/"}
        response = self.client.post(reverse("neurobank:archive-list"), data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_delete_archive(self):
        self.login()
        response = self.client.delete(reverse("neurobank:archive", args=[self.archive.name]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_can_modify_archive(self):
        self.login()
        response = self.client.patch(reverse("neurobank:archive", args=[self.archive.name]),
                                     {"name": "local_intrac"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ArchiveFilterTests(APIAuthTestCase):

    def setUp(self):
        super(ArchiveFilterTests, self).setUp()
        self.archive_1 = Archive.objects.create(
            name="intracellular",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.archive_2 = Archive.objects.create(
            name="extracellular",
            scheme="http",
            root="/meliza.org/data/extracellular")

    def test_can_filter_by_scheme(self):
        url = reverse('neurobank:archive-list')
        response = self.client.get(url, {"scheme": self.archive_1.scheme })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_can_filter_by_root(self):
        url = reverse('neurobank:archive-list')
        response = self.client.get(url, {"root": self.archive_1.root })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class ResourceFilterTests(APIAuthTestCase):

    def setUp(self):
        super(ResourceFilterTests, self).setUp()
        self.dtype1 = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")
        self.dtype2 = DataType.objects.create(
            name="acoustic_waveform",
            content_type="audio/wav")
        self.archive_local = Archive.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.archive_remote = Archive.objects.create(
            name="remote",
            scheme="http",
            root="/meliza.org/data/intracellular")
        self.resource1 = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype1,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"})
        Location.objects.create(
            resource=self.resource1,
            archive=self.archive_local)
        Location.objects.create(
            resource=self.resource1,
            archive=self.archive_remote)
        self.resource2 = Resource.objects.create(
            dtype=self.dtype2,
            created_by=self.user,
            metadata={"experimenter": "mcb2x"})
        Location.objects.create(
            resource=self.resource2,
            archive=self.archive_local)

    def test_can_filter_by_name(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"name": str(self.resource1.name)[:6]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], str(self.resource1.name))

    def test_can_filter_by_sha1(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"sha1": str(self.resource1.sha1)[:6]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], str(self.resource1.name))

    def test_can_filter_by_dtype(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"dtype": self.dtype1.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], str(self.resource1.name))

    def test_can_filter_by_user(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"created_by": self.user.username})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_can_filter_by_location(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"location": self.archive_local.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_can_filter_by_scheme(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"scheme": self.archive_remote.scheme})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_can_filter_by_metadata(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"metadata__experimenter": "mcb2x"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], str(self.resource2.name))


class LocationFilterTests(APIAuthTestCase):

    def setUp(self):
        super(LocationFilterTests, self).setUp()
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")
        self.archive_local = Archive.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.archive_remote = Archive.objects.create(
            name="remote",
            scheme="http",
            root="/meliza.org/data/intracellular")
        self.resource = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            created_by=self.user,
            metadata={"experimenter": "dmeliza"})
        Location.objects.create(
            resource=self.resource,
            archive=self.archive_local)
        Location.objects.create(
            resource=self.resource,
            archive=self.archive_remote)

    def test_can_filter_by_name(self):
        url = reverse('neurobank:location-list', args=[self.resource.name])
        response = self.client.get(url, {"name": self.archive_local.name[:4]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_can_filter_by_scheme(self):
        url = reverse('neurobank:location-list', args=[self.resource.name])
        response = self.client.get(url, {"scheme": self.archive_remote.scheme})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
