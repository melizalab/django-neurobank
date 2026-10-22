# -*- mode: python -*-

from django.contrib import admin

from nbank_registry.models import (
    Animal,
    Archive,
    DataType,
    Location,
    Resource,
    get_animal_model,
)


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
        "superseded_on",
        "superseded_by",
        "superseded_note",
    )
    list_display = ("name", "dtype", "experimenter", "animal", "created_on")
    list_select_related = ("dtype", "experimenter", "animal")
    # there can be thousands of animals and resources, too many for a drop-down.
    # animal gets autocomplete too if its model's admin supports it (see
    # get_autocomplete_fields), and a raw id field otherwise
    autocomplete_fields = ("superseded_by",)
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

    def get_autocomplete_fields(self, request):
        """Adds animal if its model has an admin with search_fields, which
        autocomplete needs. A site with its own animal model (NBANK_ANIMAL_MODEL)
        may not register one, and its admin may be registered after this one,
        so this is decided when a page is built rather than at import."""
        fields = super().get_autocomplete_fields(request)
        animal_admin = self.admin_site._registry.get(get_animal_model())
        if animal_admin is not None and animal_admin.get_search_fields(request):
            fields = (*fields, "animal")
        return fields


admin.site.register(Resource, ResourceAdmin)
admin.site.register(DataType, DataTypeAdmin)
admin.site.register(Archive, ArchiveAdmin)
# a site with its own animal model (NBANK_ANIMAL_MODEL) manages animals in that app
if not Animal._meta.swapped:
    admin.site.register(Animal, search_fields=("name",))
