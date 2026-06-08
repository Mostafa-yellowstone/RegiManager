"""Professional PDF layouts for Custom Inventory invoices and reports."""

from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = letter
MARGIN = 0.65 * inch
CONTENT_W = PAGE_W - (MARGIN * 2)

TEAL = colors.HexColor("#0f766e")
TEAL_LIGHT = colors.HexColor("#ccfbf1")
SLATE = colors.HexColor("#334155")
SLATE_LIGHT = colors.HexColor("#f8fafc")
BORDER = colors.HexColor("#e2e8f0")


def _wrap_text(text, max_chars=52):
    words = (text or "").split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _draw_header_band(pdf, space, doc_title="INVOICE"):
    pdf.setFillColor(TEAL)
    pdf.rect(0, PAGE_H - 1.15 * inch, PAGE_W, 1.15 * inch, fill=1, stroke=0)

    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(MARGIN, PAGE_H - 0.55 * inch, space.label)

    pdf.setFont("Helvetica", 9)
    y_contact = PAGE_H - 0.78 * inch
    if space.business_phone:
        pdf.drawString(MARGIN, y_contact, space.business_phone)
        y_contact -= 11
    if space.business_email:
        pdf.drawString(MARGIN, y_contact, space.business_email)

    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.52 * inch, doc_title)
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(PAGE_W - MARGIN, PAGE_H - 0.72 * inch, "Custom Inventory")


def _draw_business_address_block(pdf, space, start_y):
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(MARGIN, start_y, "BUSINESS ADDRESS")
    y = start_y - 14
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.HexColor("#475569"))
    if space.business_address:
        for line in space.business_address.splitlines():
            pdf.drawString(MARGIN, y, line.strip()[:70])
            y -= 12
    else:
        pdf.drawString(MARGIN, y, "— Add address in Business Settings —")
        y -= 12
    return y - 8


def _draw_section_box(pdf, x, y, w, h, title):
    pdf.setStrokeColor(BORDER)
    pdf.setFillColor(SLATE_LIGHT)
    pdf.roundRect(x, y - h, w, h, 6, fill=1, stroke=1)
    pdf.setFillColor(TEAL)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(x + 10, y - 16, title)


def render_inventory_invoice_pdf(pdf, invoice):
    space = invoice.space
    _draw_header_band(pdf, space, "INVOICE")

    y = PAGE_H - 1.45 * inch

    # Invoice meta row
    box_h = 58
    _draw_section_box(pdf, MARGIN, y, CONTENT_W * 0.48, box_h, "INVOICE DETAILS")
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(MARGIN + 12, y - 32, f"Invoice Number: {invoice.invoice_number}")
    pdf.drawString(MARGIN + 12, y - 46, f"Date: {invoice.invoice_date.strftime('%B %d, %Y')}")
    pdf.drawString(MARGIN + 12, y - 60, f"Payment: {invoice.get_payment_method_display()}")

    bill_x = MARGIN + CONTENT_W * 0.52
    bill_w = CONTENT_W * 0.48
    _draw_section_box(pdf, bill_x, y, bill_w, box_h, "BILL TO")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(bill_x + 12, y - 32, invoice.buyer_name[:45])
    pdf.setFont("Helvetica", 9)
    by = y - 46
    if invoice.buyer_address:
        for line in invoice.buyer_address.splitlines()[:3]:
            pdf.drawString(bill_x + 12, by, line.strip()[:42])
            by -= 12
    if invoice.buyer_phone:
        pdf.drawString(bill_x + 12, by, f"Phone: {invoice.buyer_phone}")
        by -= 12
    if invoice.buyer_email:
        pdf.drawString(bill_x + 12, by, invoice.buyer_email[:42])

    y -= box_h + 22
    y = _draw_business_address_block(pdf, space, y)

    # Line items table
    col_x = [
        MARGIN,
        MARGIN + CONTENT_W * 0.52,
        MARGIN + CONTENT_W * 0.68,
        MARGIN + CONTENT_W * 0.82,
        PAGE_W - MARGIN,
    ]
    table_top = y
    pdf.setFillColor(TEAL)
    pdf.rect(MARGIN, table_top - 22, CONTENT_W, 22, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(col_x[0] + 8, table_top - 15, "DESCRIPTION")
    pdf.drawString(col_x[1] + 4, table_top - 15, "QTY")
    pdf.drawString(col_x[2] + 4, table_top - 15, "UNIT PRICE")
    pdf.drawRightString(col_x[4] - 8, table_top - 15, "LINE TOTAL")

    y = table_top - 34
    pdf.setFont("Helvetica", 9)
    row_idx = 0
    for line in invoice.lines.all():
        if y < 1.6 * inch:
            pdf.showPage()
            _draw_header_band(pdf, space, "INVOICE")
            y = PAGE_H - 1.65 * inch
            row_idx = 0

        if row_idx % 2 == 0:
            pdf.setFillColor(colors.HexColor("#f0fdfa"))
            pdf.rect(MARGIN, y - 6, CONTENT_W, 18, fill=1, stroke=0)

        pdf.setFillColor(SLATE)
        pdf.drawString(col_x[0] + 8, y, line.description[:38])
        pdf.drawString(col_x[1] + 4, y, str(line.quantity))
        pdf.drawString(col_x[2] + 4, y, f"${line.unit_price:,.2f}")
        pdf.drawRightString(col_x[4] - 8, y, f"${line.line_total:,.2f}")
        y -= 18
        row_idx += 1

    pdf.setStrokeColor(BORDER)
    pdf.line(MARGIN, y + 4, PAGE_W - MARGIN, y + 4)

    # Totals
    totals_y = max(y - 20, 1.35 * inch)
    totals_w = 2.2 * inch
    totals_x = PAGE_W - MARGIN - totals_w
    pdf.setFillColor(SLATE_LIGHT)
    pdf.roundRect(totals_x, totals_y - 52, totals_w, 52, 6, fill=1, stroke=1)
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(totals_x + 12, totals_y - 18, "Subtotal")
    pdf.drawRightString(totals_x + totals_w - 12, totals_y - 18, f"${invoice.subtotal:,.2f}")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(TEAL)
    pdf.drawString(totals_x + 12, totals_y - 38, "TOTAL DUE")
    pdf.drawRightString(totals_x + totals_w - 12, totals_y - 38, f"${invoice.total:,.2f}")

    if invoice.notes:
        pdf.setFillColor(SLATE)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(MARGIN, totals_y - 18, "NOTES")
        pdf.setFont("Helvetica", 9)
        for i, line in enumerate(_wrap_text(invoice.notes, 90)[:3]):
            pdf.drawString(MARGIN, totals_y - 32 - (i * 12), line)

    pdf.setFillColor(colors.HexColor("#64748b"))
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawCentredString(PAGE_W / 2, 0.55 * inch, f"Thank you for your business — {space.label}")


def render_inventory_report_pdf(pdf, space, report_type, stats):
    title = "INVENTORY STOCK REPORT" if report_type == "inventory" else "SALES REPORT"
    _draw_header_band(pdf, space, "REPORT")

    y = PAGE_H - 1.45 * inch
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(MARGIN, y, title)
    y -= 18
    pdf.setFont("Helvetica", 9)
    pdf.drawString(MARGIN, y, f"Generated for: {space.label}")
    y -= 14
    from django.utils import timezone
    pdf.drawString(MARGIN, y, f"Report date: {timezone.localdate().strftime('%B %d, %Y')}")
    y -= 22

    y = _draw_business_address_block(pdf, space, y)

    if report_type == "inventory":
        summary = [
            ("Total Products", str(stats["total_products"])),
            ("Units in Stock", str(stats["total_units"])),
            ("Inventory Value", f"${stats['total_inventory_value']:,.2f}"),
            ("Low Stock Items", str(stats["low_stock_count"])),
        ]
    else:
        summary = [
            ("Sales Today", f"${stats['sales_today_total']:,.2f} ({stats['sales_today_count']} invoices)"),
            ("Sales This Month", f"${stats['sales_month_total']:,.2f} ({stats['sales_month_count']} invoices)"),
            ("Total Invoices", str(stats["invoice_count"])),
        ]

    box_h = 20 + len(summary) * 14
    _draw_section_box(pdf, MARGIN, y, CONTENT_W * 0.55, box_h, "SUMMARY")
    sy = y - 30
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(SLATE)
    for label, value in summary:
        pdf.drawString(MARGIN + 12, sy, f"{label}:")
        pdf.drawRightString(MARGIN + CONTENT_W * 0.55 - 12, sy, value)
        sy -= 14

    y -= box_h + 20

    if report_type == "inventory":
        headers = ["Product", "SKU", "Category", "Price", "Qty", "Value"]
        col_x = [MARGIN, MARGIN + 150, MARGIN + 220, MARGIN + 310, MARGIN + 370, MARGIN + 420]
        rows = []
        from .models import InventoryProduct
        for p in InventoryProduct.objects.filter(space=space).select_related("category").order_by("name"):
            rows.append([
                p.name[:28],
                p.sku[:12] or "—",
                (p.category.name[:14] if p.category else "—"),
                f"${p.unit_price:,.2f}",
                str(p.quantity),
                f"${p.unit_price * p.quantity:,.2f}",
            ])
    else:
        headers = ["Invoice #", "Date", "Buyer", "Payment", "Total"]
        col_x = [MARGIN, MARGIN + 110, MARGIN + 190, MARGIN + 340, MARGIN + 430]
        rows = []
        from .models import InventoryInvoice
        for inv in InventoryInvoice.objects.filter(space=space).order_by("-invoice_date")[:80]:
            rows.append([
                inv.invoice_number,
                inv.invoice_date.strftime("%m/%d/%Y"),
                inv.buyer_name[:22],
                inv.get_payment_method_display()[:12],
                f"${inv.total:,.2f}",
            ])

    pdf.setFillColor(TEAL)
    pdf.rect(MARGIN, y - 20, CONTENT_W, 20, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 8)
    for i, h in enumerate(headers):
        if i == len(headers) - 1 and report_type == "sales":
            pdf.drawRightString(PAGE_W - MARGIN - 8, y - 13, h)
        else:
            pdf.drawString(col_x[i] + 4, y - 13, h)

    y -= 32
    pdf.setFont("Helvetica", 8)
    for ridx, row in enumerate(rows):
        if y < inch:
            pdf.showPage()
            _draw_header_band(pdf, space, "REPORT")
            y = PAGE_H - 1.65 * inch
            ridx = 0
        if ridx % 2 == 0:
            pdf.setFillColor(colors.HexColor("#f8fafc"))
            pdf.rect(MARGIN, y - 5, CONTENT_W, 14, fill=1, stroke=0)
        pdf.setFillColor(SLATE)
        for i, cell in enumerate(row):
            if i == len(row) - 1:
                pdf.drawRightString(PAGE_W - MARGIN - 8, y, cell)
            else:
                pdf.drawString(col_x[i] + 4, y, str(cell))
        y -= 14
