from django.contrib import admin

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
