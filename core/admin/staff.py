from django.contrib import admin

from ..models import StaffDocument, StaffEmployee


@admin.register(StaffEmployee)
class StaffEmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "last_name",
        "first_name",
        "job_title",
        "department",
        "employment_status",
        "organization",
        "hire_date",
    )
    list_filter = ("organization", "employment_status", "department")
    search_fields = ("first_name", "last_name", "email", "phone", "job_title")
    autocomplete_fields = ("linked_user",)


@admin.register(StaffDocument)
class StaffDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "employee", "organization", "expires_at", "created_at")
    list_filter = ("organization", "category")
    search_fields = ("title", "employee__first_name", "employee__last_name")
    autocomplete_fields = ("employee",)
