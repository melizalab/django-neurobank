=========
Changelog
=========

Releases are listed newest first. Dates come from the release tag, or from the
upload to PyPI for releases that were never tagged. 0.10.13 was never released,
and 0.6.0 to 0.7.2 were not published to PyPI. Numbers like #46 refer to issues
on GitHub.

Unreleased
----------

API version 2.0.

Breaking changes
~~~~~~~~~~~~~~~~

* Changing the registry needs a client that asks for API 2.0, in its
  ``Accept`` header (``application/json; version=2.0``), as neurobank 1.0
  does. Requests without a version can still read everything, including the
  bulk endpoints, but anything that would change a record is a 400 that says
  to upgrade neurobank. A request for another version is a 406.
* The compatibility layer for clients before API 1.2 is gone. ``experimenter``
  and ``animal`` are only fields: responses no longer copy them into
  ``metadata``, they're refused as keys in submitted ``metadata`` (400, naming
  the field to use), and ``metadata__`` searches on them are a 400 pointing to
  ``?experimenter=`` or ``?animal=``.
* ``NBANK_METADATA_ALIASES`` is gone; a site that sets it fails Django's system
  checks.
* ``normalize_metadata`` only renames metadata keys and maps their values. It no
  longer moves values into ``experimenter`` and ``animal`` or creates users, and
  refuses mappings that name the fields or have a ``[users]`` table. Move
  existing values into the fields with 0.12 before upgrading.
* Migrating sets the key of each location in a neurobank archive that has
  none to the resource's file name (its name, plus its datatype's extension if
  the name has none), as neurobank 1.0 finds files by key. A file stored under
  another name isn't found until its key is corrected: **after migrating, run**
  ``nbank check archive --fix --no-hash`` **on each archive**, which sets each
  key from the file found. A key another location in the archive holds is left
  unset for the check to fix.

Added
~~~~~

* Resources can be marked as superseded or not to be used (#45):
  ``superseded_on`` (when it was marked; null if the resource can be used), and
  optionally ``superseded_by`` (the resource to use instead) and
  ``superseded_note`` (why, or what replaces it), which need ``superseded_on``.
  Only superusers can mark or unmark a resource, and a resource that supersedes
  others can't be deleted. Searches: ``?superseded=true|false`` and
  ``?superseded_by=``. Superseded resources are still listed by default.
* ``info/`` reports who the request is from (``user``: their username, whether
  they're a superuser, and their registry permissions), or null if anonymous.
* The resource admin looks up animals and replacements with autocomplete. A
  site with its own animal model gets autocomplete if that model's admin has
  ``search_fields``, and a raw id field otherwise.
* Searches (``resources/``) can return every result in one streamed response,
  as line-delimited JSON, instead of pages: ask for ``application/x-ndjson`` in
  the ``Accept`` header (alone: JSON wins if both are accepted).
* ``check/resources/`` checks whether a resource could be created, without
  creating it (#11): POST the same body as to ``resources/`` for 200, or 400
  with the errors creating it would give. POST a list (up to 1,000) to check
  several resources, including against each other: 200 with the errors for each.
  Needs permission to create resources.

Changed
~~~~~~~

* Downloads find the file of a location in a neurobank archive by its key, the
  file's name, as neurobank 1.0 records it. A key that names no file, or isn't
  a plain file name, isn't downloadable. Locations without a key are looked up
  by the resource's name as before.
* Bulk responses have the content type ``application/x-ndjson``.
* The registry's download location is listed with the remote locations, before
  offline ones such as tapes, instead of last.
* A resource's ``metadata`` can be sent as null, as a resource without metadata
  is read, meaning no metadata.

0.12.0 (2026-10-19)
-------------------

API version 1.2.

Breaking changes
~~~~~~~~~~~~~~~~

* Requires Python 3.11+ and Django 5.2 to 6.1; Django 4.2 is no longer
  supported. Requires Django REST framework 3.18+ and django-filter 25.1+, and
  sets upper limits on the runtime dependencies.
* Unknown experimenters and animals are refused (400), whether sent as fields or
  in ``metadata``. Create accounts and animal records before clients deposit with
  them.

Added
~~~~~

* Resources have two optional fields that refer to other records:

  * ``experimenter``: a user, by username. People who don't use the registry can
    be given inactive accounts.
  * ``animal``: a record in the animal model, by primary key. The model is set by
    ``NBANK_ANIMAL_MODEL`` (e.g. ``"birds.Animal"`` for django-bird-colony, keyed
    by UUID); the default is a minimal model of the registry's own, keyed by
    name. **Set it before migrating**: like ``AUTH_USER_MODEL``, it can't be
    changed afterwards.
  * Searches: ``?experimenter=`` and ``?animal=``, each with ``__neq`` and
    ``__isnull``, and ``?animal__istartswith=`` for the start of an animal's
    identifier.

* Compatibility with older clients. Clients written for API 1.1 and earlier
  (e.g. neurobank 0.12) set and read ``animal`` and ``experimenter`` as
  free-form metadata keys. The registry provides backwards compatibility to these
  clients by moving those keys out of ``metadata`` into the fields, copying the
  fields into ``metadata`` in responses, and turning ``metadata__`` searches on
  them into searches of the fields. A lab can name other keys to treat the same
  way with a setting, e.g. ``NBANK_METADATA_ALIASES = {"bird": "animal"}``. This
  layer goes away in API 2.0.
* ``normalize_metadata`` management command: moves existing metadata values into
  the fields, and renames keys and maps values of other metadata, from a TOML
  mappings file. ``--dry-run`` reports what would change and writes a template
  listing the values found.
* An entry in a resource's ``locations`` can be ``{"archive": name, "key": key}``
  as well as an archive name, to set the location's key when the resource is
  created.

Changed
~~~~~~~

* ``metadata__<key>__isnull`` accepts true/false in any case (and 1/0); other
  values are a 400 rather than a 500.
* ``metadata__`` searches on ``experimenter`` and ``animal`` take the value as
  text, without reading it as JSON (a UUID prefix like ``123456`` stays a
  string).
* Tests run with Django 5.2 and 6.1, and with an animal model keyed by UUID
  (``NBANK_TEST_ANIMAL_MODEL=uuid``). CI checks the code with ruff and that the
  README renders on PyPI.

Fixed
~~~~~

* Downloads use the resource's filename before searching the archive (#46).
* Updating the metadata of a resource whose metadata was null.
* Adding locations by updating a resource (was a 500).

Upgrading
~~~~~~~~~

1. Set ``NBANK_ANIMAL_MODEL`` **before** running the migrations if animals come
   from another app. Set ``NBANK_METADATA_ALIASES`` if older clients use other
   names for the fields.
2. ``python manage.py migrate`` (adds the fields, and the default animal model
   if it's used).
3. Create inactive accounts for experimenters, and records for animals, that
   aren't in the registry yet.
4. ``python manage.py normalize_metadata --dry-run > mappings.toml``; edit the
   mappings and repeat until the report is clean; then run it without
   ``--dry-run``.

0.11.0 (2026-09-29)
-------------------

API version 1.1.

Added
~~~~~

* Locations have an optional ``key``: where the resource is within the archive,
  for archives where that can't be derived from the resource's name (published
  datasets such as figshare or Dataverse, bundles, tapes). A key can be used only
  once in an archive. It can be set when a location is added and changed with
  PATCH on the location.
* ``?archive=`` lists the resources in an archive, by exact name.
* ``?sha1_contains=`` searches for part of a hash.

Changed
~~~~~~~

* ``?sha1=`` matches the full hash exactly (ignoring case), using the index.
  Use ``?sha1_contains=`` for partial hashes.
* Hashes are stored in lower case, and a duplicate that differs only in case is
  refused. A data migration converts existing hashes.

Fixed
~~~~~

* Searches by location, scheme, or ``has_location`` returned a resource once for
  each matching location.
* Adding a location without ``archive_name`` was a 500.
* Fewer database queries for resource and location lists.

0.10.15 (2026-09-29)
--------------------

Added
~~~~~

* ``?has_location=`` finds resources with or without locations (#42).

Fixed
~~~~~

* Data type and archive names that are too long get a clear error (#44).
* Bulk endpoints refuse a bare string or number instead of a list of names
  (#41).
* Metadata that isn't an object is refused (#43).

0.10.14 (2026-09-24)
--------------------

Added
~~~~~

* Archives have an ``accessibility``: local, remote, or offline, so clients can
  prefer local copies.

Changed
~~~~~~~

* Values in ``metadata__`` searches are read as JSON when they parse, so
  ``?metadata__pen=3`` matches the number 3; quote a value to match it as a
  string (#40).
* Tests use an in-memory SQLite database by default; CI runs them against
  PostgreSQL 17 on Python 3.10 to 3.14 and Django 4.2 and 5.2.

0.10.12 (2025-07-03)
--------------------

Added
~~~~~

* Records include the resource's ``filename``, with the data type's extension.
* Superusers can change a resource's hash.

Fixed
~~~~~

* A missing migration.
* Searching in the admin, and slow admin pages (some list filters were removed).

0.10.11 (2025-05-07)
--------------------

* The bulk locations endpoint can be filtered, and data type extensions can be
  edited in the admin.

0.10.10 (2025-05-07)
--------------------

* Data types have an ``extension``, used to give file names in the bulk
  locations endpoint.
* Location lists can be filtered.
* Requires Django REST framework 3.15.2+.

0.10.9 (2024-12-17)
-------------------

* Bulk location records include the resource's hash (#12).
* Requires Python 3.10+ and Django 4.2+. Packaging moved to ``pyproject.toml``
  and uv; tests run on GitHub Actions, and releases are published from tags.

0.10.8 (2023-08-31)
-------------------

* The bulk endpoints stream line-delimited JSON, one record per line (#13).

0.10.7 (2023-08-24)
-------------------

* Bulk requests must name at least one resource.

0.10.6 (2023-08-24)
-------------------

* Bulk endpoints for records and locations of many resources at once:
  ``bulk/resources/`` and ``bulk/locations/`` (#10).
* Location lists no longer check that a downloadable file exists; a missing file
  shows up when it's downloaded. This makes location queries faster, and removes
  the dependency on the neurobank client.

0.10.5 (2023-02-20)
-------------------

* The locations of a downloadable resource include one for downloading it from
  the registry.
* Users with permission to delete resources can delete them; anyone else gets a
  403.

0.10.4 (2023-02-16)
-------------------

* New URL for downloads, ``download/<name>/``.

0.10.3 (2023-01-24)
-------------------

* Supports Django 4.0; requires Python 3.8+.
* License changed from GPL 3 to BSD 3-Clause. Packaging moved to ``setup.cfg``.

0.10.2 (2021-12-10)
-------------------

* Restores ``apps.py``, missing from 0.10.1.

0.10.1 (2021-12-10)
-------------------

* Supports Django 3.2.

0.10.0 (2021-12-10)
-------------------

Breaking changes
~~~~~~~~~~~~~~~~

* The app is renamed from ``neurobank`` to ``nbank_registry``; change
  ``INSTALLED_APPS`` and the URLconf.

Added
~~~~~

* Resources can be downloaded from archives on the server
  (``resources/<name>/download``), using django-sendfile2. Data types have a
  ``downloadable`` flag, and records of downloadable resources include a
  ``download_url``.

0.9.1 (2021-04-06)
------------------

* Metadata is stored in a ``JSONField`` instead of an ``HStoreField``, so values
  keep their types.
* Resource names can be up to 255 characters (was 64). Lists have default
  orderings.

0.9.0 (2021-04-06)
------------------

* Supports Django 3.0; Python 2 is no longer supported.

0.8.5 (2021-04-06)
------------------

* ``metadata`` is optional when a resource is registered.
* Fixed adding a location to a resource.

0.8.4 (2019-08-02)
------------------

* Resources can be excluded by metadata value with ``metadata__<key>__neq``.

0.8.2 (2019-08-01)
------------------

* PATCH on a resource changes the metadata keys it names and leaves the others
  (#6).

0.8.1 (2019-07-19)
------------------

* An ``info/`` endpoint gives the registry's version and API version (#5).

0.8.0 (2019-01-19)
------------------

* Supports Django 2.x.

0.7.7 (2018-05-11)
------------------

Breaking changes
~~~~~~~~~~~~~~~~

* Domains are renamed archives, including the ``domains/`` endpoint (#4).

Added
~~~~~

* Metadata can be edited in the admin.

0.7.2 (2018-02-14)
------------------

* Resource lists are paginated, with links in the ``Link`` header.
* Separate permissions for adding data types and domains.

0.7.1 (2018-02-12)
------------------

* Fixed the URL of the 404 page.

0.7.0 (2018-02-11)
------------------

Breaking changes
~~~~~~~~~~~~~~~~

* Resource names can be any URL-safe string instead of a UUID. The registry
  assigns a short base-62 name if none is given.

Added
~~~~~

* Locations can be given when a resource is registered.
* Domains can be filtered, and a domain's scheme and root must be unique
  together.
* Searching by name matches any part of the name.
* Unknown URLs get a JSON 404 response, and errors have clearer messages.

0.6.0 (2017-07-12)
------------------

First release: resources identified by UUID, with a data type, an optional
hash, metadata, and locations in domains; searches on metadata; authentication,
with each resource recording who registered it.
