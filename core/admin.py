from django.contrib import admin
from .models import Organization, OrganizationMembership, ServiceAuditLog, ServiceRecord, CustomServiceType, SiteNews, ClientIntake, Client, Vehicle, InventoryService, MarketingCampaignLog




class MembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    fields = (
        'user',
        'role',
        'can_view_reports',
        'can_view_net_profit',
        'can_manage_referrals',
        'can_trigger_automation',
    )
    readonly_fields = ('user',)
    verbose_name = "Agent / Member"
    verbose_name_plural = "Agents & Members"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "invite_code", "intake_link_display", "is_automation_enabled")
    list_filter = ("state", "city", "is_automation_enabled")
    search_fields = ("name", "address_line", "city", "state", "phone_number")
    readonly_fields = ("intake_link_display",)
    inlines = [MembershipInline]

    def intake_link_display(self, obj):
        from django.utils.html import format_html
        url = f"/intake/{obj.portal_token}/"
        return format_html('<a href="{}" target="_blank">Open Intake Portal</a>', url)
    
    intake_link_display.short_description = "Public Intake Link"

    class Media:
        js = ('core/js/admin_automation_toggle.js',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # If automation is disabled for this psb, revoke the permission from ALL members
        if not obj.is_automation_enabled:
            obj.memberships.filter(can_trigger_automation=True).update(can_trigger_automation=False)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "role", "can_trigger_automation", "created_at")
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
        "paid_amount",
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

@admin.register(SiteNews)
class SiteNewsAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "content")

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "phone_number", "organization", "created_at")
    list_filter = ("organization", "state", "created_at")
    search_fields = ("first_name", "last_name", "email", "phone_number")
    ordering = ("-created_at",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("vin", "year", "make", "model", "plate_number", "client", "created_at")
    list_filter = ("vehicle_type", "fuel_type", "plate_type", "created_at")
    search_fields = ("vin", "plate_number", "make", "model", "client__first_name", "client__last_name")
    ordering = ("-created_at",)


@admin.register(ClientIntake)
class ClientIntakeAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "organization", "status", "created_at", "processed_by")
    list_filter = ("status", "organization")
    search_fields = ("first_name", "last_name", "vin")
    readonly_fields = ("created_at", "processed_at", "processed_by")


@admin.register(InventoryService)
class InventoryServiceAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "organization", "price", "stock", "created_at")
    list_filter = ("organization",)
    search_fields = ("label", "key", "organization__name")


@admin.register(MarketingCampaignLog)
class MarketingCampaignLogAdmin(admin.ModelAdmin):
    list_display = ("subject", "inventory_service", "organization", "recipients_count", "sent_by", "sent_at")
    list_filter = ("organization", "inventory_service")
    search_fields = ("subject", "body", "sent_by__username")
    readonly_fields = ("sent_at",)



# Patch get_urls on default AdminSite to register crm-import
from django.urls import path
from .admin_views import crm_import_view

original_get_urls = admin.site.get_urls

def new_get_urls():
    urls = original_get_urls()
    custom_urls = [
        path('crm-import/', admin.site.admin_view(crm_import_view), name='crm-import'),
    ]
    return custom_urls + urls

admin.site.get_urls = new_get_urls

