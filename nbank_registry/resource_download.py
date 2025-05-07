# -*- coding: utf-8 -*-
# -*- mode: python -*-
"""Helper code to enable resources to be downloaded from the server.

A resource is downloadable if the dtype is marked as downloadable and if it has
a location that resolves to a local path on the server. The code to resolve this
local path has been vendored from the neurobank package.

"""

from pathlib import Path

from nbank_registry import errors


def local_resource_path(resource) -> Path:
    if not resource.dtype.downloadable:
        raise errors.NonDownloadableDtypeError()
    for location in resource.location_set.all():
        try:
            return location_to_path(location)
        except errors.SchemeNotImplementedError:
            pass
    raise errors.SchemeNotImplementedError()


def location_to_path(location) -> Path:
    if location.archive.scheme != "neurobank":
        raise errors.SchemeNotImplementedError()
    id = location.resource.name
    id_stub = id[:2]
    partial = Path(location.archive.root) / "resources" / id_stub / id
    try:
        path = resolve_extension(partial)
    except FileNotFoundError as err:
        raise errors.MissingFileError(location.resource, partial.parent) from err
    if not path.is_file():
        raise errors.NotAFileError(location.resource, partial)
    return path


def resolve_extension(path: Path) -> Path:
    """Resolves the full path including extension of a resource.

    This function is needed if the 'keep_extension' policy is True, in which
    case resource 'xyzzy' could refer to a file called 'xyzzy.wav' or
    'xyzzy.json', etc. If no resource associated with the supplied path exists,
    raises FileNotFoundError.

    """
    if path.exists():
        return path
    paths = path.parent.glob(f"{path.name}.*")
    try:
        return next(paths)
    except StopIteration as err:
        raise FileNotFoundError(f"resource '{path}' does not exist") from err
