
## django-neurobank

This is a Django application that provides name resolution services to [neurobank](https://github.com/melizalab/neurobank)* using an HTTP API.

The data management strategy behind **neurobank** is simple: every resource gets a unique identifier. As long as you use the correct identifier, you can unambiguously locate the resource. Resources include *sources*, which are used to control an experiment, and *data*, which result from running the experiment. Identifiers can be pretty much anything that's encodable in a URL and isn't too long. You can use manually-assigned identifiers like `st32_1_2_1` or let the API generate short, memorable codes like `heengei8`

To use this strategy, you need to be able to do two things: register each resource you create somewhere, and then resolve resource names to locations so that you can access your data. Being able to attach searchable metadata to your resources is pretty handy, too. This software provides a backend for these tasks. You'll also need [neurobank](https://github.com/melizalab/neurobank) or some other client software to take care of storing your files.

This software is licensed for you to use under the Gnu Public License, version 3. See COPYING for details

### Quick start

1. Install the package from source: `python setup.py install`. Worth putting in a virtualenv.

1. Add `neurobank` to your INSTALLED_APPS setting like this:

```python
INSTALLED_APPS = (
    ...
    'neurobank',
)
```

You'll also need to add `rest_framework` and `django_filters`.

2. Include the neurobank URLconf in your project urls.py like this::

```python
url(r'^neurobank/', include(neurobank.urls')),
```

3. Run `python manage.py migrate` to create the database tables.

4. Start the development server and point your browser to http://127.0.0.1:8000/neurobank/
   to view records and inspect the API.

### Using the registry

Documentation is still in progress. We need a list of endpoints and supported verbs. However, the interface can be accessed through a browser.

Deleting is not supported in the HTTP API. A fundamental concept behind a registry is that resources have unique identifiers, which are never re-used or changed. You can edit locations, metadata, and other attributes using PUT. If you desperately need to change a name or delete an identifier, you'll have to use the Django database admin or directly access the backing database.

This application is still under development, and you should probably only allow access from trusted networks. Authentication is required to modify or add resources, archives, or data types. Authentication uses the django user app, and credentials are sent in plain text. Your site should only be deployed as a reverse proxy behind an encrpyting https-enabled web server like nginx.
