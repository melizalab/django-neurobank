# -*- mode: python -*-

from django.contrib import admin

from nbank_registry.models import Animal, Archive, DataType, Location, Resource


class LocationInline(admin.TabularInline):
    model = Location
    fields = ("archive", "key")


class DataTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "content_type", "extension")


class ArchiveAdmin(admin.ModelAdmin):
    list_display = ("name", "scheme", "root", "accessibility")
    list_filter = ("scheme", "accessibility")
    search_fields = ("name__istartswith", "scheme__istartswith", "root__icontains")


class ResourceAdmin(admin.ModelAdmin):
    date_hierarchy = "created_on"
    fields = (
        "name",
        "sha1",
        "dtype",
        "experimenter",
        "animal",
        "metadata",
        "created_by",
    )
    list_display = ("name", "dtype", "experimenter", "animal", "created_on")
    list_select_related = ("dtype", "experimenter", "animal")
    # there can be thousands of animals, too many for a drop-down
    raw_id_fields = ("animal",)
    list_filter = (
        "dtype",
        "location__archive",
        "created_by",
        "experimenter",
    )
    search_fields = (
        "name__istartswith",
        "sha1__istartswith",
        "dtype__name",
        "animal__pk",
        "metadata__icontains",
    )
    inlines = (LocationInline,)


admin.site.register(Resource, ResourceAdmin)
admin.site.register(DataType, DataTypeAdmin)
admin.site.register(Archive, ArchiveAdmin)
# a site with its own animal model (NBANK_ANIMAL_MODEL) manages animals in that app
if not Animal._meta.swapped:
    admin.site.register(Animal)
