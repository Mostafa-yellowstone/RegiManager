from django.contrib import admin
from .models import Organization, OrganizationMembership, ServiceAuditLog, ServiceRecord, CustomServiceType


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "address_line", "city", "state", "slug", "created_at")
    list_filter = ("state", "city")
    search_fields = ("name", "address_line", "city", "state", "slug")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "role", "created_at")
    list_filter = ("role", "organization")
    search_fields = ("organization__name", "user__username", "user__email")


@admin.register(ServiceRecord)
class ServiceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "organization",
        "service_type",
        "status",
        "client_name",
        "handled_by",
        "processing_fee",
        "dmv_fee",
        "sales_tax",
        "credit_card_fee",
        "service_fee",
        "created_at",
    )
    list_filter = ("service_type", "status", "organization")
    search_fields = ("receipt_number", "client_name", "client_identifier", "handled_by__username")


@admin.register(ServiceAuditLog)
class ServiceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("organization", "service_record", "actor", "action", "created_at")
    list_filter = ("action", "organization")
    search_fields = ("actor__username", "service_record__receipt_number", "details")


@admin.register(CustomServiceType)
class CustomServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("label", "key", "organization__name")

