from django.contrib import admin
from neurobank.models import Resource, DataType, Domain, Location

class LocationInline(admin.TabularInline):
    model = Location


class DataTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'content_type')


class DomainAdmin(admin.ModelAdmin):
    list_display = ('name', 'scheme', 'root')
    list_filter = ('name', 'scheme')
    search_fields = ('name__istartswith', 'scheme__istartswith', 'root__icontains')


class ResourceAdmin(admin.ModelAdmin):
    fields = ('name', 'sha1', 'dtype', 'metadata')
    list_display = ('name', 'dtype',)
    list_filter = ('name', 'dtype')
    search_fields = ('name__istartswith', 'sha1__istartswith', 'dtype', 'metadata__icontains')
    inlines = (LocationInline,)

admin.site.register(Resource, ResourceAdmin)
admin.site.register(DataType, DataTypeAdmin)
admin.site.register(Domain, DomainAdmin)
