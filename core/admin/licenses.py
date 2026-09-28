from django.contrib import admin

from ..models import AgencyLicense, AgencyLicenseDocument, AgencyLicenseFolder


class AgencyLicenseInline(admin.TabularInline):
    model = AgencyLicense
    extra = 0
    fields = ("title", "license_number", "expiration_date", "reminder_days", "is_active")


@admin.register(AgencyLicenseFolder)
class AgencyLicenseFolderAdmin(admin.ModelAdmin):
    list_display = ("state_name", "state_code", "organization")
    list_filter = ("state_code",)
    inlines = [AgencyLicenseInline]


@admin.register(AgencyLicense)
class AgencyLicenseAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "expiration_date", "reminder_days", "is_active")
    search_fields = ("title", "license_number", "holder_name")


@admin.register(AgencyLicenseDocument)
class AgencyLicenseDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "license", "uploaded_at")
