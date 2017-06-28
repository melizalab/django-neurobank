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

    def test_can_access_resource_detail(self):
        response = self.client.get(reverse('neurobank:resource', args=[self.resource.name]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_nonexistent_resource_detail(self):
        response = self.client.get(reverse('neurobank:resource', args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
