# -*- coding: utf-8 -*-
# -*- mode: python -*-
from django.contrib.auth import get_user_model
from django.test import TestCase

from nbank_registry.models import DataType, Resource


def get_sentinel_user():
    return get_user_model().objects.get_or_create(username="deleted")[0]


class ResourceModelTests(TestCase):
    def test_filename(self):
        user = get_sentinel_user()
        dtype = DataType.objects.create(
            name="vocalization-wav",
            content_type="audio/x-wav",
            downloadable=True,
            extension="wav",
        )
        resource = Resource.objects.create(name="abc", dtype=dtype, created_by=user)
        self.assertEqual(resource.filename(), "abc.wav")

        resource = Resource.objects.create(name="abc.rst", dtype=dtype, created_by=user)
        self.assertEqual(resource.filename(), "abc.rst")

        dtype = DataType.objects.create(
            name="intracellular-abfdir",
            content_type="",
            downloadable=False,
            extension="",
        )

        resource = Resource.objects.create(name="def", dtype=dtype, created_by=user)
        self.assertEqual(resource.filename(), "def")

        resource = Resource.objects.create(name="def.txt", dtype=dtype, created_by=user)
        self.assertEqual(resource.filename(), "def.txt")

        dtype = DataType.objects.create(
            name="eeg-arf",
            content_type="application/vnd.meliza-org.arf",
            downloadable=False,
            extension=".arf",
        )
        resource = Resource.objects.create(name="qqr", dtype=dtype, created_by=user)
        self.assertEqual(resource.filename(), "qqr.arf")
