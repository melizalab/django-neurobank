# -*- coding: utf-8 -*-
# Generated by Django 1.11.2 on 2017-06-27 16:26
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('neurobank', '0012_auto_20170627_1049'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='location',
            unique_together=set([('resource', 'domain')]),
        ),
    ]
