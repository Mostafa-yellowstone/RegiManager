"""TLC Policy Profitability Engine — computed metrics for agency owners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Count, Sum
from django.utils import timezone

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
    collected = ZERO

    for row in installments:
        late_fees += _d(row.late_fee)
        nsf_fees += _d(row.nsf_fee)
        inst_fee = _d(row.installment_fee)
        if row.is_paid:
            collected += _d(row.amount) + inst_fee + _d(row.late_fee) + _d(row.nsf_fee)
            installment_fees_collected += inst_fee
        else:
            remaining_balance += _d(row.balance or row.amount) + inst_fee
            installment_fees_outstanding += inst_fee
            if row.due_date and row.due_date < today:
                past_due += _d(row.balance or row.amount)
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
        "dmv_net_profit": profit,
        "service_count": rows.count(),
    }


def summarize_agency_expenses(policy: TLCPolicy) -> dict:
    rows = policy.agency_expenses.all()
    total = ZERO
    by_type: dict[str, Decimal] = {}
    for row in rows:
        amount = _d(row.amount)
        total += amount
        by_type[row.expense_type] = by_type.get(row.expense_type, ZERO) + amount
    return {"total_expenses": total, "by_type": by_type}


def summarize_reinstatements(policy: TLCPolicy) -> dict:
    rows = policy.reinstatements.all()
    reinstatement_fees = ZERO
    paid_fees = ZERO
    for row in rows:
        reinstatement_fees += _d(row.reinstatement_fee)
        if row.is_paid:
            paid_fees += _d(row.reinstatement_fee)
    return {
        "reinstatement_count": rows.count(),
        "reinstatement_fees_total": reinstatement_fees,
        "reinstatement_fees_collected": paid_fees,
    }


def summarize_commission(policy: TLCPolicy) -> dict:
    expected = _d(policy.carrier_commission_amount)
    received = _d(policy.commission_received)
    chargeback = _d(policy.commission_chargeback)
    pending = max(expected - received - chargeback, ZERO)
    renewal = ZERO
    if policy.policy_type == policy.PolicyType.RENEWAL and policy.renewal_commission_rate:
        premium = ZERO
        if hasattr(policy, "premium_breakdown") and policy.premium_breakdown:
            premium = _d(policy.premium_breakdown.total_written_premium)
        renewal = (premium * _d(policy.renewal_commission_rate) / Decimal("100")).quantize(
            Decimal("0.01")
        )
    return {
        "expected_commission": expected,
        "commission_received": received,
        "pending_commission": pending,
        "chargeback": chargeback,
        "renewal_commission": renewal,
        "commission_remaining": pending,
    }


def build_policy_profitability(policy: TLCPolicy, *, today: date | None = None) -> dict:
    """Full profitability snapshot for a single TLC policy."""
    today = today or timezone.localdate()
    breakdown = getattr(policy, "premium_breakdown", None)
    installments = summarize_installments(policy, today=today)
    dmv = summarize_dmv_services(policy)
    expenses = summarize_agency_expenses(policy)
    reinstatements = summarize_reinstatements(policy)
    commission = summarize_commission(policy)

    written_premium = _d(breakdown.total_written_premium) if breakdown else ZERO
    down_payment = _d(breakdown.down_payment) if breakdown else ZERO

    broker_fees = _d(policy.broker_fee_collected)
    finance_fees = _d(policy.finance_fee_collected)
    policy_fees = _d(breakdown.policy_fee) if breakdown else ZERO
    inspection_fees = _d(breakdown.inspection_fee) if breakdown else ZERO
    endorsement_fees = ZERO
    for row in policy.endorsements.all():
        endorsement_fees += _d(row.premium_difference)

    carrier_commission = commission["expected_commission"]
    total_collected = (
        installments.total_collected
        + down_payment
        + broker_fees
        + finance_fees
        + reinstatements["reinstatement_fees_collected"]
    )
    if policy.amount_collected_from_client:
        total_collected = max(total_collected, _d(policy.amount_collected_from_client))

    gross_agency_revenue = (
        carrier_commission
        + broker_fees
        + finance_fees
        + policy_fees
        + inspection_fees
        + endorsement_fees
        + installments.installment_fees_collected
        + dmv["dmv_net_profit"]
    )

    producer_commission = _d(policy.producer_commission_amount)
    csr_commission = _d(policy.csr_commission_amount)
    office_expenses = expenses["by_type"].get("office_allocation", ZERO)
    advertising = expenses["by_type"].get("advertising", ZERO)
    merchant_fees = expenses["by_type"].get("merchant_fees", ZERO)
    chargebacks = expenses["by_type"].get("chargebacks", ZERO) + commission["chargeback"]

    total_expenses = expenses["total_expenses"] + producer_commission + csr_commission

    net_profit = gross_agency_revenue - total_expenses

    carrier_premium = written_premium
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

    customer_balance = (
        installments.total_remaining_balance
        + _d(policy.endorsement_balance)
        + installments.past_due_amount
    )

    return {
        "written_premium": _money(written_premium),
        "down_payment": _money(down_payment),
        "total_collected": _money(total_collected),
        "remaining_customer_balance": _money(customer_balance),
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
        "reinstatement_fees": _money(reinstatements["reinstatement_fees_collected"]),
        "broker_fees_collected": _money(broker_fees),
        "carrier_commission": _money(carrier_commission),
        "dmv_revenue": _money(dmv["dmv_revenue"]),
        "dmv_cost": _money(dmv["dmv_cost"]),
        "dmv_net_profit": _money(dmv["dmv_net_profit"]),
        "producer_commission": _money(producer_commission),
        "csr_commission": _money(csr_commission),
        "office_expenses": _money(office_expenses),
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
        },
        "customer_balance": {
            "total_policy_balance": _money(customer_balance + total_collected),
            "past_due": _money(installments.past_due_amount),
            "current_due": _money(installments.total_remaining_balance - installments.past_due_amount),
            "next_installment": _money(
                policy.installments.filter(is_paid=False).order_by("due_date").values_list("amount", flat=True).first()
                or ZERO
            ),
            "late_fees": _money(installments.late_fees_collected),
            "nsf_fees": _money(installments.nsf_fees_collected),
            "reinstatement_fees": _money(reinstatements["reinstatement_fees_collected"]),
            "endorsement_balance": _money(policy.endorsement_balance),
            "remaining_balance": _money(customer_balance),
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
        "installments", "dmv_services", "agency_expenses", "endorsements", "reinstatements"
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


def tlc_space_period_profit(space, today: date) -> dict:
    """Owner API profit rollup for the TLC space."""
    from .tlc_models import TLCPolicy

    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    def _profit_for_range(start: date, end: date) -> dict:
        qs = TLCPolicy.objects.filter(space=space, created_at__date__gte=start, created_at__date__lte=end)
        net = ZERO
        for policy in qs.select_related("premium_breakdown").prefetch_related(
            "installments", "dmv_services", "agency_expenses"
        ):
            snap = build_policy_profitability(policy, today=end)
            net += Decimal(snap["net_profit"])
        return {"profit": _money(net), "transactions": qs.count()}

    return {
        "key": space.key,
        "label": space.label,
        "today": _profit_for_range(today, today),
        "month": _profit_for_range(month_start, today),
        "year": _profit_for_range(year_start, today),
    }
