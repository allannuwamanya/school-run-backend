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

    list_display = ('full_name', 'email', 'role', 'nin_verified', 'is_staff', 'is_active')
    list_filter = ('role', 'nin_verified', 'is_staff', 'is_active')
    search_fields = ('full_name', 'email', 'phone')


admin.site.register(user,UserModelAdmin)
admin.site.register(models.ErrorLog)


@admin.register(models.AccountDeletionLog)
class AccountDeletionLogAdmin(admin.ModelAdmin):
    """View-only — deleted accounts' audit trail. No add/change/delete
    permission is granted here; models.AccountDeletionLog also blocks
    delete() itself, so this can't be cleared out via the admin UI either."""
    list_display = ("deleted_at", "target_full_name", "target_phone", "target_role", "deleted_by_name")
    list_filter = ("target_role",)
    search_fields = ("target_full_name", "target_phone", "deleted_by_name")
    ordering = ("-deleted_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False