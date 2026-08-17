from django.contrib import admin
from django.utils.html import format_html

from ..insurance_esign_models import InsuranceESignEnvelope
from ..models import DocumentFolder, KnowledgeHubMaterial, Space, SpaceDocumentRecord, SpaceDocumentType


@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("label", "key", "organization__name")


@admin.register(KnowledgeHubMaterial)
class KnowledgeHubMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "space", "step_number", "created_at")
    list_filter = ("space", "space__organization")
    search_fields = ("title", "description")


@admin.register(DocumentFolder)
class DocumentFolderAdmin(admin.ModelAdmin):
    list_display = ("name", "space", "parent", "organization", "created_at")
    list_filter = ("organization",)
    search_fields = ("name",)


@admin.register(SpaceDocumentType)
class SpaceDocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "space", "organization", "created_at")
    list_filter = ("organization",)


@admin.register(SpaceDocumentRecord)
class SpaceDocumentRecordAdmin(admin.ModelAdmin):
    list_display = ("record_number", "document_type", "order_number", "quantity", "space", "added_by", "created_at")
    list_filter = ("organization", "document_type")
    search_fields = ("record_number", "order_number", "range_start", "range_end")


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
                "fields": ("signer_token", "signed_user_agent", "fields_json", "audit_json", "created_at", "updated_at"),
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
        return format_html('<a href="{}" target="_blank" rel="noopener">Download original</a>', obj.original_file.url)

    @admin.display(description="Signed PDF")
    def signed_download(self, obj):
        if not obj.signed_file:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Download signed</a>', obj.signed_file.url)

