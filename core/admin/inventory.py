from django.contrib import admin

from ..models import (
    InventoryBuyer,
    InventoryCategory,
    InventoryInvoice,
    InventoryProduct,
    InventoryPurchase,
    InventoryPurchaseLine,
    InventoryStockMovement,
    InventorySupplier,
)


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "space", "organization")
    list_filter = ("organization",)


@admin.register(InventoryProduct)
class InventoryProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "unit_price", "quantity", "space", "is_active")
    list_filter = ("organization", "is_active", "category")
    search_fields = ("name", "sku")


@admin.register(InventoryBuyer)
class InventoryBuyerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "space", "organization")
    search_fields = ("name", "phone", "email")


@admin.register(InventoryInvoice)
class InventoryInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "buyer_name", "invoice_date", "subtotal", "sales_tax", "total", "status")
    list_filter = ("status", "organization")
    search_fields = ("invoice_number", "buyer_name")


@admin.register(InventoryStockMovement)
class InventoryStockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "movement_type", "quantity_change", "quantity_after", "created_at")
    list_filter = ("movement_type", "product__organization")


@admin.register(InventorySupplier)
class InventorySupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "company_name", "space", "is_active")
    list_filter = ("organization", "is_active")


@admin.register(InventoryPurchase)
class InventoryPurchaseAdmin(admin.ModelAdmin):
    list_display = ("purchase_number", "supplier", "purchase_date", "total_cost", "space")
    list_filter = ("organization",)


@admin.register(InventoryPurchaseLine)
class InventoryPurchaseLineAdmin(admin.ModelAdmin):
    list_display = ("purchase", "description", "quantity", "unit_cost", "line_total")
