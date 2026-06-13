from decimal import Decimal

from django.contrib import admin
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.html import format_html

from ..models import Referral, ReferralPayment, ServiceRecord


class ReferralServiceRecordInline(admin.TabularInline):
    model = ServiceRecord
    fk_name = "referral"
    extra = 0
    fields = (
        "receipt_number",
        "service_type",
        "status",
        "client_name",
        "processing_fee",
        "referral_commission",
        "service_fee",
        "referral_balance",
        "is_referral_paid",
        "created_at",
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
    model = ReferralPayment
    extra = 0
    fields = ("payment_type", "amount", "payment_date", "status", "reference_number", "notes")
    ordering = ("-payment_date",)


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "organization",
        "referral_fee",
        "initial_balance",
        "total_outstanding_display",
        "is_partner",
    )
    list_filter = ("category", "organization", "is_partner")
    search_fields = ("name", "email", "phone_no", "address", "organization__name")
    ordering = ("name",)
    inlines = [ReferralPaymentInline, ReferralServiceRecordInline]
    fieldsets = (
        ("Partner", {"fields": ("organization", "name", "category", "is_partner")}),
        ("Contact", {"fields": ("email", "phone_no", "website", "address")}),
        ("Financials", {"fields": ("referral_fee", "initial_balance")}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            total_outstanding=Coalesce(
                Sum(
                    "service_records__referral_balance",
                    filter=Q(service_records__is_referral_paid=False),
                ),
                Value(Decimal("0")),
                output_field=DecimalField(),
            )
        )

    def total_outstanding_display(self, obj):
        total = (
            obj.service_records.filter(is_referral_paid=False).aggregate(
                total=Coalesce(Sum("referral_balance"), Value(Decimal("0")))
            )["total"]
        )
        color = "#dc2626" if total > 0 else "#16a34a"
        return format_html('<span style="color:{};font-weight:600;">${}</span>', color, f"{total:,.2f}")

    total_outstanding_display.short_description = "Outstanding Balance"
    total_outstanding_display.admin_order_field = "total_outstanding"


@admin.register(ReferralPayment)
class ReferralPaymentAdmin(admin.ModelAdmin):
    list_display = ("referral", "payment_type", "amount_display", "payment_date", "status", "reference_number", "created_at")
    list_filter = ("payment_type", "status", "referral__organization")
    search_fields = ("referral__name", "reference_number", "notes")
    ordering = ("-payment_date",)
    autocomplete_fields = ("referral", "service_record")

    def amount_display(self, obj):
        return f"${obj.amount:,.2f}"

    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"
