from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from accounts.models import Driver, VerificationDocument


class VerificationDocumentInline(admin.TabularInline):
    model = VerificationDocument
    extra = 0
    fields = ('doc_type', 'file', 'status', 'verified_at')
    readonly_fields = ('verified_at',)


@admin.register(Driver)
class DriverAdmin(ImportExportModelAdmin):
    list_display = ('user', 'vehicle_make', 'vehicle_model', 'plate', 'seats', 'rating', 'is_verified')
    list_filter = ('is_verified', 'vehicle_make')
    search_fields = ('user__full_name', 'user__phone', 'plate')
    inlines = [VerificationDocumentInline]
    readonly_fields = ('rating',)


@admin.register(VerificationDocument)
class VerificationDocumentAdmin(ImportExportModelAdmin):
    list_display = ('driver', 'doc_type', 'status', 'verified_at')
    list_filter = ('doc_type', 'status')
    search_fields = ('driver__user__full_name', 'driver__plate')
