# -*- coding: utf-8 -*-
# -*- mode: python -*-
import hashlib
import uuid

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from neurobank.models import Resource, DataType, Domain, Location

class ResourceTests(APITestCase):

    def setUp(self):
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")
        self.domain = Domain.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.resource = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            metadata={"experimenter": "dmeliza"})
        self.location = Location.objects.create(
            resource=self.resource,
            domain=self.domain)


    def test_can_access_resource_list(self):
        response = self.client.get(reverse('neurobank:resource-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_create_resource(self):
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name,})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response2 = self.client.get(reverse('neurobank:resource',
                                            args=[response.data["name"]]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_can_create_resource_with_own_uuid(self):
        myuuid = str(uuid.uuid4())
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name, "name": myuuid})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response2 = self.client.get(reverse('neurobank:resource',
                                            args=[myuuid]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_cannot_create_resource_with_invalid_uuid(self):
        myuuid = "blahblahblah"
        response = self.client.post(reverse('neurobank:resource-list'),
                                    {"dtype": self.dtype.name, "name": myuuid})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_access_resource_detail(self):
        response = self.client.get(reverse('neurobank:resource', args=[self.resource.name]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset({
            "name": str(self.resource.name),
            "sha1": self.resource.sha1,
            "dtype": self.dtype.name,
            "metadata": self.resource.metadata,
            "locations": [self.domain.name]}, response.data)

    def test_cannot_access_nonexistent_resource_detail(self):
        response = self.client.get(reverse('neurobank:resource', args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_delete_resource(self):
        response = self.client.delete(reverse('neurobank:resource', args=[self.resource.name]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_cannot_modify_name(self):
        response = self.client.patch(reverse('neurobank:resource', args=[self.resource.name]),
                                     {"name": str(uuid.uuid4())})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_modify_sha1(self):
        response = self.client.patch(reverse('neurobank:resource', args=[self.resource.name]),
                                     {"sha1": hashlib.sha1(b"blah").hexdigest()})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_update_metadata(self):
        response = self.client.patch(reverse('neurobank:resource', args=[self.resource.name]),
                                     {"metadata": {"test_field": "value"}}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictContainsSubset({"test_field": "value"}, response.data["metadata"])


class LocationTests(APITestCase):

    def setUp(self):
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")
        self.domain = Domain.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.resource = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            metadata={"experimenter": "dmeliza"})

    def test_can_add_and_delete_location(self):
        url = reverse('neurobank:location-list', args=[self.resource.name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

        response = self.client.post(url, {"domain_name": self.domain.name}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        response = self.client.post(url, {"domain_name": self.domain.name})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.delete(reverse("neurobank:location",
                                              args=[self.resource.name, self.domain.name]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class DataTypeTests(APITestCase):

    def setUp(self):
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
        data = {"name": "acoustic_waveform",
                "content_type": "audio/wav"}
        response = self.client.post(reverse("neurobank:datatype-list"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data, data)

        response2 = self.client.get(reverse("neurobank:datatype", args=[data["name"]]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data, data)

    def test_cannot_delete_datatype(self):
        response = self.client.delete(reverse("neurobank:datatype", args=[self.dtype.name]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_cannot_modify_datatype(self):
        response = self.client.patch(reverse("neurobank:datatype", args=[self.dtype.name]),
                                     {"name": "blahblahblah"})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class DomainTests(APITestCase):

    def setUp(self):
        self.domain = Domain.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")

    def test_can_access_domain_list(self):
        response = self.client.get(reverse("neurobank:domain-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_can_access_domain_detail(self):
        response = self.client.get(reverse("neurobank:domain", args=[self.domain.name]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data,
                         {"name": self.domain.name,
                          "scheme": self.domain.scheme,
                          "root": self.domain.root})

    def test_cannot_access_nonexistent_domain_detail(self):
        response = self.client.get(reverse('neurobank:domain', args=["blarg"]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_create_domain(self):
        data = {"name": "remote",
                "scheme": "http",
                "root": "/meliza.org/spike_times/"}
        response = self.client.post(reverse("neurobank:domain-list"), data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data, data)

        response2 = self.client.get(reverse("neurobank:domain", args=[data["name"]]))
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data, data)

    def test_cannot_delete_domain(self):
        response = self.client.delete(reverse("neurobank:domain", args=[self.domain.name]))
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_can_modify_domain(self):
        response = self.client.patch(reverse("neurobank:domain", args=[self.domain.name]),
                                     {"name": "local_intrac"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ResourceFilterTests(APITestCase):

    def setUp(self):
        self.dtype1 = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")
        self.dtype2 = DataType.objects.create(
            name="acoustic_waveform",
            content_type="audio/wav")
        self.domain_local = Domain.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.domain_remote = Domain.objects.create(
            name="remote",
            scheme="http",
            root="/meliza.org/data/intracellular")
        self.resource1 = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype1,
            metadata={"experimenter": "dmeliza"})
        Location.objects.create(
            resource=self.resource1,
            domain=self.domain_local)
        Location.objects.create(
            resource=self.resource1,
            domain=self.domain_remote)
        self.resource2 = Resource.objects.create(
            dtype=self.dtype2,
            metadata={"experimenter": "mcb2x"})
        Location.objects.create(
            resource=self.resource2,
            domain=self.domain_local)

    def test_can_filter_by_uuid(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"name": str(self.resource1.name)[:6]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], str(self.resource1.name))

    def test_can_filter_by_dtype(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"dtype": self.dtype1.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], str(self.resource1.name))

    def test_can_filter_by_location(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"location": self.domain_local.name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_can_filter_by_scheme(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"scheme": self.domain_remote.scheme})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


    def test_can_filter_by_metadata(self):
        response = self.client.get(reverse('neurobank:resource-list'),
                                   {"metadata__experimenter": "mcb2x"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], str(self.resource2.name))


class LocationFilterTests(APITestCase):

    def setUp(self):
        self.dtype = DataType.objects.create(
            name="spike_times",
            content_type="application/vnd.meliza-org.pproc+json; version=1.0")
        self.domain_local = Domain.objects.create(
            name="local",
            scheme="neurobank",
            root="/home/data/intracellular")
        self.domain_remote = Domain.objects.create(
            name="remote",
            scheme="http",
            root="/meliza.org/data/intracellular")
        self.resource = Resource.objects.create(
            sha1=hashlib.sha1(b"").hexdigest(),
            dtype=self.dtype,
            metadata={"experimenter": "dmeliza"})
        Location.objects.create(
            resource=self.resource,
            domain=self.domain_local)
        Location.objects.create(
            resource=self.resource,
            domain=self.domain_remote)

    def test_can_filter_by_name(self):
        url = reverse('neurobank:location-list', args=[self.resource.name])
        response = self.client.get(url, {"name": self.domain_local.name[:4]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_can_filter_by_scheme(self):
        url = reverse('neurobank:location-list', args=[self.resource.name])
        response = self.client.get(url, {"scheme": self.domain_remote.scheme})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
