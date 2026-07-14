"""Professional TLC insurance payment receipt PDF generator."""

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
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0B3A6E")
BLUE = colors.HexColor("#1D4ED8")
LIGHT = colors.HexColor("#F1F5F9")
CARD = colors.HexColor("#FFFFFF")
MUTED = colors.HexColor("#64748B")
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
    styles = {
        "title": ParagraphStyle(
            "tlc_title",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=NAVY,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "tlc_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=MUTED,
        ),
        "h2": ParagraphStyle(
            "tlc_h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "tlc_body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            textColor=colors.HexColor("#0F172A"),
            leading=12,
        ),
        "label": ParagraphStyle(
            "tlc_label",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=MUTED,
            leading=10,
        ),
        "value": ParagraphStyle(
            "tlc_value",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=colors.HexColor("#0F172A"),
            leading=11,
        ),
        "right": ParagraphStyle(
            "tlc_right",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#0F172A"),
        ),
        "center": ParagraphStyle(
            "tlc_center",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            alignment=TA_CENTER,
            textColor=MUTED,
        ),
        "badge": ParagraphStyle(
            "tlc_badge",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "tlc_footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=MUTED,
            alignment=TA_CENTER,
            leading=10,
        ),
    }
    return styles


def _kv_table(pairs, styles, col_widths=None):
    data = []
    for label, value in pairs:
        data.append(
            [
                Paragraph(str(label), styles["label"]),
                Paragraph(str(value or "—"), styles["value"]),
            ]
        )
    table = Table(data, colWidths=col_widths or [1.6 * inch, 2.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _section_card(title, inner, styles, width=7.5 * inch):
    header = Paragraph(title, styles["h2"])
    wrap = Table([[header], [inner]], colWidths=[width])
    wrap.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ]
        )
    )
    return wrap


def _status_color(code: str):
    code = (code or "").lower()
    if code in {"active", "completed", "paid", "reinstated"}:
        return SUCCESS
    if code in {"pending", "upcoming", "suspended"}:
        return WARN
    if code in {"cancelled", "failed", "reversed", "past due"}:
        return DANGER
    return BLUE


def render_tlc_receipt_pdf(receipt) -> bytes:
    """Render a Letter-size professional TLC payment receipt PDF."""
    snapshot = receipt.snapshot_json or {}
    agency = snapshot.get("agency") or {}
    customer = snapshot.get("customer") or {}
    policy = snapshot.get("policy") or {}
    payment = snapshot.get("payment") or {}
    breakdown = snapshot.get("breakdown") or {}
    installment_summary = snapshot.get("installment_summary") or {}
    schedule = snapshot.get("schedule") or []
    history = snapshot.get("history") or []
    account = snapshot.get("account_summary") or {}
    notices = snapshot.get("notices") or []
    styles = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title=f"Receipt {receipt.receipt_number}",
    )
    story = []

    logo_cell = Paragraph(f"<b>{agency.get('name') or 'Xpress Insurance Solutions'}</b>", styles["title"])
    logo_path = agency.get("logo_path") or ""
    if logo_path:
        try:
            logo_cell = Image(logo_path, width=1.6 * inch, height=0.55 * inch, kind="proportional")
        except Exception:
            pass

    meta_lines = [
        f"<b>RECEIPT</b><br/>",
        f"Receipt # {receipt.receipt_number}<br/>",
        f"Payment Date {payment.get('payment_date') or '—'}<br/>",
        f"Payment Time {payment.get('payment_time') or '—'}<br/>",
        f"Transaction ID {payment.get('transaction_id') or '—'}<br/>",
        f"Processed By {payment.get('processed_by') or '—'}<br/>",
        f"Phone {agency.get('phone') or '—'} · Email {agency.get('email') or '—'}",
    ]
    header = Table(
        [[logo_cell, Paragraph("".join(meta_lines), styles["right"])]],
        colWidths=[4.2 * inch, 3.3 * inch],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=8))

    status_code = policy.get("status_code") or ""
    badge = Table(
        [[Paragraph((policy.get("status") or "ACTIVE").upper(), styles["badge"])]],
        colWidths=[1.8 * inch],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _status_color(status_code)),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    company_customer = Table(
        [
            [
                _kv_table(
                    [
                        ("Agency", agency.get("name")),
                        ("Address", agency.get("address")),
                        ("License", agency.get("license") or "—"),
                        ("NPN", agency.get("npn") or "—"),
                    ],
                    styles,
                ),
                _kv_table(
                    [
                        ("Customer", customer.get("name")),
                        ("Business", customer.get("business_name") or "—"),
                        ("Phone", customer.get("phone") or "—"),
                        ("Address", customer.get("address") or "—"),
                    ],
                    styles,
                ),
                badge,
            ]
        ],
        colWidths=[2.7 * inch, 2.8 * inch, 2.0 * inch],
    )
    story.append(_section_card("Company & Customer", company_customer, styles))
    story.append(Spacer(1, 8))

    policy_block = _kv_table(
        [
            ("Policy Number", policy.get("policy_number")),
            ("Carrier", policy.get("carrier")),
            ("Policy Type", policy.get("policy_type")),
            ("Effective", policy.get("effective_date")),
            ("Expiration", policy.get("expiration_date")),
            ("Vehicle", policy.get("vehicle") or "—"),
            ("VIN", policy.get("vin") or "—"),
            ("Plate", policy.get("plate_number") or "—"),
            ("TLC #", policy.get("tlc_number") or "—"),
            ("Driver", policy.get("driver") or "—"),
        ],
        styles,
        col_widths=[1.4 * inch, 5.8 * inch],
    )
    story.append(_section_card("Policy Information", policy_block, styles))
    story.append(Spacer(1, 8))

    payment_info = _kv_table(
        [
            ("Payment Type", payment.get("transaction_type")),
            ("Description", payment.get("description")),
            ("Status", payment.get("status")),
            ("Amount Due", _money(payment.get("amount_due"))),
            ("Amount Received", _money(payment.get("amount_received"))),
        ],
        styles,
        col_widths=[1.6 * inch, 5.6 * inch],
    )
    story.append(_section_card("Payment Details", payment_info, styles))
    story.append(Spacer(1, 8))

    break_rows = [
        [Paragraph("<b>Description</b>", styles["body"]), Paragraph("<b>Amount</b>", styles["right"])]
    ]
    for label, key in [
        ("Policy Premium", "policy_premium"),
        ("Installment Fee", "installment_fee"),
        ("Late Fee", "late_fee"),
        ("NSF Fee", "nsf_fee"),
        ("Reinstatement Fee", "reinstatement_fee"),
        ("Endorsement Fee", "endorsement_fee"),
        ("DMV Fee", "dmv_fee"),
        ("Broker Fee", "broker_fee"),
    ]:
        amount = Decimal(str(breakdown.get(key) or 0))
        if amount == 0:
            continue
        break_rows.append(
            [Paragraph(label, styles["body"]), Paragraph(_money(amount), styles["right"])]
        )
    break_rows.extend(
        [
            [
                Paragraph("<b>TOTAL DUE</b>", styles["value"]),
                Paragraph(f"<b>{_money(breakdown.get('total_due'))}</b>", styles["right"]),
            ],
            [
                Paragraph("<b>PAYMENT RECEIVED</b>", styles["value"]),
                Paragraph(f"<b>{_money(breakdown.get('payment_received'))}</b>", styles["right"]),
            ],
            [
                Paragraph("<b>REMAINING BALANCE</b>", styles["value"]),
                Paragraph(f"<b>{_money(breakdown.get('remaining_balance'))}</b>", styles["right"]),
            ],
        ]
    )
    break_table = Table(break_rows, colWidths=[5.5 * inch, 1.7 * inch])
    break_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
                ("BACKGROUND", (0, -3), (-1, -1), LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(_section_card("Payment Breakdown", break_table, styles))
    story.append(Spacer(1, 8))

    splits = payment.get("splits") or []
    if splits:
        split_rows = [
            [
                Paragraph("<b>Method</b>", styles["body"]),
                Paragraph("<b>Reference</b>", styles["body"]),
                Paragraph("<b>Amount</b>", styles["body"]),
                Paragraph("<b>Approval</b>", styles["body"]),
                Paragraph("<b>Last 4</b>", styles["body"]),
                Paragraph("<b>Notes</b>", styles["body"]),
            ]
        ]
        for row in splits:
            split_rows.append(
                [
                    Paragraph(row.get("payment_method") or "—", styles["body"]),
                    Paragraph(row.get("reference_number") or "—", styles["body"]),
                    Paragraph(_money(row.get("amount")), styles["body"]),
                    Paragraph(row.get("approval_number") or "—", styles["body"]),
                    Paragraph(row.get("last_four") or "—", styles["body"]),
                    Paragraph(row.get("notes") or "—", styles["body"]),
                ]
            )
        split_table = Table(
            split_rows,
            colWidths=[1.2 * inch, 1.3 * inch, 1.0 * inch, 1.2 * inch, 0.8 * inch, 1.7 * inch],
        )
        split_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(_section_card("Split Payment Methods", split_table, styles))
        story.append(Spacer(1, 8))

    paid = int(installment_summary.get("paid_count") or 0)
    total = int(installment_summary.get("total_count") or 0)
    bar_blocks = "█" * min(paid, 12) + "░" * max(min(total, 12) - paid, 0)
    progress = _kv_table(
        [
            ("Installments Paid", f"{paid} of {total}"),
            ("Remaining", installment_summary.get("remaining_count")),
            ("Monthly Payment", _money(installment_summary.get("monthly_payment"))),
            ("Next Due", installment_summary.get("next_due_date") or "—"),
            ("Past Due", _money(installment_summary.get("past_due"))),
            ("Current Balance", _money(installment_summary.get("current_balance"))),
            ("Progress", f"{bar_blocks}  {paid}/{total}"),
        ],
        styles,
        col_widths=[1.6 * inch, 5.6 * inch],
    )
    story.append(_section_card("Installment Summary", progress, styles))
    story.append(Spacer(1, 8))

    if history:
        hist_rows = [
            [
                Paragraph("<b>Date</b>", styles["body"]),
                Paragraph("<b>Receipt #</b>", styles["body"]),
                Paragraph("<b>Type</b>", styles["body"]),
                Paragraph("<b>Amount</b>", styles["body"]),
                Paragraph("<b>Method</b>", styles["body"]),
                Paragraph("<b>Status</b>", styles["body"]),
            ]
        ]
        for row in history[:12]:
            hist_rows.append(
                [
                    Paragraph(row.get("date") or "—", styles["body"]),
                    Paragraph(row.get("receipt_number") or "—", styles["body"]),
                    Paragraph(row.get("transaction_type") or "—", styles["body"]),
                    Paragraph(_money(row.get("amount")), styles["body"]),
                    Paragraph(row.get("payment_method") or "—", styles["body"]),
                    Paragraph(row.get("status") or "—", styles["body"]),
                ]
            )
        hist_table = Table(
            hist_rows,
            colWidths=[0.95 * inch, 1.35 * inch, 1.4 * inch, 0.9 * inch, 1.5 * inch, 1.0 * inch],
        )
        hist_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(KeepTogether([_section_card("Payment History", hist_table, styles)]))
        story.append(Spacer(1, 8))

    if schedule:
        sched_rows = [
            [
                Paragraph("<b>#</b>", styles["body"]),
                Paragraph("<b>Due Date</b>", styles["body"]),
                Paragraph("<b>Amount</b>", styles["body"]),
                Paragraph("<b>Status</b>", styles["body"]),
            ]
        ]
        for row in schedule:
            sched_rows.append(
                [
                    Paragraph(str(row.get("installment_number") or ""), styles["body"]),
                    Paragraph(row.get("due_date") or "—", styles["body"]),
                    Paragraph(_money(row.get("amount")), styles["body"]),
                    Paragraph(row.get("status") or "—", styles["body"]),
                ]
            )
        sched_table = Table(sched_rows, colWidths=[0.7 * inch, 2.2 * inch, 2.2 * inch, 2.1 * inch])
        sched_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        remaining = installment_summary.get("remaining_count") or 0
        payoff = next((r.get("due_date") for r in reversed(schedule) if r.get("status") != "Paid"), "—")
        footer_note = Paragraph(
            f"Remaining installments: <b>{remaining}</b> · Remaining balance: "
            f"<b>{_money(account.get('outstanding_balance'))}</b> · Expected payoff: <b>{payoff}</b>",
            styles["body"],
        )
        story.append(
            KeepTogether(
                [
                    _section_card(
                        "Future Payment Schedule",
                        Table([[sched_table], [footer_note]], colWidths=[7.2 * inch]),
                        styles,
                    )
                ]
            )
        )
        story.append(Spacer(1, 8))

    account_block = _kv_table(
        [
            ("Original Premium", _money(account.get("original_premium"))),
            ("Endorsements", _money(account.get("endorsements"))),
            ("Current Written Premium", _money(account.get("current_written_premium"))),
            ("Fees Collected", _money(account.get("fees"))),
            ("Payments Made", _money(account.get("payments_made"))),
            ("Outstanding Balance", _money(account.get("outstanding_balance"))),
        ],
        styles,
        col_widths=[2.2 * inch, 5.0 * inch],
    )
    story.append(_section_card("Account Summary", account_block, styles))
    story.append(Spacer(1, 8))

    notice_paras = [Paragraph(f"• {n}", styles["body"]) for n in notices]
    story.append(_section_card("Important Notices", Table([[n] for n in notice_paras]), styles))
    story.append(Spacer(1, 12))

    sig = Table(
        [
            [
                Paragraph("Customer Signature _________________________", styles["body"]),
                Paragraph("Date ______________", styles["body"]),
            ],
            [
                Paragraph("Agency Representative ______________________", styles["body"]),
                Paragraph(f"Hash {receipt.content_hash[:16]}…", styles["label"]),
            ],
        ],
        colWidths=[4.5 * inch, 2.7 * inch],
    )
    story.append(sig)
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=6))
    story.append(
        Paragraph(
            f"<b>{agency.get('name') or 'Xpress Insurance Solutions Inc.'}</b><br/>"
            "Thank you for choosing Xpress Insurance Solutions Inc. · Licensed Insurance Agency<br/>"
            f"{agency.get('phone') or ''} · {agency.get('email') or ''}<br/>"
            "This document is confidential. Powered by Xpress Insurance Solutions Agency Management System.",
            styles["footer"],
        )
    )

    doc.build(story)
    return buffer.getvalue()
