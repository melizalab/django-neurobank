# -*- coding: utf-8 -*-
# -*- mode: python -*-
from __future__ import unicode_literals

from django.contrib import admin

from nbank_registry.models import Archive, DataType, Location, Resource


class LocationInline(admin.TabularInline):
    model = Location


class DataTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "content_type", "extension")


class ArchiveAdmin(admin.ModelAdmin):
    list_display = ("name", "scheme", "root")
    list_filter = ("scheme",)
    search_fields = ("name__istartswith", "scheme__istartswith", "root__icontains")


class ResourceAdmin(admin.ModelAdmin):
    date_hierarchy = "created_on"
    fields = ("name", "sha1", "dtype", "metadata", "created_by")
    list_display = ("name", "dtype", "created_by", "created_on")
    list_filter = (
        "dtype",
        "location__archive",
        "created_by",
    )
    search_fields = (
        "name__istartswith",
        "sha1__istartswith",
        "dtype__name",
        "metadata__icontains",
    )
    inlines = (LocationInline,)


admin.site.register(Resource, ResourceAdmin)
admin.site.register(DataType, DataTypeAdmin)
admin.site.register(Archive, ArchiveAdmin)
