django-neurobank
----------------

|ProjectStatus|_ |Version|_ |BuildStatus|_ |License|_ |PythonVersions|_

.. |ProjectStatus| image:: https://www.repostatus.org/badges/latest/active.svg
.. _ProjectStatus: https://www.repostatus.org/#active

.. |Version| image:: https://img.shields.io/pypi/v/django-neurobank.svg
.. _Version: https://pypi.python.org/pypi/django-neurobank/

.. |BuildStatus| image:: https://github.com/melizalab/django-neurobank/actions/workflows/test-app.yml/badge.svg
.. _BuildStatus: https://github.com/melizalab/django-neurobank/actions/workflows/test-app.yml

.. |License| image:: https://img.shields.io/pypi/l/django-neurobank.svg
.. _License: https://opensource.org/license/bsd-3-clause/

.. |PythonVersions| image:: https://img.shields.io/pypi/pyversions/django-neurobank.svg
.. _PythonVersions: https://pypi.python.org/pypi/django-neurobank/

This is a Django application that provides name resolution services to
`neurobank <https://github.com/melizalab/neurobank>`__ using an HTTP
API.

The data management strategy behind **neurobank** is simple: every
resource gets a unique identifier. As long as you use the correct
identifier, you can unambiguously locate the resource. Resources include
*sources*, which are used to control an experiment, and *data*, which
result from running the experiment. Identifiers can be pretty much
anything that’s encodable in a URL and isn’t too long. You can use
manually-assigned identifiers like ``st32_1_2_1`` or let the API
generate short, memorable codes like ``heengei8``

To use this strategy, you need to be able to do two things: register
each resource you create somewhere, and then resolve resource names to
locations so that you can access your data. Being able to attach
searchable metadata to your resources is pretty handy, too. This
software provides a backend for these tasks. You’ll also need
`neurobank <https://github.com/melizalab/neurobank>`__ or some other
client software to take care of storing your files.

This software is licensed for you to use under the BSD License. See
COPYING for details.

Installation
~~~~~~~~~~~~

1. Requires Python 3.11+ and Django 5.2 LTS through 6.1. Production sites
   should use PostgreSQL; SQLite works for trying it out.

2. Install the package, and a database driver for PostgreSQL:
   ``pip install django-neurobank "psycopg[binary]"``

3. Add the registry and the apps it uses to ``INSTALLED_APPS``:

   .. code:: python

      INSTALLED_APPS = [
          ...
          "rest_framework",
          "django_filters",
          "nbank_registry",
      ]

4. Choose settings that can't be changed later, **before the first
   migration**:

   - ``NBANK_ANIMAL_MODEL``: the model that ``animal`` refers to, if animals
     are kept in another app in the same project (e.g. ``"birds.Animal"`` for
     `django-bird-colony <https://github.com/melizalab/django-bird-colony>`__).
     Leave it unset to use the registry's own minimal model. Like
     ``AUTH_USER_MODEL``, it can't be changed once the migrations have run.

   Other optional settings:

   - ``NBANK_METADATA_ALIASES``: other metadata keys that older clients use for
     the fields, e.g. ``{"bird": "animal"}`` (for clients written for API 1.1
     and earlier; see ``CHANGELOG.rst`` for 0.12.0).
   - ``NEUROBANK_AUTO_ID_LENGTH``: the length of the identifiers the registry
     generates (default 8).
   - ``SENDFILE_BACKEND`` and ``SENDFILE_ROOT``, for downloading resources from
     archives on the server. The registry uses `django-sendfile2
     <https://django-sendfile2.readthedocs.io/en/latest/backends.html>`__ to
     have the web server send the files; the backend depends on the server, and
     the archives must be accesible to the web server under ``SENDFILE_ROOT``.

5. Include the registry's URLs in your project's ``urls.py``. The second line
   lets people log in to the browsable API and is optional if you don't need that.

   .. code:: python

      from django.urls import include, path

      urlpatterns = [
          ...
          path("neurobank/", include("nbank_registry.urls")),
          path("api-auth/", include("rest_framework.urls")),
      ]

6. Run ``python manage.py migrate`` to create the database tables, and
   ``python manage.py createsuperuser`` for an account that can add records.

7. Start the development server and point your browser to
   http://127.0.0.1:8000/neurobank/ to view records and inspect the API.

When upgrading, read ``CHANGELOG.rst`` for the version: some releases add
settings that have to be in place before migrating.

Using the registry
~~~~~~~~~~~~~~~~~~

The API can be browsed with a web browser. Reading is open to everyone;
changing anything requires logging in (HTTP Basic or a session) as a user with
Django's permissions for that kind of record, and asking for the current API
version in the ``Accept`` header (``application/json; version=2.0``), as
neurobank 1.0 and later do. Requests that don't ask for a version can read but
not change anything, so older clients can still find resources but get a 400
asking them to upgrade if they try to deposit. The endpoints, relative to where
the registry's URLs are included:

- ``info/``: the registry's version and API version, and who the request is
  from: ``user`` is null for an anonymous request, or the ``username``, whether
  they're a ``superuser``, and the registry ``permissions`` they have (e.g.
  ``add_resource``). Wrong credentials are refused.
- ``resources/``: list and search resources (GET), register one (POST). See
  OPTIONS for the search parameters; ``metadata__<key>`` searches metadata.
- ``resources/<name>/``: a resource's record (GET), change it (PUT, PATCH),
  delete it (DELETE).
- ``resources/<name>/locations/``: a resource's locations (GET), add one (POST).
- ``resources/<name>/locations/<archive>/``: one location (GET), change its key
  (PATCH), remove it (DELETE).
- ``archives/``, ``archives/<name>/``: archives (GET, POST; GET, PUT, PATCH).
- ``datatypes/``, ``datatypes/<name>/``: data types (GET, POST; GET).
- ``check/resources/``: whether a resource could be created (POST the same body
  as to ``resources/``), without creating it: 200, or 400 with the errors
  creating it would give. POST a list of bodies (up to 1,000) to check several:
  200 with the errors for each one in order (``{}`` if it could be created),
  counting a name or hash that an earlier one in the list has. Another deposit
  can still take a name or hash before the resource is created.
- ``bulk/resources/``, ``bulk/locations/``: records or locations for many
  resources at once (POST ``{"names": [...]}``), as line-delimited JSON.
- ``download/<name>/``: the resource's file, for resources in archives on the
  server.

Besides free-form ``metadata``, each resource has two optional fields that
refer to other records, which can be searched exactly (``?experimenter=``,
``?animal=``), excluded (``?animal__neq=``), or tested for a missing value
(``?animal__isnull=true``). Animals can also be matched by the start of their
identifier, such as the first part of a UUID (``?animal__istartswith=``):

- ``experimenter``: the username of the person who collected or produced the
  data. It must be a user in the registry database (i.e., the
  ``AUTH_USER_MODEL``). People who don't use the registry (e.g., external
  collaborators) can be given inactive accounts.
- ``animal``: the animal the data came from, by the primary key of the animal
  model. It must be a record in that model; animals from elsewhere can be given
  placeholder records. Leave it empty for synthetic data or data from more than
  one animal.

By default, animals are kept in a minimal model of the registry's own, keyed by
name and managed in the admin. If you use `django-bird-colony
<https://github.com/melizalab/django-bird-colony>`__ in the same site, set
``NBANK_ANIMAL_MODEL = "birds.Animal"`` to use that model instead. Like
``AUTH_USER_MODEL``, this must be set before the registry's migrations are first
run. You always have to use the animal's full official ID with the animal field,
except when searching for partial IDs with ``?animal__istartswith=``.

A resource that shouldn't be used, such as a duplicate or an erroneous deposit
caught after others have cited it, can be marked as superseded instead of being
deleted, so its name stays valid and clients can warn about it. A resource is
superseded when ``superseded_on`` is set (to when it was marked).
``superseded_by`` can name the resource to use instead, and ``superseded_note``
can say why, or name the replacements of a resource that was split; with no
replacement, the resource just shouldn't be used. Both need ``superseded_on``,
and setting it to null unmarks the resource and clears them. Only superusers
can mark or unmark resources, and a resource that supersedes others can't be
deleted. Searches include superseded resources: ``?superseded=false`` leaves
them out, and ``?superseded_by=`` finds those a resource replaces.

When a resource is created (or updated), ``locations`` lists the archives that
hold it, by name. An entry can also be ``{"archive": name, "key": key}`` to
record where the resource is within the archive, such as the name of the stored
file; a key can be used only once in an archive. Records list locations by
archive name. A location's key can be changed later through the resource's
locations.

A fundamental concept behind a registry is that resources have unique
identifiers, which are never re-used or changed. Names can't be changed through
the API, and only users with Django's permission to delete resources (normally
superusers) can delete one. This is for repairs, not routine use. Locations,
metadata, and the other fields can be changed with PUT or PATCH.

This application is still under development, and you should
only allow access from trusted networks. Authentication is required to
modify or add resources, archives, or data types. Authentication uses
the django user app, and credentials are sent in plain text. Your site
should only be deployed as a reverse proxy behind an encrypting
https-enabled web server like nginx.

Administration
~~~~~~~~~~~~~~

One problem with user-defined metadata is that keys and values can be misspelled
or drift. The ``normalize_metadata`` administrative script can help to address
some of these issues as they accumulate. You can also use this script when
migrating from older databases (pre 0.12) to move free-form metadata values into the
``animal`` and ``experimenter`` fields.

To get started, run ``python manage.py normalize_metadata --dry-run >
mappings.toml``. This reports what would change and writes a template listing
every value found, with values that can't be stored (an experimenter who isn't a
user, or an animal that isn't in the animal model) first. Edit it to add:

- aliases: other names for a field, whose values move into the field, or for a
  metadata key, which is renamed (e.g. ``experiment = "protocol"``);
- inactive users to create;
- value mappings for the fields (``[animal]``) and for metadata keys
  (``[metadata.protocol]``): ``"old" = "new"``, or ``"old" = { move = "key" }``
  to keep a value in metadata under another key and leave the field or key
  empty. Add an empty table for a metadata key to have the dry run list its
  values.

The command doesn't create animals; add placeholder records for the ones that
aren't in the animal model. Repeat the dry run with ``--mappings mappings.toml``
until the report looks right, and then run it without ``--dry-run``. Values that
can't be stored in a field, and resources whose values conflict, are left as
they are. The command can be run as many times as you want before committing the
changes by turning off ``--dry-run``.

Development
~~~~~~~~~~~

Recommend using `uv <https://docs.astral.sh/uv/>`__ for development.

Run ``uv sync`` to create a virtual environment and install
dependencies. ``uv sync --no-dev --frozen`` for deployment.

Testing: ``uv run pytest``. Settings are in
``nbank_registry/tests/settings.py``. By default tests run against an
in-memory SQLite database. To test against PostgreSQL (as CI does), run
``uv sync --group postgres`` and set ``NBANK_TEST_DB=postgres``, with
``POSTGRES_HOST``, ``POSTGRES_USER`` and the like for the server (see
``settings.py``). ``NBANK_TEST_ANIMAL_MODEL=uuid`` runs the tests with an
animal model keyed by UUID, like django-bird-colony's. Environment variables
can also go in a ``.env`` or ``.test.env`` file.

Lint with ``uv run ruff check`` and ``uv run ruff format``.
