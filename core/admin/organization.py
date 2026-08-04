from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from ..models import Organization, OrganizationMembership, UserSession
from ..agent_portal_models import AgentActivityEvent, AgentAttendanceSession, AgentTask
from ..us_states import US_STATES, normalize_state_code


class OrganizationAdminForm(forms.ModelForm):
    state = forms.ChoiceField(
        choices=US_STATES,
        required=False,
        help_text="Motor vehicle state for this PSB. Vehicle profiles show DMV forms for this state.",
    )

    class Meta:
        model = Organization
        fields = "__all__"

    def clean_state(self):
        value = self.cleaned_data.get("state") or ""
        return normalize_state_code(value)


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
        "can_assign_agent_tasks",
        "can_delete_receipt",
        "can_issue_refund",
        "can_view_banking",
        "can_manage_news",
        "can_manage_knowledge_hub",
        "accessible_spaces",
        "profile_photo",
        "signature",
    )
    readonly_fields = ("user",)
    verbose_name = "Agent / Member"
    verbose_name_plural = "Agents & Members"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    form = OrganizationAdminForm
    change_form_template = "admin/core/organization/change_form.html"
    list_display = (
        "name",
        "city",
        "state",
        "psbc_license",
        "psbc_license_expiration_date",
        "email",
        "invite_code",
        "intake_link_display",
        "is_public_intake_enabled",
        "is_public_insurance_intake_enabled",
        "is_automation_enabled",
        "backup_download_link",
    )
    list_filter = ("state", "city", "is_public_intake_enabled", "is_public_insurance_intake_enabled", "is_automation_enabled")
    search_fields = ("name", "address_line", "city", "state", "phone_number", "email", "psbc_license")
    readonly_fields = ("intake_link_display", "insurance_intake_link_display", "backup_download_link")
    inlines = [MembershipInline]
    fieldsets = (
        ("PSB Profile", {
            "fields": (
                "name",
                "business_owner_name",
                "logo",
                "address_line",
                "city",
                "state",
                "phone_number",
                "email",
                "psbc_license",
                "psbc_license_effective_date",
                "psbc_license_expiration_date",
                "psbc_license_alert_days",
            ),
            "description": (
                "Choose the PSB motor vehicle state from the dropdown (e.g. CT, PA, NJ). "
                "This controls which DMV forms appear on vehicle profiles. "
                "Set Business owner name to the full legal name shown on receipts; users with the Owner role are not used. "
                "PSB license dates drive dashboard renewal alerts for owners."
            ),
        }),
        ("Access & Limits", {"fields": ("invite_code", "portal_token", "max_agents", "is_active")}),
        ("Features", {
            "fields": (
                "is_automation_enabled",
                "is_public_intake_enabled",
                "intake_link_display",
            ),
        }),
        (
            "Insurance Intake Portal",
            {
                "fields": (
                    "is_public_insurance_intake_enabled",
                    "insurance_intake_link_display",
                    "insurance_intake_display_name",
                    "insurance_intake_tagline",
                    "insurance_ezlynx_quote_url",
                    "insurance_intake_portal_mode",
                    "insurance_show_review_button",
                    "insurance_review_link",
                ),
                "description": (
                    "Public insurance intake branding and EZLynx consumer quoting embed. "
                    "Set the EZLynx / AgentInsure quote URL and choose dual mode to capture leads in RegiManager "
                    "before clients complete the embedded quote application."
                ),
            },
        ),
        ("Public Intake", {"fields": ("show_review_button", "review_link")}),
    )

    def intake_link_display(self, obj):
        if not obj.is_public_intake_enabled:
            return "Disabled (enable Public Intake Portal)"
        url = f"/intake/{obj.portal_token}/"
        return format_html('<a href="{}" target="_blank">Open Intake Portal</a>', url)

    intake_link_display.short_description = "Public Intake Link"

    def insurance_intake_link_display(self, obj):
        if not obj.is_public_insurance_intake_enabled:
            return "Disabled (enable Insurance Intake Portal)"
        url = f"/insurance-intake/{obj.portal_token}/"
        return format_html('<a href="{}" target="_blank">Open Insurance Intake Portal</a>', url)

    insurance_intake_link_display.short_description = "Insurance Intake Link"

    def backup_download_link(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = reverse("admin:psb-backup-download", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="white-space:nowrap;">Download backup</a>',
            url,
        )

    backup_download_link.short_description = "Backup"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["psb_backup_download_url"] = reverse(
            "admin:psb-backup-download", args=[object_id]
        )
        extra_context["psb_backup_import_url"] = reverse("admin:psb-backup-import")
        extra_context["show_psb_backup"] = request.user.is_superuser
        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    class Media:
        js = ("core/js/admin_automation_toggle.js",)

    def save_model(self, request, obj, form, change):
        obj.state = normalize_state_code(obj.state)
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
    search_fields = (
        "organization__name",
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
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
                    "can_deal_with_tlc",
                    "can_assign_agent_tasks",
                    "can_delete_receipt",
                    "can_issue_refund",
                    "can_view_banking",
                    "can_manage_news",
                    "can_manage_knowledge_hub",
                    "can_manage_documents",
                    "can_manage_email_marketing",
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
        ("Profile", {"fields": ("profile_photo", "signature")}),
    )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "session_key", "created_at")
    search_fields = ("user__username",)
    readonly_fields = ("user", "session_key", "created_at")


@admin.register(AgentAttendanceSession)
class AgentAttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("membership", "organization", "work_date", "opened_at", "closed_at")
    list_filter = ("organization", "work_date")
    search_fields = ("membership__user__username", "organization__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "assigned_to_label",
        "status",
        "is_done",
        "due_date",
        "created_by",
        "created_at",
        "completed_at",
    )
    list_filter = ("organization", "status", "is_done", "due_date", "created_at")
    search_fields = (
        "title",
        "description",
        "completion_note",
        "assigned_to__user__username",
        "assigned_to__user__first_name",
        "assigned_to__user__last_name",
        "created_by__username",
    )
    list_editable = ("status", "is_done")
    # Keep FK pickers simple so tasks can be created even when autocomplete
    # search wiring for User/Membership is incomplete on some deploys.
    raw_id_fields = ("assigned_to", "created_by")
    autocomplete_fields = ("organization",)
    readonly_fields = ("completed_at", "created_at", "updated_at")
    date_hierarchy = "created_at"
    ordering = ("is_done", "-created_at")
    actions = ("mark_tasks_done", "mark_tasks_open")
    fieldsets = (
        (
            "Task",
            {
                "fields": (
                    "organization",
                    "assigned_to",
                    "title",
                    "description",
                    "due_date",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "is_done",
                    "completion_note",
                    "completed_at",
                    "created_by",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="Assigned to", ordering="assigned_to__user__username")
    def assigned_to_label(self, obj):
        user = obj.assigned_to.user if obj.assigned_to_id else None
        if not user:
            return "—"
        return user.get_full_name().strip() or user.username

    def save_model(self, request, obj, form, change):
        from django.utils import timezone

        if obj.status == AgentTask.Status.DONE or obj.is_done:
            obj.status = AgentTask.Status.DONE
            obj.is_done = True
            if not obj.completed_at:
                obj.completed_at = timezone.now()
        else:
            obj.is_done = False
            obj.completed_at = None
            if not obj.status:
                obj.status = AgentTask.Status.TODO
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Mark selected tasks as done")
    def mark_tasks_done(self, request, queryset):
        from django.utils import timezone

        updated = queryset.exclude(status=AgentTask.Status.DONE).update(
            status=AgentTask.Status.DONE,
            is_done=True,
            completed_at=timezone.now(),
        )
        self.message_user(request, f"Marked {updated} task(s) done.")

    @admin.action(description="Reopen selected tasks")
    def mark_tasks_open(self, request, queryset):
        updated = queryset.filter(is_done=True).update(
            status=AgentTask.Status.TODO,
            is_done=False,
            completed_at=None,
        )
        self.message_user(request, f"Reopened {updated} task(s).")


@admin.register(AgentActivityEvent)
class AgentActivityEventAdmin(admin.ModelAdmin):
    list_display = ("title", "domain", "event_type", "organization", "actor", "created_at")
    list_filter = ("domain", "event_type", "organization")
    search_fields = ("title", "detail", "actor__username")
    readonly_fields = ("created_at",)
