from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from .models import School, Child, Schedule


class ScheduleInline(admin.StackedInline):
    model = Schedule
    extra = 0


@admin.register(School)
class SchoolAdmin(ImportExportModelAdmin):
    list_display = ('name', 'address', 'location')
    search_fields = ('name', 'address')


@admin.register(Child)
class ChildAdmin(ImportExportModelAdmin):
    list_display = ('full_name', 'parent', 'school', 'class_name', 'blood_type', 'is_active')
    list_filter = ('school', 'is_active', 'gender')
    search_fields = ('full_name', 'parent__user__full_name', 'parent__user__phone')
    inlines = [ScheduleInline]
