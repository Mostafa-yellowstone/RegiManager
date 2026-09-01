"""Branded Insurance Space payment general ledger PDF (carrier evidence)."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .daily_payments import PAYMENT_METHOD_META
from .models import BankTransaction, DailyPaymentTransaction, Space

NAVY = colors.HexColor("#0B3A6E")
TEAL = colors.HexColor("#0F766E")
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
SOFT = colors.HexColor("#F8FAFC")
BAND = colors.HexColor("#EEF4FA")
SUCCESS = colors.HexColor("#047857")
WARN = colors.HexColor("#B45309")
WHITE = colors.white
ZERO = Decimal("0.00")

PAGE = letter
PAGE_W, PAGE_H = PAGE
MARGIN_X = 0.5 * inch
MARGIN_TOP = 1.18 * inch
MARGIN_BOTTOM = 0.58 * inch
CONTENT_W = PAGE_W - (MARGIN_X * 2)

RECEIPT_ACCOUNTS = {
    "new_business": ("4010", "Premium receipts — new business"),
    "renewal": ("4020", "Premium receipts — renewal"),
    "monthly_payment": ("4030", "Premium receipts — installment"),
    "endorsement": ("4040", "Premium receipts — endorsement"),
    "misc": ("4090", "Other insurance receipts"),
}

METHOD_ACCOUNTS = {
    "cash": ("1010", "Cash on hand"),
    "zelle": ("1020", "Electronic deposits — Zelle"),
    "credit_card": ("1030", "Credit card receipts"),
    "checks": ("1040", "Checks received"),
}


def _money(value) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        amount = ZERO
    if amount < 0:
        return f"(${abs(amount):,.2f})"
    return f"${amount:,.2f}"


def _safe(value, fallback="—") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _parse_iso_date(raw: str):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _logo_path(space: Space | None, org) -> str:
    for candidate in (
        getattr(space, "logo", None) if space else None,
        getattr(org, "logo", None),
    ):
        if not candidate:
            continue
        try:
            path = candidate.path
        except Exception:
            continue
        if path and os.path.isfile(path):
            return path
    return ""


def agency_branding(org, space: Space | None = None) -> dict:
    space = space or Space.objects.filter(organization=org, key="insurance").first()
    name = (
        (getattr(org, "insurance_intake_display_name", "") or "").strip()
        or (space.label if space and space.label else "")
        or org.name
    )
    space_address = (space.business_address or "").replace("\n", ", ").strip() if space else ""
    org_address = ", ".join(
        part for part in [org.address_line, org.city, org.state] if part
    )
    return {
        "name": name,
        "tagline": (getattr(org, "insurance_intake_tagline", "") or "").strip(),
        "address": space_address or org_address,
        "phone": ((space.business_phone if space else "") or org.phone_number or "").strip(),
        "email": ((space.business_email if space else "") or org.email or "").strip(),
        "license": (org.psbc_license or "").strip(),
        "owner": (org.business_owner_name or "").strip(),
        "logo_path": _logo_path(space, org),
        "space_label": (space.label if space else "Insurance") or "Insurance",
    }


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "gl_title", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=16, textColor=NAVY, leading=19, alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "gl_sub", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.5, textColor=MUTED, leading=11,
        ),
        "agency": ParagraphStyle(
            "gl_agency", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=11, textColor=NAVY, leading=13,
        ),
        "meta": ParagraphStyle(
            "gl_meta", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.5, textColor=MUTED, leading=9.5, alignment=TA_RIGHT,
        ),
        "section": ParagraphStyle(
            "gl_section", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9.5, textColor=NAVY, leading=12,
        ),
        "body": ParagraphStyle(
            "gl_body", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.6, textColor=INK, leading=10,
        ),
        "body_right": ParagraphStyle(
            "gl_body_r", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.6, textColor=INK, leading=10, alignment=TA_RIGHT,
        ),
        "body_bold": ParagraphStyle(
            "gl_body_b", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.6, textColor=INK, leading=10,
        ),
        "th": ParagraphStyle(
            "gl_th", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.7, textColor=WHITE, leading=8.4,
        ),
        "th_right": ParagraphStyle(
            "gl_th_r", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.7, textColor=WHITE, leading=8.4, alignment=TA_RIGHT,
        ),
        "group": ParagraphStyle(
            "gl_group", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, textColor=TEAL, leading=10,
        ),
        "kpi_label": ParagraphStyle(
            "gl_kpi_l", parent=base["Normal"], fontName="Helvetica",
            fontSize=6.6, textColor=MUTED, leading=8, alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "gl_kpi_v", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=11, textColor=NAVY, leading=13, alignment=TA_CENTER,
        ),
        "notice": ParagraphStyle(
            "gl_notice", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.4, textColor=INK, leading=10,
        ),
        "footer": ParagraphStyle(
            "gl_footer", parent=base["Normal"], fontName="Helvetica",
            fontSize=6.4, textColor=MUTED, leading=8, alignment=TA_CENTER,
        ),
        "cert": ParagraphStyle(
            "gl_cert", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.5, textColor=INK, leading=10.2,
        ),
        "muted": ParagraphStyle(
            "gl_muted", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.4, textColor=MUTED, leading=9.5, alignment=TA_CENTER,
        ),
    }


def _p(text, style):
    return Paragraph(_safe(text, "&nbsp;").replace("\n", "<br/>"), style)


def build_ledger_dataset(org, *, start=None, end=None, company_id=None, method=""):
    receipts = (
        DailyPaymentTransaction.objects.filter(organization=org)
        .select_related("client", "insurance_company", "insurance_policy", "recorded_by")
        .order_by("transaction_date", "id")
    )
    bank_rows = (
        BankTransaction.objects.filter(bank_account__organization=org)
        .select_related("bank_account", "insurance_company")
        .order_by("date", "id")
    )
    if start:
        receipts = receipts.filter(transaction_date__gte=start)
        bank_rows = bank_rows.filter(date__gte=start)
    if end:
        receipts = receipts.filter(transaction_date__lte=end)
        bank_rows = bank_rows.filter(date__lte=end)
    if company_id:
        receipts = receipts.filter(insurance_company_id=company_id)
        bank_rows = bank_rows.filter(insurance_company_id=company_id)
    if method:
        receipts = receipts.filter(payment_method=method)

    receipts = list(receipts)
    bank_rows = list(bank_rows)

    total = sum((tx.amount for tx in receipts), ZERO)
    cleared = sum((tx.amount for tx in receipts if tx.is_cleared), ZERO)
    pending = total - cleared
    by_method = defaultdict(lambda: ZERO)
    by_type = defaultdict(lambda: ZERO)
    by_carrier = defaultdict(lambda: {"total": ZERO, "count": 0, "name": "", "license": ""})
    for tx in receipts:
        by_method[tx.payment_method] += tx.amount
        by_type[tx.payment_type] += tx.amount
        key = tx.insurance_company_id or 0
        bucket = by_carrier[key]
        bucket["total"] += tx.amount
        bucket["count"] += 1
        bucket["name"] = tx.insurance_company.name if tx.insurance_company_id else "Unassigned carrier"
        bucket["license"] = (
            tx.insurance_company.license_number if tx.insurance_company_id else ""
        )

    bank_in = sum(
        (row.amount for row in bank_rows if BankTransaction.is_credit_type(row.transaction_type)),
        ZERO,
    )
    bank_out = sum(
        (
            row.amount
            for row in bank_rows
            if not BankTransaction.is_credit_type(row.transaction_type)
        ),
        ZERO,
    )

    return {
        "receipts": receipts,
        "bank_rows": bank_rows,
        "total": total,
        "cleared": cleared,
        "pending": pending,
        "count": len(receipts),
        "by_method": dict(by_method),
        "by_type": dict(by_type),
        "by_carrier": dict(by_carrier),
        "bank_in": bank_in,
        "bank_out": bank_out,
    }


def _header_footer(canvas, doc, brand, period_label, prepared_by):
    canvas.saveState()
    canvas.setPageSize(PAGE)
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - 0.78 * inch, PAGE_W, 0.78 * inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, PAGE_H - 0.82 * inch, PAGE_W, 0.04 * inch, fill=1, stroke=0)

    x = MARGIN_X
    logo = brand.get("logo_path")
    if logo:
        try:
            canvas.drawImage(
                logo,
                x,
                PAGE_H - 0.70 * inch,
                width=0.52 * inch,
                height=0.52 * inch,
                preserveAspectRatio=True,
                mask="auto",
            )
            x += 0.62 * inch
        except Exception:
            pass

    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(x, PAGE_H - 0.34 * inch, brand["name"][:72])
    canvas.setFont("Helvetica", 7.2)
    contact = "  ·  ".join(
        part for part in [brand.get("address"), brand.get("phone"), brand.get("email")] if part
    )
    canvas.drawString(x, PAGE_H - 0.54 * inch, contact[:78])

    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 0.32 * inch, "GENERAL LEDGER")
    canvas.setFont("Helvetica", 7.4)
    canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 0.48 * inch, "Payment evidence report")
    canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 0.62 * inch, period_label)

    canvas.setFillColor(SOFT)
    canvas.rect(0, 0, PAGE_W, 0.42 * inch, fill=1, stroke=0)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN_X, 0.42 * inch, PAGE_W - MARGIN_X, 0.42 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.4)
    stamp = timezone.localtime().strftime("%b %d, %Y  %I:%M %p")
    canvas.drawString(
        MARGIN_X,
        0.18 * inch,
        f"Official payment record  ·  Prepared {stamp} by {prepared_by}",
    )
    canvas.drawRightString(PAGE_W - MARGIN_X, 0.18 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _kpi_table(data, styles):
    cards = [
        ("Receipts", str(data["count"])),
        ("Total collected", _money(data["total"])),
        ("Cleared / deposited", _money(data["cleared"])),
        ("Held / uncleared", _money(data["pending"])),
        ("Bank income postings", _money(data["bank_in"])),
        ("Bank disbursements", _money(data["bank_out"])),
    ]
    col_w = CONTENT_W / 3

    def _card(label, value):
        return Table(
            [[_p(label, styles["kpi_label"])], [_p(value, styles["kpi_value"])]],
            colWidths=[col_w - 6],
        )

    rows = [
        [_card(label, value) for label, value in cards[i:i + 3]]
        for i in range(0, len(cards), 3)
    ]
    table = Table(rows, colWidths=[col_w] * 3)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _receipt_table(receipts, styles):
    headers = [
        _p("Ref #", styles["th"]),
        _p("Date", styles["th"]),
        _p("Payer / insured", styles["th"]),
        _p("Carrier", styles["th"]),
        _p("GL / type", styles["th"]),
        _p("Amount", styles["th_right"]),
        _p("Clearing", styles["th"]),
    ]
    col_w = [
        CONTENT_W * 0.10,
        CONTENT_W * 0.10,
        CONTENT_W * 0.18,
        CONTENT_W * 0.15,
        CONTENT_W * 0.25,
        CONTENT_W * 0.11,
        CONTENT_W * 0.11,
    ]
    rows = [headers]
    grouped = defaultdict(list)
    for tx in receipts:
        grouped[tx.transaction_date].append(tx)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
    ]
    row_index = 1
    for txn_date in sorted(grouped):
        day_total = sum((tx.amount for tx in grouped[txn_date]), ZERO)
        rows.append([
            Paragraph(
                f"Posting date {txn_date.strftime('%A, %B %d, %Y')}  ·  {len(grouped[txn_date])} receipt(s)  ·  {_money(day_total)}",
                styles["group"],
            ),
            "", "", "", "", "", "",
        ])
        style_cmds.append(("SPAN", (0, row_index), (-1, row_index)))
        style_cmds.append(("BACKGROUND", (0, row_index), (-1, row_index), BAND))
        row_index += 1
        for tx in grouped[txn_date]:
            acct_no, acct_name = RECEIPT_ACCOUNTS.get(
                tx.payment_type, ("4090", "Other insurance receipts")
            )
            method_no, method_name = METHOD_ACCOUNTS.get(
                tx.payment_method, ("1090", "Other receipts")
            )
            notes = (tx.notes or "").strip()
            desc = (
                f"<b>{acct_no}</b> {acct_name}"
                f"<br/><font color='#64748B'>{tx.get_payment_type_display()} · {method_no} {tx.get_payment_method_display()}</font>"
            )
            if notes:
                desc += f"<br/><font color='#64748B'>{_safe(notes)[:80]}</font>"
            clearing = "Cleared" if tx.is_cleared else "Held"
            if tx.is_cleared and tx.cleared_date:
                clearing += f"<br/>{tx.cleared_date.strftime('%m/%d/%Y')}"
            payer = tx.client.name if tx.client_id else "—"
            if tx.insurance_policy_id and tx.insurance_policy.policy_number:
                payer += f"<br/><font color='#64748B'>Pol. {_safe(tx.insurance_policy.policy_number)}</font>"
            recorded = ""
            if tx.recorded_by_id:
                recorded = tx.recorded_by.get_full_name() or tx.recorded_by.username
            if recorded:
                desc += f"<br/><font color='#64748B'>{_safe(recorded)}</font>"
            rows.append([
                _p(f"PMT-{tx.id:06d}", styles["body_bold"]),
                _p(txn_date.strftime("%m/%d/%Y"), styles["body"]),
                Paragraph(_safe(payer), styles["body"]),
                _p(tx.insurance_company.name if tx.insurance_company_id else "—", styles["body"]),
                Paragraph(desc, styles["body"]),
                _p(_money(tx.amount), styles["body_right"]),
                Paragraph(
                    f"<font color='{'#047857' if tx.is_cleared else '#B45309'}'><b>{clearing}</b></font>",
                    styles["body"],
                ),
            ])
            if row_index % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, row_index), (-1, row_index), SOFT))
            row_index += 1

    table = Table(rows, colWidths=col_w, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))
    return table


def _carrier_table(by_carrier, styles):
    headers = [
        _p("Carrier", styles["th"]),
        _p("License", styles["th"]),
        _p("Receipts", styles["th_right"]),
        _p("Collected", styles["th_right"]),
        _p("Evidence use", styles["th"]),
    ]
    col_w = [
        CONTENT_W * 0.24,
        CONTENT_W * 0.16,
        CONTENT_W * 0.12,
        CONTENT_W * 0.16,
        CONTENT_W * 0.32,
    ]
    rows = [headers]
    for key, bucket in sorted(by_carrier.items(), key=lambda item: item[1]["name"].lower()):
        rows.append([
            _p(bucket["name"], styles["body_bold"]),
            _p(bucket["license"] or "—", styles["body"]),
            _p(str(bucket["count"]), styles["body_right"]),
            _p(_money(bucket["total"]), styles["body_right"]),
            _p(
                "Present this page with the register as proof of premiums collected for this carrier.",
                styles["body"],
            ),
        ])
    table = Table(rows, colWidths=col_w, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("BACKGROUND", (0, 1), (-1, -1), SOFT),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
    ]))
    return table


def _bank_table(bank_rows, styles):
    headers = [
        _p("Date", styles["th"]),
        _p("Account", styles["th"]),
        _p("Carrier", styles["th"]),
        _p("Category", styles["th"]),
        _p("Description", styles["th"]),
        _p("Type", styles["th"]),
        _p("Amount", styles["th_right"]),
    ]
    col_w = [
        CONTENT_W * 0.11,
        CONTENT_W * 0.16,
        CONTENT_W * 0.15,
        CONTENT_W * 0.14,
        CONTENT_W * 0.22,
        CONTENT_W * 0.11,
        CONTENT_W * 0.11,
    ]
    rows = [headers]
    for row in bank_rows:
        signed = row.amount if BankTransaction.is_credit_type(row.transaction_type) else -row.amount
        rows.append([
            _p(row.date.strftime("%m/%d/%Y"), styles["body"]),
            _p(row.bank_account.account_name if row.bank_account_id else "—", styles["body"]),
            _p(row.insurance_company.name if row.insurance_company_id else "—", styles["body"]),
            _p(row.category, styles["body"]),
            _p(row.description or "—", styles["body"]),
            _p(row.get_transaction_type_display(), styles["body"]),
            _p(_money(signed), styles["body_right"]),
        ])
    table = Table(rows, colWidths=col_w, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
    ]))
    return table


def _method_type_tables(data, styles):
    method_rows = [[_p("Method", styles["th"]), _p("GL account", styles["th"]), _p("Amount", styles["th_right"])]]
    for key, meta in PAYMENT_METHOD_META.items():
        acct_no, acct_name = METHOD_ACCOUNTS.get(key, ("1090", "Other"))
        method_rows.append([
            _p(meta["label"], styles["body"]),
            _p(f"{acct_no}  {acct_name}", styles["body"]),
            _p(_money(data["by_method"].get(key, ZERO)), styles["body_right"]),
        ])
    type_rows = [[_p("Payment type", styles["th"]), _p("GL account", styles["th"]), _p("Amount", styles["th_right"])]]
    for key, label in DailyPaymentTransaction.PaymentType.choices:
        acct_no, acct_name = RECEIPT_ACCOUNTS.get(key, ("4090", "Other"))
        type_rows.append([
            _p(label, styles["body"]),
            _p(f"{acct_no}  {acct_name}", styles["body"]),
            _p(_money(data["by_type"].get(key, ZERO)), styles["body_right"]),
        ])
    half = CONTENT_W / 2 - 8
    left = Table(method_rows, colWidths=[half * 0.28, half * 0.50, half * 0.22])
    right = Table(type_rows, colWidths=[half * 0.32, half * 0.46, half * 0.22])
    grid = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
    ])
    left.setStyle(grid)
    right.setStyle(grid)
    wrap = Table([[left, right]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    wrap.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    return wrap


def render_insurance_ledger_pdf(
    org,
    *,
    start=None,
    end=None,
    company_id=None,
    method="",
    prepared_by="Staff",
) -> bytes:
    space = Space.objects.filter(organization=org, key="insurance").first()
    brand = agency_branding(org, space)
    data = build_ledger_dataset(
        org, start=start, end=end, company_id=company_id, method=method
    )
    styles = _styles()

    if start and end:
        period_label = f"{start.strftime('%b %d, %Y')}  –  {end.strftime('%b %d, %Y')}"
    elif start:
        period_label = f"From {start.strftime('%b %d, %Y')}"
    elif end:
        period_label = f"Through {end.strftime('%b %d, %Y')}"
    else:
        period_label = "All recorded insurance payments"

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=PAGE,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=f"Insurance General Ledger — {brand['name']}",
        author=brand["name"],
    )
    frame = Frame(
        MARGIN_X,
        MARGIN_BOTTOM,
        CONTENT_W,
        PAGE_H - MARGIN_TOP - MARGIN_BOTTOM,
        id="body",
        showBoundary=0,
    )
    doc.addPageTemplates([
        PageTemplate(
            id="ledger",
            frames=[frame],
            pagesize=PAGE,
            onPage=lambda c, d: _header_footer(c, d, brand, period_label, prepared_by),
        )
    ])

    story = []
    story.append(_p("Insurance payment general ledger", styles["title"]))
    story.append(_p(
        "Chronological cash-receipts journal of premiums and fees collected in Insurance Space. "
        "Use this document as evidence of payment to carriers, banks, and internal audit.",
        styles["subtitle"],
    ))
    story.append(Spacer(1, 8))
    story.append(_kpi_table(data, styles))
    story.append(Spacer(1, 10))

    cert = (
        f"<b>Certification.</b> {brand['name']} certifies that the receipts listed below were collected "
        f"from insureds during <b>{period_label}</b>, totaling <b>{_money(data['total'])}</b>. "
        "Amounts marked Cleared have been deposited or reconciled; amounts marked Held remain in the "
        "agency cash drawer / undeposited funds. This is an agency record of collection — not a carrier invoice."
    )
    cert_table = Table([[Paragraph(cert, styles["cert"])]], colWidths=[CONTENT_W])
    cert_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("BOX", (0, 0), (-1, -1), 0.6, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(cert_table)
    story.append(Spacer(1, 12))

    story.append(_p("1.  Receipts register  ·  grouped by transaction date", styles["section"]))
    story.append(Spacer(1, 6))
    if data["receipts"]:
        story.append(_receipt_table(data["receipts"], styles))
    else:
        story.append(_p("No insurance receipts were recorded in this period.", styles["muted"]))

    story.append(Spacer(1, 14))
    story.append(_p("2.  Recap by tender and by business type", styles["section"]))
    story.append(Spacer(1, 6))
    story.append(_method_type_tables(data, styles))

    story.append(Spacer(1, 14))
    story.append(_p("3.  Carrier evidence summary", styles["section"]))
    story.append(_p(
        "Totals an insurance company can match against its own billed premiums for this agency.",
        styles["subtitle"],
    ))
    story.append(Spacer(1, 6))
    if data["by_carrier"]:
        story.append(_carrier_table(data["by_carrier"], styles))
    else:
        story.append(_p("No carrier-assigned receipts in this period.", styles["muted"]))

    story.append(Spacer(1, 14))
    story.append(_p("4.  Bank and carrier GL postings", styles["section"]))
    story.append(_p(
        "Income and expense entries posted to Insurance Space bank accounts in the same period.",
        styles["subtitle"],
    ))
    story.append(Spacer(1, 6))
    if data["bank_rows"]:
        story.append(_bank_table(data["bank_rows"], styles))
    else:
        story.append(_p("No bank ledger postings in this period.", styles["muted"]))

    story.append(Spacer(1, 16))
    story.append(_p(
        "End of report. Retain with daily payment backups and carrier remittance packages. "
        "Questions: use the agency phone or email printed in the letterhead.",
        styles["footer"],
    ))

    doc.build(story)
    return buffer.getvalue()


def parse_ledger_filters(request):
    start = _parse_iso_date(request.GET.get("start_date"))
    end = _parse_iso_date(request.GET.get("end_date"))
    company_raw = (request.GET.get("company") or "").strip()
    company_id = int(company_raw) if company_raw.isdigit() else None
    method = (request.GET.get("method") or "").strip()
    if method not in PAYMENT_METHOD_META:
        method = ""
    return start, end, company_id, method
