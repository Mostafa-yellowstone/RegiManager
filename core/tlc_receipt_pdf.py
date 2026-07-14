"""One-page professional TLC insurance payment receipt PDF."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0B3A6E")
BLUE = colors.HexColor("#2563EB")
LIGHT = colors.HexColor("#F8FAFC")
SOFT = colors.HexColor("#EFF6FF")
MUTED = colors.HexColor("#64748B")
INK = colors.HexColor("#0F172A")
SUCCESS = colors.HexColor("#059669")
WARN = colors.HexColor("#D97706")
DANGER = colors.HexColor("#DC2626")
BORDER = colors.HexColor("#E2E8F0")
PAGE_W = 7.6 * inch


def _money(value) -> str:
    try:
        return f"${Decimal(str(value or 0)).quantize(Decimal('0.01')):,.2f}"
    except Exception:
        return "$0.00"


def _safe(value, fallback="—") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "r_brand", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=11, textColor=NAVY, leading=13, alignment=TA_LEFT,
        ),
        "agency_line": ParagraphStyle(
            "r_agency_line", parent=base["Normal"], fontName="Helvetica",
            fontSize=7, textColor=MUTED, leading=9, alignment=TA_LEFT,
        ),
        "receipt_title": ParagraphStyle(
            "r_title", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=13, textColor=NAVY, alignment=TA_RIGHT, leading=15,
        ),
        "meta": ParagraphStyle(
            "r_meta", parent=base["Normal"], fontName="Helvetica",
            fontSize=7, textColor=MUTED, alignment=TA_RIGHT, leading=9,
        ),
        "section": ParagraphStyle(
            "r_section", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.5, textColor=NAVY, leading=9,
        ),
        "label": ParagraphStyle(
            "r_label", parent=base["Normal"], fontName="Helvetica",
            fontSize=6, textColor=MUTED, leading=7.5,
        ),
        "value": ParagraphStyle(
            "r_value", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=7.5, textColor=INK, leading=9,
        ),
        "body": ParagraphStyle(
            "r_body", parent=base["Normal"], fontName="Helvetica",
            fontSize=7, textColor=INK, leading=8.5,
        ),
        "th": ParagraphStyle(
            "r_th", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.5, textColor=colors.white, leading=8,
        ),
        "badge": ParagraphStyle(
            "r_badge", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=6.5, textColor=colors.white, alignment=TA_CENTER, leading=8,
        ),
        "footer": ParagraphStyle(
            "r_footer", parent=base["Normal"], fontName="Helvetica",
            fontSize=6, textColor=MUTED, alignment=TA_CENTER, leading=7.5,
        ),
        "notice": ParagraphStyle(
            "r_notice", parent=base["Normal"], fontName="Helvetica",
            fontSize=6.5, textColor=MUTED, alignment=TA_LEFT, leading=8,
        ),
    }


def _status_color(code: str):
    code = (code or "").lower()
    if code in {"active", "completed", "paid", "reinstated"}:
        return SUCCESS
    if code in {"pending", "upcoming", "suspended"}:
        return WARN
    if code in {"cancelled", "failed", "reversed", "past due"}:
        return DANGER
    return BLUE


def _stack_field(label: str, value, styles, width: float):
    """Label stacked above value — avoids side-by-side overflow."""
    table = Table(
        [
            [Paragraph(_safe(label, ""), styles["label"])],
            [Paragraph(_safe(value), styles["value"])],
        ],
        colWidths=[width],
    )
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _field_grid(pairs, styles, cols=3, total_width=PAGE_W - 0.2 * inch):
    col_w = total_width / cols
    cells = []
    row = []
    for label, value in pairs:
        row.append(_stack_field(label, value, styles, col_w - 0.05 * inch))
        if len(row) == cols:
            cells.append(row)
            row = []
    if row:
        while len(row) < cols:
            row.append("")
        cells.append(row)
    if not cells:
        return Spacer(1, 1)
    table = Table(cells, colWidths=[col_w] * cols)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _card(title: str, content, styles, width=PAGE_W):
    head = Paragraph(title.upper(), styles["section"])
    wrap = Table([[head], [content]], colWidths=[width])
    wrap.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
    ]))
    return wrap


def render_tlc_receipt_pdf(receipt) -> bytes:
    """Render a clean single-page TLC payment receipt."""
    snapshot = receipt.snapshot_json or {}
    agency = snapshot.get("agency") or {}
    customer = snapshot.get("customer") or {}
    policy = snapshot.get("policy") or {}
    payment = snapshot.get("payment") or {}
    breakdown = snapshot.get("breakdown") or {}
    installment_summary = snapshot.get("installment_summary") or {}
    account = snapshot.get("account_summary") or {}
    notices = snapshot.get("notices") or []
    styles = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.3 * inch,
        bottomMargin=0.28 * inch,
        title=f"Receipt {receipt.receipt_number}",
    )
    story = []

    # ── Header: logo + agency block | receipt meta ──
    agency_name = _safe(agency.get("name"), "Xpress Insurance Solutions")
    agency_bits = [Paragraph(agency_name, styles["brand"])]
    if agency.get("address"):
        agency_bits.append(Paragraph(_safe(agency.get("address")), styles["agency_line"]))
    contact = " · ".join(p for p in [agency.get("phone"), agency.get("email")] if p)
    if contact:
        agency_bits.append(Paragraph(contact, styles["agency_line"]))

    logo_flowable = None
    logo_path = agency.get("logo_path") or ""
    if logo_path:
        try:
            logo_flowable = Image(logo_path, width=1.15 * inch, height=0.42 * inch, kind="proportional")
        except Exception:
            logo_flowable = None

    left_rows = []
    if logo_flowable is not None:
        left_rows.append([logo_flowable])
    for bit in agency_bits:
        left_rows.append([bit])
    left = Table(left_rows, colWidths=[4.4 * inch])
    left.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    badge = Table(
        [[Paragraph(_safe(policy.get("status"), "ACTIVE").upper(), styles["badge"])]],
        colWidths=[1.2 * inch],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _status_color(policy.get("status_code"))),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    right = Table(
        [
            [Paragraph("PAYMENT RECEIPT", styles["receipt_title"])],
            [Paragraph(
                f"<b>#{_safe(receipt.receipt_number)}</b><br/>"
                f"{_safe(payment.get('transaction_id'))}<br/>"
                f"{_safe(payment.get('transaction_type'))} · {_safe(payment.get('status'), 'Completed')}<br/>"
                f"By {_safe(payment.get('processed_by'))}",
                styles["meta"],
            )],
            [badge],
        ],
        colWidths=[3.0 * inch],
    )
    right.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(Table([[left, right]], colWidths=[4.5 * inch, 3.1 * inch]))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=5))

    # ── Customer only (agency already under logo — no license/NPN) ──
    customer_block = _field_grid(
        [
            ("Customer Name", customer.get("name")),
            ("Business / Policy Holder", customer.get("business_name") or customer.get("name")),
            ("Phone", customer.get("phone")),
            ("Email", customer.get("email")),
            ("Address", customer.get("address")),
        ],
        styles,
        cols=3,
        total_width=PAGE_W - 0.25 * inch,
    )
    story.append(_card("Customer", customer_block, styles))
    story.append(Spacer(1, 4))

    # ── Policy ──
    story.append(_card(
        "Policy",
        _field_grid(
            [
                ("Policy Number", policy.get("policy_number")),
                ("Carrier", policy.get("carrier")),
                ("Policy Type", policy.get("policy_type")),
                ("Effective", policy.get("effective_date")),
                ("Expiration", policy.get("expiration_date")),
                ("Status", policy.get("status")),
                ("Vehicle", policy.get("vehicle")),
                ("VIN", policy.get("vin")),
                ("Plate", policy.get("plate_number")),
                ("TLC #", policy.get("tlc_number")),
                ("Driver", policy.get("driver")),
                ("Payment Type", payment.get("transaction_type")),
            ],
            styles,
            cols=4,
            total_width=PAGE_W - 0.25 * inch,
        ),
        styles,
    ))
    story.append(Spacer(1, 4))

    # ── Payment methods ──
    pay_date = payment.get("payment_date") or "—"
    pay_time = payment.get("payment_time") or ""
    datetime_label = f"{pay_date}" + (f"  {pay_time}" if pay_time else "")
    split_rows = [[
        Paragraph("Date / Time", styles["th"]),
        Paragraph("Method", styles["th"]),
        Paragraph("Amount", styles["th"]),
        Paragraph("Notes", styles["th"]),
    ]]
    splits = payment.get("splits") or []
    if not splits:
        splits = [{"payment_method": "—", "amount": payment.get("amount_received"), "notes": ""}]
    for row in splits:
        split_rows.append([
            Paragraph(datetime_label, styles["body"]),
            Paragraph(_safe(row.get("payment_method")), styles["body"]),
            Paragraph(_money(row.get("amount")), styles["body"]),
            Paragraph(_safe(row.get("notes")), styles["body"]),
        ])
    split_rows.append([
        Paragraph("<b>Total Received</b>", styles["value"]),
        Paragraph("", styles["body"]),
        Paragraph(f"<b>{_money(payment.get('amount_received'))}</b>", styles["value"]),
        Paragraph(f"Due {_money(payment.get('amount_due'))}", styles["label"]),
    ])
    split_table = Table(
        split_rows,
        colWidths=[1.7 * inch, 1.5 * inch, 1.15 * inch, 2.85 * inch],
    )
    split_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("BACKGROUND", (0, -1), (-1, -1), SOFT),
        ("GRID", (0, 0), (-1, -2), 0.25, BORDER),
        ("LINEABOVE", (0, -1), (-1, -1), 0.7, BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(_card("Payment Methods", split_table, styles))
    story.append(Spacer(1, 4))

    # ── This transaction amounts ──
    charge_pairs = []
    for label, key in [
        ("Premium", "policy_premium"),
        ("Installment Fee", "installment_fee"),
        ("Late Fee", "late_fee"),
        ("NSF Fee", "nsf_fee"),
        ("Reinstatement", "reinstatement_fee"),
        ("Endorsement Fee", "endorsement_fee"),
        ("DMV Fee", "dmv_fee"),
    ]:
        amount = Decimal(str(breakdown.get(key) or 0))
        if amount:
            charge_pairs.append((label, _money(amount)))
    charge_pairs.extend([
        ("Total Due", _money(breakdown.get("total_due"))),
        ("Received", _money(breakdown.get("payment_received"))),
        ("Remaining Balance", _money(breakdown.get("remaining_balance"))),
    ])
    story.append(_card(
        "This Transaction",
        _field_grid(charge_pairs, styles, cols=3, total_width=PAGE_W - 0.25 * inch),
        styles,
    ))
    story.append(Spacer(1, 4))

    # ── Installment progress ──
    paid = int(installment_summary.get("paid_count") or 0)
    total = int(installment_summary.get("total_count") or 0)
    filled = min(paid, 10)
    empty = max(min(total, 10) - filled, 0)
    bar = "█" * filled + "░" * empty
    story.append(_card(
        "Installment Progress",
        _field_grid(
            [
                ("Paid", f"{paid} of {total}"),
                ("Remaining", installment_summary.get("remaining_count")),
                ("Progress", bar),
                ("Monthly", _money(installment_summary.get("monthly_payment"))),
                ("Next Due", installment_summary.get("next_due_date") or "—"),
                ("Past Due", _money(installment_summary.get("past_due"))),
            ],
            styles,
            cols=3,
            total_width=PAGE_W - 0.25 * inch,
        ),
        styles,
    ))
    story.append(Spacer(1, 4))

    # ── Account summary cards (3 across) ──
    summary_items = [
        ("Original Premium", _money(account.get("original_premium"))),
        ("Endorsements", _money(account.get("endorsements"))),
        ("Current Written", _money(account.get("current_written_premium"))),
        ("Fees Collected", _money(account.get("fees"))),
        ("Payments Made", _money(account.get("payments_made"))),
        ("Outstanding Balance", _money(account.get("outstanding_balance"))),
    ]
    card_w = (PAGE_W - 0.35 * inch) / 3
    summary_rows = []
    row = []
    for label, value in summary_items:
        cell = Table(
            [
                [Paragraph(label, styles["label"])],
                [Paragraph(value, styles["value"])],
            ],
            colWidths=[card_w - 0.08 * inch],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        row.append(cell)
        if len(row) == 3:
            summary_rows.append(row)
            row = []
    summary_table = Table(summary_rows, colWidths=[card_w] * 3)
    summary_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(_card("Account Summary", summary_table, styles))
    story.append(Spacer(1, 4))

    # ── Notices + footer (kept on page 1) ──
    notice_text = "  ·  ".join(notices) if notices else "Thank you for your payment."
    story.append(Paragraph(notice_text, styles["notice"]))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=2))
    story.append(Paragraph(
        f"<b>{agency_name}</b>  ·  Thank you for your business  ·  Keep this receipt for your records<br/>"
        f"Hash {str(receipt.content_hash or '')[:12]}…  ·  "
        "Powered by Xpress Insurance Solutions Agency Management System",
        styles["footer"],
    ))

    doc.build(story)
    return buffer.getvalue()
