# -*- coding: utf-8 -*-
# -*- mode: python -*-
import hashlib
import uuid

from django.core.urlresolvers import reverse
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
