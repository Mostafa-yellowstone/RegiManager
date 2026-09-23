from django.contrib import admin

from ..models import DefenseDrivingEnrollment, DefenseDrivingPackage, SpaceImportantDocument


@admin.register(DefenseDrivingPackage)
class DefenseDrivingPackageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "price",
        "provider_take",
        "is_active",
        "sort_order",
        "updated_at",
    )
    list_filter = ("organization", "is_active")
    search_fields = ("name", "organization__name")


@admin.register(DefenseDrivingEnrollment)
class DefenseDrivingEnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "enrollment_number",
        "client",
        "package",
        "channel",
        "status",
        "psb_profit",
        "organization",
    )
    list_filter = ("organization", "channel", "status")
    search_fields = (
        "enrollment_number",
        "certificate_number",
        "client__first_name",
        "client__last_name",
    )
    autocomplete_fields = ("client",)


@admin.register(SpaceImportantDocument)
class SpaceImportantDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "space", "organization", "uploaded_by", "created_at")
    list_filter = ("organization", "category", "space__key")
    search_fields = ("title", "notes", "space__label")
