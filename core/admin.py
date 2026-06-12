from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, DecimalField, Value
from django.db.models.functions import Coalesce
from decimal import Decimal
from .models import (
    Organization, OrganizationMembership, ServiceAuditLog, ServiceRecord,
    CustomServiceType, SiteNews, ClientIntake, Client, Vehicle,
    Space, Referral, ReferralPayment,
    UserSession, ServiceDocument, KnowledgeHubMaterial,
    InventoryBuyer, InventoryCategory, InventoryInvoice,
    InventoryProduct, InventoryPurchase, InventoryPurchaseLine,
    InventoryStockMovement, InventorySupplier,
    MotorclubConfig, MotorclubB2BPartner, MotorclubMembership,
    DocumentFolder, SpaceDocumentType, SpaceDocumentRecord,
)



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
        'can_view_spaces',
        'can_deal_with_insurance',
        'can_delete_receipt',
        'can_view_commission',
        'can_view_banking',
        'can_manage_news',
        'can_manage_knowledge_hub',
        'accessible_spaces',
        'signature',
    )
    readonly_fields = ('user',)
    verbose_name = "Agent / Member"
    verbose_name_plural = "Agents & Members"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "psbc_license", "invite_code", "intake_link_display", "is_public_intake_enabled", "is_automation_enabled")
    list_filter = ("state", "city", "is_public_intake_enabled", "is_automation_enabled")
    search_fields = ("name", "address_line", "city", "state", "phone_number", "psbc_license")
    readonly_fields = ("intake_link_display",)
    inlines = [MembershipInline]

    def intake_link_display(self, obj):
        if not obj.is_public_intake_enabled:
            return "Disabled (enable Public Intake Portal)"
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
    list_display = ("organization", "user", "role", "can_view_spaces", "can_deal_with_insurance", "can_delete_receipt", "can_trigger_automation", "can_view_commission", "can_view_banking", "can_manage_news", "can_manage_knowledge_hub", "can_manage_documents", "created_at")
    list_filter = ("role", "organization", "can_view_spaces", "can_deal_with_insurance", "can_view_commission", "can_view_banking", "can_manage_news", "can_manage_knowledge_hub", "can_manage_documents")
    search_fields = ("organization__name", "user__username", "user__email")
    fieldsets = (
        (None, {
            "fields": ("organization", "user", "role", "is_active"),
        }),
        ("Permissions", {
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
        }),
        ("Spaces Access", {
            "description": "Required for all members, including PSB owners: enable Spaces page access, then pick which spaces they can open.",
            "fields": (
                "can_view_spaces",
                "accessible_spaces",
            ),
        }),
        ("Other", {
            "fields": ("signature",),
        }),
    )
    filter_horizontal = ("accessible_spaces",)


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
        "other_fees",
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
    list_display = ("title", "organization", "is_active", "published_by", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("title", "content", "organization__name")

@admin.register(KnowledgeHubMaterial)
class KnowledgeHubMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "space", "step_number", "created_at")
    list_filter = ("space", "space__organization")
    search_fields = ("title", "description")

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


@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("label", "key", "organization__name")


@admin.register(DocumentFolder)
class DocumentFolderAdmin(admin.ModelAdmin):
    list_display = ("name", "space", "parent", "organization", "created_at")
    list_filter = ("organization",)


@admin.register(SpaceDocumentType)
class SpaceDocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "space", "organization", "created_at")
    list_filter = ("organization",)


@admin.register(SpaceDocumentRecord)
class SpaceDocumentRecordAdmin(admin.ModelAdmin):
    list_display = ("record_number", "document_type", "order_number", "quantity", "space", "added_by", "created_at")
    list_filter = ("organization", "document_type")
    search_fields = ("record_number", "order_number", "range_start", "range_end")


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "space", "organization")
    list_filter = ("organization",)


@admin.register(InventoryProduct)
class InventoryProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "unit_price", "quantity", "space")
    list_filter = ("organization", "is_active")


@admin.register(InventoryBuyer)
class InventoryBuyerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "space", "organization")


@admin.register(InventoryInvoice)
class InventoryInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "buyer_name", "invoice_date", "subtotal", "sales_tax", "total", "status")
    list_filter = ("status", "organization")


@admin.register(InventoryStockMovement)
class InventoryStockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "movement_type", "quantity_change", "quantity_after", "created_at")


@admin.register(InventorySupplier)
class InventorySupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "company_name", "space", "is_active")
    list_filter = ("organization", "is_active")


@admin.register(InventoryPurchase)
class InventoryPurchaseAdmin(admin.ModelAdmin):
    list_display = ("purchase_number", "supplier", "purchase_date", "total_cost", "space")


@admin.register(InventoryPurchaseLine)
class InventoryPurchaseLineAdmin(admin.ModelAdmin):
    list_display = ("purchase", "description", "quantity", "unit_cost", "line_total")


@admin.register(ServiceDocument)
class ServiceDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document_type_display",
        "linked_vehicle",
        "linked_service_record",
        "uploaded_at",
        "file_download_link",
    )
    list_filter = ("document_type", "uploaded_at")
    search_fields = (
        "vehicle__vin",
        "vehicle__plate_number",
        "service_record__receipt_number",
        "service_record__client_name",
    )
    readonly_fields = ("uploaded_at", "file_download_link")
    ordering = ("-uploaded_at",)

    def document_type_display(self, obj):
        return obj.get_document_type_display()
    document_type_display.short_description = "Document Type"
    document_type_display.admin_order_field = "document_type"

    def linked_vehicle(self, obj):
        if obj.vehicle:
            return format_html(
                '<a href="/admin/core/vehicle/{}/change/">{} – {} {} {}</a>',
                obj.vehicle.id,
                obj.vehicle.vin or "—",
                obj.vehicle.year or "",
                obj.vehicle.make or "",
                obj.vehicle.model or "",
            )
        return "—"
    linked_vehicle.short_description = "Vehicle"

    def linked_service_record(self, obj):
        if obj.service_record:
            return format_html(
                '<a href="/admin/core/servicerecord/{}/change/">{}</a>',
                obj.service_record.id,
                obj.service_record.receipt_number or f"#{obj.service_record.id}",
            )
        return "—"
    linked_service_record.short_description = "Service Record"

    def file_download_link(self, obj):
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank" download>⬇ Download</a>',
                obj.file.url,
            )
        return "No file"
    file_download_link.short_description = "File"


# ─────────────────────────────────────────────
# Referral & ReferralPayment Admin
# ─────────────────────────────────────────────

class ReferralServiceRecordInline(admin.TabularInline):
    """Read-only inline showing all transactions linked to this referral."""
    model = ServiceRecord
    fk_name = "referral"
    extra = 0
    fields = (
        "receipt_number", "service_type", "status",
        "client_name", "processing_fee", "dmv_fee",
        "credit_card_fee", "other_fees", "service_fee",
        "referral_balance", "is_referral_paid", "created_at",
    )
    readonly_fields = fields
    verbose_name = "Transaction"
    verbose_name_plural = "Transactions (Service Records)"
    ordering = ("-created_at",)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReferralPaymentInline(admin.TabularInline):
    """Editable inline for payments made by/to a referral."""
    model = ReferralPayment
    extra = 0
    fields = (
        "payment_type", "amount", "payment_date",
        "status", "reference_number", "notes",
    )
    ordering = ("-payment_date",)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "organization", "phone_no", "email",
        "initial_balance", "total_outstanding_display", "is_partner",
    )
    list_filter = ("category", "organization", "is_partner")
    search_fields = ("name", "email", "phone_no", "address", "organization__name")
    ordering = ("name",)
    inlines = [ReferralPaymentInline, ReferralServiceRecordInline]

    def get_queryset(self, request):
        from django.db.models import Q
        qs = super().get_queryset(request)
        qs = qs.annotate(
            total_outstanding=Coalesce(
                Sum("service_records__referral_balance",
                    filter=Q(service_records__is_referral_paid=False)),
                Value(Decimal("0")),
                output_field=DecimalField(),
            )
        )
        return qs

    def total_outstanding_display(self, obj):
        """Sum of referral_balance across all unpaid transactions."""
        total = (
            obj.service_records
            .filter(is_referral_paid=False)
            .aggregate(total=Coalesce(Sum("referral_balance"), Value(Decimal("0"))))
            ["total"]
        )
        color = "#dc2626" if total > 0 else "#16a34a"
        return format_html(
            '<span style="color: {}; font-weight: 600;">${}</span>',
            color, f"{total:,.2f}"
        )
    total_outstanding_display.short_description = "Outstanding Balance"
    total_outstanding_display.admin_order_field = "total_outstanding"


@admin.register(ReferralPayment)
class ReferralPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "referral", "payment_type", "amount_display",
        "payment_date", "status", "reference_number", "created_at",
    )
    list_filter = ("payment_type", "status", "referral__organization")
    search_fields = ("referral__name", "reference_number", "notes")
    ordering = ("-payment_date",)
    autocomplete_fields = ("referral", "service_record")

    def amount_display(self, obj):
        return f"${obj.amount:,.2f}"
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "session_key", "created_at")
    search_fields = ("user__username",)
    readonly_fields = ("user", "session_key", "created_at")



# Patch get_urls on default AdminSite to register crm-import
from django.urls import path
from .admin_views import crm_import_view

@admin.register(MotorclubConfig)
class MotorclubConfigAdmin(admin.ModelAdmin):
    list_display = ("organization", "tier_35_provider_take", "tier_50_provider_take", "updated_at")


@admin.register(MotorclubB2BPartner)
class MotorclubB2BPartnerAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "contact_name", "is_active", "created_at")
    list_filter = ("organization", "is_active")


@admin.register(MotorclubMembership)
class MotorclubMembershipAdmin(admin.ModelAdmin):
    list_display = ("membership_number", "client", "tier", "channel", "status", "psb_profit", "organization")
    list_filter = ("organization", "channel", "status", "tier")
    search_fields = ("membership_number", "client__first_name", "client__last_name")


original_get_urls = admin.site.get_urls

def new_get_urls():
    urls = original_get_urls()
    custom_urls = [
        path('crm-import/', admin.site.admin_view(crm_import_view), name='crm-import'),
    ]
    return custom_urls + urls

admin.site.get_urls = new_get_urls
