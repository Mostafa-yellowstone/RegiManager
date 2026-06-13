from django.contrib import admin

from ..models import CustomServiceType, ServiceAuditLog, ServiceDocument, ServiceRecord


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
        "referral_commission",
        "paid_amount",
        "service_fee",
        "created_at",
    )
    list_filter = ("service_type", "status", "organization", "payment_method")
    search_fields = ("receipt_number", "client_name", "client_identifier", "vin", "handled_by__username")
    autocomplete_fields = ("organization", "handled_by", "vehicle", "referral")
    readonly_fields = ("receipt_number", "case_id", "service_fee", "referral_balance", "created_at", "updated_at")
    ordering = ("-created_at",)
    fieldsets = (
        ("Receipt", {"fields": ("organization", "handled_by", "receipt_number", "case_id", "transaction_date", "status")}),
        ("Client Snapshot", {"fields": ("client_name", "client_identifier", "client_address", "phone_no", "email")}),
        ("Vehicle", {"fields": ("vehicle", "vehicle_number", "plate_number", "vin")}),
        ("Service", {"fields": ("service_type", "source", "referral", "transaction_type", "terminal_number", "notes")}),
        (
            "Fees",
            {
                "fields": (
                    "processing_fee",
                    "referral_commission",
                    "dmv_fee",
                    "sales_tax",
                    "dmv_sales_tax",
                    "credit_card_fee",
                    "other_fees",
                    "other_dmv_fee",
                    "service_fee",
                ),
            },
        ),
        ("Payment", {"fields": ("payment_method", "payment_method_2", "paid_amount", "paid_amount_2", "referral_balance", "is_referral_paid")}),
    )


@admin.register(ServiceAuditLog)
class ServiceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("organization", "service_record", "actor", "action", "created_at")
    list_filter = ("action", "organization")
    search_fields = ("actor__username", "service_record__receipt_number", "details")
    readonly_fields = ("organization", "service_record", "actor", "action", "details", "created_at")
    ordering = ("-created_at",)


@admin.register(CustomServiceType)
class CustomServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("label", "key", "organization__name")


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
        from django.utils.html import format_html

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
        from django.utils.html import format_html

        if obj.service_record:
            return format_html(
                '<a href="/admin/core/servicerecord/{}/change/">{}</a>',
                obj.service_record.id,
                obj.service_record.receipt_number or f"#{obj.service_record.id}",
            )
        return "—"

    linked_service_record.short_description = "Service Record"

    def file_download_link(self, obj):
        from django.utils.html import format_html

        if obj.file:
            return format_html('<a href="{}" target="_blank" download>Download</a>', obj.file.url)
        return "No file"

    file_download_link.short_description = "File"
