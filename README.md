
## django-neurobank

This is a Django application that provides name resolution services to [neurobank](https://github.com/melizalab/neurobank)* using an HTTP API.

The data management strategy behind **neurobank** is simple: every resource gets a unique identifier. As long as you use the correct identifier, you can unambiguously locate the resource. Resources include *sources*, which are used to control an experiment, and *data*, which result from running the experiment.

To use this strategy, you need to be able to do two things: register each resource you create somewhere, and then resolve resource names to locations so that you can access your data. Being able to attach searchable metadata to your resources is pretty handy, too. This software provides a backend for these tasks. You'll also need [neurobank](https://github.com/melizalab/neurobank)* or some other client software to take care of actually handling your files.

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

2. Include the neurobank URLconf in your project urls.py like this::

```python
url(r'^neurobank/', include(neurobank.urls')),
```

3. Run `python manage.py migrate` to create the database tables.

# edit below

4. Start the development server and visit http://127.0.0.1:8000/admin/neurobank/
   to create birds, events, etc. (you'll need the Admin app enabled).

5. Visit http://127.0.0.1:8000/neurobank/ to use views.
