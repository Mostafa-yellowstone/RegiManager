"""TLC Policy Profitability Engine — computed metrics for agency owners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Count, Sum
from django.utils import timezone

from .tlc_accounting import (
    build_accounting_snapshot,
    endorsement_commission_total,
    policy_written_premium,
)

if TYPE_CHECKING:
    from .tlc_models import TLCPolicy

ZERO = Decimal("0.00")


def _d(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _money(value) -> str:
    return str(_d(value))


@dataclass(frozen=True)
class InstallmentSummary:
    installments_paid: int
    total_installments: int
    remaining_installments: int
    total_remaining_balance: Decimal
    days_late: int
    next_due_date: date | None
    past_due_amount: Decimal
    late_fees_collected: Decimal
    nsf_fees_collected: Decimal
    installment_fees_collected: Decimal
    installment_fees_outstanding: Decimal
    installment_commission_collected: Decimal
    installment_commission_outstanding: Decimal
    net_premium_collected: Decimal
    total_collected: Decimal


def summarize_installments(policy: TLCPolicy, *, today: date | None = None) -> InstallmentSummary:
    today = today or timezone.localdate()
    installments = list(policy.installments.all().order_by("installment_number"))
    total = len(installments)
    paid = sum(1 for row in installments if row.is_paid)
    remaining = max(total - paid, 0)
    remaining_balance = ZERO
    past_due = ZERO
    days_late = 0
    next_due: date | None = None
    late_fees = ZERO
    nsf_fees = ZERO
    installment_fees_collected = ZERO
    installment_fees_outstanding = ZERO
    commission_collected = ZERO
    commission_outstanding = ZERO
    net_premium_collected = ZERO
    collected = ZERO

    for row in installments:
        inst_fee = _d(row.installment_fee)
        commission = _d(row.commission_amount)
        row_total = _d(row.total_due)
        if row.is_paid:
            collected += row_total
            net_premium_collected += _d(row.amount)
            installment_fees_collected += inst_fee
            commission_collected += commission
            late_fees += _d(row.late_fee)
            nsf_fees += _d(row.nsf_fee)
        else:
            outstanding = _d(row.balance or row_total)
            remaining_balance += outstanding
            installment_fees_outstanding += inst_fee
            commission_outstanding += commission
            if row.due_date and row.due_date < today:
                past_due += outstanding
                days_late = max(days_late, (today - row.due_date).days)
            elif next_due is None and row.due_date:
                next_due = row.due_date

    return InstallmentSummary(
        installments_paid=paid,
        total_installments=total,
        remaining_installments=remaining,
        total_remaining_balance=remaining_balance,
        days_late=days_late,
        next_due_date=next_due,
        past_due_amount=past_due,
        late_fees_collected=late_fees,
        nsf_fees_collected=nsf_fees,
        installment_fees_collected=installment_fees_collected,
        installment_fees_outstanding=installment_fees_outstanding,
        installment_commission_collected=commission_collected,
        installment_commission_outstanding=commission_outstanding,
        net_premium_collected=net_premium_collected,
        total_collected=collected,
    )


def summarize_dmv_services(policy: TLCPolicy) -> dict:
    rows = policy.dmv_services.all()
    revenue = ZERO
    cost = ZERO
    profit = ZERO
    for row in rows:
        revenue += _d(row.fee_charged)
        cost += _d(row.dmv_tlc_cost)
        profit += _d(row.agency_profit)
    return {
        "dmv_revenue": revenue,
        "dmv_cost": cost,
        "dmv_fees_collected": revenue,
        "dmv_net_profit": profit,
        "service_count": rows.count(),
    }


def summarize_reinstatements(policy: TLCPolicy) -> dict:
    rows = policy.reinstatements.all()
    reinstatement_fees = ZERO
    for row in rows:
        reinstatement_fees += _d(row.reinstatement_fee)
    return {
        "reinstatement_count": rows.count(),
        "reinstatement_fees_total": reinstatement_fees,
        "reinstatement_fees_collected": reinstatement_fees,
    }


def summarize_commission(policy: TLCPolicy, accounting: dict) -> dict:
    expected = accounting["expected_commission"]
    earned = accounting["earned_commission"]
    received = _d(policy.commission_received)
    chargeback = accounting["commission_chargeback"]
    pending = accounting["pending_commission"]
    renewal = ZERO
    if policy.policy_type == policy.PolicyType.RENEWAL and policy.renewal_commission_rate:
        premium = policy_written_premium(policy)
        renewal = (premium * _d(policy.renewal_commission_rate) / Decimal("100")).quantize(
            Decimal("0.01")
        )
    return {
        "expected_commission": expected,
        "commission_earned": earned,
        "commission_received": received,
        "pending_commission": pending,
        "chargeback": chargeback,
        "unearned_commission": accounting["unearned_commission"],
        "renewal_commission": renewal,
        "commission_remaining": pending,
    }


def build_policy_profitability(policy: TLCPolicy, *, today: date | None = None) -> dict:
    """Full profitability snapshot for a single TLC policy."""
    today = today or timezone.localdate()
    breakdown = getattr(policy, "premium_breakdown", None)
    accounting = build_accounting_snapshot(policy, today=today)
    installments = summarize_installments(policy, today=today)
    dmv = summarize_dmv_services(policy)
    reinstatements = summarize_reinstatements(policy)
    commission = summarize_commission(policy, accounting)

    written_premium = accounting["base_written_premium"]
    current_written_premium = accounting["current_written_premium"]
    billing_amount = accounting["billing_amount"]
    endorsement_adjustments = accounting["endorsement_premium_adjustments"]
    down_payment = _d(breakdown.down_payment) if breakdown else ZERO

    broker_fees = _d(policy.broker_fee_collected)
    finance_fees = _d(policy.finance_fee_collected)
    policy_fees = _d(breakdown.policy_fee) if breakdown else ZERO
    inspection_fees = _d(breakdown.inspection_fee) if breakdown else ZERO

    total_collected = (
        installments.total_collected
        + broker_fees
        + finance_fees
        + reinstatements["reinstatement_fees_collected"]
    )
    if policy.amount_collected_from_client:
        total_collected = max(total_collected, _d(policy.amount_collected_from_client))

    # Installment fees are carrier pass-through — never agency profit.
    gross_agency_revenue = (
        commission["commission_earned"]
        + broker_fees
        + finance_fees
        + policy_fees
        + inspection_fees
        + installments.late_fees_collected
        + installments.nsf_fees_collected
        + reinstatements["reinstatement_fees_collected"]
        + dmv["dmv_net_profit"]
    )

    producer_commission = _d(policy.producer_commission_amount)
    csr_commission = _d(policy.csr_commission_amount)
    total_expenses = producer_commission + csr_commission + commission["chargeback"]

    net_profit = gross_agency_revenue - total_expenses

    carrier_premium = accounting["carrier_premium_due"]
    collected_from_client = total_collected
    remitted = _d(policy.amount_remitted_to_carrier)
    remitted_rows = policy.carrier_remittances.aggregate(total=Sum("amount"))
    if remitted_rows["total"]:
        remitted = max(remitted, _d(remitted_rows["total"]))
    remaining_due_carrier = max(carrier_premium - remitted + _d(policy.carrier_credits), ZERO)
    carrier_net_due = remaining_due_carrier - _d(policy.carrier_refunds)
    overpayment = ZERO
    if remitted > carrier_premium:
        overpayment = remitted - carrier_premium

    return {
        "written_premium": _money(written_premium),
        "current_written_premium": _money(current_written_premium),
        "billing_amount": _money(billing_amount),
        "endorsement_adjustments": _money(endorsement_adjustments),
        "return_premium": _money(accounting["return_premium"]),
        "down_payment": _money(down_payment),
        "total_collected": _money(total_collected),
        "net_premium_collected": _money(installments.net_premium_collected),
        "installments_paid": installments.installments_paid,
        "installments_total": installments.total_installments,
        "installments_label": f"{installments.installments_paid} / {installments.total_installments}",
        "next_due_date": installments.next_due_date.isoformat() if installments.next_due_date else None,
        "past_due_amount": _money(installments.past_due_amount),
        "days_late": installments.days_late,
        "late_fees_collected": _money(installments.late_fees_collected),
        "nsf_fees": _money(installments.nsf_fees_collected),
        "installment_fees_collected": _money(installments.installment_fees_collected),
        "installment_fees_outstanding": _money(installments.installment_fees_outstanding),
        "installment_fees_total": _money(accounting["installment_fees_total"]),
        "installment_commission_collected": _money(installments.installment_commission_collected),
        "installment_commission_outstanding": _money(installments.installment_commission_outstanding),
        "installment_commission_total": _money(
            installments.installment_commission_collected
            + installments.installment_commission_outstanding
        ),
        "endorsement_commission": _money(endorsement_commission_total(policy)),
        "reinstatement_fees": _money(reinstatements["reinstatement_fees_collected"]),
        "broker_fees_collected": _money(broker_fees),
        "carrier_commission": _money(commission["expected_commission"]),
        "commission_rate": str(_d(policy.commission_rate)),
        "commission_earned": _money(commission["commission_earned"]),
        "unearned_commission": _money(commission["unearned_commission"]),
        "commission_chargeback": _money(commission["chargeback"]),
        "dmv_revenue": _money(dmv["dmv_revenue"]),
        "dmv_cost": _money(dmv["dmv_cost"]),
        "dmv_fees_collected": _money(dmv["dmv_fees_collected"]),
        "dmv_net_profit": _money(dmv["dmv_net_profit"]),
        "producer_commission": _money(producer_commission),
        "csr_commission": _money(csr_commission),
        "gross_agency_revenue": _money(gross_agency_revenue),
        "total_expenses": _money(total_expenses),
        "net_profit": _money(net_profit),
        "company_net_due": _money(carrier_net_due),
        "carrier_balance": {
            "collected_from_customer": _money(collected_from_client),
            "carrier_premium": _money(carrier_premium),
            "already_paid_to_carrier": _money(remitted),
            "remaining_due_carrier": _money(remaining_due_carrier),
            "overpayment": _money(overpayment),
            "credits": _money(policy.carrier_credits),
            "carrier_net_due": _money(carrier_net_due),
            "net_premium_collected": _money(installments.net_premium_collected),
            "return_premium": _money(accounting["return_premium"]),
        },
        "commission": {k: _money(v) if isinstance(v, Decimal) else v for k, v in commission.items()},
        "dmv": {k: _money(v) if isinstance(v, Decimal) else v for k, v in dmv.items()},
        "reinstatements": {
            k: _money(v) if isinstance(v, Decimal) else v for k, v in reinstatements.items()
        },
        "as_of": today.isoformat(),
    }


def tlc_dashboard_stats(space, *, today: date | None = None) -> dict:
    """Aggregate TLC space metrics for dashboard cards."""
    from .tlc_models import TLCPolicy

    today = today or timezone.localdate()
    month_start = today.replace(day=1)
    policies = TLCPolicy.objects.filter(space=space)
    active_count = policies.filter(status=TLCPolicy.Status.ACTIVE).count()
    pending_count = policies.filter(status=TLCPolicy.Status.PENDING).count()
    cancelled_count = policies.filter(
        status__in=[TLCPolicy.Status.CANCELLED, TLCPolicy.Status.SUSPENDED]
    ).count()

    net_profit_total = ZERO
    gross_revenue_total = ZERO
    policies_with_profit = 0
    for policy in policies.select_related("premium_breakdown").prefetch_related(
        "installments", "dmv_services", "endorsements", "reinstatements", "cancellations"
    )[:500]:
        snapshot = build_policy_profitability(policy, today=today)
        net_profit_total += Decimal(snapshot["net_profit"])
        gross_revenue_total += Decimal(snapshot["gross_agency_revenue"])
        policies_with_profit += 1

    month_policies = policies.filter(created_at__date__gte=month_start)
    return {
        "total_policies": policies.count(),
        "active_policies": active_count,
        "pending_policies": pending_count,
        "cancelled_policies": cancelled_count,
        "month_new_policies": month_policies.count(),
        "aggregate_net_profit": net_profit_total,
        "aggregate_gross_revenue": gross_revenue_total,
        "policies_analyzed": policies_with_profit,
    }


def tlc_space_period_profit(
    space,
    today: date,
    *,
    custom_range: tuple[date, date] | None = None,
) -> dict:
    """Owner API profit rollup for the TLC space."""
    from .tlc_models import TLCPolicy

    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    def _profit_for_range(start: date, end: date) -> dict:
        qs = TLCPolicy.objects.filter(space=space, created_at__date__gte=start, created_at__date__lte=end)
        net = ZERO
        for policy in qs.select_related("premium_breakdown").prefetch_related(
            "installments", "dmv_services", "endorsements", "cancellations"
        ):
            snap = build_policy_profitability(policy, today=end)
            net += Decimal(snap["net_profit"])
        return {
            "profit": _money(net),
            "revenue": _money(net),
            "transactions": qs.count(),
        }

    payload = {
        "key": space.key,
        "label": space.label,
        "today": _profit_for_range(today, today),
        "month": _profit_for_range(month_start, today),
        "year": _profit_for_range(year_start, today),
    }
    if custom_range:
        start, end = custom_range
        payload["custom"] = _profit_for_range(start, end)
        payload["range"] = {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "source": "ledger",
        }
    else:
        payload["custom"] = {"profit": "0.00", "revenue": "0.00", "transactions": 0}
    return payload

