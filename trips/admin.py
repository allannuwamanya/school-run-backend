from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import Assignment, Trip, Stop, LiveLocation


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0
    fields = ('sequence', 'child', 'status', 'eta', 'picked_at', 'dropped_at')
    readonly_fields = ('picked_at', 'dropped_at')


@admin.register(Assignment)
class AssignmentAdmin(ImportExportModelAdmin):
    list_display = ('parent', 'driver', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('parent__user__full_name', 'driver__user__full_name', 'driver__plate')


@admin.register(Trip)
class TripAdmin(ImportExportModelAdmin):
    list_display = ('driver', 'service_date', 'direction', 'status', 'started_at', 'ended_at')
    list_filter = ('status', 'direction', 'service_date')
    search_fields = ('driver__user__full_name', 'driver__plate')
    inlines = [StopInline]
    readonly_fields = ('started_at', 'ended_at')


@admin.register(LiveLocation)
class LiveLocationAdmin(admin.ModelAdmin):
    list_display = ('driver', 'latitude', 'longitude', 'updated_at')
    readonly_fields = ('updated_at',)
