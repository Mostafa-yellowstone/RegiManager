"""Supplier domain logic for Custom Inventory."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    InventoryProduct,
    InventoryPurchase,
    InventoryPurchaseLine,
    InventoryStockMovement,
    InventorySupplier,
)
from .inventory_crm import record_stock_movement


def generate_purchase_number(organization):
    year = timezone.localdate().year
    prefix = f"PO-{year}-"
    last = (
        InventoryPurchase.objects.filter(
            organization=organization,
            purchase_number__startswith=prefix,
        )
        .order_by("-purchase_number")
        .values_list("purchase_number", flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except ValueError:
            seq = InventoryPurchase.objects.filter(organization=organization).count() + 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def product_unit_profit(product):
    return product.unit_price - product.cost_price


def product_margin_percent(product):
    if not product.unit_price or product.unit_price <= 0:
        return Decimal("0.00")
    return (product_unit_profit(product) / product.unit_price) * Decimal("100")


def enrich_product_profit(product):
    profit = product_unit_profit(product)
    product.unit_profit = profit
    product.margin_percent = product_margin_percent(product)
    product.potential_profit = profit * product.quantity
    return product


def recalculate_purchase_totals(purchase):
    total = sum((line.line_total for line in purchase.lines.all()), Decimal("0.00"))
    purchase.total_cost = total
    purchase.save(update_fields=["total_cost", "updated_at"])
    return purchase


@transaction.atomic
def apply_purchase_receipt(purchase, user=None):
    for line in purchase.lines.select_related("product"):
        if not line.product_id:
            continue
        product = line.product
        qty = int(line.quantity)
        record_stock_movement(
            product,
            InventoryStockMovement.MovementType.RECEIVE,
            qty,
            reference=purchase.purchase_number,
            notes=f"Received from {purchase.supplier.name}",
            user=user,
        )
        product.cost_price = line.unit_cost
        if not product.primary_supplier_id:
            product.primary_supplier = purchase.supplier
        product.save(update_fields=["cost_price", "primary_supplier", "updated_at"])


def supplier_dashboard_data(space):
    suppliers_qs = (
        InventorySupplier.objects.filter(space=space, is_active=True)
        .annotate(purchase_count=Count("purchases"))
        .order_by("name")
    )
    supplier_cards = []
    for supplier in suppliers_qs:
        spent = (
            InventoryPurchase.objects.filter(supplier=supplier).aggregate(
                total=Coalesce(Sum("total_cost"), Decimal("0.00"))
            )["total"]
            or Decimal("0.00")
        )
        products = list(
            InventoryProduct.objects.filter(space=space, primary_supplier=supplier, is_active=True)
        )
        for p in products:
            enrich_product_profit(p)
        total_potential_profit = sum((p.potential_profit for p in products), Decimal("0.00"))
        supplier_cards.append({
            "supplier": supplier,
            "total_spent": spent,
            "purchase_count": supplier.purchase_count,
            "product_count": len(products),
            "products": products,
            "potential_profit": total_potential_profit,
        })

    recent_purchases = (
        InventoryPurchase.objects.filter(space=space)
        .select_related("supplier", "created_by")
        .prefetch_related("lines__product")
        .order_by("-purchase_date", "-created_at")[:60]
    )
    total_supplier_spend = (
        InventoryPurchase.objects.filter(space=space).aggregate(
            total=Coalesce(Sum("total_cost"), Decimal("0.00"))
        )["total"]
        or Decimal("0.00")
    )
    return {
        "supplier_cards": supplier_cards,
        "recent_purchases": recent_purchases,
        "supplier_count": suppliers_qs.count(),
        "total_supplier_spend": total_supplier_spend,
    }
