# -*- mode: python -*-
"""An animal model keyed by UUID, like django-bird-colony's, for testing
NBANK_ANIMAL_MODEL (NBANK_TEST_ANIMAL_MODEL=uuid)."""

import uuid

from django.db import models


class Animal(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return self.name or str(self.uuid)
