# -*- coding: utf-8 -*-
# -*- mode: python -*-


class NotAvailableForDownloadError(Exception):
    pass


class MissingFileError(NotAvailableForDownloadError):
    def __init__(self, resource, path):
        self.resource = resource
        self.path = path

    def __str__(self):
        return f"Could not find resource '{self.resource}' in directory" f" {self.path}"


class NotAFileError(NotAvailableForDownloadError):
    def __init__(self, resource, path):
        self.resource = resource
        self.path = path

    def __str__(self):
        return (
            f"Resource '{self.resource}' was found in directory"
            f" {self.path}, but it is not a file, so it cannot be"
            " downloaded"
        )


class SchemeNotImplementedError(NotAvailableForDownloadError):
    def __str__(self):
        return "The requested resource is not in an archive that uses a scheme supported by this registry"


class NonDownloadableDtypeError(NotAvailableForDownloadError):
    def __str__(self):
        return "The resource is not of a downloadable datatype"
