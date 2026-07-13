from django.contrib import admin

from ..tlc_models import (
    TLCCarrier,
    TLCCarrierRemittance,
    TLCDMVService,
    TLCEndorsement,
    TLCFinanceCompany,
    TLCInstallment,
    TLCPolicy,
    TLCPolicyCancellation,
    TLCPolicyDocument,
    TLCPolicyTimelineEvent,
    TLCPremiumBreakdown,
    TLCReinstatement,
)


class TLCInstallmentInline(admin.TabularInline):
    model = TLCInstallment
    extra = 0


class TLCPremiumBreakdownInline(admin.StackedInline):
    model = TLCPremiumBreakdown
    extra = 0


@admin.register(TLCPolicy)
class TLCPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_number",
        "carrier",
        "named_insured",
        "status",
        "organization",
        "effective_date",
        "created_at",
    )
    list_filter = ("status", "policy_type", "organization", "carrier")
    search_fields = (
        "policy_number",
        "named_insured",
        "business_name",
        "vin",
        "plate_number",
        "tlc_base_number",
    )
    inlines = [TLCPremiumBreakdownInline, TLCInstallmentInline]


@admin.register(TLCCarrier)
class TLCCarrierAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "created_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "organization__name")
    ordering = ("organization", "name")


@admin.register(TLCFinanceCompany)
class TLCFinanceCompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "contact_phone",
        "contact_email",
        "default_installment_fee",
        "is_active",
        "created_at",
    )
    list_filter = ("organization", "is_active")
    search_fields = ("name", "contact_phone", "contact_email", "organization__name")
    ordering = ("organization", "name")


@admin.register(TLCReinstatement)
class TLCReinstatementAdmin(admin.ModelAdmin):
    list_display = ("policy", "cancellation_date", "reinstatement_date", "reinstatement_fee", "dmv_document_number")


@admin.register(TLCEndorsement)
class TLCEndorsementAdmin(admin.ModelAdmin):
    list_display = (
        "policy",
        "endorsement_type",
        "written_premium_before",
        "written_premium_after",
        "premium_difference",
        "endorsement_fee",
        "coverage_change_date",
    )


@admin.register(TLCDMVService)
class TLCDMVServiceAdmin(admin.ModelAdmin):
    list_display = ("policy", "service_type", "fee_charged", "dmv_tlc_cost", "agency_profit", "service_date")


@admin.register(TLCCarrierRemittance)
class TLCCarrierRemittanceAdmin(admin.ModelAdmin):
    list_display = ("policy", "amount", "remittance_date")


@admin.register(TLCPolicyCancellation)
class TLCPolicyCancellationAdmin(admin.ModelAdmin):
    list_display = (
        "policy",
        "cancellation_date",
        "reason",
        "unearned_commission",
        "return_premium",
        "successor_policy_number",
    )


@admin.register(TLCPolicyDocument)
class TLCPolicyDocumentAdmin(admin.ModelAdmin):
    list_display = ("policy", "document_type", "title", "uploaded_at")


@admin.register(TLCPolicyTimelineEvent)
class TLCPolicyTimelineEventAdmin(admin.ModelAdmin):
    list_display = ("policy", "event_type", "title", "event_date")
