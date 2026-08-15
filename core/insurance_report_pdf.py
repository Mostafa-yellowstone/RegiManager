"""Branded Insurance Space Reporting Center PDFs."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter, landscape
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

from .daily_payments import PAYMENT_METHOD_META, summarize_daily_payments
from .insurance_commissions import build_adjusted_unearned_map, policy_unearned_commission, refund_total
from .insurance_company_license import company_license_status
from .insurance_ledger_pdf import agency_branding
from .insurance_quote_pipeline_models import InsuranceQuoteLead
from .insurance_space_metrics import build_agent_stats
from .insurance_targets_metrics import build_insurance_targets_dashboard, resolve_target_month
from .models import (
    BankTransaction,
    DailyPaymentTransaction,
    InsuranceCompany,
    InsurancePolicy,
    InsurancePolicyInstallment,
    OrganizationMembership,
)
from .psb_receipt_pdf import dollars_to_words

NAVY = colors.HexColor("#0B3A6E")
TEAL = colors.HexColor("#0F766E")
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#E2E8F0")
SOFT = colors.HexColor("#F8FAFC")
BAND = colors.HexColor("#EEF4FA")
WHITE = colors.white
ZERO = Decimal("0.00")


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


def parse_iso_date(raw: str):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def period_label(start, end, fallback="All records"):
    if start and end:
        return f"{start.strftime('%b %d, %Y')}  –  {end.strftime('%b %d, %Y')}"
    if start:
        return f"From {start.strftime('%b %d, %Y')}"
    if end:
        return f"Through {end.strftime('%b %d, %Y')}"
    return fallback


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("r_title", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=15, textColor=NAVY, leading=18),
        "subtitle": ParagraphStyle("r_sub", parent=base["Normal"], fontName="Helvetica", fontSize=8.4, textColor=MUTED, leading=11),
        "section": ParagraphStyle("r_sec", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.4, textColor=NAVY, leading=12),
        "body": ParagraphStyle("r_body", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, textColor=INK, leading=9.8),
        "body_r": ParagraphStyle("r_body_r", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, textColor=INK, leading=9.8, alignment=TA_RIGHT),
        "body_b": ParagraphStyle("r_body_b", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.5, textColor=INK, leading=9.8),
        "th": ParagraphStyle("r_th", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.6, textColor=WHITE, leading=8.2),
        "th_r": ParagraphStyle("r_th_r", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.6, textColor=WHITE, leading=8.2, alignment=TA_RIGHT),
        "kpi_l": ParagraphStyle("r_kpi_l", parent=base["Normal"], fontName="Helvetica", fontSize=6.5, textColor=MUTED, leading=8, alignment=TA_CENTER),
        "kpi_v": ParagraphStyle("r_kpi_v", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11, textColor=NAVY, leading=13, alignment=TA_CENTER),
        "muted": ParagraphStyle("r_muted", parent=base["Normal"], fontName="Helvetica", fontSize=8, textColor=MUTED, leading=11, alignment=TA_CENTER),
        "notice": ParagraphStyle("r_notice", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, textColor=INK, leading=10.2),
        "amount": ParagraphStyle("r_amt", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=22, textColor=NAVY, leading=26, alignment=TA_CENTER),
        "receipt_meta": ParagraphStyle("r_rm", parent=base["Normal"], fontName="Helvetica", fontSize=8, textColor=INK, leading=11),
        "footer": ParagraphStyle("r_ft", parent=base["Normal"], fontName="Helvetica", fontSize=6.4, textColor=MUTED, leading=8, alignment=TA_CENTER),
    }


def _p(text, style):
    return Paragraph(_safe(text, "&nbsp;").replace("\n", "<br/>"), style)


def _header_footer(canvas, doc, brand, title, period_label_text, prepared_by, page_w, page_h, margin_x):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, page_h - 0.78 * inch, page_w, 0.78 * inch, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, page_h - 0.82 * inch, page_w, 0.04 * inch, fill=1, stroke=0)
    x = margin_x
    logo = brand.get("logo_path")
    if logo:
        try:
            canvas.drawImage(logo, x, page_h - 0.70 * inch, width=0.52 * inch, height=0.52 * inch, preserveAspectRatio=True, mask="auto")
            x += 0.62 * inch
        except Exception:
            pass
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(x, page_h - 0.34 * inch, brand["name"][:70])
    canvas.setFont("Helvetica", 7.1)
    contact = "  ·  ".join(p for p in [brand.get("address"), brand.get("phone"), brand.get("email")] if p)
    canvas.drawString(x, page_h - 0.50 * inch, contact[:118])
    extras = []
    if brand.get("license"):
        extras.append(f"License {brand['license']}")
    if brand.get("owner"):
        extras.append(f"Principal {brand['owner']}")
    if extras:
        canvas.drawString(x, page_h - 0.64 * inch, "  ·  ".join(extras)[:118])
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawRightString(page_w - margin_x, page_h - 0.34 * inch, title[:42])
    canvas.setFont("Helvetica", 7.3)
    canvas.drawRightString(page_w - margin_x, page_h - 0.50 * inch, "Reporting Center")
    canvas.drawRightString(page_w - margin_x, page_h - 0.64 * inch, period_label_text[:48])
    canvas.setFillColor(SOFT)
    canvas.rect(0, 0, page_w, 0.42 * inch, fill=1, stroke=0)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.4)
    canvas.line(margin_x, 0.42 * inch, page_w - margin_x, 0.42 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.3)
    stamp = timezone.localtime().strftime("%b %d, %Y  %I:%M %p")
    canvas.drawString(margin_x, 0.18 * inch, f"Official agency record  ·  Prepared {stamp} by {prepared_by}")
    canvas.drawRightString(page_w - margin_x, 0.18 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(org, *, title, subtitle, period, prepared_by, flowables, landscape_mode=True) -> bytes:
    brand = agency_branding(org)
    page = landscape(letter) if landscape_mode else letter
    page_w, page_h = page
    margin_x = 0.5 * inch if landscape_mode else 0.62 * inch
    margin_top = 1.18 * inch
    margin_bottom = 0.58 * inch
    content_w = page_w - (margin_x * 2)
    styles = _styles()
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=page,
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=margin_top,
        bottomMargin=margin_bottom,
        title=f"{title} — {brand['name']}",
        author=brand["name"],
    )
    frame = Frame(margin_x, margin_bottom, content_w, page_h - margin_top - margin_bottom, id="body", showBoundary=0)
    doc.addPageTemplates([
        PageTemplate(
            id="report",
            frames=[frame],
            onPage=lambda c, d: _header_footer(c, d, brand, title, period, prepared_by, page_w, page_h, margin_x),
        )
    ])
    story = [_p(title, styles["title"]), _p(subtitle, styles["subtitle"]), Spacer(1, 8)]
    story.extend(flowables)
    story.append(Spacer(1, 14))
    story.append(_p("End of report. Letterhead uses Insurance Space branding (logo, address, phone, email, license).", styles["footer"]))
    doc.build(story)
    return buffer.getvalue()


def kpi_row(pairs, styles, content_w):
    col_w = content_w / max(len(pairs), 1)
    cells = [
        Table([[_p(label, styles["kpi_l"])], [_p(value, styles["kpi_v"])]], colWidths=[col_w - 6])
        for label, value in pairs
    ]
    table = Table([cells], colWidths=[col_w] * len(pairs))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def data_table(headers, rows, col_widths, styles, header_color=NAVY):
    head = [_p(h, styles["th_r"] if str(h).endswith("$") or h in {"Amount", "Premium", "Commission", "Unearned", "Collected", "Due"} else styles["th"]) for h in headers]
    data = [head]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            style = styles["body_r"] if i == len(row) - 1 and headers[i] in {"Amount", "Premium", "Commission", "Unearned", "Collected", "Due", "Count"} else styles["body"]
            if i == 0:
                style = styles["body_b"]
            cells.append(cell if hasattr(cell, "wrapOn") else _p(cell, style))
        data.append(cells)
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
    ]))
    return table


def notice_box(text, styles, width):
    table = Table([[Paragraph(text, styles["notice"])]], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("BOX", (0, 0), (-1, -1), 0.6, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _content_w(landscape_mode=True):
    page = landscape(letter) if landscape_mode else letter
    margin = 0.5 * inch if landscape_mode else 0.62 * inch
    return page[0] - (margin * 2)


def _filter_receipts(org, start=None, end=None, company_id=None, day=None):
    qs = DailyPaymentTransaction.objects.filter(organization=org).select_related(
        "client", "insurance_company", "insurance_policy", "recorded_by"
    )
    if day:
        qs = qs.filter(transaction_date=day)
    if start:
        qs = qs.filter(transaction_date__gte=start)
    if end:
        qs = qs.filter(transaction_date__lte=end)
    if company_id:
        qs = qs.filter(insurance_company_id=company_id)
    return qs.order_by("transaction_date", "id")


def _policies(org):
    return InsurancePolicy.objects.filter(organization=org).select_related(
        "client", "insurance_company", "added_by"
    )


def render_remittance_pdf(org, *, start=None, end=None, company_id=None, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(True)
    receipts = list(_filter_receipts(org, start, end, company_id))
    grouped = defaultdict(list)
    for tx in receipts:
        key = tx.insurance_company_id or 0
        grouped[key].append(tx)
    total = sum((tx.amount for tx in receipts), ZERO)
    flow = [
        kpi_row([
            ("Receipts", str(len(receipts))),
            ("Collected for carriers", _money(total)),
            ("Carriers in pack", str(len(grouped))),
        ], styles, width),
        Spacer(1, 8),
        notice_box(
            "<b>Carrier remittance pack.</b> Present this with copies of receipts as evidence that premiums "
            "were collected by this agency for the named insurance companies during the period shown.",
            styles,
            width,
        ),
        Spacer(1, 10),
    ]
    if not receipts:
        flow.append(_p("No receipts in this period.", styles["muted"]))
    for company_key, rows in sorted(grouped.items(), key=lambda item: (item[1][0].insurance_company.name if item[1][0].insurance_company_id else "zzz")):
        company = rows[0].insurance_company
        name = company.name if company else "Unassigned carrier"
        license_no = company.license_number if company else ""
        subtotal = sum((tx.amount for tx in rows), ZERO)
        flow.append(_p(f"{name}  ·  {len(rows)} receipt(s)  ·  {_money(subtotal)}" + (f"  ·  License {license_no}" if license_no else ""), styles["section"]))
        flow.append(Spacer(1, 4))
        table_rows = []
        for tx in rows:
            table_rows.append([
                f"PMT-{tx.id:06d}",
                tx.transaction_date.strftime("%m/%d/%Y"),
                tx.client.name if tx.client_id else "—",
                tx.get_payment_type_display(),
                tx.get_payment_method_display(),
                "Cleared" if tx.is_cleared else "Held",
                _money(tx.amount),
            ])
        flow.append(data_table(
            ["Ref #", "Date", "Insured", "Type", "Method", "Status", "Amount"],
            table_rows,
            [0.95*inch, 0.9*inch, 2.2*inch, 1.4*inch, 1.2*inch, 0.9*inch, 1.0*inch],
            styles,
            header_color=TEAL,
        ))
        flow.append(Spacer(1, 12))
    return build_pdf(
        org,
        title="Carrier remittance pack",
        subtitle="Evidence of premiums collected, grouped by insurance company, for remittance and audit packages.",
        period=period_label(start, end),
        prepared_by=prepared_by,
        flowables=flow,
        landscape_mode=True,
    )


def render_payment_receipt_pdf(org, payment: DailyPaymentTransaction, *, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(False)
    payer = payment.client.name if payment.client_id else "—"
    carrier = payment.insurance_company.name if payment.insurance_company_id else "—"
    policy_no = payment.insurance_policy.policy_number if payment.insurance_policy_id else "—"
    recorded = ""
    if payment.recorded_by_id:
        recorded = payment.recorded_by.get_full_name() or payment.recorded_by.username
    words = dollars_to_words(payment.amount)
    pairs = [
        ("Receipt number", f"PMT-{payment.id:06d}"),
        ("Date received", payment.transaction_date.strftime("%B %d, %Y")),
        ("Payer / insured", payer),
        ("Insurance company", carrier),
        ("Policy number", policy_no),
        ("Payment type", payment.get_payment_type_display()),
        ("Method", payment.get_payment_method_display()),
        ("Clearing status", "Cleared / deposited" if payment.is_cleared else "Held — undeposited"),
        ("Received by", recorded or "—"),
        ("Notes", payment.notes or "—"),
    ]
    rows = [[_p(label, styles["body"]), _p(value, styles["body_b"])] for label, value in pairs]
    detail = Table(rows, colWidths=[2.1 * inch, width - 2.1 * inch])
    detail.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), SOFT),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow = [
        _p("OFFICIAL PAYMENT RECEIPT", styles["section"]),
        Spacer(1, 6),
        _p(_money(payment.amount), styles["amount"]),
        _p(f"{words} dollars", styles["muted"]),
        Spacer(1, 10),
        detail,
        Spacer(1, 10),
        notice_box(
            "<b>Proof of payment.</b> This agency acknowledges receipt of the amount shown from the named insured. "
            "This is not a policy or a binder. Coverage is determined solely by the insurance company. "
            "Keep this receipt with your records.",
            styles,
            width,
        ),
    ]
    return build_pdf(
        org,
        title="Payment receipt",
        subtitle="Branded evidence of funds received in Insurance Space Daily Payments.",
        period=payment.transaction_date.strftime("%b %d, %Y"),
        prepared_by=prepared_by,
        flowables=flow,
        landscape_mode=False,
    )


def render_agent_production_pdf(org, *, start=None, end=None, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(True)
    policies = _policies(org)
    memberships = OrganizationMembership.objects.filter(
        organization=org, can_deal_with_insurance=True, is_active=True, user__is_active=True
    ).select_related("user")
    stats, best = build_agent_stats(policies, memberships, start, end)
    rows = []
    for row in stats:
        rows.append([
            row["fullname"],
            str(row["quotes_count"]),
            str(row["policies_bound"]),
            _money(row["total_premium"]),
            _money(row["total_commission"]),
            _money(row["total_broker_fee"]),
            _money(row["total_profit"]),
        ])
    flow = [
        kpi_row([
            ("Producers", str(len(stats))),
            ("Bound policies", str(sum(s["policies_bound"] for s in stats))),
            ("Premium", _money(sum((s["total_premium"] for s in stats), ZERO))),
            ("Best producer", best["fullname"] if best else "—"),
        ], styles, width),
        Spacer(1, 10),
        data_table(
            ["Producer", "Quotes", "Bound", "Premium", "Commission", "Broker fee", "Profit"],
            rows or [["—", "0", "0", "$0.00", "$0.00", "$0.00", "$0.00"]],
            [2.2*inch, 0.8*inch, 0.8*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1.15*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="Producer production report",
        subtitle="Quotes, binds, premium, commission, and broker fee by insurance agent for coaching and payroll.",
        period=period_label(start, end),
        prepared_by=prepared_by,
        flowables=flow,
    )


def render_unearned_pdf(org, *, start=None, end=None, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(True)
    policies = list(_policies(org).filter(stage__in=InsurancePolicy.BOUND_STAGES, status="inactive"))
    if start:
        policies = [p for p in policies if p.inactive_date and p.inactive_date >= start]
    if end:
        policies = [p for p in policies if p.inactive_date and p.inactive_date <= end]
    companies = InsuranceCompany.objects.filter(organization=org)
    refunds = BankTransaction.objects.filter(insurance_company__in=companies)
    if start:
        refunds = refunds.filter(date__gte=start)
    if end:
        refunds = refunds.filter(date__lte=end)
    refunds = list(refunds)
    rows = []
    total_raw = ZERO
    total_adj = ZERO
    for company in companies:
        company_pols = [p for p in policies if p.insurance_company_id == company.id]
        company_pols.sort(key=lambda p: (p.inactive_date or p.start_date, p.id))
        company_refunded = refund_total([t for t in refunds if t.insurance_company_id == company.id])
        adjusted = build_adjusted_unearned_map(company_pols, company_refunded)
        for p in company_pols:
            raw = policy_unearned_commission(p)
            adj = adjusted.get(p.id, raw)
            total_raw += raw
            total_adj += adj
            rows.append([
                p.client.name if p.client_id else "—",
                p.policy_number,
                company.name,
                (p.inactive_date or p.start_date).strftime("%m/%d/%Y") if (p.inactive_date or p.start_date) else "—",
                _money(p.commission_amount),
                _money(raw),
                _money(adj),
            ])
    flow = [
        kpi_row([
            ("Cancelled policies", str(len(rows))),
            ("Gross unearned", _money(total_raw)),
            ("After refunds applied", _money(total_adj)),
        ], styles, width),
        Spacer(1, 8),
        notice_box(
            "<b>Unearned commission statement.</b> Amounts due back after cancellation, after FIFO application of "
            "commission refund bank postings. Use with carrier statements and the general ledger.",
            styles,
            width,
        ),
        Spacer(1, 10),
        data_table(
            ["Insured", "Policy #", "Carrier", "Inactive", "Commission", "Unearned", "Adjusted"],
            rows or [["—", "—", "—", "—", "$0.00", "$0.00", "$0.00"]],
            [1.7*inch, 1.2*inch, 1.5*inch, 0.9*inch, 1.1*inch, 1.1*inch, 1.05*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="Unearned commission statement",
        subtitle="Cancelled / inactive policies and commission due back after refunds.",
        period=period_label(start, end, "All inactive policies"),
        prepared_by=prepared_by,
        flowables=flow,
    )


def render_cashout_pdf(org, *, day: date, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(False)
    receipts = list(_filter_receipts(org, day=day))
    method_cards, grand = summarize_daily_payments(receipts)
    cleared = sum((tx.amount for tx in receipts if tx.is_cleared), ZERO)
    held = grand - cleared
    rows = []
    for tx in receipts:
        rows.append([
            f"PMT-{tx.id:06d}",
            tx.client.name if tx.client_id else "—",
            tx.insurance_company.name if tx.insurance_company_id else "—",
            tx.get_payment_method_display(),
            "Cleared" if tx.is_cleared else "Held",
            _money(tx.amount),
        ])
    method_rows = [[card["label"], _money(card["total"])] for card in method_cards]
    flow = [
        kpi_row([
            ("Receipts", str(len(receipts))),
            ("Day total", _money(grand)),
            ("To deposit (held)", _money(held)),
            ("Already cleared", _money(cleared)),
        ], styles, width),
        Spacer(1, 8),
        notice_box(
            f"<b>Daily cash-out / deposit slip</b> for {day.strftime('%A, %B %d, %Y')}. "
            "Take held cash and checks to the bank with this page. Electronic tenders are listed for reconciling.",
            styles,
            width,
        ),
        Spacer(1, 10),
        _p("Tender recap", styles["section"]),
        Spacer(1, 4),
        data_table(["Method", "Amount"], method_rows, [3.4*inch, 3.4*inch], styles, header_color=TEAL),
        Spacer(1, 10),
        _p("Receipts", styles["section"]),
        Spacer(1, 4),
        data_table(
            ["Ref #", "Insured", "Carrier", "Method", "Status", "Amount"],
            rows or [["—", "—", "—", "—", "—", "$0.00"]],
            [0.95*inch, 1.5*inch, 1.4*inch, 0.9*inch, 0.8*inch, 0.85*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="Daily cash-out",
        subtitle="One-day deposit slip for cash, checks, Zelle, and cards collected in Insurance Space.",
        period=day.strftime("%b %d, %Y"),
        prepared_by=prepared_by,
        flowables=flow,
        landscape_mode=False,
    )


def render_book_of_business_pdf(org, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(True)
    policies = list(_policies(org).filter(stage__in=InsurancePolicy.BOUND_STAGES, status="active"))
    by_type = defaultdict(lambda: {"count": 0, "premium": ZERO, "commission": ZERO})
    by_company = defaultdict(lambda: {"count": 0, "premium": ZERO, "name": ""})
    rows = []
    for p in policies:
        key = p.insurance_type or "unspecified"
        by_type[key]["count"] += 1
        by_type[key]["premium"] += p.premium
        by_type[key]["commission"] += p.commission_amount
        ck = p.insurance_company_id or 0
        by_company[ck]["count"] += 1
        by_company[ck]["premium"] += p.premium
        by_company[ck]["name"] = p.insurance_company.name if p.insurance_company_id else "—"
        rows.append([
            p.client.name if p.client_id else "—",
            p.policy_number,
            p.insurance_company.name if p.insurance_company_id else "—",
            p.get_insurance_type_display() if p.insurance_type else "—",
            p.start_date.strftime("%m/%d/%Y") if p.start_date else "—",
            p.end_date.strftime("%m/%d/%Y") if p.end_date else "—",
            _money(p.premium),
        ])
    type_rows = []
    labels = dict(InsurancePolicy.INSURANCE_TYPE_CHOICES)
    for key, bucket in sorted(by_type.items(), key=lambda i: -i[1]["premium"]):
        type_rows.append([labels.get(key, key.replace("_", " ").title()), str(bucket["count"]), _money(bucket["premium"]), _money(bucket["commission"])])
    company_rows = [
        [b["name"], str(b["count"]), _money(b["premium"])]
        for b in sorted(by_company.values(), key=lambda i: -i["premium"])
    ]
    total_prem = sum((p.premium for p in policies), ZERO)
    flow = [
        kpi_row([
            ("Active policies", str(len(policies))),
            ("Premium in force", _money(total_prem)),
            ("Carriers", str(len(by_company))),
            ("Lines of business", str(len(by_type))),
        ], styles, width),
        Spacer(1, 10),
        _p("By line of business", styles["section"]),
        Spacer(1, 4),
        data_table(["Line", "Policies", "Premium", "Commission"], type_rows or [["—", "0", "$0.00", "$0.00"]], [3.5*inch, 1.2*inch, 1.8*inch, 1.8*inch], styles, header_color=TEAL),
        Spacer(1, 10),
        _p("By carrier", styles["section"]),
        Spacer(1, 4),
        data_table(["Carrier", "Policies", "Premium"], company_rows or [["—", "0", "$0.00"]], [5.2*inch, 1.5*inch, 1.6*inch], styles),
        Spacer(1, 10),
        _p("Active policy register", styles["section"]),
        Spacer(1, 4),
        data_table(
            ["Insured", "Policy #", "Carrier", "Type", "Effective", "Expiration", "Premium"],
            rows[:200] or [["—", "—", "—", "—", "—", "—", "$0.00"]],
            [1.6*inch, 1.2*inch, 1.5*inch, 1.4*inch, 0.9*inch, 0.95*inch, 1.0*inch],
            styles,
        ),
    ]
    if len(rows) > 200:
        flow.append(Spacer(1, 6))
        flow.append(_p(f"Showing first 200 of {len(rows)} active policies.", styles["muted"]))
    return build_pdf(
        org,
        title="Book of business snapshot",
        subtitle="In-force bound policies by line and carrier as of today.",
        period=timezone.localdate().strftime("%b %d, %Y"),
        prepared_by=prepared_by,
        flowables=flow,
    )


def render_aging_pdf(org, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(True)
    today = timezone.localdate()
    rows_qs = (
        InsurancePolicyInstallment.objects.filter(
            policy__organization=org,
            is_paid=False,
            policy__stage__in=InsurancePolicy.BOUND_STAGES,
        )
        .select_related("policy__client", "policy__insurance_company")
        .order_by("due_date")
    )
    buckets = {"Current": ZERO, "1–30 past due": ZERO, "31–60 past due": ZERO, "61+ past due": ZERO}
    table_rows = []
    for row in rows_qs:
        days = (today - row.due_date).days
        if days <= 0:
            bucket = "Current"
        elif days <= 30:
            bucket = "1–30 past due"
        elif days <= 60:
            bucket = "31–60 past due"
        else:
            bucket = "61+ past due"
        buckets[bucket] += row.total_due
        table_rows.append([
            row.policy.client.name if row.policy.client_id else "—",
            row.policy.policy_number,
            row.policy.insurance_company.name if row.policy.insurance_company_id else "—",
            row.display_number,
            row.due_date.strftime("%m/%d/%Y"),
            bucket,
            _money(row.total_due),
        ])
    flow = [
        kpi_row([(label, _money(amount)) for label, amount in buckets.items()], styles, width),
        Spacer(1, 10),
        data_table(
            ["Insured", "Policy #", "Carrier", "Inst.", "Due", "Aging", "Due"],
            table_rows or [["—", "—", "—", "—", "—", "—", "$0.00"]],
            [1.7*inch, 1.2*inch, 1.6*inch, 0.7*inch, 0.9*inch, 1.3*inch, 1.05*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="Installment aging",
        subtitle="Unpaid policy installments: current vs past due buckets for collections follow-up.",
        period=today.strftime("%b %d, %Y"),
        prepared_by=prepared_by,
        flowables=flow,
    )


def render_quote_conversion_pdf(org, *, start=None, end=None, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(True)
    leads = InsuranceQuoteLead.objects.filter(organization=org).select_related("assigned_to__user")
    if start:
        leads = leads.filter(created_at__date__gte=start)
    if end:
        leads = leads.filter(created_at__date__lte=end)
    leads = list(leads)
    by_stage = defaultdict(int)
    by_agent = defaultdict(lambda: defaultdict(int))
    for lead in leads:
        stage = lead.stage if lead.stage != InsuranceQuoteLead.Stage.NEW else InsuranceQuoteLead.Stage.ASSIGNED
        by_stage[stage] += 1
        agent = "Unassigned"
        if lead.assigned_to_id:
            agent = lead.assigned_to.user.get_full_name() or lead.assigned_to.user.username
        by_agent[agent][stage] += 1
        by_agent[agent]["total"] += 1
    won = by_stage.get("won", 0)
    lost = by_stage.get("lost", 0)
    closed = won + lost
    conv = f"{(won / closed * 100):.1f}%" if closed else "—"
    stage_keys = ["assigned", "quoting", "quoted", "won", "lost"]
    stage_rows = [[dict(InsuranceQuoteLead.Stage.choices).get(k, k).title(), str(by_stage.get(k, 0))] for k in stage_keys]
    agent_rows = []
    for agent, counts in sorted(by_agent.items(), key=lambda i: -i[1]["total"]):
        a_won = counts.get("won", 0)
        a_lost = counts.get("lost", 0)
        a_closed = a_won + a_lost
        agent_rows.append([
            agent,
            str(counts["total"]),
            str(counts.get("quoting", 0)),
            str(counts.get("quoted", 0)),
            str(a_won),
            str(a_lost),
            f"{(a_won / a_closed * 100):.0f}%" if a_closed else "—",
        ])
    flow = [
        kpi_row([
            ("Leads", str(len(leads))),
            ("Won", str(won)),
            ("Lost", str(lost)),
            ("Close rate", conv),
        ], styles, width),
        Spacer(1, 10),
        _p("Pipeline by stage", styles["section"]),
        Spacer(1, 4),
        data_table(["Stage", "Count"], stage_rows, [4.5*inch, 2*inch], styles, header_color=TEAL),
        Spacer(1, 10),
        _p("Conversion by producer", styles["section"]),
        Spacer(1, 4),
        data_table(
            ["Producer", "Leads", "Quoting", "Quoted", "Won", "Lost", "Close %"],
            agent_rows or [["—", "0", "0", "0", "0", "0", "—"]],
            [2.2*inch, 0.9*inch, 1.0*inch, 1.0*inch, 0.8*inch, 0.8*inch, 0.9*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="Quote pipeline conversion",
        subtitle="Assigned → quoting → quoted → won/lost, overall and by producer.",
        period=period_label(start, end),
        prepared_by=prepared_by,
        flowables=flow,
    )


def render_compliance_pdf(org, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(False)
    today = timezone.localdate()
    companies = list(InsuranceCompany.objects.filter(organization=org).order_by("name"))
    rows = []
    expired = expiring = missing = 0
    for company in companies:
        status = company_license_status(company, today=today)
        if status["state"] == "expired":
            expired += 1
        elif status["state"] == "expiring":
            expiring += 1
        elif status["state"] == "missing":
            missing += 1
        exp = status["expiration_date"].strftime("%m/%d/%Y") if status["expiration_date"] else "—"
        rows.append([
            company.name,
            status["license_number"] or "—",
            exp,
            status["label"],
        ])
    psb_exp = org.psbc_license_expiration_date.strftime("%m/%d/%Y") if org.psbc_license_expiration_date else "Not on file"
    flow = [
        kpi_row([
            ("Carriers", str(len(companies))),
            ("Expired", str(expired)),
            ("Expiring soon", str(expiring)),
            ("Dates missing", str(missing)),
        ], styles, width),
        Spacer(1, 8),
        notice_box(
            f"<b>Agency license.</b> PSBC No. {_safe(org.psbc_license, 'not on file')}  ·  "
            f"Expires {psb_exp}. Renew before expiration to keep receipts and filings valid.",
            styles,
            width,
        ),
        Spacer(1, 10),
        data_table(
            ["Carrier", "License #", "Expiration", "Status"],
            rows or [["—", "—", "—", "—"]],
            [2.1*inch, 1.3*inch, 1.1*inch, 2.3*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="License & compliance calendar",
        subtitle="Carrier appointments/licenses and the agency PSB license, with renewal alerts.",
        period=today.strftime("%b %d, %Y"),
        prepared_by=prepared_by,
        flowables=flow,
        landscape_mode=False,
    )


def render_targets_pdf(org, *, year: int, month: int, prepared_by="Staff") -> bytes:
    styles = _styles()
    width = _content_w(True)
    dash = build_insurance_targets_dashboard(org, _policies(org), year=year, month=month)
    mt = dash.get("monthly_target") or {}
    totals = dash.get("totals") or {}
    rows = []
    for card in dash.get("line_cards") or []:
        if not card.get("is_active") and not card["binds"] and not card["quotes"]:
            continue
        rows.append([
            card["label"],
            str(card["quotes"]),
            str(card["binds"]),
            _money(card["premium_actual"]),
            _money(card["premium_target"]),
            f"{card['progress_pct']}%",
            _money(card["premium_gap"]),
        ])
    insights = dash.get("insights") or []
    flow = [
        kpi_row([
            ("Premium actual", _money(totals.get("premium_actual", 0))),
            ("Premium target", _money(mt.get("premium_target", 0))),
            ("Commission actual", _money(totals.get("commission_actual", 0))),
            ("Commission target", _money(mt.get("commission_target", 0))),
        ], styles, width),
        Spacer(1, 8),
    ]
    if insights:
        flow.append(notice_box("<br/>".join(f"• {item}" for item in insights[:4]), styles, width))
        flow.append(Spacer(1, 10))
    flow.append(data_table(
        ["Line of business", "Quotes", "Binds", "Actual $", "Target $", "Pace", "Gap"],
        rows or [["—", "0", "0", "$0.00", "$0.00", "—", "$0.00"]],
        [2.2*inch, 0.8*inch, 0.8*inch, 1.2*inch, 1.2*inch, 0.8*inch, 1.15*inch],
        styles,
    ))
    month_name = date(year, month, 1).strftime("%B %Y")
    return build_pdf(
        org,
        title="Targets vs actual",
        subtitle="Monthly premium and commission goals against binds and quotes, by line of business.",
        period=month_name,
        prepared_by=prepared_by,
        flowables=flow,
    )


def render_commission_production_pdf(org, *, start=None, end=None, prepared_by="Staff") -> bytes:
    """Cleaner replacement-style commission register used alongside the legacy canvas report."""
    styles = _styles()
    width = _content_w(True)
    policies = list(_policies(org))
    if start:
        policies = [p for p in policies if p.start_date and p.start_date >= start]
    if end:
        policies = [p for p in policies if p.start_date and p.start_date <= end]
    active = [p for p in policies if p.stage in InsurancePolicy.BOUND_STAGES and p.status == "active"]
    rows = []
    for p in policies:
        rows.append([
            p.client.name if p.client_id else "—",
            p.policy_number,
            p.insurance_company.name if p.insurance_company_id else "—",
            f"{p.stage} / {p.status}",
            _money(p.premium),
            f"{p.commission_rate}%",
            _money(p.commission_amount),
        ])
    flow = [
        kpi_row([
            ("Policies in range", str(len(policies))),
            ("Active bound", str(len(active))),
            ("Active premium", _money(sum((p.premium for p in active), ZERO))),
            ("Active commission", _money(sum((p.commission_amount for p in active), ZERO))),
        ], styles, width),
        Spacer(1, 10),
        data_table(
            ["Insured", "Policy #", "Carrier", "Status", "Premium", "Rate", "Commission"],
            rows[:250] or [["—", "—", "—", "—", "$0.00", "—", "$0.00"]],
            [1.7*inch, 1.2*inch, 1.5*inch, 1.2*inch, 1.0*inch, 0.7*inch, 1.15*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="Commission production",
        subtitle="Policy-level premiums and commissions for the selected effective-date range.",
        period=period_label(start, end),
        prepared_by=prepared_by,
        flowables=flow,
    )
