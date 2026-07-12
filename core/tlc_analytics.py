"""Receivables aging and renewal forecasting for the TLC space."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from .tlc_models import TLCPolicy

ZERO = Decimal("0.00")


def _d(value) -> Decimal:
    return Decimal(str(value or ZERO)).quantize(Decimal("0.01"))


def build_receivables_aging(space, *, today: date | None = None) -> dict:
    """Bucket unpaid installment balances into 30/60/90+ day aging."""
    today = today or timezone.localdate()
    buckets = {
        "current": ZERO,
        "days_1_30": ZERO,
        "days_31_60": ZERO,
        "days_61_90": ZERO,
        "days_90_plus": ZERO,
    }
    policies_with_balance = 0
    total_outstanding = ZERO

    policies = TLCPolicy.objects.filter(space=space).prefetch_related("installments")
    for policy in policies:
        policy_has_balance = False
        for inst in policy.installments.filter(is_paid=False):
            amount = _d(inst.balance or inst.amount) + _d(inst.installment_fee)
            if amount <= ZERO:
                continue
            policy_has_balance = True
            total_outstanding += amount
            if not inst.due_date or inst.due_date >= today:
                buckets["current"] += amount
                continue
            days = (today - inst.due_date).days
            if days <= 30:
                buckets["days_1_30"] += amount
            elif days <= 60:
                buckets["days_31_60"] += amount
            elif days <= 90:
                buckets["days_61_90"] += amount
            else:
                buckets["days_90_plus"] += amount
        if policy_has_balance:
            policies_with_balance += 1

    return {
        "total_outstanding": total_outstanding,
        "policies_with_balance": policies_with_balance,
        "buckets": {key: str(val.quantize(Decimal("0.01"))) for key, val in buckets.items()},
    }


def build_renewal_forecast(space, *, today: date | None = None, horizon_days: int = 90) -> dict:
    """Forecast renewals and expected revenue in the next N days."""
    today = today or timezone.localdate()
    horizon_end = today + timedelta(days=horizon_days)
    rows = []
    expected_premium = ZERO
    expected_commission = ZERO
    renewal_count = 0

    qs = (
        TLCPolicy.objects.filter(space=space, renewal_date__gte=today, renewal_date__lte=horizon_end)
        .select_related("premium_breakdown")
        .order_by("renewal_date")
    )
    for policy in qs:
        premium = ZERO
        if hasattr(policy, "premium_breakdown") and policy.premium_breakdown:
            premium = _d(policy.premium_breakdown.total_written_premium)
        commission = _d(policy.carrier_commission_amount)
        expected_premium += premium
        expected_commission += commission
        renewal_count += 1
        rows.append(
            {
                "policy_id": policy.id,
                "policy_number": policy.policy_number,
                "named_insured": policy.named_insured or policy.business_name,
                "carrier": policy.carrier,
                "renewal_date": policy.renewal_date.isoformat() if policy.renewal_date else None,
                "written_premium": str(premium),
                "expected_commission": str(commission),
            }
        )

    return {
        "horizon_days": horizon_days,
        "renewal_count": renewal_count,
        "expected_premium": str(expected_premium),
        "expected_commission": str(expected_commission),
        "renewals": rows,
    }
