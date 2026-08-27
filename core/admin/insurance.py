"""Insurance CRM admin — organized like TLC for backend control of Insurance Space data."""

from django.contrib import admin
from django.utils.html import format_html

from ..insurance_esign_models import InsuranceESignEnvelope
from ..insurance_quote_pipeline_models import (
    InsuranceAgentOffDay,
    InsuranceQuoteDistributionConfig,
    InsuranceQuoteLead,
    InsuranceQuoteLeadDocument,
    InsuranceQuoteLeadDriver,
    InsuranceQuoteLeadVehicle,
)
from ..insurance_targets_models import (
    InsuranceLineTarget,
    InsuranceMarketPremiumAssumption,
    InsuranceMonthlyTarget,
)
from ..models import (
    BankAccount,
    BankTransaction,
    DailyPaymentTransaction,
    InsuranceCompany,
    InsuranceCompanyDocument,
    InsurancePolicy,
    InsurancePolicyDocument,
    InsurancePolicyDriver,
    InsurancePolicyInstallment,
    InsurancePolicyVehicle,
    InsuranceTypeOption,
)


# ── Inlines ──────────────────────────────────────────────────────────────


class InsuranceCompanyDocumentInline(admin.TabularInline):
    model = InsuranceCompanyDocument
    extra = 0
    fields = ("title", "document", "document_date", "uploaded_at")
    readonly_fields = ("uploaded_at",)


class InsurancePolicyDocumentInline(admin.TabularInline):
    model = InsurancePolicyDocument
    extra = 0
    fields = ("document_type", "title", "file", "uploaded_by", "uploaded_at")
    readonly_fields = ("uploaded_at",)
    raw_id_fields = ("uploaded_by",)


class InsurancePolicyInstallmentInline(admin.TabularInline):
    model = InsurancePolicyInstallment
    extra = 0
    fields = (
        "installment_number",
        "due_date",
        "amount",
        "installment_fee",
        "is_paid",
        "notes",
    )


class InsurancePolicyVehicleInline(admin.TabularInline):
    model = InsurancePolicyVehicle
    extra = 0
    fields = (
        "auto_number",
        "year",
        "make",
        "vin",
        "plate_number",
        "effective_date",
        "expiration_date",
    )


class InsurancePolicyDriverInline(admin.TabularInline):
    model = InsurancePolicyDriver
    extra = 0
    fields = ("name", "effective_date", "expiry_date")


class InsuranceQuoteLeadDocumentInline(admin.TabularInline):
    model = InsuranceQuoteLeadDocument
    extra = 0
    fields = ("file", "original_name", "uploaded_by", "created_at")
    readonly_fields = ("created_at",)
    raw_id_fields = ("uploaded_by",)


class InsuranceQuoteLeadDriverInline(admin.TabularInline):
    model = InsuranceQuoteLeadDriver
    extra = 0
    fields = ("full_name", "dl_number", "date_of_birth", "sort_order")


class InsuranceQuoteLeadVehicleInline(admin.TabularInline):
    model = InsuranceQuoteLeadVehicle
    extra = 0
    fields = ("year", "make", "model", "vin", "sort_order")


class InsuranceLineTargetInline(admin.TabularInline):
    model = InsuranceLineTarget
    extra = 0
    fields = (
        "insurance_type",
        "premium_target",
        "commission_target",
        "market_avg_premium",
        "is_active",
    )


# ── Markets & companies ──────────────────────────────────────────────────


@admin.register(InsuranceTypeOption)
class InsuranceTypeOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("label", "key", "organization__name")
    autocomplete_fields = ("organization",)
    ordering = ("organization", "label")


@admin.register(InsuranceCompany)
class InsuranceCompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "license_number",
        "broker_arrangement",
        "license_expiration_date",
        "created_at",
    )
    list_filter = ("organization", "broker_arrangement")
    search_fields = ("name", "license_number", "organization__name")
    autocomplete_fields = ("organization",)
    ordering = ("organization", "name")
    inlines = [InsuranceCompanyDocumentInline]
    fieldsets = (
        (None, {"fields": ("organization", "name", "broker_arrangement")}),
        (
            "License",
            {
                "fields": (
                    "license_number",
                    "license_effective_date",
                    "license_expiration_date",
                    "license_alert_days",
                )
            },
        ),
        ("Meta", {"fields": ("created_at",), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at",)


@admin.register(InsuranceCompanyDocument)
class InsuranceCompanyDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "insurance_company", "document_date", "uploaded_at")
    list_filter = ("insurance_company__organization",)
    search_fields = ("title", "insurance_company__name")
    raw_id_fields = ("insurance_company",)
    date_hierarchy = "uploaded_at"


# ── Policies (book of business) ──────────────────────────────────────────


@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_number",
        "client",
        "insurance_company",
        "stage",
        "status",
        "insurance_type",
        "premium",
        "commission_amount",
        "organization",
        "bound_date",
        "created_at",
    )
    list_filter = (
        "stage",
        "status",
        "insurance_type",
        "business_type",
        "source",
        "commission_received",
        "organization",
        "insurance_company",
    )
    search_fields = (
        "policy_number",
        "named_insured",
        "vin",
        "plate_number",
        "driver_name",
        "client__first_name",
        "client__last_name",
        "client__email",
        "insurance_company__name",
    )
    autocomplete_fields = ("organization", "client", "insurance_company")
    raw_id_fields = ("added_by",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [
        InsurancePolicyInstallmentInline,
        InsurancePolicyVehicleInline,
        InsurancePolicyDriverInline,
        InsurancePolicyDocumentInline,
    ]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "organization",
                    "client",
                    "policy_number",
                    "insurance_company",
                    "stage",
                    "status",
                    "insurance_type",
                    "source",
                    "business_type",
                )
            },
        ),
        (
            "Coverage & insured",
            {
                "fields": (
                    "named_insured",
                    "insured_address",
                    "vin",
                    "plate_number",
                    "driver_name",
                    "start_date",
                    "end_date",
                    "renewal_date",
                    "bound_date",
                    "inactive_date",
                    "insurance_period_months",
                )
            },
        ),
        (
            "Premium & commission",
            {
                "fields": (
                    "premium",
                    "broker_fee",
                    "payment_method",
                    "commission_rate",
                    "commission_amount",
                    "unearned_commission",
                    "commission_received",
                )
            },
        ),
        ("Attribution", {"fields": ("added_by", "created_at", "updated_at")}),
    )
    readonly_fields = ("commission_amount", "created_at", "updated_at")


@admin.register(InsurancePolicyDocument)
class InsurancePolicyDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "policy", "uploaded_by", "uploaded_at")
    list_filter = ("document_type", "policy__organization")
    search_fields = ("title", "policy__policy_number")
    raw_id_fields = ("policy", "uploaded_by")
    date_hierarchy = "uploaded_at"


@admin.register(InsurancePolicyInstallment)
class InsurancePolicyInstallmentAdmin(admin.ModelAdmin):
    list_display = (
        "policy",
        "installment_number",
        "due_date",
        "amount",
        "installment_fee",
        "is_paid",
    )
    list_filter = ("is_paid", "policy__organization")
    search_fields = ("policy__policy_number", "notes")
    raw_id_fields = ("policy",)
    date_hierarchy = "due_date"


# ── Daily payments & banking ─────────────────────────────────────────────


@admin.register(DailyPaymentTransaction)
class DailyPaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_date",
        "client",
        "amount",
        "payment_type",
        "payment_method",
        "insurance_company",
        "is_cleared",
        "organization",
        "recorded_by",
    )
    list_filter = (
        "payment_type",
        "payment_method",
        "is_cleared",
        "organization",
        "transaction_date",
    )
    search_fields = (
        "client__first_name",
        "client__last_name",
        "insurance_policy__policy_number",
        "insurance_company__name",
        "notes",
    )
    autocomplete_fields = ("organization", "client", "insurance_company")
    raw_id_fields = ("insurance_policy", "recorded_by", "updated_by")
    date_hierarchy = "transaction_date"
    ordering = ("-transaction_date", "-created_at")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("account_name", "bank_name", "organization", "balance", "created_at")
    list_filter = ("organization",)
    search_fields = ("account_name", "bank_name", "account_number", "organization__name")
    autocomplete_fields = ("organization",)
    ordering = ("organization", "account_name")


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "bank_account",
        "transaction_type",
        "amount",
        "category",
        "insurance_company",
        "created_at",
    )
    list_filter = ("transaction_type", "bank_account__organization", "date")
    search_fields = (
        "category",
        "description",
        "bank_account__account_name",
        "insurance_company__name",
    )
    raw_id_fields = ("bank_account", "insurance_company")
    date_hierarchy = "date"
    ordering = ("-date", "-created_at")


# ── Quote pipeline ───────────────────────────────────────────────────────


@admin.register(InsuranceQuoteLead)
class InsuranceQuoteLeadAdmin(admin.ModelAdmin):
    list_display = (
        "client_name",
        "phone",
        "insurance_type",
        "stage",
        "assignment_mode",
        "assigned_to",
        "organization",
        "created_at",
    )
    list_filter = (
        "stage",
        "assignment_mode",
        "coverage_type",
        "heard_about",
        "organization",
    )
    search_fields = (
        "client_name",
        "phone",
        "email",
        "vin",
        "dl_number",
        "street_address",
        "city",
        "notes",
    )
    autocomplete_fields = ("organization",)
    raw_id_fields = ("created_by", "assigned_to", "agent_task")
    filter_horizontal = ("recommended_companies",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [
        InsuranceQuoteLeadDriverInline,
        InsuranceQuoteLeadVehicleInline,
        InsuranceQuoteLeadDocumentInline,
    ]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "organization",
                    "client_name",
                    "phone",
                    "email",
                    "heard_about",
                    "insurance_type",
                    "stage",
                )
            },
        ),
        (
            "Address",
            {
                "fields": (
                    "street_address",
                    "apartment",
                    "city",
                    "state",
                    "zip_code",
                )
            },
        ),
        (
            "Risk",
            {
                "fields": (
                    "has_prior",
                    "is_experienced",
                    "has_accident",
                    "vehicle_ownership",
                    "coverage_type",
                    "vehicle_year",
                    "vehicle_make",
                    "vehicle_model",
                    "vin",
                    "dl_number",
                    "date_of_birth",
                    "notes",
                    "recommended_companies",
                )
            },
        ),
        (
            "Assignment",
            {
                "fields": (
                    "assigned_to",
                    "assigned_at",
                    "assignment_mode",
                    "agent_task",
                    "created_by",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(InsuranceQuoteDistributionConfig)
class InsuranceQuoteDistributionConfigAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "is_auto_enabled",
        "skip_sundays",
        "require_attendance_present",
        "last_assigned_membership",
        "updated_at",
    )
    list_filter = ("is_auto_enabled", "skip_sundays", "require_attendance_present")
    search_fields = ("organization__name",)
    autocomplete_fields = ("organization",)
    raw_id_fields = ("last_assigned_membership",)


@admin.register(InsuranceAgentOffDay)
class InsuranceAgentOffDayAdmin(admin.ModelAdmin):
    list_display = ("membership", "organization", "off_date", "reason", "created_at")
    list_filter = ("organization",)
    search_fields = (
        "membership__user__username",
        "membership__user__first_name",
        "membership__user__last_name",
        "reason",
    )
    autocomplete_fields = ("organization",)
    raw_id_fields = ("membership", "created_by")
    date_hierarchy = "off_date"


# ── Targets & forecast ───────────────────────────────────────────────────


@admin.register(InsuranceMonthlyTarget)
class InsuranceMonthlyTargetAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "year",
        "month",
        "premium_target",
        "commission_target",
        "updated_at",
    )
    list_filter = ("organization", "year")
    search_fields = ("organization__name", "notes")
    autocomplete_fields = ("organization",)
    inlines = [InsuranceLineTargetInline]
    ordering = ("-year", "-month")


@admin.register(InsuranceMarketPremiumAssumption)
class InsuranceMarketPremiumAssumptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "insurance_type", "avg_premium", "updated_at")
    list_filter = ("organization",)
    search_fields = ("insurance_type", "organization__name")
    autocomplete_fields = ("organization",)


# ── E-signature ──────────────────────────────────────────────────────────


@admin.register(InsuranceESignEnvelope)
class InsuranceESignEnvelopeAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "status",
        "signer_name",
        "signer_email",
        "has_signed_file",
        "signed_at",
        "created_at",
    )
    list_filter = ("status", "organization", "created_at")
    search_fields = ("title", "signer_name", "signer_email", "organization__name")
    autocomplete_fields = ("organization",)
    raw_id_fields = ("created_by", "signed_by")
    readonly_fields = (
        "signer_token",
        "signed_ip",
        "signed_user_agent",
        "signed_at",
        "created_at",
        "updated_at",
        "original_download",
        "signed_download",
        "fields_json",
        "audit_json",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    fieldsets = (
        (
            "Envelope",
            {
                "fields": (
                    "organization",
                    "title",
                    "status",
                    "original_file",
                    "original_download",
                    "signed_file",
                    "signed_download",
                )
            },
        ),
        (
            "Signer",
            {
                "fields": (
                    "signer_name",
                    "signer_email",
                    "signed_by",
                    "signed_at",
                    "signed_ip",
                    "created_by",
                )
            },
        ),
        (
            "Audit",
            {
                "classes": ("collapse",),
                "fields": (
                    "signer_token",
                    "signed_user_agent",
                    "fields_json",
                    "audit_json",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def delete_model(self, request, obj):
        obj.delete()

    def delete_queryset(self, request, queryset):
        for envelope in queryset:
            envelope.delete()

    @admin.display(description="Signed PDF", boolean=True)
    def has_signed_file(self, obj):
        return bool(obj.signed_file)

    @admin.display(description="Original PDF")
    def original_download(self, obj):
        if not obj.original_file:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Download original</a>',
            obj.original_file.url,
        )

    @admin.display(description="Signed PDF")
    def signed_download(self, obj):
        if not obj.signed_file:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Download signed</a>',
            obj.signed_file.url,
        )
