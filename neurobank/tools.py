# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals
import random
import basehash

from django.conf import settings

auto_id_length = getattr(settings, "NEUROBANK_AUTO_ID_LENGTH", 8)
base36 = basehash.base36(auto_id_length)

def random_id():
    """Generate a random base36 id"""
    randi = random.randint(0, base36.maximum)
    return base36.hash(randi).lower()


from django.contrib.postgres.operations import HStoreExtension
