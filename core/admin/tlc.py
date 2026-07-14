from django.contrib import admin

from ..tlc_models import (
    TLCCarrier,
    TLCCarrierRemittance,
    TLCDMVService,
    TLCEndorsement,
    TLCFinanceCompany,
    TLCInstallment,
    TLCPaymentSplit,
    TLCPaymentTransaction,
    TLCPolicy,
    TLCPolicyCancellation,
    TLCPolicyDocument,
    TLCPolicyTimelineEvent,
    TLCPremiumBreakdown,
    TLCReceipt,
    TLCReinstatement,
)


class TLCInstallmentInline(admin.TabularInline):
    model = TLCInstallment
    extra = 0


class TLCPremiumBreakdownInline(admin.StackedInline):
    model = TLCPremiumBreakdown
    extra = 0


class TLCPaymentSplitInline(admin.TabularInline):
    model = TLCPaymentSplit
    extra = 0
    fields = (
        "payment_method",
        "amount",
        "reference_number",
        "approval_number",
        "last_four",
        "notes",
        "sort_order",
    )


class TLCReceiptInline(admin.TabularInline):
    model = TLCReceipt
    extra = 0
    fields = ("receipt_number", "version", "generated_at", "generated_by", "pdf_file")
    readonly_fields = ("receipt_number", "version", "generated_at", "generated_by", "pdf_file")
    can_delete = False
    show_change_link = True


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


@admin.register(TLCPaymentTransaction)
class TLCPaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_id",
        "policy",
        "organization",
        "transaction_type",
        "amount_due",
        "amount_received",
        "payment_date",
        "status",
        "processed_by",
        "created_at",
    )
    list_filter = ("transaction_type", "status", "organization", "payment_date")
    search_fields = (
        "transaction_id",
        "policy__policy_number",
        "policy__named_insured",
        "description",
        "notes",
    )
    readonly_fields = ("transaction_id", "created_at")
    date_hierarchy = "payment_date"
    raw_id_fields = ("policy", "processed_by", "installment", "reinstatement", "endorsement", "dmv_service")
    inlines = [TLCPaymentSplitInline, TLCReceiptInline]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "organization",
                    "policy",
                    "transaction_id",
                    "transaction_type",
                    "status",
                    "description",
                )
            },
        ),
        (
            "Amounts",
            {"fields": ("amount_due", "amount_received", "payment_date", "payment_time")},
        ),
        (
            "Linked records",
            {
                "fields": ("installment", "reinstatement", "endorsement", "dmv_service"),
            },
        ),
        ("Audit", {"fields": ("processed_by", "notes", "created_at")}),
    )


@admin.register(TLCReceipt)
class TLCReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "policy",
        "transaction",
        "version",
        "generated_at",
        "generated_by",
        "has_pdf",
    )
    list_filter = ("generated_at", "version")
    search_fields = (
        "receipt_number",
        "policy__policy_number",
        "transaction__transaction_id",
        "content_hash",
    )
    readonly_fields = (
        "receipt_number",
        "version",
        "generated_at",
        "content_hash",
        "snapshot_json",
        "pdf_file",
    )
    date_hierarchy = "generated_at"
    raw_id_fields = ("policy", "transaction", "generated_by")

    @admin.display(boolean=True, description="PDF")
    def has_pdf(self, obj):
        return bool(obj.pdf_file)
