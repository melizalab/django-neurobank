# -*- coding: utf-8 -*-
# -*- mode: python -*-
import os
import sys
if sys.hexversion < 0x02060000:
    raise RuntimeError("Python 2.6 or higher required")
from setuptools import setup

from neurobank import __version__

VERSION = __version__
cls_txt = """
Development Status :: 3 - Alpha
Framework :: Django
Intended Audience :: Science/Research
License :: OSI Approved :: GNU General Public License (GPL)
Programming Language :: Python
Topic :: Scientific/Engineering
Topic :: Internet :: WWW/HTTP
Topic :: Internet :: WWW/HTTP :: Dynamic Content
"""

setup(
    name="django-neurobank",
    version=VERSION,
    description="A Django-based registry for the neurobank system",
    long_description=open(os.path.join(os.path.dirname(__file__), 'README.md')).read(),
    long_description_content_type="text/markdown",
    classifiers=[x for x in cls_txt.split("\n") if x],
    author='C Daniel Meliza',
    maintainer='C Daniel Meliza',
    url="https://github.com/melizalab/django-neurobank",
    packages=['neurobank'],
    include_package_data=True,
)
