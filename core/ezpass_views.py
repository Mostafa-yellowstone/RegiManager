"""Views and business logic for the master E-ZPass space."""

import csv
from datetime import datetime as dt_parse
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum, Q, F
from django.http import Http404, HttpResponse, JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .http import deny_access
from .models import (
    EZPassBatch,
    EZPassTag,
    InventoryBuyer,
    InventoryInvoice,
    InventoryInvoiceLine,
    InventoryProduct,
    InventoryStockMovement,
    OrganizationMembership,
    Space,
)
from .inventory_crm import (
    generate_invoice_number,
    get_or_create_buyer,
    recalculate_invoice_totals,
    record_stock_movement,
)
from .inventory_spaces import is_inventory_space
from .inventory_views import (
    _resolve_space_access,
    build_inventory_space_context,
)
from .ezpass_pdf import render_ezpass_receipt_pdf
from .views import _get_user_organizations


def _owned_ezpass_tag(request, tag_id):
    organizations = _get_user_organizations(request)
    tag = get_object_or_404(
        EZPassTag.objects.select_related("space", "batch", "invoice", "assigned_by"),
        id=tag_id,
        organization__in=organizations,
    )
    return tag


def _ensure_ezpass_products_in_sync(space):
    """
    Ensures that standard E-ZPass products exist in InventoryProduct
    and their quantities reflect current in-stock EZPassTag records.
    """
    has_tags = EZPassTag.objects.filter(space=space).exists()
    if not has_tags:
        return

    interior_count = EZPassTag.objects.filter(
        space=space, tag_type=EZPassTag.TagType.INTERIOR, status=EZPassTag.Status.IN_STOCK
    ).count()
    exterior_count = EZPassTag.objects.filter(
        space=space, tag_type=EZPassTag.TagType.EXTERIOR, status=EZPassTag.Status.IN_STOCK
    ).count()

    interior_prod = InventoryProduct.objects.filter(
        organization=space.organization,
        space=space,
        name="Interior Tag",
    ).first()
    if not interior_prod:
        interior_prod = InventoryProduct.objects.create(
            organization=space.organization,
            space=space,
            name="Interior Tag",
            sku="EZP-INT",
            description="Standard E-ZPass Windshield Transponder Tag",
            unit_price=Decimal("35.00"),
            cost_price=Decimal("25.00"),
            quantity=interior_count,
            low_stock_threshold=10,
        )
    elif interior_prod.quantity != interior_count:
        interior_prod.quantity = interior_count
        interior_prod.save(update_fields=["quantity"])

    exterior_prod = InventoryProduct.objects.filter(
        organization=space.organization,
        space=space,
        name="Exterior Tag",
    ).first()
    if not exterior_prod:
        exterior_prod = InventoryProduct.objects.create(
            organization=space.organization,
            space=space,
            name="Exterior Tag",
            sku="EZP-EXT",
            description="License Plate Mount E-ZPass Transponder Tag",
            unit_price=Decimal("40.00"),
            cost_price=Decimal("28.00"),
            quantity=exterior_count,
            low_stock_threshold=5,
        )
    elif exterior_prod.quantity != exterior_count:
        exterior_prod.quantity = exterior_count
        exterior_prod.save(update_fields=["quantity"])


def build_ezpass_space_context(request, card, is_owner, membership):
    """Builds the comprehensive context for the master E-ZPass operation hub."""
    _ensure_ezpass_products_in_sync(card)

    tags_qs = (
        EZPassTag.objects.filter(space=card)
        .select_related("batch", "assigned_by", "invoice")
        .order_by("-assigned_at", "-created_at")
    )
    all_tags = list(tags_qs)

    batches_qs = (
        EZPassBatch.objects.filter(space=card)
        .select_related("created_by")
        .prefetch_related("tags")
        .order_by("-received_date", "-created_at")
    )
    batches = list(batches_qs)

    total_tags = len(all_tags)
    in_stock_tags = [t for t in all_tags if t.status == EZPassTag.Status.IN_STOCK]
    sold_tags = [t for t in all_tags if t.status == EZPassTag.Status.SOLD]
    defective_tags = [t for t in all_tags if t.status == EZPassTag.Status.DEFECTIVE]
    lost_tags = [t for t in all_tags if t.status == EZPassTag.Status.LOST]

    in_stock_count = len(in_stock_tags)
    sold_count = len(sold_tags)
    defective_count = len(defective_tags)
    lost_count = len(lost_tags)

    # Type breakdown
    interior_in_stock = sum(1 for t in in_stock_tags if t.tag_type == EZPassTag.TagType.INTERIOR)
    exterior_in_stock = sum(1 for t in in_stock_tags if t.tag_type == EZPassTag.TagType.EXTERIOR)
    commercial_in_stock = sum(1 for t in in_stock_tags if t.tag_type == EZPassTag.TagType.COMMERCIAL)
    motorcycle_in_stock = sum(1 for t in in_stock_tags if t.tag_type == EZPassTag.TagType.MOTORCYCLE)

    # Low stock logic
    low_stock_threshold = 10
    is_low_stock = in_stock_count <= low_stock_threshold
    is_critical_stock = in_stock_count <= 3
    is_out_of_stock = in_stock_count == 0

    # Profits & Financial calculations
    total_stock_value = sum((t.cost_price for t in in_stock_tags), Decimal("0.00"))
    total_retail_stock_value = sum((t.retail_price for t in in_stock_tags), Decimal("0.00"))
    total_gross_revenue = sum((t.retail_price for t in sold_tags), Decimal("0.00"))
    total_cogs = sum((t.cost_price for t in sold_tags), Decimal("0.00"))
    net_profit = total_gross_revenue - total_cogs
    profit_margin = (
        (net_profit / total_gross_revenue * 100)
        if total_gross_revenue > 0
        else Decimal("0.0")
    )
    avg_profit_per_tag = (
        (net_profit / Decimal(sold_count))
        if sold_count > 0
        else Decimal("0.0")
    )

    # Today & Month metrics
    today = timezone.localdate()
    today_sold = [t for t in sold_tags if t.assigned_at and t.assigned_at.date() == today]
    today_sold_count = len(today_sold)
    today_revenue = sum((t.retail_price for t in today_sold), Decimal("0.00"))
    today_profit = sum((t.profit for t in today_sold), Decimal("0.00"))

    month_start = today.replace(day=1)
    month_sold = [t for t in sold_tags if t.assigned_at and t.assigned_at.date() >= month_start]
    month_sold_count = len(month_sold)
    month_revenue = sum((t.retail_price for t in month_sold), Decimal("0.00"))
    month_profit = sum((t.profit for t in month_sold), Decimal("0.00"))

    # Also build standard inventory context so tabs (Products, Reports, Documents) work
    inv_context = build_inventory_space_context(request, card, is_owner, membership)
    # Sync total inventory value in stats to match retail stock
    if inv_context.get("stats"):
        inv_context["stats"]["total_units"] = in_stock_count
        if total_retail_stock_value > 0:
            inv_context["stats"]["total_inventory_value"] = total_retail_stock_value
        inv_context["stats"]["low_stock_count"] = 1 if is_low_stock else 0

    return {
        **inv_context,
        "is_ezpass_master": True,
        "tags": all_tags,
        "available_tags": in_stock_tags,
        "batches": batches,
        "total_tags": total_tags,
        "in_stock_count": in_stock_count,
        "sold_count": sold_count,
        "defective_count": defective_count,
        "lost_count": lost_count,
        "interior_in_stock": interior_in_stock,
        "exterior_in_stock": exterior_in_stock,
        "commercial_in_stock": commercial_in_stock,
        "motorcycle_in_stock": motorcycle_in_stock,
        "low_stock_threshold": low_stock_threshold,
        "is_low_stock": is_low_stock,
        "is_critical_stock": is_critical_stock,
        "is_out_of_stock": is_out_of_stock,
        "total_stock_value": total_stock_value,
        "total_retail_stock_value": total_retail_stock_value,
        "total_gross_revenue": total_gross_revenue,
        "total_cogs": total_cogs,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "avg_profit_per_tag": avg_profit_per_tag,
        "today_sold_count": today_sold_count,
        "today_revenue": today_revenue,
        "today_profit": today_profit,
        "month_sold_count": month_sold_count,
        "month_revenue": month_revenue,
        "month_profit": month_profit,
    }


@login_required
@require_POST
def issue_ezpass_tag(request, space_id):
    """Issues/sells an E-ZPass tag to a customer, creates an invoice, and records stock."""
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        deny_access("Access denied.")

    tag_id = request.POST.get("tag_id", "").strip()
    tag_number = request.POST.get("tag_number", "").strip()

    tag = None
    if tag_id.isdigit():
        tag = EZPassTag.objects.filter(space=space, id=int(tag_id)).first()
    elif tag_number:
        tag = EZPassTag.objects.filter(space=space, tag_number=tag_number).first()

    if not tag:
        messages.error(request, "Selected E-ZPass tag was not found.")
        return redirect("inventory-detail", inventory_id=space.id)

    if tag.status == EZPassTag.Status.SOLD:
        messages.error(request, f"Tag #{tag.tag_number} is already marked as SOLD.")
        return redirect("inventory-detail", inventory_id=space.id)

    customer_name = request.POST.get("customer_name", "").strip()
    if not customer_name:
        messages.error(request, "Customer name is required to register an E-ZPass tag.")
        return redirect("inventory-detail", inventory_id=space.id)

    customer_phone = request.POST.get("customer_phone", "").strip()
    customer_email = request.POST.get("customer_email", "").strip()
    customer_address = request.POST.get("customer_address", "").strip()
    plate_number = request.POST.get("plate_number", "").strip().upper()
    plate_state = request.POST.get("plate_state", "NY").strip().upper() or "NY"
    vehicle_year = request.POST.get("vehicle_year", "").strip()
    vehicle_make = request.POST.get("vehicle_make", "").strip()
    vehicle_model = request.POST.get("vehicle_model", "").strip()
    vehicle_vin = request.POST.get("vehicle_vin", "").strip().upper()
    payment_method = request.POST.get("payment_method", EZPassTag.PaymentMethod.CASH)
    notes = request.POST.get("notes", "").strip()

    try:
        toll_deposit = Decimal(request.POST.get("toll_deposit", "25.00") or "25.00")
        convenience_fee = Decimal(request.POST.get("convenience_fee", "10.00") or "10.00")
        retail_price = toll_deposit + convenience_fee
    except (InvalidOperation, ValueError):
        toll_deposit = Decimal("25.00")
        convenience_fee = Decimal("10.00")
        retail_price = Decimal("35.00")

    try:
        with transaction.atomic():
            # 1. Update tag
            tag.status = EZPassTag.Status.SOLD
            tag.customer_name = customer_name
            tag.customer_phone = customer_phone
            tag.customer_email = customer_email
            tag.customer_address = customer_address
            tag.plate_number = plate_number
            tag.plate_state = plate_state
            tag.vehicle_year = vehicle_year
            tag.vehicle_make = vehicle_make
            tag.vehicle_model = vehicle_model
            tag.vehicle_vin = vehicle_vin
            tag.toll_deposit = toll_deposit
            tag.convenience_fee = convenience_fee
            tag.retail_price = retail_price
            tag.payment_method = payment_method
            tag.assigned_at = timezone.now()
            tag.assigned_by = request.user
            if notes:
                tag.notes = f"{tag.notes}\n{notes}".strip()

            # 2. Match or create buyer
            buyer = get_or_create_buyer(
                space, space.organization, customer_name, customer_phone, customer_email
            )
            if customer_address and not buyer.address:
                buyer.address = customer_address
                buyer.save(update_fields=["address"])

            # 3. Create invoice for accounting
            invoice = InventoryInvoice.objects.create(
                organization=space.organization,
                space=space,
                invoice_number=generate_invoice_number(space.organization),
                buyer=buyer,
                buyer_name=customer_name,
                buyer_phone=customer_phone,
                buyer_email=customer_email,
                buyer_address=customer_address,
                invoice_date=timezone.localdate(),
                status=InventoryInvoice.Status.COMPLETED,
                payment_method=payment_method,
                notes=f"E-ZPass On-The-Go Tag #{tag.tag_number} issued for vehicle plate {plate_state} {plate_number}",
                subtotal=retail_price,
                sales_tax=Decimal("0.00"),
                total=retail_price,
                created_by=request.user,
            )

            # Itemized line
            InventoryInvoiceLine.objects.create(
                invoice=invoice,
                description=f"E-ZPass Transponder #{tag.tag_number} ({tag.get_tag_type_display()}) - Plate: {plate_state} {plate_number}",
                quantity=1,
                unit_price=retail_price,
                line_total=retail_price,
            )

            tag.invoice = invoice
            tag.save()

            # Adjust matching InventoryProduct quantity
            matching_prod = InventoryProduct.objects.filter(
                space=space,
                name__icontains="interior" if tag.tag_type == EZPassTag.TagType.INTERIOR else "exterior"
            ).first()
            if matching_prod and matching_prod.quantity > 0:
                matching_prod.quantity -= 1
                matching_prod.save(update_fields=["quantity"])
                record_stock_movement(
                    matching_prod,
                    InventoryStockMovement.MovementType.SALE,
                    -1,
                    reference=invoice.invoice_number,
                    notes=f"Tag #{tag.tag_number} issued to {customer_name}",
                    user=request.user,
                )

        messages.success(
            request,
            f"E-ZPass Tag #{tag.tag_number} successfully issued to {customer_name}! Invoice #{invoice.invoice_number} created."
        )

        if request.POST.get("print_receipt") == "1":
            return redirect("ezpass-receipt-view", tag_id=tag.id)

    except Exception as e:
        messages.error(request, f"Error issuing E-ZPass tag: {e}")

    return redirect("inventory-detail", inventory_id=space.id)


@login_required
@require_POST
def batch_intake_ezpass(request, space_id):
    """Receives a shipment / batch of E-ZPass tags and saves inventory documents (packing slips, invoices)."""
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        deny_access("Access denied.")

    supplier_name = request.POST.get("supplier_name", "").strip() or "NYS Thruway Authority / E-ZPass NY"
    batch_number = request.POST.get("batch_number", "").strip() or f"EZB-{timezone.now().strftime('%Y%m%d%H%M')}"
    received_date_str = request.POST.get("received_date", "").strip()
    tag_type = request.POST.get("tag_type", EZPassTag.TagType.INTERIOR)
    notes = request.POST.get("notes", "").strip()

    try:
        received_date = (
            dt_parse.strptime(received_date_str, "%Y-%m-%d").date()
            if received_date_str
            else timezone.localdate()
        )
    except ValueError:
        received_date = timezone.localdate()

    try:
        unit_cost = Decimal(request.POST.get("unit_cost", "25.00") or "25.00")
        retail_price = Decimal(request.POST.get("retail_price", "35.00") or "35.00")
        toll_deposit = Decimal(request.POST.get("toll_deposit", "25.00") or "25.00")
        convenience_fee = retail_price - toll_deposit
    except (InvalidOperation, ValueError):
        unit_cost = Decimal("25.00")
        retail_price = Decimal("35.00")
        toll_deposit = Decimal("25.00")
        convenience_fee = Decimal("10.00")

    # Document upload for what we received as inventory
    uploaded_doc = request.FILES.get("document")
    doc_name = uploaded_doc.name if uploaded_doc else ""

    # Parse tag numbers
    entry_mode = request.POST.get("entry_mode", "range")
    tag_numbers = []

    if entry_mode == "range":
        tag_prefix = request.POST.get("tag_prefix", "").strip()
        range_start_str = request.POST.get("range_start", "").strip()
        range_end_str = request.POST.get("range_end", "").strip()

        if not range_start_str or not range_end_str:
            messages.error(request, "Start and end numbers are required for range intake.")
            return redirect("inventory-detail", inventory_id=space.id)

        try:
            start_num = int(range_start_str)
            end_num = int(range_end_str)
            if end_num < start_num:
                messages.error(request, "Range end number must be greater than or equal to start number.")
                return redirect("inventory-detail", inventory_id=space.id)
            if (end_num - start_num + 1) > 250:
                messages.error(request, "Maximum 250 tags per batch intake.")
                return redirect("inventory-detail", inventory_id=space.id)

            pad_len = max(len(range_start_str), len(range_end_str))
            for n in range(start_num, end_num + 1):
                num_str = str(n).zfill(pad_len)
                tag_numbers.append(f"{tag_prefix}{num_str}")
        except ValueError:
            messages.error(request, "Start and end numbers must be integers.")
            return redirect("inventory-detail", inventory_id=space.id)

    else:
        # Paste list of tag numbers
        raw_list = request.POST.get("tag_list", "")
        for line in raw_list.replace(",", "\n").splitlines():
            clean = line.strip()
            if clean and clean not in tag_numbers:
                tag_numbers.append(clean)

    if not tag_numbers:
        messages.error(request, "No valid tag numbers provided.")
        return redirect("inventory-detail", inventory_id=space.id)

    total_cost = unit_cost * len(tag_numbers)

    try:
        with transaction.atomic():
            batch = EZPassBatch.objects.create(
                organization=space.organization,
                space=space,
                batch_number=batch_number,
                supplier_name=supplier_name,
                received_date=received_date,
                quantity=len(tag_numbers),
                unit_cost=unit_cost,
                total_cost=total_cost,
                tag_prefix=request.POST.get("tag_prefix", "").strip(),
                tag_range_start=tag_numbers[0] if tag_numbers else "",
                tag_range_end=tag_numbers[-1] if tag_numbers else "",
                document=uploaded_doc,
                document_name=doc_name,
                notes=notes,
                created_by=request.user,
            )

            created_count = 0
            skipped_count = 0
            for t_num in tag_numbers:
                if EZPassTag.objects.filter(space=space, tag_number=t_num).exists():
                    skipped_count += 1
                    continue
                EZPassTag.objects.create(
                    organization=space.organization,
                    space=space,
                    batch=batch,
                    tag_number=t_num,
                    tag_type=tag_type,
                    status=EZPassTag.Status.IN_STOCK,
                    cost_price=unit_cost,
                    retail_price=retail_price,
                    toll_deposit=toll_deposit,
                    convenience_fee=convenience_fee,
                )
                created_count += 1

            _ensure_ezpass_products_in_sync(space)

        doc_msg = f" with attached manifest '{doc_name}'" if doc_name else ""
        skip_msg = f" ({skipped_count} skipped because already registered)" if skipped_count else ""
        messages.success(
            request,
            f"Successfully recorded Batch {batch.batch_number}: {created_count} tags added to inventory{doc_msg}{skip_msg}!"
        )
    except Exception as e:
        messages.error(request, f"Error receiving batch: {e}")

    return redirect("inventory-detail", inventory_id=space.id)


@login_required
@require_POST
def add_single_ezpass_tag(request, space_id):
    """Adds a single E-ZPass tag to inventory."""
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        deny_access("Access denied.")

    tag_number = request.POST.get("tag_number", "").strip()
    if not tag_number:
        messages.error(request, "Tag number is required.")
        return redirect("inventory-detail", inventory_id=space.id)

    if EZPassTag.objects.filter(space=space, tag_number=tag_number).exists():
        messages.error(request, f"Tag #{tag_number} already exists in this space.")
        return redirect("inventory-detail", inventory_id=space.id)

    tag_type = request.POST.get("tag_type", EZPassTag.TagType.INTERIOR)
    try:
        cost_price = Decimal(request.POST.get("cost_price", "25.00") or "25.00")
        retail_price = Decimal(request.POST.get("retail_price", "35.00") or "35.00")
        toll_deposit = Decimal(request.POST.get("toll_deposit", "25.00") or "25.00")
        convenience_fee = retail_price - toll_deposit
    except (InvalidOperation, ValueError):
        cost_price = Decimal("25.00")
        retail_price = Decimal("35.00")
        toll_deposit = Decimal("25.00")
        convenience_fee = Decimal("10.00")

    try:
        EZPassTag.objects.create(
            organization=space.organization,
            space=space,
            tag_number=tag_number,
            tag_type=tag_type,
            status=EZPassTag.Status.IN_STOCK,
            cost_price=cost_price,
            retail_price=retail_price,
            toll_deposit=toll_deposit,
            convenience_fee=convenience_fee,
            notes=request.POST.get("notes", "").strip(),
        )
        _ensure_ezpass_products_in_sync(space)
        messages.success(request, f"Tag #{tag_number} added to in-stock inventory.")
    except Exception as e:
        messages.error(request, f"Error adding tag: {e}")

    return redirect("inventory-detail", inventory_id=space.id)


@login_required
@require_POST
def update_ezpass_tag_status(request, tag_id):
    """Updates the status of an E-ZPass tag (e.g. mark defective, lost, or back to in_stock)."""
    tag = _owned_ezpass_tag(request, tag_id)
    space = tag.space

    new_status = request.POST.get("status", "").strip()
    reason = request.POST.get("reason", "").strip()

    if new_status not in EZPassTag.Status.values:
        messages.error(request, "Invalid status choice.")
        return redirect("inventory-detail", inventory_id=space.id)

    old_status_label = tag.get_status_display()
    tag.status = new_status
    if reason:
        tag.notes = f"{tag.notes}\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] Status -> {tag.get_status_display()}: {reason}".strip()
    tag.save()
    _ensure_ezpass_products_in_sync(space)

    messages.success(request, f"Tag #{tag.tag_number} status changed from {old_status_label} to {tag.get_status_display()}.")
    return redirect("inventory-detail", inventory_id=space.id)


@login_required
def delete_ezpass_tag(request, tag_id):
    """Deletes an E-ZPass tag from inventory (manager/owner only)."""
    tag = _owned_ezpass_tag(request, tag_id)
    space = tag.space
    t_num = tag.tag_number
    tag.delete()
    _ensure_ezpass_products_in_sync(space)
    messages.success(request, f"Tag #{t_num} deleted from inventory.")
    return redirect("inventory-detail", inventory_id=space.id)


@login_required
def ezpass_receipt_view(request, tag_id):
    """Printable, beautiful HTML receipt and driver registration instructions handout."""
    tag = _owned_ezpass_tag(request, tag_id)
    return render(
        request,
        "core/ezpass_receipt.html",
        {
            "tag": tag,
            "space": tag.space,
            "organization": tag.space.organization,
        },
    )


@login_required
def ezpass_receipt_pdf(request, tag_id):
    """Downloads an official PDF receipt for an E-ZPass issuance."""
    tag = _owned_ezpass_tag(request, tag_id)

    response = HttpResponse(content_type="application/pdf")
    filename = f"ezpass-receipt-{tag.tag_number}.pdf"
    response["Content-Disposition"] = f'inline; filename="{filename}"'

    pdf = canvas.Canvas(response, pagesize=letter)
    render_ezpass_receipt_pdf(pdf, tag)
    pdf.save()
    return response


@login_required
def ezpass_batch_document_download(request, batch_id):
    """Downloads the uploaded supplier manifest or invoice document for an E-ZPass intake batch."""
    organizations = _get_user_organizations(request)
    batch = get_object_or_404(
        EZPassBatch.objects.select_related("space"),
        id=batch_id,
        organization__in=organizations,
    )
    if not batch.document:
        raise Http404("No document attached to this batch.")

    return FileResponse(batch.document.open("rb"), as_attachment=True, filename=batch.document_name or f"manifest-{batch.batch_number}.pdf")


@login_required
def delete_ezpass_batch(request, batch_id):
    """Deletes an intake batch record without deleting sold tags."""
    organizations = _get_user_organizations(request)
    batch = get_object_or_404(
        EZPassBatch.objects.select_related("space"),
        id=batch_id,
        organization__in=organizations,
    )
    space = batch.space
    b_num = batch.batch_number
    batch.delete()
    messages.success(request, f"Batch record {b_num} removed.")
    return redirect("inventory-detail", inventory_id=space.id)


@login_required
def export_ezpass_csv(request, space_id):
    """Exports full E-ZPass inventory, trackers, and profit breakdown to CSV."""
    space, is_owner, membership = _resolve_space_access(request, space_id)
    if not space:
        deny_access("Access denied.")

    response = HttpResponse(content_type="text/csv")
    filename = f"ezpass-inventory-report-{timezone.localdate().strftime('%Y%m%d')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([space.label, "E-ZPass Inventory, Tracker & Profit Report"])
    writer.writerow(["Generated At", timezone.now().strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])
    writer.writerow([
        "Tag Number",
        "Type",
        "Status",
        "Cost Price ($)",
        "Retail Price ($)",
        "Toll Deposit ($)",
        "Fee / Markup ($)",
        "Net Profit ($)",
        "Customer Name",
        "Customer Phone",
        "Customer Email",
        "Plate Number",
        "Plate State",
        "Vehicle",
        "Assigned At",
        "Assigned By",
        "Payment Method",
        "Batch #",
        "Notes",
    ])

    tags = (
        EZPassTag.objects.filter(space=space)
        .select_related("batch", "assigned_by", "invoice")
        .order_by("-assigned_at", "-created_at")
    )
    for t in tags:
        veh = " ".join(filter(None, [t.vehicle_year, t.vehicle_make, t.vehicle_model]))
        writer.writerow([
            t.tag_number,
            t.get_tag_type_display(),
            t.get_status_display(),
            f"{t.cost_price:.2f}",
            f"{t.retail_price:.2f}",
            f"{t.toll_deposit:.2f}",
            f"{t.convenience_fee:.2f}",
            f"{t.profit:.2f}",
            t.customer_name,
            t.customer_phone,
            t.customer_email,
            t.plate_number,
            t.plate_state,
            veh,
            t.assigned_at.strftime("%Y-%m-%d %H:%M") if t.assigned_at else "",
            t.assigned_by.get_full_name() or t.assigned_by.username if t.assigned_by else "",
            t.get_payment_method_display(),
            t.batch.batch_number if t.batch else "",
            t.notes.replace("\n", " "),
        ])

    return response
