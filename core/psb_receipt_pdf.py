"""NY DMV Private Service Bureau receipt PDF (official form layout)."""

from __future__ import annotations

import os
import re
from decimal import Decimal, ROUND_DOWN

from django.http import HttpResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .models import OrganizationMembership, ServiceRecord

OFFICIAL_FOOTER = (
    "This is a Liscensed Private Service Bureau, but is not an official agency "
    "of the Department of Motor Vehicles , State of New York "
)

SERVICE_ROW_SPECS = [
    ("obtaining_plates", "Obtaining Plates", {
        "new_plates", "vehicle_registration", "motorcycle_registration",
        "registration_renewal", "title_only", "surrender_plates", "replace_lost_item",
    }),
    ("sales_tax", "Sales Tax", set()),
    ("transfer", "Transfer of Vehicle", {"transfer_plate"}),
    ("duplicate_title", "Duplicate Title", {"duplicate_title", "get_title"}),
    ("duplicate_reg", "Duplicate Registration", {"duplicate_registration"}),
    ("road_test", "Road Test Appt.", {"road_test", "road_test_appt"}),
    ("other", "Other", {"other"}),
]


def _currency(value) -> str:
    amount = value or Decimal("0")
    return f"${amount:.2f}"


def _dollars_to_words(amount) -> str:
    dollars = int(Decimal(str(amount or 0)).quantize(Decimal("1"), rounding=ROUND_DOWN))
    if dollars == 0:
        return "Zero"

    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def under_thousand(n: int) -> str:
        if n == 0:
            return ""
        if n < 20:
            return ones[n]
        if n < 100:
            return f"{tens[n // 10]}{' ' + ones[n % 10] if n % 10 else ''}".strip()
        return f"{ones[n // 100]} Hundred{' ' + under_thousand(n % 100) if n % 100 else ''}".strip()

    parts = []
    millions = dollars // 1_000_000
    if millions:
        parts.append(f"{under_thousand(millions)} Million")
        dollars %= 1_000_000
    thousands = dollars // 1_000
    if thousands:
        parts.append(f"{under_thousand(thousands)} Thousand")
        dollars %= 1_000
    if dollars:
        parts.append(under_thousand(dollars))
    return " ".join(parts)


def format_receipt_number_display(service_record) -> str:
    """Show receipt # as digits only (consecutive per PSB, e.g. 00001)."""
    if not service_record.organization_id:
        digits = re.sub(r"\D", "", str(service_record.receipt_number or ""))
        return digits[-5:].zfill(5) if digits else "00000"

    seq = ServiceRecord.objects.filter(
        organization_id=service_record.organization_id,
        id__lte=service_record.id,
    ).count()
    return f"{seq:05d}"


def _format_org_header_name(org) -> str:
    name = (org.name or "").strip().upper()
    if name and "PRIVATE SERVICE BUREAU" not in name and "PSB" not in name:
        if not name.endswith("INC") and not name.endswith("INC."):
            name = f"{name} PRIVATE SERVICE BUREAU, INC."
    return name


def _format_org_address(org) -> str:
    line = (org.address_line or "").strip()
    city_state = ", ".join(p for p in [(org.city or "").strip(), (org.state or "").strip()] if p)
    if line and city_state:
        return f"{line}, {city_state}"
    return line or city_state


def _resolve_business_owner_name(org) -> str:
    explicit = (getattr(org, "business_owner_name", None) or "").strip()
    if explicit:
        return explicit

    owners = OrganizationMembership.objects.filter(
        organization=org,
        role=OrganizationMembership.Role.OWNER,
        is_active=True,
    ).select_related("user")
    names = []
    for membership in owners:
        name = membership.user.get_full_name() or membership.user.username
        if name:
            names.append(name.strip())
    return ", ".join(names)


def _resolve_client_name(service_record) -> str:
    name = service_record.client_name
    if not name and service_record.vehicle and service_record.vehicle.client:
        name = service_record.vehicle.client.name
    return (name or "").strip()


def _resolve_client_address(service_record) -> str:
    address = service_record.client_address
    if not address and service_record.vehicle and service_record.vehicle.client:
        address = service_record.vehicle.client.full_address
    return (address or "").strip()


def _build_service_row_amounts(service_record) -> dict:
    amounts = {
        key: {"dmv": Decimal("0"), "fee": Decimal("0"), "other_label": ""}
        for key, _, _ in SERVICE_ROW_SPECS
    }
    st = (service_record.service_type or "").strip()

    matched_key = "other"
    for key, _label, type_keys in SERVICE_ROW_SPECS:
        if type_keys and st in type_keys:
            matched_key = key
            break

    if matched_key == "other" and st and st != "other":
        amounts["other"]["other_label"] = service_record.service_type_label

    amounts[matched_key]["dmv"] += service_record.dmv_fee or Decimal("0")
    amounts[matched_key]["fee"] += service_record.processing_fee or Decimal("0")

    amounts["sales_tax"]["dmv"] = service_record.dmv_sales_tax or Decimal("0")
    amounts["sales_tax"]["fee"] = service_record.sales_tax or Decimal("0")

    amounts["other"]["dmv"] += service_record.other_dmv_fee or Decimal("0")
    amounts["other"]["fee"] += service_record.other_fees or Decimal("0")

    return amounts


def _draw_labeled_field(pdf, x, y, width, label, value, label_size=8, value_size=9):
    pdf.setFont("Helvetica", label_size)
    label_w = pdf.stringWidth(label, "Helvetica", label_size)
    pdf.drawString(x, y, label)
    line_x = x + label_w + 4
    line_y = y - 2
    pdf.line(line_x, line_y, x + width, line_y)
    if value:
        pdf.setFont("Helvetica", value_size)
        pdf.drawString(line_x + 2, y, str(value)[: int((width - label_w) / 5.5)])


def _draw_sum_of_dollars_line(pdf, margin, inner_w, inner_right, y, grand_total):
    sum_words = _dollars_to_words(grand_total)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(margin + 12, y, "The sum of")
    sum_x = margin + 58
    sum_w = inner_w - 124
    pdf.line(sum_x, y - 2, sum_x + sum_w, y - 2)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(sum_x + 4, y, sum_words[:58])
    pdf.setFont("Helvetica", 8.5)
    pdf.drawRightString(inner_right - 12, y, "Dollars")


def _draw_amount_cell(pdf, x, y, w, h, amount):
    pdf.rect(x, y, w, h)
    if amount:
        pdf.drawRightString(x + w - 4, y + 5, _currency(amount))
    else:
        pdf.drawRightString(x + w - 4, y + 5, "$ _________")


def _draw_receipt_payment_history_page(pdf, service_record, margin_x):
    from .service_payments import (
        compute_ledger_rows,
        receipt_outstanding_balance,
        receipt_summary_description,
        total_paid_for_receipt,
    )

    width, height = letter
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin_x, height - 50, "PAYMENT HISTORY — ATTACHMENT")

    rows = compute_ledger_rows(service_record)
    row_h = 14
    header_h = 28
    table_w = 530
    n_rows = max(len(rows), 1)
    table_h = header_h + (n_rows * row_h)
    py = height - 90

    pdf.setLineWidth(0.5)
    pdf.rect(margin_x, py - table_h, table_w, table_h)
    col1 = margin_x + 78
    col2 = margin_x + 228
    col3 = margin_x + 308
    col4 = margin_x + 378
    header_y = py - header_h
    for x in (col1, col2, col3, col4):
        pdf.line(x, py - table_h, x, py)
    pdf.line(margin_x, header_y, margin_x + table_w, header_y)

    pdf.setFont("Helvetica", 6)
    pdf.drawString(margin_x + 4, header_y + 6, "Date")
    pdf.drawString(col1 + 4, header_y + 6, "Description")
    pdf.drawString(col2 + 4, header_y + 6, "Total")
    pdf.drawString(col3 + 4, header_y + 6, "Paid")
    pdf.drawString(col4 + 4, header_y + 6, "Outstanding Balance")

    pdf.setFont("Helvetica", 7)
    if rows:
        for idx, row in enumerate(rows):
            row_y = header_y - (idx + 1) * row_h
            pdf.line(margin_x, row_y, margin_x + table_w, row_y)
            pdf.drawString(margin_x + 4, row_y + 4, row.payment_date.strftime("%b %d, %Y")[:14])
            pdf.drawString(col1 + 4, row_y + 4, row.description[:30])
            if row.is_opening:
                pdf.drawRightString(col2 + 76, row_y + 4, _currency(row.line_total or Decimal("0")))
            else:
                pdf.drawRightString(col2 + 76, row_y + 4, "—")
            pdf.drawRightString(col3 + 66, row_y + 4, _currency(row.line_paid))
            pdf.drawRightString(margin_x + table_w - 4, row_y + 4, _currency(row.balance_after))
    else:
        row_y = header_y - row_h
        pdf.line(margin_x, row_y, margin_x + table_w, row_y)
        summary_date = service_record.transaction_date or service_record.created_at.date()
        pdf.drawString(margin_x + 4, row_y + 4, summary_date.strftime("%b %d, %Y")[:14])
        pdf.drawString(col1 + 4, row_y + 4, receipt_summary_description(service_record)[:30])
        pdf.drawRightString(col2 + 76, row_y + 4, _currency(service_record.service_fee or Decimal("0")))
        pdf.drawRightString(col3 + 66, row_y + 4, _currency(total_paid_for_receipt(service_record)))
        pdf.drawRightString(margin_x + table_w - 4, row_y + 4, _currency(receipt_outstanding_balance(service_record)))

    from .models import ServiceRecordPayment

    entries = list(service_record.payment_entries.all())
    total_cc = Decimal("0")
    for entry in entries:
        if entry.entry_type != ServiceRecordPayment.ENTRY_OPENING:
            total_cc += entry.cc_fee or Decimal("0")
    if not entries:
        total_cc = service_record.credit_card_fee or Decimal("0")

    ledger_paid = total_paid_for_receipt(service_record)
    final_outstanding = rows[-1].balance_after if rows else receipt_outstanding_balance(service_record)

    py_totals = py - table_h - 30
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(margin_x, py_totals + 4, "Total CC Fees")
    pdf.drawRightString(margin_x + 116, py_totals + 4, _currency(total_cc))
    pdf.drawString(margin_x + 130, py_totals + 4, "Total Paid")
    pdf.drawRightString(margin_x + 246, py_totals + 4, _currency(ledger_paid))
    pdf.drawString(margin_x + 260, py_totals + 4, "Outstanding Balance")
    pdf.drawRightString(margin_x + 411, py_totals + 4, _currency(final_outstanding))


def render_psb_service_receipt(pdf, service_record) -> None:
    width, height = letter
    margin = 36
    inner_w = width - (margin * 2)
    inner_right = margin + inner_w

    pdf.setLineWidth(1.5)
    pdf.rect(margin, margin, inner_w, height - (margin * 2))

    org = service_record.organization
    y = height - margin - 22

    header_name = _format_org_header_name(org)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, y, header_name[:72])
    y -= 14

    owner_name = _resolve_business_owner_name(org)
    if owner_name:
        owner_line_y = y
        pdf.setStrokeColorRGB(0.75, 0.75, 0.75)
        pdf.setLineWidth(0.5)
        pdf.line(width / 2 - 90, owner_line_y + 10, width / 2 + 90, owner_line_y + 10)
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.setFillColorRGB(0.2, 0.2, 0.2)
        pdf.drawCentredString(width / 2, owner_line_y, owner_name.upper()[:70])
        pdf.setFillColorRGB(0, 0, 0)
        y -= 16

    address = _format_org_address(org).upper()
    pdf.setFont("Helvetica", 8.5)
    if address:
        pdf.drawCentredString(width / 2, y, address[:95])
        y -= 12

    psbc_license = (org.psbc_license or "").strip()
    psb_email = (org.email or "").strip()
    if psbc_license or psb_email:
        license_bits = []
        if psbc_license:
            license_bits.append(f"PSBC No. {psbc_license}")
        if psb_email:
            license_bits.append(f"Email: {psb_email}")
        pdf.setFont("Helvetica", 7.5)
        pdf.drawCentredString(width / 2, y, "  |  ".join(license_bits)[:100])
        y -= 12

    phone = (org.phone_number or "").strip()
    pdf.setFont("Helvetica", 8.5)
    if phone:
        pdf.drawString(margin + 12, y, f"Phone: {phone}")
    pdf.drawRightString(inner_right - 12, y, "Fax: _________________________")
    y -= 20

    dt = service_record.transaction_date or service_record.created_at.date()
    receipt_num = format_receipt_number_display(service_record)

    half = inner_w / 2 - 8
    _draw_labeled_field(pdf, margin + 12, y, half - 12, "Date:", dt.strftime("%m/%d/%Y"))
    _draw_labeled_field(pdf, margin + 12 + half, y, half - 12, "Receipt #:", receipt_num)
    y -= 28

    client_name = _resolve_client_name(service_record)
    _draw_labeled_field(pdf, margin + 12, y, inner_w - 24, "Customer Name:", client_name.upper())
    y -= 28

    client_address = _resolve_client_address(service_record)
    _draw_labeled_field(pdf, margin + 12, y, inner_w - 24, "Customer Address:", client_address.upper())
    y -= 28

    grand_total = service_record.service_fee or Decimal("0")
    _draw_sum_of_dollars_line(pdf, margin, inner_w, inner_right, y, grand_total)
    y -= 22

    col_svc_x = margin + 12
    col_dmv_x = margin + 292
    col_fee_x = margin + 392
    col_dmv_w = 88
    col_fee_w = 88
    row_h = 18
    table_right = inner_right - 12

    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(col_svc_x, y, "Services Provided")
    pdf.drawCentredString(col_dmv_x + col_dmv_w / 2, y, "DMV Fee")
    pdf.drawCentredString(col_fee_x + col_fee_w / 2, y, "Fee for Service")
    y -= 3
    pdf.line(col_svc_x, y, table_right, y)
    pdf.line(col_dmv_x, margin + 52, col_dmv_x, y)
    pdf.line(col_fee_x, margin + 52, col_fee_x, y)
    y -= row_h

    row_amounts = _build_service_row_amounts(service_record)
    total_dmv = Decimal("0")
    total_fee = Decimal("0")
    table_top = y + row_h

    pdf.setFont("Helvetica", 7.5)
    for key, label, _types in SERVICE_ROW_SPECS:
        data = row_amounts[key]
        dmv_amt = data["dmv"]
        fee_amt = data["fee"]
        total_dmv += dmv_amt
        total_fee += fee_amt

        display_label = label
        if key == "other" and data.get("other_label"):
            display_label = f"Other: {data['other_label']}"
        elif key == "other":
            display_label = "Other: _________________________"

        pdf.drawString(col_svc_x + 4, y + 4, display_label[:44])
        _draw_amount_cell(pdf, col_dmv_x, y, col_dmv_w, row_h - 2, dmv_amt)
        _draw_amount_cell(pdf, col_fee_x, y, col_fee_w, row_h - 2, fee_amt)
        pdf.line(col_svc_x, y, table_right, y)
        y -= row_h

    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(col_svc_x + 4, y + 4, "TOTAL")
    _draw_amount_cell(pdf, col_dmv_x, y, col_dmv_w, row_h - 2, total_dmv)
    _draw_amount_cell(pdf, col_fee_x, y, col_fee_w, row_h - 2, total_fee)
    pdf.line(col_svc_x, y, table_right, y)
    pdf.line(col_svc_x, table_top, table_right, table_top)
    pdf.line(table_right, table_top, table_right, y)
    y -= 30

    agent_name = ""
    if service_record.handled_by:
        agent_name = service_record.handled_by.get_full_name() or service_record.handled_by.username

    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin + 12, y, "Received by:")
    recv_line_w = inner_w - 88
    recv_x = margin + 68
    pdf.line(recv_x, y - 2, recv_x + recv_line_w, y - 2)
    if agent_name:
        pdf.setFont("Helvetica", 8.5)
        pdf.drawString(recv_x + 2, y, agent_name)
    y -= 11
    pdf.setFont("Helvetica-Oblique", 6.5)
    pdf.drawCentredString(
        recv_x + recv_line_w / 2,
        y,
        "(Printed name of officer or employee performing the service)",
    )
    y -= 20

    sig_line_y = y - 2
    pdf.line(recv_x, sig_line_y, recv_x + recv_line_w, sig_line_y)
    try:
        membership = OrganizationMembership.objects.filter(
            organization=service_record.organization,
            user=service_record.handled_by,
        ).first()
        if membership and membership.signature and os.path.exists(membership.signature.path):
            pdf.drawImage(
                membership.signature.path,
                recv_x + 4,
                sig_line_y + 2,
                width=96,
                height=26,
                mask="auto",
            )
    except Exception:
        pass
    y -= 11
    pdf.setFont("Helvetica-Oblique", 6.5)
    pdf.drawCentredString(
        recv_x + recv_line_w / 2,
        y,
        "(Signature of officer or employee performing the service)",
    )

    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawCentredString(width / 2, margin + 16, OFFICIAL_FOOTER)

    pdf.showPage()
    _draw_receipt_payment_history_page(pdf, service_record, margin)


def build_service_receipt_pdf_response(service_record) -> HttpResponse:
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="receipt-{format_receipt_number_display(service_record)}.pdf"'
    )
    pdf = canvas.Canvas(response, pagesize=letter)
    render_psb_service_receipt(pdf, service_record)
    pdf.save()
    return response
