"""Producer commission statement PDF (Reporting Center, producer profile, and producer portal)."""

from __future__ import annotations

from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib.units import inch
from reportlab.platypus import Spacer

from .insurance_producers import ZERO, money, summarize_producer
from .insurance_report_pdf import (
    _content_w,
    _money,
    _p,
    _styles,
    build_pdf,
    data_table,
    kpi_row,
    notice_box,
    period_label,
)
from .models import InsurancePolicy, InsuranceProducerPayout, InsuranceTypeOption

MAX_ROWS = 400


def _e(value, fallback="—") -> str:
    text = str(value or "").strip()
    return escape(text) if text else fallback


def _insured(policy) -> str:
    return _e(policy.client.name if policy.client_id else "")


def _carrier(policy) -> str:
    return _e(policy.insurance_company.name if policy.insurance_company_id else "")


def _rate_label(policy) -> str:
    basis = "premium" if policy.producer_rate_basis == "premium" else "commission"
    rate = policy.producer_rate
    if rate is None:
        return "—"
    return f"{rate.normalize():f}% of {basis}"


def _schedule_label(lg) -> str:
    if not lg.is_monthly:
        return "Once"
    text = f"{_money(lg.per_month)}/mo × {lg.term_months}"
    if lg.earns:
        text += f"<br/>{lg.months_earned} of {lg.term_months} earned"
    return text


def _status_label(policy) -> str:
    """Policy status only. The pipeline stage is not shown on the statement."""
    getter = getattr(policy, "get_status_display", None)
    label = getter() if callable(getter) else getattr(policy, "status", "")
    text = str(label or "").strip()
    return text or "—"


def _statement_date(value) -> str:
    if not value:
        return "—"
    return value.strftime("%m/%d/%Y")


def _insurance_type_labels(organization) -> dict:
    labels = dict(InsurancePolicy.INSURANCE_TYPE_CHOICES)
    labels.update(
        InsuranceTypeOption.objects.filter(organization=organization).values_list("key", "label")
    )
    return labels


def _policy_type_label(policy, labels) -> str:
    key = str(getattr(policy, "insurance_type", "") or "").strip()
    if not key:
        return "—"
    label = labels.get(key) or key.replace("_", " ").upper()
    return escape(str(label))


def _business_label(policy) -> str:
    getter = getattr(policy, "get_business_type_display", None)
    label = getter() if callable(getter) else getattr(policy, "business_type", "")
    text = str(label or "").strip()
    raw = str(getattr(policy, "business_type", "") or "").strip()
    if text and text == raw:
        text = text.replace("_", " ").title()
    return escape(text) if text else "—"


def render_producer_statement_pdf(producer, *, start=None, end=None, prepared_by="Staff") -> bytes:
    """Ledger for every policy as of today, plus payouts recorded inside the date range."""
    styles = _styles()
    width = _content_w(True)
    policies = (
        InsurancePolicy.objects.filter(producer=producer)
        .select_related("client", "insurance_company")
        .prefetch_related("producer_payouts")
        .order_by("-start_date", "-id")
    )
    summary = summarize_producer(producer, policies=policies)

    payouts = InsuranceProducerPayout.objects.filter(producer=producer).select_related(
        "policy", "policy__client"
    )
    if start:
        payouts = payouts.filter(paid_on__gte=start)
    if end:
        payouts = payouts.filter(paid_on__lte=end)
    payouts = list(payouts.order_by("paid_on", "id")[:MAX_ROWS])
    period_paid = money(sum((p.amount for p in payouts), ZERO))

    type_labels = _insurance_type_labels(producer.organization)
    policy_rows = []
    for lg in summary.ledgers[:MAX_ROWS]:
        p = lg.policy
        policy_rows.append([
            _e(p.policy_number),
            _insured(p),
            _carrier(p),
            _policy_type_label(p, type_labels),
            _business_label(p),
            _status_label(p),
            _statement_date(p.start_date),
            _statement_date(p.end_date),
            _money(p.premium),
            _rate_label(p),
            _money(lg.effective_total),
            _p(_schedule_label(lg), styles["body"]),
            _money(lg.paid),
            _money(lg.due_now) if not lg.owes_back else f"({_money(lg.owes_back)})",
        ])

    payout_rows = []
    for po in payouts:
        payout_rows.append([
            po.paid_on.strftime("%b %d, %Y"),
            _e(po.policy.policy_number),
            _insured(po.policy),
            "Deduction" if po.amount < 0 else "Payment",
            po.get_method_display(),
            _e(po.note),
            _money(po.amount),
        ])

    deduction_rows = [
        [
            _e(lg.policy.policy_number),
            _insured(lg.policy),
            lg.policy.inactive_date.strftime("%b %d, %Y") if lg.policy.inactive_date else "—",
            _money(lg.earned_to_date),
            _money(lg.paid),
            _money(lg.owes_back),
        ]
        for lg in summary.ledgers
        if lg.owes_back > 0
    ]

    rate_text = (
        f"{Decimal(str(producer.default_rate or 0)).normalize():f}% of "
        f"{'the premium' if producer.rate_basis == 'premium' else 'agency commission'}"
    )
    flow = [
        kpi_row([
            ("Total commission", _money(summary.total_commission)),
            ("Paid to date", _money(summary.paid)),
            ("Due now", _money(summary.due_now)),
            ("Deductions", _money(-summary.deductions) if summary.deductions else _money(ZERO)),
            ("Net to pay now", _money(summary.net_payable)),
            ("Still to come", _money(summary.upcoming)),
        ], styles, width),
        Spacer(1, 8),
        notice_box(
            f"<b>{_e(producer.name)}</b> · default rate {rate_text}"
            f"{' · license ' + _e(producer.license_number) if producer.license_number else ''}. "
            f"{summary.active_count} active and {summary.inactive_count} inactive policies. "
            + (
                f"{_money(summary.carried_deduction)} from cancelled policies carries forward to future commissions."
                if summary.carried_deduction
                else "Deductions from cancelled policies are taken from the amount due."
            ),
            styles,
            width,
        ),
        Spacer(1, 10),
        _p("Policies", styles["section"]),
        Spacer(1, 4),
        data_table(
            [
                "Policy #", "Insured", "Carrier", "Type", "Business", "Status",
                "Effective", "Expiration", "Premium", "Rate", "Commission", "Schedule", "Paid", "Due",
            ],
            policy_rows or [["—"] * 14],
            [
                0.56 * inch, 0.52 * inch, 0.62 * inch, 1.16 * inch, 0.86 * inch, 0.56 * inch,
                0.68 * inch, 0.68 * inch, 0.64 * inch, 1.05 * inch, 0.68 * inch, 0.80 * inch,
                0.59 * inch, 0.60 * inch,
            ],
            styles,
        ),
        Spacer(1, 12),
        _p(f"Payouts in this period · net {_money(period_paid)}", styles["section"]),
        Spacer(1, 4),
        data_table(
            ["Date", "Policy #", "Insured", "Type", "Method", "Note", "Amount"],
            payout_rows or [["—", "—", "—", "—", "—", "No payouts in this period", "$0.00"]],
            [0.95 * inch, 1.05 * inch, 1.6 * inch, 0.85 * inch, 0.85 * inch, 3.3 * inch, 1.2 * inch],
            styles,
        ),
    ]
    if deduction_rows:
        flow += [
            Spacer(1, 12),
            _p("Deductions from inactive policies", styles["section"]),
            Spacer(1, 4),
            data_table(
                ["Policy #", "Insured", "Cancelled", "Earned", "Paid", "To deduct"],
                deduction_rows,
                [1.2 * inch, 2.4 * inch, 1.4 * inch, 1.5 * inch, 1.5 * inch, 1.8 * inch],
                styles,
            ),
        ]
    return build_pdf(
        producer.organization,
        title="Producer statement",
        subtitle=f"{_e(producer.name)} · commission ledger as of today; payouts listed for the selected dates.",
        period=period_label(start, end),
        prepared_by=prepared_by,
        flowables=flow,
    )
