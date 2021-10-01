# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals
from pathlib import Path

from django.contrib.postgres.fields import JSONField
from django.db import models

from nbank_registry.tools import random_id
from nbank_registry import errors


class Resource(models.Model):
    """A resource has a unique identifier, a defined type, and some optional metadata"""
    id = models.AutoField(primary_key=True)
    name = models.SlugField(max_length=255, default=random_id, unique=True)
    sha1 = models.CharField(
        max_length=40, unique=True,
        blank=True, null=True,
        help_text="specify only for resources whose contents must not change (i.e., sources)"
    )
    dtype = models.ForeignKey("DataType", on_delete=models.PROTECT)
    locations = models.ManyToManyField("Archive", through="Location")
    created_on = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User',
                              related_name='resources',
                              on_delete=models.CASCADE)
    metadata = JSONField(blank=True, null=True)

    def __str__(self):
        return str(self.name)

    def resolve_to_path(self):
        if not self.dtype.downloadable:
            raise errors.NonDownloadableDtypeError()
        for location in self.location_set.all():
            try:
                return location.resolve_to_path()
            except errors.SchemeNotImplementedError:
                pass
        raise errors.SchemeNotImplementedError()

    class Meta:
        ordering = ["-id"]


class DataType(models.Model):
    """A datatype has a name and an optional link to a specification"""
    name = models.SlugField(max_length=32, unique=True)
    content_type = models.CharField(max_length=128, blank=True, null=True)
    downloadable = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class Archive(models.Model):
    """An archive defines a method and authority for locating a resource"""
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
    resource = models.ForeignKey("Resource", on_delete=models.CASCADE)
    archive = models.ForeignKey("Archive", on_delete=models.CASCADE)

    def resolve_to_path(self):
        if self.archive.scheme == "neurobank":
            return self._resolve_neurobank_path(self)
        raise errors.SchemeNotImplementedError()

    @staticmethod
    def _resolve_neurobank_path(location):
        import nbank
        from nbank_registry.serializers import LocationSerializer
        serialized_location = LocationSerializer(location).data
        path_without_ext = nbank.core.get_archive(serialized_location)
        path = nbank.archive.find_resource(path_without_ext)
        if path is None:
            raise errors.MissingFileError(location.resource, path_without_ext)
        if not Path(path).is_file():
            raise errors.NotAFileError(location.resource, path_without_ext)
        return path

    def __str__(self):
        return ":".join((self.archive.name, str(self.resource)))

    class Meta:
        unique_together = ("resource", "archive")
        ordering = ["-id"]
