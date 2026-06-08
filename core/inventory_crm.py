"""Helpers for the Custom Inventory space CRM."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    InventoryBuyer,
    InventoryCategory,
    InventoryInvoice,
    InventoryInvoiceLine,
    InventoryProduct,
    InventoryStockMovement,
)


def generate_invoice_number(organization):
    year = timezone.localdate().year
    prefix = f"INV-{year}-"
    last = (
        InventoryInvoice.objects.filter(
            organization=organization,
            invoice_number__startswith=prefix,
        )
        .order_by("-invoice_number")
        .values_list("invoice_number", flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except ValueError:
            seq = InventoryInvoice.objects.filter(organization=organization).count() + 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def record_stock_movement(product, movement_type, quantity_change, reference="", notes="", user=None):
    product.quantity = max(0, product.quantity + quantity_change)
    product.save(update_fields=["quantity", "updated_at"])
    return InventoryStockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        quantity_change=quantity_change,
        quantity_after=product.quantity,
        reference=reference,
        notes=notes,
        created_by=user,
    )


@transaction.atomic
def apply_invoice_stock_deductions(invoice, user=None):
    for line in invoice.lines.select_related("product"):
        if not line.product_id:
            continue
        product = line.product
        qty = -int(line.quantity)
        if product.quantity + qty < 0:
            raise ValueError(f"Insufficient stock for {product.name}")
        record_stock_movement(
            product,
            InventoryStockMovement.MovementType.SALE,
            qty,
            reference=invoice.invoice_number,
            notes=f"Sold on {invoice.invoice_number}",
            user=user,
        )


def recalculate_invoice_totals(invoice):
    lines = invoice.lines.all()
    subtotal = sum((line.line_total for line in lines), Decimal("0.00"))
    invoice.subtotal = subtotal
    invoice.total = subtotal
    invoice.save(update_fields=["subtotal", "total", "updated_at"])
    return invoice


def inventory_dashboard_stats(space):
    products_qs = InventoryProduct.objects.filter(space=space, is_active=True)
    total_products = products_qs.count()
    total_units = products_qs.aggregate(total=Coalesce(Sum("quantity"), 0))["total"] or 0
    total_value = sum((p.unit_price * p.quantity for p in products_qs), Decimal("0.00"))
    low_stock = products_qs.filter(quantity__lte=F("low_stock_threshold")).order_by("quantity", "name")

    today = timezone.localdate()
    month_start = today.replace(day=1)
    invoices_qs = InventoryInvoice.objects.filter(
        space=space,
        status=InventoryInvoice.Status.COMPLETED,
    )
    sales_today = invoices_qs.filter(invoice_date=today).aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00")),
        count=Count("id"),
    )
    sales_month = invoices_qs.filter(invoice_date__gte=month_start).aggregate(
        total=Coalesce(Sum("total"), Decimal("0.00")),
        count=Count("id"),
    )

    return {
        "total_products": total_products,
        "total_units": total_units,
        "total_inventory_value": total_value,
        "low_stock_products": list(low_stock[:10]),
        "low_stock_count": low_stock.count(),
        "sales_today_total": sales_today["total"] or Decimal("0.00"),
        "sales_today_count": sales_today["count"] or 0,
        "sales_month_total": sales_month["total"] or Decimal("0.00"),
        "sales_month_count": sales_month["count"] or 0,
        "category_count": InventoryCategory.objects.filter(space=space).count(),
        "buyer_count": InventoryBuyer.objects.filter(space=space).count(),
        "invoice_count": invoices_qs.count(),
    }


def category_stats(space):
    categories = InventoryCategory.objects.filter(space=space).annotate(
        product_count=Count("products"),
    )
    stats = []
    for cat in categories:
        products = cat.products.filter(is_active=True)
        value = sum((p.unit_price * p.quantity for p in products), Decimal("0.00"))
        units = sum(p.quantity for p in products)
        stats.append({
            "category": cat,
            "product_count": cat.product_count,
            "total_units": units,
            "total_value": value,
        })
    return stats


def get_or_create_buyer(space, org, name, phone="", email="", address=""):
    buyer = InventoryBuyer.objects.filter(space=space, name__iexact=name).first()
    if buyer:
        return buyer
    return InventoryBuyer.objects.create(
        organization=org,
        space=space,
        name=name,
        phone=phone,
        email=email,
        address=address,
    )
