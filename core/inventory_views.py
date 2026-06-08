"""Views for the Custom Inventory space CRM."""

import csv
from datetime import datetime as dt_parse
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .inventory_crm import (
    apply_invoice_stock_deductions,
    category_stats,
    generate_invoice_number,
    get_or_create_buyer,
    inventory_dashboard_stats,
    recalculate_invoice_totals,
    record_stock_movement,
)
from .models import (
    InventoryBuyer,
    InventoryCategory,
    InventoryInvoice,
    InventoryInvoiceLine,
    InventoryProduct,
    InventoryStockMovement,
    OrganizationMembership,
    Space,
)
from .views import _get_user_organizations


def _resolve_space_access(request, space_id):
    organizations = _get_user_organizations(request)
    space = get_object_or_404(Space, id=space_id, organization__in=organizations, key="custom_inventory")

    if request.user.is_superuser:
        return space, True, None

    membership = OrganizationMembership.objects.filter(
        user=request.user,
        organization=space.organization,
        is_active=True,
        organization__is_active=True,
    ).first()
    if not membership:
        return None, False, None

    is_owner = membership.role == OrganizationMembership.Role.OWNER
    if not is_owner and not membership.accessible_spaces.filter(id=space.id).exists():
        return None, False, membership

    return space, is_owner, membership


def build_inventory_space_context(request, card, is_owner, membership):
    tab = request.GET.get("tab", "dashboard")
    stats = inventory_dashboard_stats(card)
    cat_stats = category_stats(card)

    products = (
        InventoryProduct.objects.filter(space=card)
        .select_related("category")
        .order_by("category__name", "name")
    )
    categories = InventoryCategory.objects.filter(space=card).order_by("name")
    buyers = InventoryBuyer.objects.filter(space=card).order_by("-created_at")
    invoices = (
        InventoryInvoice.objects.filter(space=card)
        .select_related("buyer", "created_by")
        .prefetch_related("lines")
        .order_by("-invoice_date", "-created_at")[:100]
    )
    recent_movements = (
        InventoryStockMovement.objects.filter(product__space=card)
        .select_related("product", "created_by")
        .order_by("-created_at")[:25]
    )

    product_filter = request.GET.get("product_q", "").strip()
    category_filter = request.GET.get("category_id", "").strip()
    if product_filter:
        products = products.filter(
            Q(name__icontains=product_filter) | Q(sku__icontains=product_filter)
        )
    if category_filter.isdigit():
        products = products.filter(category_id=int(category_filter))

    return {
        "card": card,
        "is_owner": is_owner,
        "active_org": card.organization,
        "active_tab": tab,
        "stats": stats,
        "category_stats": cat_stats,
        "categories": categories,
        "products": products,
        "buyers": buyers,
        "invoices": invoices,
        "recent_movements": recent_movements,
        "product_filter": product_filter,
        "category_filter": category_filter,
    }


@login_required
@require_POST
def add_inventory_category(request, space_id):
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        return HttpResponseForbidden("Access denied.")

    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    if not name:
        messages.error(request, "Category name is required.")
        return redirect("inventory-detail", inventory_id=space.id)

    try:
        InventoryCategory.objects.create(
            organization=space.organization,
            space=space,
            name=name,
            description=description,
        )
        messages.success(request, f"Category '{name}' added.")
    except Exception as e:
        messages.error(request, f"Error adding category: {e}")

    return redirect(f"/dashboard/inventory/{space.id}/?tab=categories")


@login_required
def delete_inventory_category(request, category_id):
    organizations = _get_user_organizations(request)
    category = get_object_or_404(
        InventoryCategory,
        id=category_id,
        organization__in=organizations,
        space__key="custom_inventory",
    )
    space = category.space
    name = category.name
    category.delete()
    messages.success(request, f"Category '{name}' deleted.")
    return redirect(f"/dashboard/inventory/{space.id}/?tab=categories")


@login_required
@require_POST
def add_inventory_product(request, space_id):
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        return HttpResponseForbidden("Access denied.")

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Product name is required.")
        return redirect(f"/dashboard/inventory/{space.id}/?tab=products")

    category_id = request.POST.get("category_id", "").strip()
    category = None
    if category_id.isdigit():
        category = InventoryCategory.objects.filter(space=space, id=int(category_id)).first()

    try:
        InventoryProduct.objects.create(
            organization=space.organization,
            space=space,
            category=category,
            name=name,
            sku=request.POST.get("sku", "").strip(),
            description=request.POST.get("description", "").strip(),
            unit_price=Decimal(request.POST.get("unit_price", "0") or "0"),
            quantity=int(request.POST.get("quantity", "0") or 0),
            low_stock_threshold=int(request.POST.get("low_stock_threshold", "5") or 5),
        )
        messages.success(request, f"Product '{name}' added.")
    except (InvalidOperation, ValueError) as e:
        messages.error(request, f"Invalid product data: {e}")
    except Exception as e:
        messages.error(request, f"Error adding product: {e}")

    return redirect(f"/dashboard/inventory/{space.id}/?tab=products")


@login_required
def edit_inventory_product(request, product_id):
    organizations = _get_user_organizations(request)
    product = get_object_or_404(
        InventoryProduct,
        id=product_id,
        organization__in=organizations,
        space__key="custom_inventory",
    )
    space = product.space

    if request.method == "GET":
        return JsonResponse({
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "description": product.description,
            "category_id": product.category_id or "",
            "unit_price": str(product.unit_price),
            "quantity": product.quantity,
            "low_stock_threshold": product.low_stock_threshold,
            "is_active": product.is_active,
        })

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Product name is required.")
        return redirect(f"/dashboard/inventory/{space.id}/?tab=products")

    category_id = request.POST.get("category_id", "").strip()
    category = None
    if category_id.isdigit():
        category = InventoryCategory.objects.filter(space=space, id=int(category_id)).first()

    try:
        product.name = name
        product.sku = request.POST.get("sku", "").strip()
        product.description = request.POST.get("description", "").strip()
        product.category = category
        product.unit_price = Decimal(request.POST.get("unit_price", "0") or "0")
        product.quantity = int(request.POST.get("quantity", "0") or 0)
        product.low_stock_threshold = int(request.POST.get("low_stock_threshold", "5") or 5)
        product.is_active = request.POST.get("is_active") in ("1", "on", "true")
        product.save()
        messages.success(request, f"Product '{name}' updated.")
    except (InvalidOperation, ValueError) as e:
        messages.error(request, f"Invalid product data: {e}")

    return redirect(f"/dashboard/inventory/{space.id}/?tab=products")


@login_required
def delete_inventory_product(request, product_id):
    organizations = _get_user_organizations(request)
    product = get_object_or_404(
        InventoryProduct,
        id=product_id,
        organization__in=organizations,
        space__key="custom_inventory",
    )
    space = product.space
    name = product.name
    product.delete()
    messages.success(request, f"Product '{name}' deleted.")
    return redirect(f"/dashboard/inventory/{space.id}/?tab=products")


@login_required
@require_POST
def adjust_inventory_stock(request, product_id):
    organizations = _get_user_organizations(request)
    product = get_object_or_404(
        InventoryProduct,
        id=product_id,
        organization__in=organizations,
        space__key="custom_inventory",
    )
    space = product.space

    adjustment = int(request.POST.get("adjustment", "0") or 0)
    movement_type = request.POST.get("movement_type", InventoryStockMovement.MovementType.ADJUSTMENT)
    notes = request.POST.get("notes", "").strip()

    if adjustment == 0:
        messages.error(request, "Adjustment quantity cannot be zero.")
        return redirect(f"/dashboard/inventory/{space.id}/?tab=products")

    if movement_type not in InventoryStockMovement.MovementType.values:
        movement_type = InventoryStockMovement.MovementType.ADJUSTMENT

    if product.quantity + adjustment < 0:
        messages.error(request, "Stock cannot go below zero.")
        return redirect(f"/dashboard/inventory/{space.id}/?tab=products")

    record_stock_movement(
        product,
        movement_type,
        adjustment,
        notes=notes,
        user=request.user,
    )
    messages.success(request, f"Stock updated for '{product.name}'.")
    return redirect(f"/dashboard/inventory/{space.id}/?tab=products")


@login_required
@require_POST
def add_inventory_buyer(request, space_id):
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        return HttpResponseForbidden("Access denied.")

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Buyer name is required.")
        return redirect(f"/dashboard/inventory/{space.id}/?tab=buyers")

    InventoryBuyer.objects.create(
        organization=space.organization,
        space=space,
        name=name,
        phone=request.POST.get("phone", "").strip(),
        email=request.POST.get("email", "").strip(),
        address=request.POST.get("address", "").strip(),
        notes=request.POST.get("notes", "").strip(),
    )
    messages.success(request, f"Buyer '{name}' added.")
    return redirect(f"/dashboard/inventory/{space.id}/?tab=buyers")


@login_required
def delete_inventory_buyer(request, buyer_id):
    organizations = _get_user_organizations(request)
    buyer = get_object_or_404(
        InventoryBuyer,
        id=buyer_id,
        organization__in=organizations,
        space__key="custom_inventory",
    )
    space = buyer.space
    name = buyer.name
    buyer.delete()
    messages.success(request, f"Buyer '{name}' removed.")
    return redirect(f"/dashboard/inventory/{space.id}/?tab=buyers")


@login_required
@require_POST
def add_inventory_invoice(request, space_id):
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        return HttpResponseForbidden("Access denied.")

    buyer_name = request.POST.get("buyer_name", "").strip()
    if not buyer_name:
        messages.error(request, "Buyer name is required.")
        return redirect(f"/dashboard/inventory/{space.id}/?tab=invoices")

    buyer_phone = request.POST.get("buyer_phone", "").strip()
    buyer_email = request.POST.get("buyer_email", "").strip()
    buyer_address = request.POST.get("buyer_address", "").strip()
    buyer_id = request.POST.get("buyer_id", "").strip()
    invoice_date_str = request.POST.get("invoice_date", "").strip()
    payment_method = request.POST.get("payment_method", InventoryInvoice.PaymentMethod.CASH)
    notes = request.POST.get("notes", "").strip()

    try:
        invoice_date = (
            dt_parse.strptime(invoice_date_str, "%Y-%m-%d").date()
            if invoice_date_str
            else timezone.localdate()
        )
    except ValueError:
        invoice_date = timezone.localdate()

    descriptions = request.POST.getlist("line_description")
    quantities = request.POST.getlist("line_quantity")
    unit_prices = request.POST.getlist("line_unit_price")
    product_ids = request.POST.getlist("line_product_id")

    if not descriptions:
        messages.error(request, "Add at least one line item.")
        return redirect(f"/dashboard/inventory/{space.id}/?tab=invoices")

    buyer = None
    if buyer_id.isdigit():
        buyer = InventoryBuyer.objects.filter(space=space, id=int(buyer_id)).first()
        if buyer and not buyer_address:
            buyer_address = buyer.address
    if not buyer:
        buyer = get_or_create_buyer(
            space, space.organization, buyer_name, buyer_phone, buyer_email
        )
        if buyer_address and not buyer.address:
            buyer.address = buyer_address
            buyer.save(update_fields=["address"])

    try:
        with transaction.atomic():
            invoice = InventoryInvoice.objects.create(
                organization=space.organization,
                space=space,
                invoice_number=generate_invoice_number(space.organization),
                buyer=buyer,
                buyer_name=buyer_name,
                buyer_phone=buyer_phone,
                buyer_email=buyer_email,
                buyer_address=buyer_address,
                invoice_date=invoice_date,
                status=InventoryInvoice.Status.COMPLETED,
                payment_method=payment_method,
                notes=notes,
                created_by=request.user,
            )

            for i, desc in enumerate(descriptions):
                desc = desc.strip()
                if not desc:
                    continue
                try:
                    qty = int(quantities[i] if i < len(quantities) else 1)
                    price = Decimal(unit_prices[i] if i < len(unit_prices) else "0")
                except (InvalidOperation, ValueError, IndexError):
                    continue
                if qty <= 0:
                    continue

                product = None
                pid = product_ids[i] if i < len(product_ids) else ""
                if str(pid).isdigit():
                    product = InventoryProduct.objects.filter(space=space, id=int(pid)).first()

                InventoryInvoiceLine.objects.create(
                    invoice=invoice,
                    product=product,
                    description=desc,
                    quantity=qty,
                    unit_price=price,
                )

            if not invoice.lines.exists():
                invoice.delete()
                messages.error(request, "No valid line items.")
                return redirect(f"/dashboard/inventory/{space.id}/?tab=invoices")

            recalculate_invoice_totals(invoice)
            apply_invoice_stock_deductions(invoice, user=request.user)

        messages.success(request, f"Invoice {invoice.invoice_number} created.")
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"Error creating invoice: {e}")

    return redirect(f"/dashboard/inventory/{space.id}/?tab=invoices")


@login_required
def delete_inventory_invoice(request, invoice_id):
    organizations = _get_user_organizations(request)
    invoice = get_object_or_404(
        InventoryInvoice,
        id=invoice_id,
        organization__in=organizations,
        space__key="custom_inventory",
    )
    space = invoice.space
    number = invoice.invoice_number
    invoice.delete()
    messages.success(request, f"Invoice {number} deleted.")
    return redirect(f"/dashboard/inventory/{space.id}/?tab=invoices")


@login_required
def inventory_invoice_pdf(request, invoice_id):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from .inventory_pdf import render_inventory_invoice_pdf

    organizations = _get_user_organizations(request)
    invoice = get_object_or_404(
        InventoryInvoice.objects.select_related("space").prefetch_related("lines"),
        id=invoice_id,
        organization__in=organizations,
        space__key="custom_inventory",
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="invoice-{invoice.invoice_number}.pdf"'

    pdf = canvas.Canvas(response, pagesize=letter)
    render_inventory_invoice_pdf(pdf, invoice)
    pdf.save()
    return response


@login_required
def export_inventory_report(request, space_id):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from .inventory_crm import inventory_dashboard_stats
    from .inventory_pdf import render_inventory_report_pdf

    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        return HttpResponseForbidden("Access denied.")

    report_type = request.GET.get("type", "inventory")
    export_fmt = request.GET.get("export", "csv")
    stats = inventory_dashboard_stats(space)
    safe_name = space.label.replace(" ", "-").lower()[:30]

    if export_fmt == "pdf":
        response = HttpResponse(content_type="application/pdf")
        filename = f"{safe_name}-{'sales' if report_type == 'sales' else 'stock'}-report.pdf"
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        pdf = canvas.Canvas(response, pagesize=letter)
        render_inventory_report_pdf(pdf, space, report_type, stats)
        pdf.save()
        return response

    if report_type == "sales":
        rows = [
            [space.label, "Sales Report"],
            ["Business Address", space.business_address.replace("\n", ", ") if space.business_address else ""],
            ["Phone", space.business_phone],
            ["Email", space.business_email],
            [],
            ["Invoice #", "Date", "Buyer", "Buyer Phone", "Payment Method", "Total", "Status"],
        ]
        for inv in InventoryInvoice.objects.filter(space=space).order_by("-invoice_date"):
            rows.append([
                inv.invoice_number,
                inv.invoice_date.strftime("%Y-%m-%d"),
                inv.buyer_name,
                inv.buyer_phone,
                inv.get_payment_method_display(),
                f"{inv.total:.2f}",
                inv.get_status_display(),
            ])
        rows.extend([[], ["Total Invoices", str(stats["invoice_count"])], ["Month Sales", f"{stats['sales_month_total']:.2f}"]])
        filename = f"{safe_name}-sales-report"
    else:
        rows = [
            [space.label, "Inventory Stock Report"],
            ["Business Address", space.business_address.replace("\n", ", ") if space.business_address else ""],
            ["Phone", space.business_phone],
            ["Email", space.business_email],
            [],
            ["Product", "SKU", "Category", "Unit Price", "Quantity", "Total Value", "Low Stock Alert"],
        ]
        for p in InventoryProduct.objects.filter(space=space).select_related("category").order_by("name"):
            rows.append([
                p.name,
                p.sku,
                p.category.name if p.category else "",
                f"{p.unit_price:.2f}",
                str(p.quantity),
                f"{p.unit_price * p.quantity:.2f}",
                "YES" if p.quantity <= p.low_stock_threshold else "NO",
            ])
        rows.extend([
            [],
            ["Total Products", str(stats["total_products"])],
            ["Total Units", str(stats["total_units"])],
            ["Total Inventory Value", f"{stats['total_inventory_value']:.2f}"],
        ])
        filename = f"{safe_name}-stock-report"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)
    for row in rows:
        writer.writerow(row)
    return response
