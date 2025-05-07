# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

from pathlib import Path

from django.db import models

from nbank_registry.tools import random_id


class Resource(models.Model):
    """A resource has a unique identifier, a defined type, and some optional metadata"""

    id = models.AutoField(primary_key=True)
    name = models.SlugField(max_length=255, default=random_id, unique=True)
    sha1 = models.CharField(
        max_length=40,
        unique=True,
        blank=True,
        null=True,
        help_text="specify only for resources whose contents must not change (i.e., sources)",
    )
    dtype = models.ForeignKey("DataType", on_delete=models.PROTECT)
    locations = models.ManyToManyField("Archive", through="Location")
    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User", related_name="resources", on_delete=models.CASCADE
    )
    metadata = models.JSONField(blank=True, null=True)

    def __str__(self):
        return str(self.name)

    def filename(self):
        name = Path(self.name)
        if not name.suffix and self.dtype.extension:
            ext = self.dtype.extension.lstrip(".")
            return str(name.with_suffix(f".{ext}"))
        else:
            return self.name

    class Meta:
        ordering = ["-id"]


class DataType(models.Model):
    """A datatype has a name and an optional link to a specification"""

    id = models.AutoField(primary_key=True)
    name = models.SlugField(max_length=32, unique=True)
    content_type = models.CharField(max_length=128, blank=True)
    downloadable = models.BooleanField(default=False)
    extension = models.CharField(
        max_length=8,
        blank=True,
        help_text="default file extension for this data type for clients to use in naming downloaded resources",
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class Archive(models.Model):
    """An archive defines a method and authority for locating a resource"""

    id = models.AutoField(primary_key=True)
    name = models.SlugField(max_length=32, unique=True, help_text="a descriptive name")
    scheme = models.CharField(max_length=16)
    root = models.CharField(max_length=512, help_text="root path for resources")

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ("scheme", "root")
        ordering = ["name"]


class Location(models.Model):
    """A location consists of a resource and an archive"""

    id = models.AutoField(primary_key=True)
    resource = models.ForeignKey("Resource", on_delete=models.CASCADE)
    archive = models.ForeignKey("Archive", on_delete=models.CASCADE)

    def __str__(self):
        return ":".join((self.archive.name, str(self.resource)))

    class Meta:
        unique_together = ("resource", "archive")
        ordering = ["-id"]
