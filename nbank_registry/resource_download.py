# -*- mode: python -*-
"""Helper code to enable resources to be downloaded from the server.

A resource is downloadable if the dtype is marked as downloadable and if it has
a location that resolves to a local path on the server.

"""

from pathlib import Path

from nbank_registry import errors


def local_resource_path(resource) -> Path:
    """Returns the path of the resource's file, from the first of its locations that
    has it on the server.

    Raises NonDownloadableDtypeError if its dtype isn't downloadable. If no location
    has the file, raises the error of the first location in an archive the server can
    read (MissingFileError or NotAFileError), or SchemeNotImplementedError if there's
    no such location.
    """
    if not resource.dtype.downloadable:
        raise errors.NonDownloadableDtypeError()
    error = None
    for location in resource.location_set.all():
        try:
            return location_to_path(location)
        except errors.SchemeNotImplementedError:
            pass
        except (errors.MissingFileError, errors.NotAFileError) as err:
            error = error or err
    raise error or errors.SchemeNotImplementedError()


def location_to_path(location) -> Path:
    """Returns the path of the file for a location in a neurobank archive.

    The location's key is the name of the file. A location without a key (from a
    client that doesn't record keys) is looked up by the resource's filename, then
    its bare name, then any file named with the resource's name and an extension.
    """
    if location.archive.scheme != "neurobank":
        raise errors.SchemeNotImplementedError()
    resource = location.resource
    id = resource.name
    id_stub = id[:2]
    stub_dir = Path(location.archive.root) / "resources" / id_stub
    partial = stub_dir / id
    if location.key is not None:
        # a key is a file name; a path could reach outside the archive
        if Path(location.key).name != location.key:
            raise errors.MissingFileError(resource, stub_dir)
        path = stub_dir / location.key
        if not path.exists():
            raise errors.MissingFileError(resource, stub_dir)
    else:
        # try the predicted names first (cheap stat calls) before globbing the
        # whole stub directory
        for candidate in (stub_dir / resource.filename(), partial):
            if candidate.exists():
                path = candidate
                break
        else:
            try:
                path = resolve_extension(partial)
            except FileNotFoundError as err:
                raise errors.MissingFileError(resource, stub_dir) from err
    if not path.is_file():
        raise errors.NotAFileError(resource, partial)
    return path


def resolve_extension(path: Path) -> Path:
    """Returns the file stored for path, which may have an extension that path lacks:
    resource 'xyzzy' could be stored as 'xyzzy.wav' or 'xyzzy.json'. Raises
    FileNotFoundError if there's no such file."""
    if path.exists():
        return path
    paths = path.parent.glob(f"{path.name}.*")
    try:
        return next(paths)
    except StopIteration as err:
        raise FileNotFoundError(f"resource '{path}' does not exist") from err
