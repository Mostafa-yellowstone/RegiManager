"""Installment schedule generation for TLC policies."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from .tlc_models import TLCInstallment, TLCPolicy, TLCPremiumBreakdown

ZERO = Decimal("0.00")


def _add_months(start: date, months: int) -> date:
    target = start + relativedelta(months=months)
    last_day = monthrange(target.year, target.month)[1]
    return target.replace(day=min(start.day, last_day))


def generate_installment_schedule(policy: TLCPolicy, *, replace_existing: bool = False) -> int:
    """
    Build installment rows from premium breakdown.
    Includes per-installment installment_fee on every scheduled payment.
    Returns number of installments created.
    """
    try:
        breakdown: TLCPremiumBreakdown = policy.premium_breakdown
    except TLCPremiumBreakdown.DoesNotExist:
        return 0

    count = breakdown.number_of_installments or 0
    monthly = breakdown.monthly_installment or ZERO
    per_fee = breakdown.installment_fee or ZERO
    if count <= 0 or monthly <= ZERO:
        return 0

    if replace_existing:
        policy.installments.all().delete()

    start_date = policy.effective_date or date.today()
    created = 0
    for number in range(1, count + 1):
        due = _add_months(start_date, number - 1)
        TLCInstallment.objects.update_or_create(
            policy=policy,
            installment_number=number,
            defaults={
                "due_date": due,
                "amount": monthly,
                "installment_fee": per_fee,
                "is_paid": False,
                "balance": monthly + per_fee,
            },
        )
        created += 1
    return created
