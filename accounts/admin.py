from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from . import models
from import_export.admin import ImportExportModelAdmin
# Register your models here.
user = get_user_model()


class UserModelAdmin(ImportExportModelAdmin):

    def get_queryset(self, request):
        return self.model.all_objects.all()

    list_display = ('full_name',  'email', 'auth_provider', 'photo', 'is_staff', 'is_active')
    list_filter = ('full_name',  'email', 'is_staff', 'is_active')
    search_fields = ('full_name',  'email',   'is_staff', 'is_active')


admin.site.register(user,UserModelAdmin)
admin.site.register(models.ErrorLog)