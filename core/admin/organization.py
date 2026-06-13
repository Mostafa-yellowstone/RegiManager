from django.contrib import admin
from django.utils.html import format_html

from ..models import Organization, OrganizationMembership, UserSession


class MembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    fields = (
        "user",
        "role",
        "can_view_reports",
        "can_view_net_profit",
        "can_manage_referrals",
        "can_trigger_automation",
        "can_view_spaces",
        "can_deal_with_insurance",
        "can_delete_receipt",
        "can_view_commission",
        "can_view_banking",
        "can_manage_news",
        "can_manage_knowledge_hub",
        "accessible_spaces",
        "signature",
    )
    readonly_fields = ("user",)
    verbose_name = "Agent / Member"
    verbose_name_plural = "Agents & Members"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "city",
        "state",
        "psbc_license",
        "invite_code",
        "intake_link_display",
        "is_public_intake_enabled",
        "is_automation_enabled",
    )
    list_filter = ("state", "city", "is_public_intake_enabled", "is_automation_enabled")
    search_fields = ("name", "address_line", "city", "state", "phone_number", "psbc_license")
    readonly_fields = ("intake_link_display",)
    inlines = [MembershipInline]
    fieldsets = (
        ("PSB Profile", {"fields": ("name", "logo", "address_line", "city", "state", "phone_number", "psbc_license")}),
        ("Access & Limits", {"fields": ("invite_code", "portal_token", "max_agents", "is_active")}),
        ("Features", {"fields": ("is_automation_enabled", "is_public_intake_enabled", "intake_link_display")}),
        ("Insurance Space", {"fields": ("insurance_space_locked", "insurance_space_password")}),
        ("Public Intake", {"fields": ("show_review_button", "review_link")}),
    )

    def intake_link_display(self, obj):
        if not obj.is_public_intake_enabled:
            return "Disabled (enable Public Intake Portal)"
        url = f"/intake/{obj.portal_token}/"
        return format_html('<a href="{}" target="_blank">Open Intake Portal</a>', url)

    intake_link_display.short_description = "Public Intake Link"

    class Media:
        js = ("core/js/admin_automation_toggle.js",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not obj.is_automation_enabled:
            obj.memberships.filter(can_trigger_automation=True).update(can_trigger_automation=False)


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "user",
        "role",
        "is_active",
        "can_view_spaces",
        "can_manage_referrals",
        "can_trigger_automation",
        "created_at",
    )
    list_filter = (
        "role",
        "organization",
        "is_active",
        "can_view_spaces",
        "can_manage_referrals",
        "can_trigger_automation",
    )
    search_fields = ("organization__name", "user__username", "user__email")
    filter_horizontal = ("accessible_spaces",)
    fieldsets = (
        (None, {"fields": ("organization", "user", "role", "is_active")}),
        (
            "Permissions",
            {
                "fields": (
                    "can_view_reports",
                    "can_view_net_profit",
                    "can_manage_referrals",
                    "can_trigger_automation",
                    "can_deal_with_insurance",
                    "can_deal_with_motorclub",
                    "can_delete_receipt",
                    "can_view_commission",
                    "can_view_banking",
                    "can_manage_news",
                    "can_manage_knowledge_hub",
                    "can_manage_documents",
                ),
            },
        ),
        (
            "Spaces Access",
            {
                "description": "Enable the Spaces page, then choose which spaces this member can open.",
                "fields": ("can_view_spaces", "accessible_spaces"),
            },
        ),
        ("Other", {"fields": ("signature",)}),
    )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "session_key", "created_at")
    search_fields = ("user__username",)
    readonly_fields = ("user", "session_key", "created_at")
