from django.contrib import admin
from neurobank.models import Resource, DataType, Domain, Location

class LocationInline(admin.TabularInline):
    model = Location

class ResourceAdmin(admin.ModelAdmin):
    fields = ('name', 'dtype',)
    list_display = ('name', 'dtype',)
    list_filter = ('name', 'dtype')
    search_fields = ('name__istartswith', 'dtype')
    inlines = (LocationInline,)

admin.site.register(Resource, ResourceAdmin)

for model in (DataType, Domain):
    admin.site.register(model)
