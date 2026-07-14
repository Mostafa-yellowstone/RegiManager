"""One-page professional TLC insurance payment receipt PDF."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
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
BLUE = colors.HexColor("#1D4ED8")
LIGHT = colors.HexColor("#F8FAFC")
SOFT = colors.HexColor("#EFF6FF")
MUTED = colors.HexColor("#64748B")
INK = colors.HexColor("#0F172A")
SUCCESS = colors.HexColor("#059669")
WARN = colors.HexColor("#D97706")
DANGER = colors.HexColor("#DC2626")
BORDER = colors.HexColor("#E2E8F0")


def _money(value) -> str:
    try:
        return f"${Decimal(str(value or 0)).quantize(Decimal('0.01')):,.2f}"
    except Exception:
        return "$0.00"


def _styles():
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "xis_brand", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=14, textColor=NAVY, leading=17,
        ),
        "receipt_title": ParagraphStyle(
            "xis_rtitle", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=16, textColor=NAVY, alignment=TA_RIGHT, leading=18,
        ),
        "meta": ParagraphStyle(
            "xis_meta", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, textColor=MUTED, alignment=TA_RIGHT, leading=11,
        ),
        "section": ParagraphStyle(
            "xis_section", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, textColor=NAVY, spaceBefore=0, spaceAfter=4, leading=11,
        ),
        "label": ParagraphStyle(
            "xis_label", parent=base["Normal"], fontName="Helvetica",
            fontSize=7, textColor=MUTED, leading=9,
        ),
        "value": ParagraphStyle(
            "xis_value", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, textColor=INK, leading=11,
        ),
        "body": ParagraphStyle(
            "xis_body", parent=base["Normal"], fontName="Helvetica",
            fontSize=8, textColor=INK, leading=10,
        ),
        "small": ParagraphStyle(
            "xis_small", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.5, textColor=MUTED, leading=9,
        ),
        "badge": ParagraphStyle(
            "xis_badge", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8, textColor=colors.white, alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "xis_footer", parent=base["Normal"], fontName="Helvetica",
            fontSize=7, textColor=MUTED, alignment=TA_CENTER, leading=9,
        ),
        "summary_label": ParagraphStyle(
            "xis_sum_l", parent=base["Normal"], fontName="Helvetica",
            fontSize=7, textColor=MUTED, leading=9,
        ),
        "summary_value": ParagraphStyle(
            "xis_sum_v", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, textColor=INK, leading=11,
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


def _field_cell(label, value, styles):
    return [
        Paragraph(str(label), styles["label"]),
        Paragraph(str(value or "—"), styles["value"]),
    ]


def _info_grid(pairs, styles, cols=3):
    """Build a compact label/value grid with N columns of field pairs."""
    cells = []
    row = []
    for label, value in pairs:
        cell = Table([_field_cell(label, value, styles)], colWidths=[2.35 * inch])
        cell.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        row.append(cell)
        if len(row) == cols:
            cells.append(row)
            row = []
    if row:
        while len(row) < cols:
            row.append("")
        cells.append(row)
    if not cells:
        return Spacer(1, 1)
    table = Table(cells, colWidths=[2.4 * inch] * cols)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _panel(title, content, styles, width=7.5 * inch):
    header = Paragraph(title.upper(), styles["section"])
    wrap = Table([[header], [content]], colWidths=[width])
    wrap.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    return wrap


def render_tlc_receipt_pdf(receipt) -> bytes:
    """Render a single Letter-page TLC payment receipt."""
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
        topMargin=0.35 * inch,
        bottomMargin=0.35 * inch,
        title=f"Receipt {receipt.receipt_number}",
    )
    story = []

    # Header
    left_bits = []
    logo_path = agency.get("logo_path") or ""
    if logo_path:
        try:
            left_bits.append(Image(logo_path, width=1.35 * inch, height=0.48 * inch, kind="proportional"))
        except Exception:
            left_bits.append(Paragraph(agency.get("name") or "Agency", styles["brand"]))
    else:
        left_bits.append(Paragraph(agency.get("name") or "Agency", styles["brand"]))
    left_bits.append(Paragraph(
        "<br/>".join(
            part for part in [
                agency.get("address") or "",
                " · ".join(p for p in [agency.get("phone"), agency.get("email")] if p),
            ] if part
        ),
        styles["small"],
    ))
    left = Table([[b] for b in left_bits], colWidths=[4.2 * inch])
    left.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    badge = Table(
        [[Paragraph((policy.get("status") or "ACTIVE").upper(), styles["badge"])]],
        colWidths=[1.45 * inch],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _status_color(policy.get("status_code"))),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    right = Table(
        [
            [Paragraph("RECEIPT", styles["receipt_title"])],
            [Paragraph(
                f"<b>#{receipt.receipt_number}</b><br/>"
                f"Txn {payment.get('transaction_id') or '—'}<br/>"
                f"{payment.get('transaction_type') or 'Payment'} · {payment.get('status') or 'Completed'}<br/>"
                f"Processed by {payment.get('processed_by') or '—'}",
                styles["meta"],
            )],
            [badge],
        ],
        colWidths=[3.2 * inch],
    )
    right.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(Table([[left, right]], colWidths=[4.3 * inch, 3.2 * inch]))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.4, color=NAVY, spaceAfter=6))

    # Company | Customer side-by-side
    company_grid = _info_grid(
        [
            ("Agency", agency.get("name")),
            ("Address", agency.get("address")),
            ("Phone", agency.get("phone")),
            ("Email", agency.get("email")),
            ("License", agency.get("license") or "—"),
            ("NPN", agency.get("npn") or "—"),
        ],
        styles,
        cols=2,
    )
    customer_grid = _info_grid(
        [
            ("Customer", customer.get("name")),
            ("Business / Policy Holder", customer.get("business_name") or customer.get("name")),
            ("Phone", customer.get("phone")),
            ("Email", customer.get("email")),
            ("Address", customer.get("address")),
        ],
        styles,
        cols=2,
    )
    split_head = Table(
        [[
            Paragraph("COMPANY", styles["section"]),
            Paragraph("CUSTOMER", styles["section"]),
        ]],
        colWidths=[3.7 * inch, 3.7 * inch],
    )
    company_customer = Table(
        [[split_head], [company_grid, customer_grid]],
        colWidths=[3.7 * inch, 3.7 * inch],
    )
    company_customer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(company_customer)
    story.append(Spacer(1, 6))

    # Policy
    story.append(_panel(
        "Policy Information",
        _info_grid(
            [
                ("Policy Number", policy.get("policy_number")),
                ("Carrier", policy.get("carrier")),
                ("Type", policy.get("policy_type")),
                ("Effective", policy.get("effective_date")),
                ("Expiration", policy.get("expiration_date")),
                ("Vehicle", policy.get("vehicle") or "—"),
                ("VIN", policy.get("vin")),
                ("Plate", policy.get("plate_number")),
                ("TLC #", policy.get("tlc_number")),
                ("Driver", policy.get("driver")),
                ("Payment Type", payment.get("transaction_type")),
                ("Description", payment.get("description")),
            ],
            styles,
            cols=3,
        ),
        styles,
    ))
    story.append(Spacer(1, 6))

    # Payment methods — Date, Method, Amount, Notes
    pay_date = payment.get("payment_date") or "—"
    pay_time = payment.get("payment_time") or ""
    datetime_label = f"{pay_date}" + (f" {pay_time}" if pay_time else "")
    split_rows = [[
        Paragraph("<b>Date / Time</b>", styles["body"]),
        Paragraph("<b>Method</b>", styles["body"]),
        Paragraph("<b>Amount</b>", styles["body"]),
        Paragraph("<b>Notes</b>", styles["body"]),
    ]]
    for row in payment.get("splits") or []:
        split_rows.append([
            Paragraph(datetime_label, styles["body"]),
            Paragraph(row.get("payment_method") or "—", styles["body"]),
            Paragraph(_money(row.get("amount")), styles["body"]),
            Paragraph(row.get("notes") or "—", styles["body"]),
        ])
    if len(split_rows) == 1:
        split_rows.append([
            Paragraph(datetime_label, styles["body"]),
            Paragraph("—", styles["body"]),
            Paragraph(_money(payment.get("amount_received")), styles["body"]),
            Paragraph("—", styles["body"]),
        ])
    split_rows.append([
        Paragraph("<b>Total Received</b>", styles["value"]),
        Paragraph("", styles["body"]),
        Paragraph(f"<b>{_money(payment.get('amount_received'))}</b>", styles["value"]),
        Paragraph(f"Due {_money(payment.get('amount_due'))}", styles["small"]),
    ])
    split_table = Table(split_rows, colWidths=[1.8 * inch, 1.6 * inch, 1.3 * inch, 2.5 * inch])
    split_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), SOFT),
        ("GRID", (0, 0), (-1, -2), 0.3, BORDER),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(_panel("Payment Methods", split_table, styles))
    story.append(Spacer(1, 6))

    # Compact financial strip (replaces payment details + heavy breakdown)
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
        ("Balance After", _money(breakdown.get("remaining_balance"))),
    ])
    story.append(_panel("This Transaction", _info_grid(charge_pairs, styles, cols=3), styles))
    story.append(Spacer(1, 6))

    # Installment progress + styled account summary
    paid = int(installment_summary.get("paid_count") or 0)
    total = int(installment_summary.get("total_count") or 0)
    filled = min(paid, 10)
    empty = max(min(total, 10) - filled, 0)
    bar = "█" * filled + "░" * empty
    progress = _info_grid(
        [
            ("Installments", f"{paid} of {total} paid"),
            ("Remaining", installment_summary.get("remaining_count")),
            ("Progress", f"{bar}"),
            ("Monthly", _money(installment_summary.get("monthly_payment"))),
            ("Next Due", installment_summary.get("next_due_date") or "—"),
            ("Past Due", _money(installment_summary.get("past_due"))),
        ],
        styles,
        cols=3,
    )
    story.append(_panel("Installment Progress", progress, styles))
    story.append(Spacer(1, 6))

    summary_items = [
        ("Original Premium", _money(account.get("original_premium"))),
        ("Endorsements", _money(account.get("endorsements"))),
        ("Current Written", _money(account.get("current_written_premium"))),
        ("Fees Collected", _money(account.get("fees"))),
        ("Payments Made", _money(account.get("payments_made"))),
        ("Outstanding Balance", _money(account.get("outstanding_balance"))),
    ]
    summary_cells = []
    row = []
    for label, value in summary_items:
        cell = Table(
            [[Paragraph(label, styles["summary_label"])], [Paragraph(value, styles["summary_value"])]],
            colWidths=[2.35 * inch],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        row.append(cell)
        if len(row) == 3:
            summary_cells.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append("")
        summary_cells.append(row)
    summary_table = Table(summary_cells, colWidths=[2.45 * inch] * 3)
    summary_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(_panel("Account Summary", summary_table, styles))
    story.append(Spacer(1, 6))

    notice_text = "  ·  ".join(notices) if notices else "Thank you for your payment."
    story.append(Paragraph(notice_text, styles["small"]))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER, spaceAfter=4))
    story.append(Paragraph(
        f"<b>{agency.get('name') or 'Xpress Insurance Solutions Inc.'}</b>  ·  "
        "Licensed Insurance Agency  ·  Keep this receipt for your records<br/>"
        f"Verification {receipt.content_hash[:16]}…  ·  "
        "Powered by Xpress Insurance Solutions Agency Management System",
        styles["footer"],
    ))

    doc.build(story)
    return buffer.getvalue()
