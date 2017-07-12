# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

import uuid
import posixpath as pp

from django.contrib.postgres.fields import HStoreField
from django.utils.encoding import python_2_unicode_compatible
from django.urls import reverse
from django.db import models

@python_2_unicode_compatible
class Resource(models.Model):
    """A resource has a unique identifier, a defined type, and some optional metadata"""
    name = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True)
    sha1 = models.CharField(
        max_length=40, unique=True,
        blank=True, null=True,
        help_text="specify only for resources whose contents must not change (i.e., sources)"
    )
    dtype = models.ForeignKey("DataType", on_delete=models.PROTECT)
    locations = models.ManyToManyField("Domain", through="Location")
    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User',
                              related_name='resources',
                              on_delete=models.CASCADE)
    metadata = HStoreField(blank=True, null=True)

    def __str__(self):
        return str(self.name)


@python_2_unicode_compatible
class DataType(models.Model):
    """A datatype has a name and an optional link to a specification"""
    name = models.SlugField(max_length=32, unique=True)
    content_type = models.CharField(max_length=128, blank=True, null=True)

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Domain(models.Model):
    """A domain defines a method and authority for locating a resource"""
    name = models.SlugField(max_length=32, unique=True, help_text="a descriptive name")
    scheme = models.CharField(max_length=16)
    root = models.CharField(max_length=512, help_text="root path for resources")

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Location(models.Model):
    """A location consists of a resource and a domain"""
    resource = models.ForeignKey("Resource", on_delete=models.CASCADE)
    domain = models.ForeignKey("Domain", on_delete=models.CASCADE)

    def __str__(self):
        return ":".join((self.domain.name, str(self.resource)))

    class Meta:
        unique_together = ("resource", "domain")
