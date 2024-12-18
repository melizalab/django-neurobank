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
`neurobank <https://github.com/melizalab/neurobank>`__\ \* using an HTTP
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

Quick start
~~~~~~~~~~~

1. Requires Python 3.10+. Runs on Django 4.2 LTS and 5.1.

2. Install the package: ``pip install django-neurobank``

3. Add ``neurobank`` to your INSTALLED_APPS setting like this:

.. code:: python

   INSTALLED_APPS = (
       ...
       'rest_framework',
       'django_filters',
       'nbank_registry',
   )

``neurobank`` uses ``django-sendfile2`` to efficiently serve large
files, you will need to set ``settings.SENDFILE_BACKEND`` and possibly
other keys, depending on which reverse proxy you are using. Consult `the
documentation for
django-sendfile2 <https://django-sendfile2.readthedocs.io/en/latest/backends.html>`__
for details.

3. Include the neurobank URLconf in your project urls.py like this:

.. code:: python

   url(r'^neurobank/', include(nbank_registry.urls')),

4. Run ``python manage.py migrate`` to create the database tables.

5. Start the development server and point your browser to
   http://127.0.0.1:8000/neurobank/ to view records and inspect the API.

Using the registry
~~~~~~~~~~~~~~~~~~

Documentation is still in progress. We need a list of endpoints and
supported verbs. However, the interface can be accessed through a
browser.

Deleting is not supported in the HTTP API. A fundamental concept behind
a registry is that resources have unique identifiers, which are never
re-used or changed. You can edit locations, metadata, and other
attributes using PUT. If you desperately need to change a name or delete
an identifier, you’ll have to use the Django database admin or directly
access the backing database.

This application is still under development, and you should probably
only allow access from trusted networks. Authentication is required to
modify or add resources, archives, or data types. Authentication uses
the django user app, and credentials are sent in plain text. Your site
should only be deployed as a reverse proxy behind an encrpyting
https-enabled web server like nginx.

Development
~~~~~~~~~~~

Recommend using `uv <https://docs.astral.sh/uv/>`__ for development.

Run ``uv sync`` to create a virtual environment and install
dependencies. ``uv sync --no-dev --frozen`` for deployment.

Testing: ``uv run pytest``. Requires a test database, will use settings
from ``inventory/test/settings.py``.
