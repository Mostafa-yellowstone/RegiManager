from django.contrib import admin
from .models import Organization, OrganizationMembership, ServiceAuditLog, ServiceRecord, CustomServiceType, SiteNews, ClientIntake


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
        url = f"/intake/{obj.invite_code}/"
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

@admin.register(ClientIntake)
class ClientIntakeAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "organization", "status", "created_at", "processed_by")
    list_filter = ("status", "organization")
    search_fields = ("first_name", "last_name", "vin")
    readonly_fields = ("created_at", "processed_at", "processed_by")
