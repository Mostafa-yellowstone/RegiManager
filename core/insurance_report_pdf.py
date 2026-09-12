"""Branded Insurance Space Reporting Center PDFs."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .daily_payments import PAYMENT_METHOD_META, summarize_daily_payments
from .insurance_commissions import build_adjusted_unearned_map, policy_unearned_commission, refund_total
from .insurance_policy_schedule import summarize_insurance_schedule
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
    canvas.drawString(x, page_h - 0.54 * inch, contact[:118])
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


RECEIPT_PRODUCTS = (
    "Home Owners",
    "Business",
    "Taxi",
    "Auto Commercial",
    "Auto Personal",
)

# Featured markets shown as logos on the receipt (order preserved).
# Newer partners first (after GEICO), then existing markets.
RECEIPT_CARRIER_LOGOS = (
    ("geico.png", "GEICO"),
    ("allstate.png", "Allstate"),
    ("nycm.png", "NYCM"),
    ("21st_century.png", "21st Century"),
    ("progressive.png", "Progressive"),
    ("plymouth_rock.png", "Plymouth Rock"),
    ("tapco.png", "Tapco"),
    ("next.png", "Next"),
    ("foremost.png", "Foremost"),
    ("travelers.png", "Travelers"),
    ("biberk.png", "biBERK"),
    ("hagerty.png", "Hagerty"),
    ("national_general.png", "National General"),
    ("maya.png", "Maya Assurance"),
    ("lancer.png", "Lancer Insurance"),
    ("hereford.png", "Hereford"),
    ("kingstone.png", "Kingstone"),
    ("american_transit.png", "American Transit"),
    ("attune.png", "Attune"),
)

RECEIPT_PRODUCT_TITLE = "Protect What Matters Most"
RECEIPT_CARRIERS_TITLE = "Carriers We Proudly Work With"
RECEIPT_SLOGAN = "We are the driving force behind the insurance industry"


def _receipt_amount_words(amount) -> str:
    """Amount in words with dollars and cents fully spelled out."""
    value = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    dollars = int(value)
    cents = int((value - Decimal(dollars)) * 100)
    dollar_words = dollars_to_words(dollars)
    dollar_label = "Dollar" if dollars == 1 else "Dollars"
    if cents == 0:
        return f"{dollar_words} {dollar_label} Exactly"
    cent_words = dollars_to_words(cents)
    cent_label = "Cent" if cents == 1 else "Cents"
    return f"{dollar_words} {dollar_label} and {cent_words} {cent_label}"


def _payment_fee_breakdown(payment: DailyPaymentTransaction) -> dict:
    """Payment amount plus optional Section 2119 / broker / credit-card fees and grand total."""
    base = Decimal(str(payment.amount or 0)).quantize(Decimal("0.01"))
    section = ZERO
    if payment.payment_type in (
        DailyPaymentTransaction.PaymentType.NEW_BUSINESS,
        DailyPaymentTransaction.PaymentType.RENEWAL,
    ):
        raw = getattr(payment, "section_2119", None)
        if raw is not None and raw > 0:
            section = Decimal(str(raw)).quantize(Decimal("0.01"))
    broker_fee = ZERO
    raw_broker = getattr(payment, "broker_fee", None)
    if raw_broker is not None and raw_broker > 0:
        broker_fee = Decimal(str(raw_broker)).quantize(Decimal("0.01"))
    cc_fee = ZERO
    raw_cc = getattr(payment, "credit_card_fee", None)
    if raw_cc is not None and raw_cc > 0:
        cc_fee = Decimal(str(raw_cc)).quantize(Decimal("0.01"))
    return {
        "base": base,
        "section_2119": section,
        "broker_fee": broker_fee,
        "credit_card_fee": cc_fee,
        "total": base + section + broker_fee + cc_fee,
        "has_section_2119": section > 0,
        "has_broker_fee": broker_fee > 0,
        "has_credit_card_fee": cc_fee > 0,
        "has_fees": section > 0 or broker_fee > 0 or cc_fee > 0,
    }


def apply_daily_payment_receipt_fields(payment: DailyPaymentTransaction, post) -> None:
    """Copy receipt schedule fields from an add/edit payment form POST."""
    from datetime import datetime as dt_parse

    payment.coverage = (post.get("coverage") or "").strip()[:120]

    def _optional_decimal(key: str):
        raw = (post.get(key) or "").strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except Exception:
            return None

    if getattr(payment, "payment_type", "") in (
        DailyPaymentTransaction.PaymentType.NEW_BUSINESS,
        DailyPaymentTransaction.PaymentType.RENEWAL,
    ):
        payment.section_2119 = _optional_decimal("section_2119")
    else:
        payment.section_2119 = None

    due_raw = (post.get("next_payment_due") or "").strip()
    if due_raw:
        try:
            payment.next_payment_due = dt_parse.strptime(due_raw, "%Y-%m-%d").date()
        except ValueError:
            payment.next_payment_due = None
    else:
        payment.next_payment_due = None

    payment.next_payment_amount = _optional_decimal("next_payment_amount")
    payment.remaining_amount = _optional_decimal("remaining_amount")
    payment.broker_fee = _optional_decimal("broker_fee")
    payment.credit_card_fee = _optional_decimal("credit_card_fee")

    rem_raw = (post.get("remaining_payments") or "").strip()
    if rem_raw:
        try:
            payment.remaining_payments = max(0, int(rem_raw))
        except ValueError:
            payment.remaining_payments = None
    else:
        payment.remaining_payments = None


def _payment_schedule_info(payment: DailyPaymentTransaction) -> dict:
    """Next due / remaining balance — prefer values saved on the payment, else schedule."""
    info = {
        "next_due_date": "—",
        "next_due_amount": "—",
        "remaining_amount": "—",
        "remaining_payments": "—",
    }
    policy = _match_policy_for_payment(payment)
    unpaid_count = None
    if policy:
        summary = summarize_insurance_schedule(policy)
        unpaid = [r for r in summary["installments"] if not r.is_paid]
        unpaid_count = len(unpaid)
        remaining = sum((r.total_due for r in unpaid), ZERO)
        next_date = summary["next_due_date"]
        next_amount = summary["next_due_amount"]
        info["next_due_date"] = next_date.strftime("%b %d, %Y") if next_date else "—"
        info["next_due_amount"] = _money(next_amount) if next_amount is not None else "—"
        info["remaining_amount"] = _money(remaining) if unpaid else "$0.00"
        info["remaining_payments"] = str(unpaid_count)

    if payment.next_payment_due:
        info["next_due_date"] = payment.next_payment_due.strftime("%b %d, %Y")
    if payment.next_payment_amount is not None:
        info["next_due_amount"] = _money(payment.next_payment_amount)
    if payment.remaining_amount is not None:
        info["remaining_amount"] = _money(payment.remaining_amount)
    if payment.remaining_payments is not None:
        info["remaining_payments"] = str(payment.remaining_payments)
    elif unpaid_count is None:
        info["remaining_payments"] = "—"
    return info


def _receipt_address_lines(brand: dict) -> list[str]:
    """Street address for payment receipt header/footer (two lines for Xpress)."""
    name = (brand.get("name") or "").lower()
    addr = (brand.get("address") or "").lower()
    if "xpress" in name or "yonkers" in addr or not (brand.get("address") or "").strip():
        return ["787 Yonkers Ave,", "Yonkers, NY, 10704"]
    # Keep multi-line if branding already has newlines; else one line.
    raw = (brand.get("address") or "").strip()
    parts = [p.strip() for p in raw.replace("\r", "").split("\n") if p.strip()]
    return parts or [raw]


def _carrier_logo_path(filename: str) -> str | None:
    from django.conf import settings

    path = Path(settings.BASE_DIR) / "static" / "core" / "img" / "carriers" / filename
    if path.is_file() and path.stat().st_size > 0:
        return str(path)
    return None


def _receipt_sticker_path() -> str | None:
    from django.conf import settings

    path = Path(settings.BASE_DIR) / "static" / "core" / "img" / "receipt_protection_sticker.png"
    if path.is_file() and path.stat().st_size > 0:
        return str(path)
    return None


def _receipt_qr_path() -> str | None:
    from django.conf import settings

    path = Path(settings.BASE_DIR) / "static" / "core" / "img" / "receipt_contact_qr.png"
    if path.is_file() and path.stat().st_size > 0:
        return str(path)
    return None


def _scaled_image(path: str, max_w: float, max_h: float | None = None):
    """Load a proportional ReportLab image capped to max width/height."""
    from reportlab.lib.utils import ImageReader

    reader = ImageReader(path)
    iw, ih = reader.getSize()
    if not iw or not ih:
        return None
    aspect = ih / float(iw)
    w = max_w
    h = w * aspect
    if max_h is not None and h > max_h:
        h = max_h
        w = h / aspect
    img = RLImage(path, width=w, height=h, kind="proportional")
    img.hAlign = "CENTER"
    return img


def _closing_brand_strip(content_w: float, styles: dict) -> Table | None:
    """Sticker + contact QR side-by-side — light closing strip, not a heavy card."""
    sticker_path = _receipt_sticker_path()
    qr_path = _receipt_qr_path()
    if not sticker_path and not qr_path:
        return None

    col_gap = 10
    half = (content_w - col_gap) / 2
    cells = []

    if sticker_path:
        try:
            sticker = _scaled_image(sticker_path, max_w=min(half * 0.88, 1.85 * inch), max_h=1.15 * inch)
        except Exception:
            sticker = None
        if sticker:
            left = Table([[sticker]], colWidths=[half])
            left.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            cells.append(left)

    if qr_path:
        try:
            qr = _scaled_image(qr_path, max_w=min(half * 0.72, 1.25 * inch), max_h=1.25 * inch)
        except Exception:
            qr = None
        if qr:
            right = Table([[qr]], colWidths=[half])
            right.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            cells.append(right)

    if not cells:
        return None
    if len(cells) == 1:
        row = Table([[cells[0]]], colWidths=[content_w])
    else:
        row = Table([cells], colWidths=[half, half])
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return row


def _match_policy_for_payment(payment: DailyPaymentTransaction, policy_number: str = ""):
    """Prefer linked policy, then exact policy number, then best client/company match."""
    if payment.insurance_policy_id:
        return payment.insurance_policy
    number = (policy_number or getattr(payment, "policy_number", "") or "").strip()
    base = InsurancePolicy.objects.filter(organization_id=payment.organization_id)
    if number:
        matched = base.filter(policy_number__iexact=number).first()
        if matched:
            return matched
    if not payment.client_id:
        return None
    qs = base.filter(client_id=payment.client_id)
    if payment.insurance_company_id:
        company_qs = qs.filter(insurance_company_id=payment.insurance_company_id)
        if company_qs.exists():
            qs = company_qs
    return (
        qs.filter(status=InsurancePolicy.StatusChoices.ACTIVE).order_by("-start_date", "-id").first()
        or qs.order_by("-start_date", "-id").first()
    )


def resolve_payment_policy_link(payment: DailyPaymentTransaction, policy_number: str = ""):
    """Attach a matching InsurancePolicy when a policy number is provided."""
    number = (policy_number or "").strip()
    payment.policy_number = number[:100]
    matched = _match_policy_for_payment(payment, number)
    payment.insurance_policy = matched
    if matched and not payment.policy_number:
        payment.policy_number = (matched.policy_number or "")[:100]
    return matched


def _payment_receipt_policy_info(payment: DailyPaymentTransaction) -> dict:
    policy = _match_policy_for_payment(payment)
    typed = (getattr(payment, "policy_number", "") or "").strip()
    number = typed or (policy.policy_number if policy else "") or "—"
    coverage = (getattr(payment, "coverage", "") or "").strip()
    if not coverage and policy and policy.insurance_type:
        coverage = policy.get_insurance_type_display()
    return {
        "number": number,
        "coverage": coverage,
        "policy": policy,
    }


def _policy_spotlight(policy_info: dict, content_w: float, styles: dict) -> Table:
    """Full-width policy number card for the receipt (no status)."""
    number_style = ParagraphStyle(
        "rcpt_polnum",
        parent=styles["value"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        textColor=NAVY,
        leading=13,
        alignment=TA_CENTER,
    )
    tiny = ParagraphStyle(
        "rcpt_tiny",
        parent=styles["label"],
        fontSize=6,
        textColor=MUTED,
        leading=7.5,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    number_card = Table(
        [
            [Paragraph("POLICY NUMBER", tiny)],
            [Paragraph(_safe(policy_info["number"]), number_style)],
        ],
        colWidths=[content_w],
    )
    number_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ECFEFF")),
        ("BOX", (0, 0), (-1, -1), 1.2, TEAL),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#99F6E4")),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return number_card


def _carrier_logo_row(content_w: float) -> Table | None:
    """Even logo grid with equal card sizes — all featured carriers."""
    logos: list[str | None] = []
    for filename, _label in RECEIPT_CARRIER_LOGOS:
        path = _carrier_logo_path(filename)
        if path:
            logos.append(path)
    if not logos:
        return None

    # 4 columns = larger logo tiles that stay readable on a portrait page.
    cols = 4
    gap = 4
    card_w = (content_w - (gap * (cols - 1))) / cols
    card_h = 0.52 * inch
    img_w = card_w - 4
    img_h = card_h - 4

    def _card(path: str | None):
        if not path:
            empty = Table([[""]], colWidths=[card_w], rowHeights=[card_h])
            empty.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
            ]))
            return empty
        try:
            img = RLImage(path, width=img_w, height=img_h, kind="proportional")
            img.hAlign = "CENTER"
            cell = Table([[img]], colWidths=[card_w], rowHeights=[card_h])
            cell.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            return cell
        except Exception:
            return _card(None)

    while len(logos) % cols != 0:
        logos.append(None)

    grid_rows = []
    for i in range(0, len(logos), cols):
        chunk = logos[i:i + cols]
        cards = [_card(p) for p in chunk]
        row = Table([cards], colWidths=[card_w] * cols)
        row.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), gap / 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), gap / 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        grid_rows.append([row])

    wrap = Table(grid_rows, colWidths=[content_w])
    wrap.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return wrap


def render_payment_receipt_pdf(org, payment: DailyPaymentTransaction, *, prepared_by="Staff") -> bytes:
    """Compact one-page branded daily payment receipt with policy badges and carrier logos."""
    brand = agency_branding(org)
    styles_base = getSampleStyleSheet()
    styles = {
        "eyebrow": ParagraphStyle(
            "rcpt_eye", parent=styles_base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.4, textColor=TEAL, leading=9, alignment=TA_CENTER,
        ),
        "amount": ParagraphStyle(
            "rcpt_amt", parent=styles_base["Normal"], fontName="Helvetica-Bold",
            fontSize=22, textColor=NAVY, leading=25, alignment=TA_CENTER,
        ),
        "words": ParagraphStyle(
            "rcpt_words", parent=styles_base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=INK, leading=10, alignment=TA_CENTER,
        ),
        "words_label": ParagraphStyle(
            "rcpt_words_lbl", parent=styles_base["Normal"], fontName="Helvetica",
            fontSize=6, textColor=MUTED, leading=7.5, alignment=TA_CENTER,
        ),
        "label": ParagraphStyle(
            "rcpt_lbl", parent=styles_base["Normal"], fontName="Helvetica",
            fontSize=6.2, textColor=MUTED, leading=7.5,
        ),
        "value": ParagraphStyle(
            "rcpt_val", parent=styles_base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.6, textColor=INK, leading=9,
        ),
        "section": ParagraphStyle(
            "rcpt_sec", parent=styles_base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.8, textColor=NAVY, leading=9.5,
        ),
        "section_c": ParagraphStyle(
            "rcpt_sec_c", parent=styles_base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.8, textColor=NAVY, leading=9.5, alignment=TA_CENTER,
        ),
        "pill": ParagraphStyle(
            "rcpt_pill", parent=styles_base["Normal"], fontName="Helvetica-Bold",
            fontSize=5.8, textColor=WHITE, leading=7.2, alignment=TA_CENTER,
        ),
        "notice": ParagraphStyle(
            "rcpt_note", parent=styles_base["Normal"], fontName="Helvetica",
            fontSize=6.1, textColor=INK, leading=7.8,
        ),
        "footer": ParagraphStyle(
            "rcpt_ft", parent=styles_base["Normal"], fontName="Helvetica",
            fontSize=6, textColor=MUTED, leading=7.6, alignment=TA_CENTER,
        ),
        "slogan": ParagraphStyle(
            "rcpt_slogan", parent=styles_base["Normal"], fontName="Helvetica-Oblique",
            fontSize=7.2, textColor=NAVY, leading=9, alignment=TA_CENTER,
        ),
    }

    page_w, page_h = letter
    margin_x = 0.52 * inch
    content_w = page_w - (margin_x * 2)
    payer = payment.client.name if payment.client_id else "—"
    carrier = payment.insurance_company.name if payment.insurance_company_id else "—"
    policy_info = _payment_receipt_policy_info(payment)
    schedule_info = _payment_schedule_info(payment)
    fees = _payment_fee_breakdown(payment)
    display_total = fees["total"]
    words = _receipt_amount_words(display_total)

    # Hero amount: number + words underneath (check-style)
    amount_inner = Table(
        [
            [Paragraph("AMOUNT PAID", styles["eyebrow"])],
            [Paragraph(_money(display_total), styles["amount"])],
            [HRFlowable(width="42%", thickness=1.0, color=TEAL, spaceBefore=1, spaceAfter=2, hAlign="CENTER")],
            [Paragraph("Amount in words", styles["words_label"])],
            [Paragraph(words, styles["words"])],
        ],
        colWidths=[content_w - 16],
    )
    amount_inner.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (0, 0), 1),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 1),
    ]))
    amount_block = Table([[amount_inner]], colWidths=[content_w])
    amount_block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1.4, NAVY),
        ("LINEABOVE", (0, 0), (-1, 0), 4, TEAL),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    policy_row = _policy_spotlight(policy_info, content_w, styles)

    detail_pairs = [
        ("Date", payment.transaction_date.strftime("%b %d, %Y")),
        ("Payer / insured", payer),
        ("Insurance company", carrier),
        ("Coverage", policy_info["coverage"] or "—"),
        ("Payment type", payment.get_payment_type_display()),
        ("Method", payment.get_payment_method_display()),
        ("Next payment due", schedule_info["next_due_date"]),
        ("Next payment amount", schedule_info["next_due_amount"]),
        ("Remaining amount", schedule_info["remaining_amount"]),
        ("Remaining payments", schedule_info["remaining_payments"]),
        ("Payment amount", _money(fees["base"])),
    ]
    if fees["has_section_2119"]:
        detail_pairs.append(("Section 2119", _money(fees["section_2119"])))
    if fees["has_broker_fee"]:
        detail_pairs.append(("Broker fee", _money(fees["broker_fee"])))
    if fees["has_credit_card_fee"]:
        detail_pairs.append(("Credit card fee", _money(fees["credit_card_fee"])))
    detail_pairs.append(("Total amount", _money(fees["total"])))

    detail_rows = []
    for i in range(0, len(detail_pairs), 2):
        left_lbl, left_val = detail_pairs[i]
        if i + 1 < len(detail_pairs):
            right_lbl, right_val = detail_pairs[i + 1]
        else:
            right_lbl, right_val = "", ""
        detail_rows.append([
            Paragraph(left_lbl, styles["label"]),
            Paragraph(_safe(left_val), styles["value"]),
            Paragraph(right_lbl, styles["label"]) if right_lbl else "",
            Paragraph(_safe(right_val), styles["value"]) if right_lbl else "",
        ])

    col_w = [1.15 * inch, content_w / 2 - 1.15 * inch, 1.15 * inch, content_w / 2 - 1.15 * inch]
    detail_grid = Table(detail_rows, colWidths=col_w)
    detail_grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), SOFT),
        ("BACKGROUND", (2, 0), (2, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))

    # Equal-width navy product cards — no grey subtitle text above them.
    products = list(RECEIPT_PRODUCTS)
    n_products = len(products)
    gap = 4
    pill_w = (content_w - (gap * (n_products - 1))) / n_products
    pills = []
    for product in products:
        pill = Table(
            [[Paragraph(product, styles["pill"])]],
            colWidths=[pill_w],
            rowHeights=[0.26 * inch],
        )
        pill.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        pills.append(pill)
    product_row = Table([pills], colWidths=[pill_w] * n_products)
    product_row.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), gap / 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), gap / 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    logo_row = _carrier_logo_row(content_w)
    market_rows = [
        [Paragraph(RECEIPT_PRODUCT_TITLE, styles["section_c"])],
        [Spacer(1, 3)],
        [product_row],
        [Spacer(1, 5)],
        [Paragraph(RECEIPT_CARRIERS_TITLE, styles["section_c"])],
        [Spacer(1, 3)],
    ]
    if logo_row is not None:
        market_rows.append([logo_row])
    market = Table(market_rows, colWidths=[content_w])
    market.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (0, 0), 5),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    notice = Table(
        [[Paragraph(
            "<b>Proof of payment.</b> This acknowledges receipt of the amount shown. "
            "Not a policy or binder — coverage is set by the insurance company.",
            styles["notice"],
        )]],
        colWidths=[content_w],
    )
    notice.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("BOX", (0, 0), (-1, -1), 0.5, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    address_lines = _receipt_address_lines(brand)
    thank_you = Paragraph(
        f"<b>Thank you for choosing {brand['name']}</b>",
        styles["footer"],
    )
    slogan = Paragraph(f"<i>{RECEIPT_SLOGAN}</i>", styles["slogan"])
    closing = _closing_brand_strip(content_w, styles)

    story_body = [
        Paragraph("OFFICIAL PAYMENT RECEIPT", styles["eyebrow"]),
        Spacer(1, 2),
        amount_block,
        Spacer(1, 4),
        policy_row,
        Spacer(1, 4),
        Paragraph("Transaction details", styles["section"]),
        Spacer(1, 2),
        detail_grid,
        Spacer(1, 3),
        notice,
        Spacer(1, 4),
        market,
    ]
    if closing is not None:
        story_body.extend([
            Spacer(1, 4),
            closing,
            Spacer(1, 3),
        ])
    else:
        story_body.append(Spacer(1, 2))
    story_body.extend([
        HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=2),
        thank_you,
        Spacer(1, 2),
        slogan,
    ])
    # No KeepTogether — avoids forcing a 2nd page when content is tight.
    story = story_body

    buffer = BytesIO()
    top_margin = 1.12 * inch
    bottom_margin = 0.28 * inch
    doc = BaseDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=f"Payment receipt PMT-{payment.id:06d} — {brand['name']}",
        author=brand["name"],
    )

    def _draw_chrome(canvas, doc_):
        canvas.saveState()
        header_h = 0.92 * inch
        canvas.setFillColor(NAVY)
        canvas.rect(0, page_h - header_h, page_w, header_h, fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, page_h - header_h - 0.04 * inch, page_w, 0.04 * inch, fill=1, stroke=0)

        # Slight right inset so the logo/text block sits off the left edge.
        x = margin_x + 0.10 * inch
        logo = brand.get("logo_path")
        if logo:
            try:
                from reportlab.lib.utils import ImageReader

                logo_pad = 0.045 * inch
                max_h = header_h - (logo_pad * 2)
                max_w = 1.35 * inch
                reader = ImageReader(logo)
                iw, ih = reader.getSize()
                aspect = (iw / float(ih)) if ih else 1.0
                logo_h = max_h
                logo_w = logo_h * aspect
                if logo_w > max_w:
                    logo_w = max_w
                    logo_h = logo_w / aspect if aspect else max_h
                logo_y = page_h - header_h + ((header_h - logo_h) / 2.0)
                # Left-anchor so any fit leftover stays on the right, not between logo and text.
                canvas.drawImage(
                    logo,
                    x,
                    logo_y,
                    width=logo_w,
                    height=logo_h,
                    preserveAspectRatio=True,
                    mask="auto",
                    anchor="w",
                )
                x += logo_w + 0.02 * inch
            except Exception:
                pass

        # Match brand-name top with "PAYMENT RECEIPT" (larger font sits a hair lower).
        title_y = page_h - 0.30 * inch
        name_size = 12
        receipt_label_size = 9
        name_y = title_y - ((name_size - receipt_label_size) * 0.72)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", name_size)
        canvas.drawString(x, name_y, brand["name"][:64])
        canvas.setFont("Helvetica", 7)
        line_y = name_y - 0.14 * inch
        for line in address_lines:
            canvas.drawString(x, line_y, line[:90])
            line_y -= 0.115 * inch
        phone_email = "  ·  ".join(p for p in [brand.get("phone"), brand.get("email")] if p)
        if phone_email:
            canvas.drawString(x, line_y, phone_email[:110])

        canvas.setFont("Helvetica-Bold", receipt_label_size)
        canvas.drawRightString(page_w - margin_x, title_y, "PAYMENT RECEIPT")
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(page_w - margin_x, title_y - 0.16 * inch, f"PMT-{payment.id:06d}")
        canvas.drawRightString(
            page_w - margin_x,
            title_y - 0.28 * inch,
            payment.transaction_date.strftime("%b %d, %Y"),
        )
        canvas.restoreState()

    frame = Frame(
        margin_x,
        bottom_margin,
        content_w,
        page_h - top_margin - bottom_margin,
        id="body",
        showBoundary=0,
    )
    doc.addPageTemplates([PageTemplate(id="receipt", frames=[frame], onPage=_draw_chrome)])
    doc.build(story)
    return buffer.getvalue()


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


def render_book_of_business_pdf(org, prepared_by="Staff", start=None, end=None) -> bytes:
    styles = _styles()
    width = _content_w(True)
    policies_qs = _policies(org).filter(stage__in=InsurancePolicy.BOUND_STAGES, status="active")
    if start:
        policies_qs = policies_qs.filter(start_date__gte=start)
    if end:
        policies_qs = policies_qs.filter(start_date__lte=end)
    policies = list(policies_qs)
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
    if start and end:
        period = f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"
        subtitle = "In-force bound policies effective in the selected timeframe."
    elif start:
        period = f"From {start.strftime('%b %d, %Y')}"
        subtitle = "In-force bound policies effective on or after the selected start date."
    elif end:
        period = f"Through {end.strftime('%b %d, %Y')}"
        subtitle = "In-force bound policies effective on or before the selected end date."
    else:
        period = timezone.localdate().strftime("%b %d, %Y")
        subtitle = "Full in-force book by line and carrier as of today."
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
            rows or [["—", "—", "—", "—", "—", "—", "$0.00"]],
            [1.6*inch, 1.2*inch, 1.5*inch, 1.4*inch, 0.9*inch, 0.95*inch, 1.0*inch],
            styles,
        ),
    ]
    return build_pdf(
        org,
        title="Book of business snapshot",
        subtitle=subtitle,
        period=period,
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
